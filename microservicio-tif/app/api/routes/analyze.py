from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import re
import ast
import traceback
import shutil
import asyncio
from datetime import datetime
from urllib.parse import quote

import boto3
import httpx
import rasterio
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from rasterio.enums import Resampling

from app.core.config import (
    AWS_ACCESS_KEY_ID_CUSTOM,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY_CUSTOM,
    AWS_SESSION_TOKEN_CUSTOM,
    IA_SERVICE_URL,
    MONITORING_S3_BUCKET,
    MONITORING_S3_PREFIX,
    PRODUCTIONS_API_TOKEN,
    PRODUCTIONS_API_URL,
)
from app.models.requests import ProductionSceneRequest, SceneTileRequest
from app.services.copernicus.scene_assets import SceneAssetsService
from app.services.processing.scene_tile_builder import SceneTileBuilder
from app.services.stores import crop_config_store, monitoring_store

router = APIRouter(tags=["analyze"])

scene_assets_service = SceneAssetsService()
scene_tile_builder = SceneTileBuilder()
backfill_jobs: dict[str, dict[str, Any]] = {}
production_locks: dict[int, dict[str, Any]] = {}


def _acquire_production_lock(production_id: int, action: str) -> None:
    active = production_locks.get(production_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "production_locked",
                "production_id": production_id,
                "active_action": active.get("action"),
                "locked_at": active.get("locked_at"),
                "message": f"Production {production_id} is busy with action '{active.get('action')}'.",
            },
        )
    production_locks[production_id] = {"action": action, "locked_at": datetime.now().isoformat()}


def _release_production_lock(production_id: int, action: str | None = None) -> None:
    active = production_locks.get(production_id)
    if not active:
        return
    if action and active.get("action") != action:
        return
    production_locks.pop(production_id, None)

def _mask_value(value: str | None, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"

def _build_s3_client():
    kwargs: dict[str, Any] = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID_CUSTOM and AWS_SECRET_ACCESS_KEY_CUSTOM:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID_CUSTOM
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY_CUSTOM
        if AWS_SESSION_TOKEN_CUSTOM:
            kwargs["aws_session_token"] = AWS_SESSION_TOKEN_CUSTOM
    safe_kwargs = dict(kwargs)
    if "aws_access_key_id" in safe_kwargs:
        safe_kwargs["aws_access_key_id"] = _mask_value(str(safe_kwargs["aws_access_key_id"]))
    if "aws_secret_access_key" in safe_kwargs:
        safe_kwargs["aws_secret_access_key"] = "***masked***"
    if "aws_session_token" in safe_kwargs:
        safe_kwargs["aws_session_token"] = "***masked***"
    print("Building S3 client with kwargs:", safe_kwargs)
    return boto3.client("s3", **kwargs)

s3_client = _build_s3_client()

BAND_ALIAS_MAP = {
    "band_blue": "B02",
    "band_green": "B03",
    "band_red": "B04",
    "band_rededge1": "B05",
    "band_rededge2": "B06",
    "band_rededge3": "B07",
    "band_nir": "B08",
    "band_nir_narrow": "B8A",
    "band_swir1": "B11",
    "band_swir2": "B12",
}





@router.post("/analyze", status_code=202)
async def analyze():
    return {"status": "not_implemented"}


@router.post("/scene/tile")
async def build_scene_tile(payload: SceneTileRequest):
    try:
        feature = await scene_assets_service.get_scene_assets(payload.scene_name)
        result = scene_tile_builder.build(
            scene_name=payload.scene_name,
            latitude=payload.latitude,
            longitude=payload.longitude,
            tile_size=payload.tile_size,
            assets=feature.get("assets", {}),
            bands=payload.bands,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_result(result)


@router.post("/scene/production/tile")
async def build_scene_tile_from_production(payload: ProductionSceneRequest):
    result = await _run_production_analysis(payload)
    return _serialize_result(result, payload)


@router.post("/monitoring/import")
async def import_monitoring_data(payload: dict[str, Any]):
    rows = payload.get("items", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="Payload must use items: []")
    stats = monitoring_store.upsert_productions(rows)
    return {"ok": True, **stats, "total_in_store": len(monitoring_store.productions)}


@router.post("/monitoring/import-from-api")
async def import_monitoring_from_api():
    if not PRODUCTIONS_API_URL:
        raise HTTPException(status_code=400, detail="PRODUCTIONS_API_URL is not configured")
    headers: dict[str, str] = {}
    if PRODUCTIONS_API_TOKEN:
        headers["Authorization"] = f"Bearer {PRODUCTIONS_API_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.get(PRODUCTIONS_API_URL, headers=headers)
        text = resp.text
        parsed: Any
        try:
            parsed = resp.json()
        except Exception:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "upstream_invalid_json",
                    "status_code": resp.status_code,
                    "url": PRODUCTIONS_API_URL,
                    "body_preview": text[:3000],
                },
            )
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "upstream_http_error",
                    "status_code": resp.status_code,
                    "url": PRODUCTIONS_API_URL,
                    "body": parsed,
                },
            )
        if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
            items = parsed.get("items") or []
        elif isinstance(parsed, list):
            items = parsed
            parsed = {"items": items}
        else:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "upstream_unexpected_shape",
                    "url": PRODUCTIONS_API_URL,
                    "expected": "{\"items\": [...]} or [...]",
                    "received_type": type(parsed).__name__,
                },
            )
        stats = monitoring_store.upsert_productions(items)
        return {
            "ok": True,
            "source_url": PRODUCTIONS_API_URL,
            "import": {**stats, "total_in_store": len(monitoring_store.productions)},
            "api_response": parsed,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": "import_from_api_failed",
                "url": PRODUCTIONS_API_URL,
                "message": f"{type(exc).__name__}: {exc}",
            },
        ) from exc


@router.post("/catalog/scenes/import")
async def import_scene_catalog(payload: dict[str, Any]):
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Payload must use items: []")
    imported = monitoring_store.upsert_scene_catalog(items)
    return {"ok": True, "imported": imported, "total_in_catalog": len(monitoring_store.scene_catalog)}


@router.get("/catalog/scenes")
async def list_scene_catalog():
    return {"ok": True, "items": list(monitoring_store.scene_catalog.values())}


@router.get("/monitoring/lots")
async def get_monitored_lots():
    try:
        return {"ok": True, "items": monitoring_store.list_monitored()}
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"[monitoring/lots] ERROR: {type(exc).__name__}: {exc}\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=f"/monitoring/lots failed: {type(exc).__name__}: {exc}",
        ) from exc


@router.get("/outputs/s3")
async def output_s3_proxy(path: str):
    try:
        bucket, key = _parse_s3_uri(path)
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        content_type = obj.get("ContentType") or "application/octet-stream"
        return Response(content=body, media_type=content_type)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"S3 proxy read failed: {exc}") from exc


@router.post("/monitoring/reset")
async def reset_monitoring_state():
    if production_locks:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "active_jobs",
                "message": "Cannot reset while production jobs are running.",
                "locks": production_locks,
            },
        )
    temp_root = Path("/tmp/agro-tif/outputs")
    removed_temp = False
    temp_error = None
    try:
        if temp_root.exists():
            shutil.rmtree(temp_root)
            removed_temp = True
        temp_root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        temp_error = f"{type(exc).__name__}: {exc}"

    monitoring_store.productions.clear()
    monitoring_store.analyses.clear()
    monitoring_store.scene_catalog.clear()
    monitoring_store.scenes_cache.clear()

    return {
        "ok": True,
        "cleared": {
            "productions": True,
            "analyses": True,
            "scene_catalog": True,
            "scenes_cache": True,
            "temp_outputs_removed": removed_temp,
        },
        "temp_path": str(temp_root),
        "temp_error": temp_error,
    }


@router.get("/monitoring/scenes/{production_id}")
async def list_production_scenes(production_id: int):
    payload = monitoring_store.get_payload(production_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Production not found")
    items = monitoring_store.scenes_cache.get(production_id)
    if items is None:
        items = _list_s3_scenes_for_production(production_id)
        monitoring_store.scenes_cache[production_id] = items
    selected = (payload.get("escene") or {}).get("scene_name")
    return {"ok": True, "production_id": production_id, "selected_scene": selected, "items": items}


@router.get("/monitoring/ia/{production_id}")
async def get_scene_ia_analysis(production_id: int, scene_name: str | None = None, scene_date: str | None = None):
    payload = monitoring_store.get_payload(production_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Production not found")
    target_scene = (scene_name or "").strip()
    target_date = (scene_date or "").strip()

    scene_items = _list_s3_scenes_for_production(production_id)
    if not scene_items:
        return {"ok": True, "production_id": production_id, "has_ia": False, "message": "No scenes found"}

    selected_item = None
    if target_scene:
        for x in scene_items:
            if str(x.get("scene_name") or "") == target_scene and (not target_date or str(x.get("fecha") or "") == target_date):
                selected_item = x
                break

    # 1) Try selected scene IA first.
    if selected_item:
        scene_base = str(selected_item.get("scene_prefix") or "").rstrip("/")
        ia_key = f"{scene_base}/multiband.ia.json"
        ia_payload = _read_json_from_s3_key(ia_key)
        if ia_payload is not None:
            stale = _is_analysis_stale(str(ia_payload.get("fecha_analisis") or ""))
            return {
                "ok": True,
                "production_id": production_id,
                "has_ia": True,
                "source": "selected_scene",
                "scene_name": selected_item.get("scene_name"),
                "scene_date": selected_item.get("fecha"),
                "ia": ia_payload,
                "stale": stale,
                "message": "Analisis IA cargado para la escena seleccionada.",
            }

    # 2) Fallback to latest available IA in production.
    with_ia: list[dict[str, Any]] = []
    for x in sorted(scene_items, key=lambda r: (str(r.get("fecha") or ""), str(r.get("scene_name") or "")), reverse=True):
        scene_base = str(x.get("scene_prefix") or "").rstrip("/")
        ia_key = f"{scene_base}/multiband.ia.json"
        ia_payload = _read_json_from_s3_key(ia_key)
        if ia_payload is not None:
            with_ia.append({"item": x, "ia": ia_payload})
            break

    if with_ia:
        top = with_ia[0]
        stale = _is_analysis_stale(str((top.get("ia") or {}).get("fecha_analisis") or ""))
        msg = "No hay analisis IA para la escena seleccionada; se muestra el ultimo analisis disponible."
        if stale:
            msg += " El analisis mostrado esta demasiado antiguo; se sugiere actualizar al dia de hoy."
        return {
            "ok": True,
            "production_id": production_id,
            "has_ia": True,
            "source": "latest_fallback",
            "scene_name": (top.get("item") or {}).get("scene_name"),
            "scene_date": (top.get("item") or {}).get("fecha"),
            "ia": top.get("ia"),
            "stale": stale,
            "message": msg,
        }

    return {
        "ok": True,
        "production_id": production_id,
        "has_ia": False,
        "source": "none",
        "stale": False,
        "message": "No existe analisis IA para ninguna escena de la produccion.",
    }


@router.post("/monitoring/scenes/{production_id}/select")
async def select_production_scene(production_id: int, body: dict[str, Any]):
    payload = monitoring_store.get_payload(production_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Production not found")
    scene_name = str(body.get("scene_name") or "").strip()
    scene_date = str(body.get("scene_date") or "").strip() or None
    if not scene_name:
        raise HTTPException(status_code=400, detail="scene_name is required")
    record = _load_scene_record_from_s3(production_id=production_id, scene_name=scene_name, scene_date=scene_date)
    if not record:
        raise HTTPException(status_code=404, detail="Scene metadata not found in S3")
    production_ctx = ProductionSceneRequest(**payload).production
    scene = _scene_from_s3_record(record, ProductionSceneRequest(production=production_ctx))
    payload["escene"] = scene.model_dump()
    monitoring_store.productions[production_id] = payload
    pruned_prod = _prune_runtime_for_production(production_id)
    pruned_scene = _prune_runtime_for_scene(production_id, scene_name)
    return {
        "ok": True,
        "production_id": production_id,
        "scene": payload["escene"],
        "pruned": {
            "production": pruned_prod,
            "scene": pruned_scene,
        },
    }


@router.post("/monitoring/analyze/{production_id}")
async def analyze_monitored_lot(production_id: int):
    _acquire_production_lock(production_id, "analyze_single")
    try:
        payload = monitoring_store.get_payload(production_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Production not found")
        typed_payload = ProductionSceneRequest(**payload)
        result = await _run_production_analysis(typed_payload)
        serialized = _serialize_result(result, typed_payload)
        # Keep explicit "normal/truth" image sets for UI toggle.
        if not serialized.get("truth_preview_pngs"):
            serialized["truth_preview_pngs"] = serialized.get("preview_pngs", [])
        if not serialized.get("truth_thematic_pngs"):
            serialized["truth_thematic_pngs"] = serialized.get("thematic_pngs", [])
        monitoring_store.save_analysis(production_id, serialized)
        return serialized
    finally:
        _release_production_lock(production_id, "analyze_single")


@router.post("/monitoring/upload/{production_id}")
async def upload_monitored_lot_to_s3(production_id: int):
    _acquire_production_lock(production_id, "upload")
    try:
        if not MONITORING_S3_BUCKET:
            raise HTTPException(status_code=400, detail="MONITORING_S3_BUCKET is not configured")

        analysis = monitoring_store.get_analysis_result(production_id)
        payload = monitoring_store.get_payload(production_id)
        if not analysis or not payload:
            raise HTTPException(status_code=404, detail="No analysis found for production")

        scene_name = payload.get("escene", {}).get("scene_name") or analysis.get("scene_name") or "unknown_scene"
        scene_date = payload.get("escene", {}).get("fecha") or analysis.get("scene_date") or datetime.now().strftime("%Y-%m-%d")
        base_prefix = MONITORING_S3_PREFIX.strip("/")
        # Expected structure: bucket/{prefix}/PROD_{produccion_id}/{scene_name}
        #base_key = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}"
        base_key = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}"
        uploads: dict[str, str] = {}
        local_tif = analysis.get("multiband_tif_path")
        if local_tif and str(local_tif).startswith("s3://"):
            uploads["tif_truth_path"] = str(local_tif)
            uploads["tif_render_path"] = str(analysis.get("render_tif_path") or local_tif)
        elif local_tif:
            key = f"{base_key}/multiband.tif"
            if not _s3_key_exists(key):
                s3_client.upload_file(local_tif, MONITORING_S3_BUCKET, key, ExtraArgs={"ContentType": "image/tiff"})
            uploads["tif_truth_path"] = f"s3://{MONITORING_S3_BUCKET}/{key}"
            uploads["tif_render_path"] = analysis.get("render_tif_path")

        preview_pngs: list[str] = []
        for item in analysis.get("preview_pngs", []):
            local_png = item.get("path")
            if not local_png:
                continue
            if str(local_png).startswith("s3://"):
                preview_pngs.append(str(local_png))
                continue
            filename = Path(str(local_png)).name
            key = f"{base_key}/{filename}"
            if not _s3_key_exists(key):
                s3_client.upload_file(local_png, MONITORING_S3_BUCKET, key, ExtraArgs={"ContentType": "image/png"})
            preview_pngs.append(f"s3://{MONITORING_S3_BUCKET}/{key}")

        thematic_pngs: list[str] = []
        for item in analysis.get("thematic_pngs", []):
            local_png = item.get("path")
            if not local_png:
                continue
            if str(local_png).startswith("s3://"):
                thematic_pngs.append(str(local_png))
                continue
            filename = Path(str(local_png)).name
            key = f"{base_key}/{filename}"
            if not _s3_key_exists(key):
                s3_client.upload_file(local_png, MONITORING_S3_BUCKET, key, ExtraArgs={"ContentType": "image/png"})
            thematic_pngs.append(f"s3://{MONITORING_S3_BUCKET}/{key}")

        polygon_str = payload.get("production", {}).get("poligono_asig") or payload.get("production", {}).get("poligono_zona")
        polygon_coords = _polygon_str_to_latlon_pairs(polygon_str) if polygon_str else []
        bbox = _bbox_from_polygon(polygon_coords) if polygon_coords else None

        # Merge with existing scene metadata when available, then update generated URLs.
        previous_meta: dict[str, Any] = {}
        meta_key = f"{base_key}/{scene_date}_{scene_name}.json"
        try:
            previous_obj = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=meta_key)
            previous_meta = json.loads(previous_obj["Body"].read().decode("utf-8"))
        except Exception:
            previous_meta = {}

        # Params policy:
        # - always create params for current scene
        # - if there are previous scenes, require at least one previous params source to keep history continuity
        prev_scene_record = _load_previous_scene_record_from_s3(
            production_id=production_id,
            current_scene_name=scene_name,
            current_date=scene_date,
        )
        prev_params = None
        history_incomplete = False
        if prev_scene_record:
            prev_params = _load_params_from_scene_record(prev_scene_record)
            if prev_params is None:
                has_same_date_params = _has_any_params_for_date(
                    production_id=production_id,
                    scene_date=scene_date,
                )
                # Do not block first scene of date; allow current params creation and
                # mark historical chain as partial until backfill exists.
                if not has_same_date_params:
                    history_incomplete = True
        params_key = f"{base_key}/multiband.params.json"
        ia_key = f"{base_key}/multiband.ia.json"
        params_payload = _build_scene_params_payload(
            production_id=production_id,
            scene_date=scene_date,
            analysis=analysis,
            previous_params=prev_params,
        )
        if history_incomplete:
            params_payload["historico_incompleto"] = True
            params_payload["historico_motivo"] = "No se encontraron params previos para enlazar histórico; se creó baseline con la escena actual."
        s3_client.put_object(
            Bucket=MONITORING_S3_BUCKET,
            Key=params_key,
            Body=json.dumps(params_payload, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        metadata = {
            "id": f"PROD#{production_id}",
            "clave": scene_name,
            "folio": payload.get("production", {}).get("folio"),
            "scene_id": scene_name,
            "fecha": scene_date,
            "cloud_cover": ((analysis.get("scene_record") or {}).get("cloud_cover")),
            "bbox": bbox,
            "polygon": polygon_coords,
            "scene": {"collection": "sentinel-2-l2a"},
            "bands": (analysis.get("scene_record") or {}).get("bands", {}),
            "preview": {
                "multiband": f"{base_key}/multiband.tif",
                "multiband_rendered": f"{base_key}/multiband_rendered.tif",
                "parametros": params_key,
                "recomendaciones": ia_key,
                "analisis_ia": f"{base_key}/analisis_ia.json",
                "urls": {
                    "multiband": uploads.get("tif_truth_path") or f"s3://{MONITORING_S3_BUCKET}/{base_key}/multiband.tif",
                    "multiband_rendered": analysis.get("render_tif_path") or f"s3://{MONITORING_S3_BUCKET}/{base_key}/multiband_rendered.tif",
                    "parametros": f"s3://{MONITORING_S3_BUCKET}/{params_key}",
                    "recomendaciones": f"s3://{MONITORING_S3_BUCKET}/{ia_key}",
                    "analisis_ia": f"s3://{MONITORING_S3_BUCKET}/{base_key}/analisis_ia.json",
                    "preview_pngs": preview_pngs,
                    "thematic_pngs": thematic_pngs,
                },
            },
            "generated_from": analysis.get("source_mode"),
            "uploaded_at": datetime.now().isoformat(),
        }
        if previous_meta:
            merged = previous_meta.copy()
            merged.update(metadata)
            if isinstance(previous_meta.get("preview"), dict):
                merged_preview = previous_meta["preview"].copy()
                merged_preview.update(metadata["preview"])
                merged["preview"] = merged_preview
            metadata = merged
        s3_client.put_object(
            Bucket=MONITORING_S3_BUCKET,
            Key=meta_key,
            Body=json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

        catalog_item = {
            "production_id": production_id,
            "scene_name": scene_name,
            "tif_truth_path": uploads.get("tif_truth_path"),
            "tif_render_path": uploads.get("tif_render_path"),
            "preview_pngs": preview_pngs,
            "thematic_pngs": thematic_pngs,
            "indices": analysis.get("index_stats", {}),
            "base_dir": f"s3://{MONITORING_S3_BUCKET}/{base_key}",
        }
        monitoring_store.upsert_scene_catalog([catalog_item])

        analysis["truth_tif_path"] = uploads.get("tif_truth_path") or analysis.get("truth_tif_path")
        if preview_pngs:
            analysis["preview_pngs"] = [{"path": p, "url": p} for p in preview_pngs]
        if thematic_pngs:
            analysis["thematic_pngs"] = [{"path": p, "url": p} for p in thematic_pngs]
        monitoring_store.update_analysis_result(production_id, analysis)

        return {
            "ok": True,
            "production_id": production_id,
            "scene_name": scene_name,
            "bucket": MONITORING_S3_BUCKET,
            "catalog_registered": True,
            "uploads": {
                "tif": uploads,
                "preview_pngs": preview_pngs,
                "thematic_pngs": thematic_pngs,
                "metadata_json": f"s3://{MONITORING_S3_BUCKET}/{meta_key}",
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {exc}") from exc
    finally:
        _release_production_lock(production_id, "upload")


@router.post("/monitoring/backfill/{production_id}")
async def backfill_production_scenes(production_id: int, body: dict[str, Any] | None = None):
    # Backward-compatible synchronous endpoint.
    return await _run_backfill(production_id, bool((body or {}).get("force", False)), job_id=None)


@router.post("/monitoring/backfill/start/{production_id}")
async def start_backfill_production_scenes(production_id: int, body: dict[str, Any] | None = None):
    _acquire_production_lock(production_id, "backfill")
    force = bool((body or {}).get("force", False))
    job_id = f"bf_{production_id}_{int(datetime.now().timestamp() * 1000)}"
    backfill_jobs[job_id] = {
        "job_id": job_id,
        "production_id": production_id,
        "force": force,
        "status": "running",
        "total_scenes": 0,
        "prepared_scenes": 0,
        "uploaded_scenes": 0,
        "processed_scenes": 0,
        "phase_prepare_pct": 0,
        "phase_upload_pct": 0,
        "progress_pct": 0,
        "results": [],
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
    }

    async def _bg():
        try:
            result = await _run_backfill(production_id, force, job_id=job_id)
            job = backfill_jobs.get(job_id, {})
            job["status"] = "done"
            job["finished_at"] = datetime.now().isoformat()
            job["total_scenes"] = result.get("total_scenes", 0)
            job["processed_scenes"] = result.get("total_scenes", 0)
            job["prepared_scenes"] = result.get("total_scenes", 0)
            job["uploaded_scenes"] = result.get("total_scenes", 0)
            job["phase_prepare_pct"] = 100
            job["phase_upload_pct"] = 100
            job["progress_pct"] = 100
            job["results"] = result.get("results", [])
            backfill_jobs[job_id] = job
        except Exception as exc:
            job = backfill_jobs.get(job_id, {})
            job["status"] = "error"
            job["error"] = f"{type(exc).__name__}: {exc}"
            job["finished_at"] = datetime.now().isoformat()
            backfill_jobs[job_id] = job
        finally:
            _release_production_lock(production_id, "backfill")

    asyncio.create_task(_bg())
    return {"ok": True, "job_id": job_id, "production_id": production_id, "force": force}


@router.get("/monitoring/backfill/status/{job_id}")
async def get_backfill_status(job_id: str):
    job = backfill_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backfill job not found")
    return {"ok": True, **job}


async def _run_backfill(production_id: int, force: bool, job_id: str | None):
    payload = monitoring_store.get_payload(production_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Production not found")

    items = _list_s3_scenes_for_production(production_id)
    if not items:
        raise HTTPException(status_code=404, detail="No scenes found for production in S3")

    # Historical chain must be built from oldest to newest.
    ordered = sorted(items, key=lambda x: (str(x.get("fecha") or ""), str(x.get("scene_name") or "")))
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    processed: list[dict[str, Any]] = []

    if job_id and job_id in backfill_jobs:
        backfill_jobs[job_id]["total_scenes"] = len(ordered)
        backfill_jobs[job_id]["prepared_scenes"] = 0
        backfill_jobs[job_id]["uploaded_scenes"] = 0
        backfill_jobs[job_id]["processed_scenes"] = 0
        backfill_jobs[job_id]["phase_prepare_pct"] = 0
        backfill_jobs[job_id]["phase_upload_pct"] = 0
        backfill_jobs[job_id]["progress_pct"] = 0

    # Phase 1 (parallel): prepare/generate scene analyses (heavy TIF/PNG work).
    semaphore = asyncio.Semaphore(3)
    prepared: dict[str, dict[str, Any]] = {}

    async def _prepare_one(item_local: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        scene_name_local = str(item_local.get("scene_name") or "").strip()
        scene_date_local = str(item_local.get("fecha") or "").strip()
        key_local = f"{scene_date_local}::{scene_name_local}"
        async with semaphore:
            result_local = await _prepare_scene_with_retries(
                production_id=production_id,
                base_payload=payload,
                scene_name=scene_name_local,
                scene_date=scene_date_local,
                force=force,
                max_attempts=3,
            )
            return key_local, result_local

    prep_tasks = [asyncio.create_task(_prepare_one(item)) for item in ordered]
    prepared_done = 0
    for done_task in asyncio.as_completed(prep_tasks):
        try:
            k, v = await done_task
            prepared[k] = v
        except Exception:
            pass
        prepared_done += 1
        if job_id and job_id in backfill_jobs:
            _set_backfill_phase_progress(job_id, prepared_done=prepared_done, uploaded_done=None)

    # Phase 2 (sequential): upload/params in strict old->new order.
    for item in ordered:
        scene_name = str(item.get("scene_name") or "").strip()
        scene_date = str(item.get("fecha") or "").strip()
        if not scene_name or not scene_date:
            continue
        prep_key = f"{scene_date}::{scene_name}"
        prep = prepared.get(prep_key)
        if not prep:
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "error",
                    "reason": "scene_prepare_missing",
                }
            )
            if job_id and job_id in backfill_jobs:
                _advance_backfill_upload_progress(job_id, processed)
            continue
        if prep.get("status") == "ready_existing":
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "skipped",
                    "reason": "truth_tif_and_params_already_exist",
                }
            )
            if job_id and job_id in backfill_jobs:
                _advance_backfill_upload_progress(job_id, processed)
            continue

        scene_base = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}"
        truth_key = f"{scene_base}/multiband.tif"
        params_key = f"{scene_base}/multiband.params.json"
        truth_exists = _s3_key_exists(truth_key)
        params_exists = _s3_key_exists(params_key)

        if (not force) and truth_exists and params_exists:
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "skipped",
                    "reason": "truth_tif_and_params_already_exist",
                }
            )
            if job_id and job_id in backfill_jobs:
                _advance_backfill_job(job_id, processed)
            continue

        if prep.get("status") != "prepared":
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "error",
                    "reason": prep.get("reason") or "scene_prepare_failed",
                }
            )
            if job_id and job_id in backfill_jobs:
                _advance_backfill_upload_progress(job_id, processed)
            continue

        working_payload = prep["working_payload"]
        monitoring_store.productions[production_id] = working_payload

        try:
            serialized = prep["serialized"]
            if not serialized.get("preview_pngs"):
                raise HTTPException(status_code=409, detail=f"Missing preview PNGs for scene {scene_name}")
            if not serialized.get("thematic_pngs"):
                raise HTTPException(status_code=409, detail=f"Missing thematic PNGs for scene {scene_name}")
            monitoring_store.save_analysis(production_id, serialized)
            upload_result = await upload_monitored_lot_to_s3(production_id)
            upload_assets = upload_result.get("uploads", {}) if isinstance(upload_result, dict) else {}
            upload_tif = (upload_assets.get("tif") or {}) if isinstance(upload_assets, dict) else {}
            truth_uri = str(upload_tif.get("tif_truth_path") or "")
            if not truth_uri.startswith("s3://") or not _s3_key_exists(truth_uri):
                raise HTTPException(status_code=409, detail=f"Uploaded truth tif missing in S3 for scene {scene_name}")
            if not _s3_key_exists(params_key):
                raise HTTPException(status_code=409, detail=f"Uploaded params missing in S3 for scene {scene_name}")
            up_preview = upload_assets.get("preview_pngs") or []
            up_thematic = upload_assets.get("thematic_pngs") or []
            if not up_preview or not up_thematic:
                raise HTTPException(status_code=409, detail=f"Uploaded PNG lists are incomplete for scene {scene_name}")
            for uri in [*up_preview, *up_thematic]:
                if not str(uri).startswith("s3://") or not _s3_key_exists(str(uri)):
                    raise HTTPException(status_code=409, detail=f"Uploaded image missing in S3: {uri}")
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "generated",
                    "upload": upload_result.get("uploads", {}),
                }
            )
        except HTTPException as exc:
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "error",
                    "reason": exc.detail,
                }
            )
        except Exception as exc:
            processed.append(
                {
                    "scene_name": scene_name,
                    "fecha": scene_date,
                    "status": "error",
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
        if job_id and job_id in backfill_jobs:
            _advance_backfill_upload_progress(job_id, processed)

    return {
        "ok": True,
        "production_id": production_id,
        "force": force,
        "total_scenes": len(ordered),
        "results": processed,
    }


async def _prepare_scene_with_retries(
    production_id: int,
    base_payload: dict[str, Any],
    scene_name: str,
    scene_date: str,
    force: bool,
    max_attempts: int = 3,
) -> dict[str, Any]:
    if (not force) and _s3_key_exists(
        f"{MONITORING_S3_PREFIX.strip('/') + '/' if MONITORING_S3_PREFIX.strip('/') else ''}PROD_{production_id}/{scene_name}/multiband.tif"
    ) and _s3_key_exists(
        f"{MONITORING_S3_PREFIX.strip('/') + '/' if MONITORING_S3_PREFIX.strip('/') else ''}PROD_{production_id}/{scene_name}/multiband.params.json"
    ):
        return {"status": "ready_existing", "working_payload": None, "serialized": None}

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            record = _load_scene_record_from_s3(
                production_id=production_id,
                scene_name=scene_name,
                scene_date=scene_date,
            )
            if not record:
                raise HTTPException(status_code=404, detail="scene_record_not_found")
            working_payload = json.loads(json.dumps(base_payload))
            production_ctx = ProductionSceneRequest(**working_payload).production
            scene_model = _scene_from_s3_record(record, ProductionSceneRequest(production=production_ctx))
            working_payload["escene"] = scene_model.model_dump()
            typed_payload = ProductionSceneRequest(**working_payload)
            result = await _run_production_analysis(typed_payload)
            serialized = _serialize_result(result, typed_payload)
            if not serialized.get("truth_preview_pngs"):
                serialized["truth_preview_pngs"] = serialized.get("preview_pngs", [])
            if not serialized.get("truth_thematic_pngs"):
                serialized["truth_thematic_pngs"] = serialized.get("thematic_pngs", [])
            return {"status": "prepared", "working_payload": working_payload, "serialized": serialized}
        except Exception as exc:
            last_error = f"attempt_{attempt}: {type(exc).__name__}: {exc}"
            await asyncio.sleep(min(2 * attempt, 6))
    return {"status": "error", "reason": last_error or "unknown_prepare_error"}


def _advance_backfill_upload_progress(job_id: str, processed: list[dict[str, Any]]) -> None:
    job = backfill_jobs.get(job_id) or {}
    total = int(job.get("total_scenes") or 0)
    uploaded_done = len(processed)
    _set_backfill_phase_progress(job_id, prepared_done=None, uploaded_done=uploaded_done)
    job = backfill_jobs.get(job_id) or {}
    job["results"] = processed[-8:]
    backfill_jobs[job_id] = job


def _set_backfill_phase_progress(job_id: str, prepared_done: int | None, uploaded_done: int | None) -> None:
    job = backfill_jobs.get(job_id) or {}
    total = int(job.get("total_scenes") or 0)
    if prepared_done is not None:
        job["prepared_scenes"] = prepared_done
    if uploaded_done is not None:
        job["uploaded_scenes"] = uploaded_done
    p_done = int(job.get("prepared_scenes") or 0)
    u_done = int(job.get("uploaded_scenes") or 0)
    prep_pct = int((p_done / total) * 100) if total > 0 else 0
    up_pct = int((u_done / total) * 100) if total > 0 else 0
    # Weighted progress: 50% prepare + 50% upload/register.
    progress_pct = int((prep_pct * 0.5) + (up_pct * 0.5))
    job["phase_prepare_pct"] = prep_pct
    job["phase_upload_pct"] = up_pct
    job["processed_scenes"] = u_done
    job["progress_pct"] = progress_pct
    backfill_jobs[job_id] = job


@router.post("/monitoring/ia/preview/{production_id}")
async def preview_ai_analysis(production_id: int):
    _acquire_production_lock(production_id, "ia_preview")
    try:
        if not MONITORING_S3_BUCKET:
            raise HTTPException(status_code=400, detail="MONITORING_S3_BUCKET is not configured")
        payload = monitoring_store.get_payload(production_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Production not found")

        scene = payload.get("escene") or {}
        scene_name = str(scene.get("scene_name") or "").strip()
        scene_date = str(scene.get("fecha") or "").strip()
        if not scene_name or not scene_date:
            raise HTTPException(status_code=400, detail="Scene selection is required (scene_name + fecha)")

        current_params = _load_params_for_scene(production_id, scene_name)
        if current_params is None:
            raise HTTPException(
                status_code=404,
                detail=f"Current params not found: PROD_{production_id}/{scene_name}/multiband.params.json",
            )

        previous_scene = _load_previous_scene_record_from_s3(
            production_id=production_id,
            current_scene_name=scene_name,
            current_date=scene_date,
        )
        previous_params = _load_params_from_scene_record(previous_scene) if previous_scene else None

        production = payload.get("production") or {}
        ia_input_payload = _build_ai_input_payload(
            production=production,
            current_params=current_params,
            previous_params=previous_params,
        )
        try:
            async with httpx.AsyncClient(timeout=80.0) as client:
                ia_resp = await client.post(
                    f"{IA_SERVICE_URL.rstrip('/')}/analyze",
                    json={"payload": ia_input_payload},
                )
                ia_data = ia_resp.json()
                if ia_resp.status_code >= 400:
                    detail = ia_data.get("detail") if isinstance(ia_data, dict) else ia_data
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "error": "ia_service_error",
                            "status_code": ia_resp.status_code,
                            "detail": detail,
                        },
                    )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"IA service request failed: {type(exc).__name__}: {exc}") from exc

        ia_compact = ia_data if isinstance(ia_data, dict) else {}
        ia_payload = _build_ai_output_payload(
            production=production,
            current_params=current_params,
            compact=ia_compact,
        )

        analysis = monitoring_store.get_analysis_result(production_id) or {}
        analysis["ia_preview"] = ia_payload
        if monitoring_store.get_analysis_result(production_id):
            monitoring_store.update_analysis_result(production_id, analysis)
        else:
            monitoring_store.analyses[production_id] = {
                "ndvi": None,
                "trend": None,
                "risk": "pendiente",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "result": analysis,
            }
        return {
            "ok": True,
            "production_id": production_id,
            "scene_name": scene_name,
            "ia_input": ia_input_payload,
            "ia_compact": ia_compact,
            "ia_preview": ia_payload,
        }
    finally:
        _release_production_lock(production_id, "ia_preview")


@router.post("/monitoring/ia/save/{production_id}")
async def save_ai_analysis_to_s3(production_id: int):
    _acquire_production_lock(production_id, "ia_save")
    try:
        if not MONITORING_S3_BUCKET:
            raise HTTPException(status_code=400, detail="MONITORING_S3_BUCKET is not configured")
        payload = monitoring_store.get_payload(production_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Production not found")

        scene = payload.get("escene") or {}
        scene_name = str(scene.get("scene_name") or "").strip()
        if not scene_name:
            raise HTTPException(status_code=400, detail="Scene selection is required")

        analysis = monitoring_store.get_analysis_result(production_id) or {}
        ia_payload = analysis.get("ia_preview")
        if not isinstance(ia_payload, dict):
            raise HTTPException(status_code=409, detail="No IA preview available. Generate preview first.")

        base_prefix = MONITORING_S3_PREFIX.strip("/")
        ia_key = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}/multiband.ia.json"
        s3_client.put_object(
            Bucket=MONITORING_S3_BUCKET,
            Key=ia_key,
            Body=json.dumps(ia_payload, ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        return {"ok": True, "production_id": production_id, "scene_name": scene_name, "ia_key": ia_key, "ia_uri": f"s3://{MONITORING_S3_BUCKET}/{ia_key}"}
    finally:
        _release_production_lock(production_id, "ia_save")


@router.get("/monitoring/status/{production_id}")
async def monitoring_status(production_id: int):
    analysis = monitoring_store.get_analysis_result(production_id) or {}
    truth = str(analysis.get("truth_tif_path") or "")
    render = str(analysis.get("render_tif_path") or "")
    return {
        "ok": True,
        "production_id": production_id,
        "has_analysis": bool(analysis),
        "truth_tif_uploaded": truth.startswith("s3://"),
        "render_tif_uploaded": render.startswith("s3://"),
        "truth_tif_path": truth or None,
        "render_tif_path": render or None,
    }


@router.post("/monitoring/render/{production_id}")
async def render_uploaded_tif(production_id: int):
    _acquire_production_lock(production_id, "render")
    try:
        if not MONITORING_S3_BUCKET:
            raise HTTPException(status_code=400, detail="MONITORING_S3_BUCKET is not configured")
        analysis = monitoring_store.get_analysis_result(production_id)
        payload = monitoring_store.get_payload(production_id)
        if not analysis or not payload:
            raise HTTPException(status_code=404, detail="No analysis found for production")
        truth = str(analysis.get("truth_tif_path") or "")
        if not truth.startswith("s3://"):
            raise HTTPException(status_code=400, detail="Upload base TIF to S3 first")
        expected_bands = len((payload.get("escene", {}) or {}).get("bands") or ["B04", "B03", "B02", "B08", "B05", "B06", "B07", "B8A", "B11", "B12"])
        existing_render = str(analysis.get("render_tif_path") or "")

        scene_name = payload.get("escene", {}).get("scene_name") or analysis.get("scene_name") or "unknown_scene"
        base_prefix = MONITORING_S3_PREFIX.strip("/")
        base_key = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}"

        folder_assets = _load_scene_assets_from_s3_prefix(production_id=production_id, scene_name=scene_name)
        render_path = ""
        if existing_render.startswith("s3://"):
            render_path = existing_render
        elif folder_assets and folder_assets.get("render_tif_path"):
            render_path = str(folder_assets["render_tif_path"])

        if not render_path:
            raise HTTPException(
                status_code=400,
                detail="No rendered TIF found. Upload external multiband_rendered.tif first.",
            )

        band_count = _tif_band_count(render_path, production_id, "external_render")
        if band_count < expected_bands:
            raise HTTPException(
                status_code=400,
                detail=f"Rendered TIF has {band_count} bands; expected at least {expected_bands}.",
            )

        existing_render_previews = (analysis.get("render_preview_pngs") or [])
        existing_render_thematics = (analysis.get("render_thematic_pngs") or [])
        if existing_render_previews and existing_render_thematics:
            return {"ok": True, "already_rendered": True, "render_tif_path": render_path}

        local_render = _download_s3_tif_to_local(render_path, production_id, scene_name)
        bands = (payload.get("escene", {}) or {}).get("bands") or ["B04", "B03", "B02", "B08", "B05", "B06", "B07", "B8A", "B11", "B12"]
        polygon_source = payload.get("production", {}).get("poligono_asig") or payload.get("production", {}).get("poligono_zona")
        polygon_geojson = _polygon_str_to_geojson(polygon_source) if polygon_source else None
        rendered = scene_tile_builder.build_from_multiband_tif(
            scene_name=scene_name,
            tile_size=int((payload.get("escene", {}) or {}).get("tile_size") or 256),
            multiband_tif_path=local_render,
            bands=bands,
            polygon_geojson=polygon_geojson,
            production_id=production_id,
        )

        render_preview_pngs: list[dict[str, str]] = []
        for p in rendered.get("pngs", []):
            local_png = str(p)
            filename = Path(local_png).name.replace(".png", "_render.png")
            key = f"{base_key}/{filename}"
            s3_client.upload_file(local_png, MONITORING_S3_BUCKET, key, ExtraArgs={"ContentType": "image/png"})
            render_preview_pngs.append({"path": f"s3://{MONITORING_S3_BUCKET}/{key}", "url": f"s3://{MONITORING_S3_BUCKET}/{key}"})

        render_thematic_pngs: list[dict[str, str]] = []
        for p in rendered.get("thematic_pngs", []):
            local_png = str(p)
            filename = Path(local_png).name.replace(".png", "_render.png")
            key = f"{base_key}/{filename}"
            s3_client.upload_file(local_png, MONITORING_S3_BUCKET, key, ExtraArgs={"ContentType": "image/png"})
            render_thematic_pngs.append({"path": f"s3://{MONITORING_S3_BUCKET}/{key}", "url": f"s3://{MONITORING_S3_BUCKET}/{key}"})

        analysis["render_tif_path"] = render_path
        analysis["render_preview_pngs"] = render_preview_pngs
        analysis["render_thematic_pngs"] = render_thematic_pngs
        monitoring_store.update_analysis_result(production_id, analysis)
        return {"ok": True, "render_tif_path": render_path, "generated_render_pngs": True}
    finally:
        _release_production_lock(production_id, "render")


@router.get("/", response_class=HTMLResponse)
@router.get("/scene/tile", response_class=HTMLResponse)
async def dashboard_view() -> str:
    return DASHBOARD_HTML


async def _run_production_analysis(payload: ProductionSceneRequest) -> dict[str, Any]:
    scene = payload.escene
    try:
        production_id = payload.production.produccion_id
        if not production_id:
            raise HTTPException(status_code=400, detail="produccion_id is required")

        # Only fallback to latest scene when no scene was selected.
        if scene is None:
            base_scene = _load_scene_record_from_s3(
                production_id=production_id,
                scene_name=None,
                scene_date=None,
            )
            if not base_scene:
                raise HTTPException(status_code=400, detail="escene missing and no scene record found in S3")
            scene = _scene_from_s3_record(base_scene, payload)

        # Fast deterministic lookup: previews/PROD_{id}/{scene_name}/...
        if scene and scene.scene_name:
            direct_assets = _load_scene_assets_direct(production_id=production_id, scene_name=scene.scene_name)
            if direct_assets and direct_assets.get("truth_tif_path"):
                local_tif = _download_s3_tif_to_local(
                    s3_uri=direct_assets["truth_tif_path"],
                    production_id=production_id,
                    scene_name=scene.scene_name,
                )
                latitude = scene.latitude
                longitude = scene.longitude
                polygon_source = payload.production.poligono_asig or payload.production.poligono_zona
                if polygon_source:
                    latitude, longitude = _polygon_center(polygon_source)
                polygon_geojson = _polygon_str_to_geojson(polygon_source) if polygon_source else None
                processed = scene_tile_builder.build_from_multiband_tif(
                    scene_name=scene.scene_name,
                    tile_size=scene.tile_size,
                    multiband_tif_path=local_tif,
                    bands=scene.bands,
                    polygon_geojson=polygon_geojson,
                    production_id=production_id,
                )
                render_preview_pngs: list[str] = direct_assets.get("render_preview_pngs", [])
                render_thematic_pngs: list[str] = direct_assets.get("render_thematic_pngs", [])
                if direct_assets.get("render_tif_path") and (not render_preview_pngs or not render_thematic_pngs):
                    render_preview_pngs = _render_png_variants_from_base(
                        processed.get("pngs", []),
                        Path(str(processed.get("output_dir", "/tmp/agro-tif/outputs"))),
                        "render",
                        production_id,
                    )
                    render_thematic_pngs = _render_png_variants_from_base(
                        processed.get("thematic_pngs", []),
                        Path(str(processed.get("output_dir", "/tmp/agro-tif/outputs"))),
                        "render",
                        production_id,
                    )
                previous_scene = _load_previous_scene_record_from_s3(
                    production_id=production_id,
                    current_scene_name=scene.scene_name,
                    current_date=scene.fecha,
                )
                return {
                    "scene_name": processed["scene_name"],
                    "tile_size": processed["tile_size"],
                    "bands": processed["bands"],
                    "multiband_tif": processed["multiband_tif"],
                    "pngs": processed["pngs"],
                    "output_dir": processed["output_dir"],
                    "indices": processed.get("indices", {}),
                    "index_stats": processed.get("index_stats", {}),
                    "thematic_pngs": processed.get("thematic_pngs", []),
                    "decision_summary": processed.get("decision_summary", {}),
                    "center_used": {"latitude": latitude, "longitude": longitude},
                    "manual_mode": True,
                    "source_mode": "s3_direct_tif_downloaded",
                    "truth_tif_path": direct_assets.get("truth_tif_path"),
                    "render_tif_path": direct_assets.get("render_tif_path"),
                    "render_preview_pngs": render_preview_pngs,
                    "render_thematic_pngs": render_thematic_pngs,
                    "s3_scene_record": None,
                    "previous_scene_record": previous_scene,
                }
        
        # Priority 0: check scene folder in S3 before generating/updating anything.
        if production_id and scene and scene.scene_name:
            folder_assets = _load_scene_assets_from_s3_prefix(
                production_id=production_id,
                scene_name=scene.scene_name,
            )
            if folder_assets and folder_assets.get("truth_tif_path"):
                local_tif = _download_s3_tif_to_local(
                    s3_uri=folder_assets["truth_tif_path"],
                    production_id=production_id,
                    scene_name=scene.scene_name,
                )
                latitude = scene.latitude
                longitude = scene.longitude
                polygon_source = payload.production.poligono_asig or payload.production.poligono_zona
                if polygon_source:
                    latitude, longitude = _polygon_center(polygon_source)
                polygon_geojson = _polygon_str_to_geojson(polygon_source) if polygon_source else None
                processed = scene_tile_builder.build_from_multiband_tif(
                    scene_name=scene.scene_name,
                    tile_size=scene.tile_size,
                    multiband_tif_path=local_tif,
                    bands=scene.bands,
                    polygon_geojson=polygon_geojson,
                    production_id=production_id,
                )
                render_preview_pngs: list[str] = folder_assets.get("render_preview_pngs", [])
                render_thematic_pngs: list[str] = folder_assets.get("render_thematic_pngs", [])
                if folder_assets.get("render_tif_path") and (not render_preview_pngs or not render_thematic_pngs):
                    render_preview_pngs = _render_png_variants_from_base(
                        processed.get("pngs", []),
                        Path(str(processed.get("output_dir", "/tmp/agro-tif/outputs"))),
                        "render",
                        production_id,
                    )
                    render_thematic_pngs = _render_png_variants_from_base(
                        processed.get("thematic_pngs", []),
                        Path(str(processed.get("output_dir", "/tmp/agro-tif/outputs"))),
                        "render",
                        production_id,
                    )
                previous_scene = _load_previous_scene_record_from_s3(
                    production_id=production_id,
                    current_scene_name=scene.scene_name,
                    current_date=scene.fecha,
                )
                return {
                    "scene_name": processed["scene_name"],
                    "tile_size": processed["tile_size"],
                    "bands": processed["bands"],
                    "multiband_tif": processed["multiband_tif"],
                    "pngs": processed["pngs"],
                    "output_dir": processed["output_dir"],
                    "indices": processed.get("indices", {}),
                    "index_stats": processed.get("index_stats", {}),
                    "thematic_pngs": processed.get("thematic_pngs", []),
                    "decision_summary": processed.get("decision_summary", {}),
                    "center_used": {"latitude": latitude, "longitude": longitude},
                    "manual_mode": True,
                    "source_mode": "s3_existing_scene_folder_downloaded",
                    "truth_tif_path": folder_assets.get("truth_tif_path"),
                    "render_tif_path": folder_assets.get("render_tif_path"),
                    "render_preview_pngs": render_preview_pngs,
                    "render_thematic_pngs": render_thematic_pngs,
                    "s3_scene_record": None,
                    "previous_scene_record": previous_scene,
                }

        s3_scene = None
        if production_id and scene and not scene.band_urls:
            s3_scene = _load_scene_record_from_s3(
                production_id=production_id,
                scene_name=scene.scene_name,
                scene_date=scene.fecha,
            )
            if s3_scene:
                preview = s3_scene.get("preview", {})
                tif_truth_key = preview.get("multiband") or _default_multiband_key(production_id, scene.scene_name)
                tif_render_key = preview.get("multiband_rendered") or tif_truth_key
                tif_truth_uri = _s3_uri_from_key(tif_truth_key) if tif_truth_key else None
                tif_render_uri = _s3_uri_from_key(tif_render_key) if tif_render_key else tif_truth_uri
                if tif_truth_key and _s3_key_exists(tif_truth_key):
                    tif_truth_uri = _s3_uri_from_key(tif_truth_key)
                    local_tif = _download_s3_tif_to_local(
                        s3_uri=tif_truth_uri,
                        production_id=production_id,
                        scene_name=scene.scene_name,
                    )
                    latitude = scene.latitude
                    longitude = scene.longitude
                    polygon_source = payload.production.poligono_asig or payload.production.poligono_zona
                    if polygon_source:
                        latitude, longitude = _polygon_center(polygon_source)
                    polygon_geojson = _polygon_str_to_geojson(polygon_source) if polygon_source else None
                    processed = scene_tile_builder.build_from_multiband_tif(
                        scene_name=scene.scene_name,
                        tile_size=scene.tile_size,
                        multiband_tif_path=local_tif,
                        bands=scene.bands,
                        polygon_geojson=polygon_geojson,
                        production_id=production_id,
                    )
                    previous_scene = _load_previous_scene_record_from_s3(
                        production_id=production_id,
                        current_scene_name=scene.scene_name,
                        current_date=scene.fecha,
                    )
                    return {
                        "scene_name": processed["scene_name"],
                        "tile_size": processed["tile_size"],
                        "bands": processed["bands"],
                        "multiband_tif": processed["multiband_tif"],
                        "pngs": processed["pngs"],
                        "output_dir": processed["output_dir"],
                        "indices": processed.get("indices", {}),
                        "index_stats": processed.get("index_stats", {}),
                        "thematic_pngs": processed.get("thematic_pngs", []),
                        "decision_summary": processed.get("decision_summary", {}),
                        "center_used": {"latitude": latitude, "longitude": longitude},
                        "manual_mode": True,
                        "source_mode": "s3_existing_tif_downloaded",
                        "truth_tif_path": tif_truth_uri,
                        "render_tif_path": tif_render_uri,
                        "s3_scene_record": s3_scene,
                        "previous_scene_record": previous_scene,
                    }
                scene_bands = s3_scene.get("bands", {})
                if isinstance(scene_bands, dict) and not scene.band_urls:
                    mapped = {}
                    key_map = {
                        "red": "band_red",
                        "green": "band_green",
                        "blue": "band_blue",
                        "nir": "band_nir",
                        "rededge1": "band_rededge1",
                        "rededge2": "band_rededge2",
                        "rededge3": "band_rededge3",
                        "nir_narrow": "band_nir_narrow",
                        "swir1": "band_swir1",
                        "swir2": "band_swir2",
                    }
                    for k, v in scene_bands.items():
                        norm = key_map.get(str(k).lower(), str(k))
                        mapped[norm] = v
                    scene.band_urls = _expand_missing_band_urls(mapped)

        latitude = scene.latitude
        longitude = scene.longitude
        polygon_source = payload.production.poligono_asig or payload.production.poligono_zona
        if polygon_source:
            latitude, longitude = _polygon_center(polygon_source)
        polygon_geojson = _polygon_str_to_geojson(polygon_source) if polygon_source else None

        catalog_scene = monitoring_store.get_scene(scene.scene_name, production_id=production_id or 0)
        if catalog_scene:
            return {
                "scene_name": scene.scene_name,
                "tile_size": scene.tile_size,
                "bands": scene.bands,
                "multiband_tif": catalog_scene.get("tif_render_path") or catalog_scene.get("tif_truth_path"),
                "pngs": catalog_scene.get("preview_pngs", []),
                "output_dir": catalog_scene.get("base_dir", ""),
                "indices": catalog_scene.get("indices", {}),
                "center_used": {"latitude": latitude, "longitude": longitude},
                "manual_mode": True,
                "source_mode": "catalog_existing_tif",
                "truth_tif_path": catalog_scene.get("tif_truth_path"),
                "render_tif_path": catalog_scene.get("tif_render_path"),
            }

        s3_monitoring = _read_monitoring_from_s3(payload)
        if s3_monitoring:
            if isinstance(s3_monitoring.get("band_urls"), dict) and not scene.band_urls:
                scene.band_urls = s3_monitoring["band_urls"]
            if s3_monitoring.get("scene_name") and not scene.scene_name:
                scene.scene_name = s3_monitoring["scene_name"]

        assets: dict[str, dict[str, str]] = {}
        for key, url in scene.band_urls.items():
            normalized = BAND_ALIAS_MAP.get(key.lower(), key.upper())
            assets[normalized] = {"href": url}

        if not assets:
            feature = await scene_assets_service.get_scene_assets(scene.scene_name)
            assets = feature.get("assets", {})

        result = scene_tile_builder.build(
            scene_name=scene.scene_name,
            latitude=latitude,
            longitude=longitude,
            tile_size=scene.tile_size,
            assets=assets,
            bands=scene.bands,
            polygon_geojson=polygon_geojson,
            production_id=production_id,
        )
        result["center_used"] = {"latitude": latitude, "longitude": longitude}
        result["manual_mode"] = True
        result["source_mode"] = "generated_from_band_urls"
        result["truth_tif_path"] = result["multiband_tif"]
        result["render_tif_path"] = result["multiband_tif"]
        _apply_agronomic_context(result, payload)
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _serialize_result(result: dict[str, Any], payload: ProductionSceneRequest | None = None) -> dict[str, Any]:
    thematic_pngs = result.get("thematic_pngs", [])
    render_preview_pngs = result.get("render_preview_pngs", [])
    render_thematic_pngs = result.get("render_thematic_pngs", [])
    if render_preview_pngs and isinstance(render_preview_pngs[0], dict):
        render_preview_out = [{"path": p.get("path"), "url": _to_public_url(str(p.get("url") or p.get("path") or ""))} for p in render_preview_pngs]
    else:
        render_preview_out = [{"path": p, "url": _to_public_url(str(p))} for p in render_preview_pngs]
    if render_thematic_pngs and isinstance(render_thematic_pngs[0], dict):
        render_thematic_out = [{"path": p.get("path"), "url": _to_public_url(str(p.get("url") or p.get("path") or ""))} for p in render_thematic_pngs]
    else:
        render_thematic_out = [{"path": p, "url": _to_public_url(str(p))} for p in render_thematic_pngs]
    output = {
        "ok": True,
        "scene_name": result["scene_name"],
        "tile_size": result["tile_size"],
        "bands": result["bands"],
        "multiband_tif_path": result["multiband_tif"],
        "multiband_tif_url": _to_public_url(str(result["multiband_tif"])),
        "preview_pngs": [{"path": p, "url": _to_public_url(p)} for p in result["pngs"]],
        "output_dir": result["output_dir"],
        "indices": result.get("indices", {}),
        "index_stats": result.get("index_stats", {}),
        "decision_summary": result.get("decision_summary", {}),
        "thematic_pngs": [{"path": p, "url": _to_public_url(p)} for p in thematic_pngs],
        "manual_mode": result.get("manual_mode", False),
        "source_mode": result.get("source_mode", "unknown"),
        "truth_tif_path": result.get("truth_tif_path"),
        "render_tif_path": result.get("render_tif_path"),
        "scene_record": result.get("s3_scene_record"),
        "previous_scene_record": result.get("previous_scene_record"),
        "agronomic_context": result.get("agronomic_context"),
        "render_preview_pngs": render_preview_out,
        "render_thematic_pngs": render_thematic_out,
    }
    if payload:
        output["scene_date"] = payload.escene.fecha if payload.escene else None
        output["produccion_id"] = payload.production.produccion_id
        output["folio"] = payload.production.folio
        output["center_used"] = result.get("center_used")
    return output


def _to_public_url(path: str) -> str:
    if path.startswith("s3://"):
        local = _materialize_s3_asset(path)
        if local:
            rel = Path(local).relative_to("/tmp/agro-tif/outputs")
            return f"/outputs/{quote(rel.as_posix(), safe='/')}"
        return f"/outputs/s3?path={quote(path, safe='')}"
    rel = Path(path).relative_to("/tmp/agro-tif/outputs")
    return f"/outputs/{rel.as_posix()}"


def _materialize_s3_asset(s3_uri: str) -> str | None:
    try:
        bucket, key = _parse_s3_uri(s3_uri)
        local_path = Path("/tmp/agro-tif/outputs/s3cache") / bucket / key
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if not local_path.exists() or local_path.stat().st_size == 0:
            s3_client.download_file(bucket, key, str(local_path))
        return str(local_path)
    except Exception:
        return None


def _polygon_center(polygon_str: str) -> tuple[float, float]:
    points = [p.strip() for p in polygon_str.split("|") if p.strip()]
    if len(points) < 3:
        raise ValueError("Invalid polygon: requires at least 3 points")
    lats: list[float] = []
    lons: list[float] = []
    for point in points:
        lat_str, lon_str = [v.strip() for v in point.split(",")]
        lats.append(float(lat_str))
        lons.append(float(lon_str))
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def _polygon_str_to_geojson(polygon_str: str) -> dict[str, Any]:
    points = [p.strip() for p in polygon_str.split("|") if p.strip()]
    coords: list[list[float]] = []
    for point in points:
        lat_str, lon_str = [v.strip() for v in point.split(",")]
        lat = float(lat_str)
        lon = float(lon_str)
        coords.append([lon, lat])
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def _polygon_str_to_latlon_pairs(polygon_str: str) -> list[list[float]]:
    points = [p.strip() for p in polygon_str.split("|") if p.strip()]
    out: list[list[float]] = []
    for point in points:
        lat_str, lon_str = [v.strip() for v in point.split(",")]
        out.append([float(lat_str), float(lon_str)])
    return out


def _bbox_from_polygon(latlon_pairs: list[list[float]]) -> list[float]:
    lats = [p[0] for p in latlon_pairs]
    lons = [p[1] for p in latlon_pairs]
    return [min(lons), min(lats), max(lons), max(lats)]


def _load_params_from_scene_record(scene_record: dict[str, Any]) -> dict[str, Any] | None:
    preview = scene_record.get("preview") or {}
    params_key = preview.get("parametros")
    if not params_key:
        scene_name = str(scene_record.get("scene_id") or scene_record.get("clave") or "").strip()
        prod_id = scene_record.get("__production_id")
        if scene_name and prod_id:
            base_prefix = MONITORING_S3_PREFIX.strip("/")
            params_key = f"{base_prefix + '/' if base_prefix else ''}PROD_{prod_id}/{scene_name}/multiband.params.json"
    if not params_key:
        return None
    try:
        obj = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=str(params_key))
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return None


def _has_any_params_for_date(production_id: int, scene_date: str) -> bool:
    if not MONITORING_S3_BUCKET:
        return False
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    prod_prefix = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/"
    try:
        listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=prod_prefix)
    except Exception:
        return False
    for obj in listing.get("Contents", []):
        key = str(obj.get("Key") or "")
        parsed = _parse_scene_index_key(prod_prefix, key)
        if not parsed:
            continue
        date_part, scene_name = parsed
        if date_part != scene_date:
            continue
        params_key = f"{prod_prefix}{scene_name}/multiband.params.json"
        if _s3_key_exists(params_key):
            return True
    return False


def _build_scene_params_payload(
    production_id: int,
    scene_date: str,
    analysis: dict[str, Any],
    previous_params: dict[str, Any] | None,
) -> dict[str, Any]:
    def n(value: Any, default: float = 0.0) -> float:
        return float(value) if isinstance(value, (int, float)) else float(default)

    idx = analysis.get("index_stats") or {}
    ndvi_mean = ((idx.get("ndvi") or {}).get("mean"))
    ndmi_mean = ((idx.get("ndmi") or {}).get("mean"))
    ndre_mean = ((idx.get("ndre") or {}).get("mean"))
    savi_mean = ((idx.get("savi") or {}).get("mean"))
    evi_mean = ((idx.get("evi") or {}).get("mean"))
    gndvi_mean = ((idx.get("gndvi") or {}).get("mean"))
    nbr_mean = ((idx.get("nbr") or {}).get("mean"))

    prev_hist = (previous_params or {}).get("historico", {}) if previous_params else {}
    prev_count = int(prev_hist.get("count") or 0)
    prev_ndvi_sum = float(prev_hist.get("ndvi_sum") or 0.0)
    prev_ndmi_sum = float(prev_hist.get("ndmi_sum") or 0.0)
    prev_ndre_sum = float(prev_hist.get("ndre_sum") or 0.0)
    prev_savi_sum = float(prev_hist.get("savi_sum") or 0.0)
    prev_evi_sum = float(prev_hist.get("evi_sum") or 0.0)
    prev_gndvi_sum = float(prev_hist.get("gndvi_sum") or 0.0)
    prev_nbr_sum = float(prev_hist.get("nbr_sum") or 0.0)

    cur_ndvi = n(ndvi_mean)
    cur_ndmi = n(ndmi_mean)
    cur_ndre = n(ndre_mean)
    cur_savi = n(savi_mean)
    cur_evi = n(evi_mean)
    cur_gndvi = n(gndvi_mean)
    cur_nbr = n(nbr_mean)

    count = prev_count + 1
    ndvi_sum = prev_ndvi_sum + cur_ndvi
    ndmi_sum = prev_ndmi_sum + cur_ndmi
    ndre_sum = prev_ndre_sum + cur_ndre
    savi_sum = prev_savi_sum + cur_savi
    evi_sum = prev_evi_sum + cur_evi
    gndvi_sum = prev_gndvi_sum + cur_gndvi
    nbr_sum = prev_nbr_sum + cur_nbr

    return {
        "id_produccion": production_id,
        "fecha_escena": scene_date,
        "archivo_tif": "multiband.tif",
        "sensor": "Sentinel-2",
        "resolucion_metros": 10,
        "nubosidad_pct": n(((analysis.get("scene_record") or {}).get("cloud_cover")), 0.0),
        "indices": {
            "ndvi": {"promedio": cur_ndvi, "min": cur_ndvi, "max": cur_ndvi, "zona_baja_pct": 0.0, "zona_media_pct": 100.0, "zona_alta_pct": 0.0},
            "ndwi": {"promedio": cur_ndmi, "zona_estres_hidrico_pct": 0.0},
            "ndre": {"promedio": cur_ndre},
            "savi": {"promedio": cur_savi},
            "evi": {"promedio": cur_evi},
            "gndvi": {"promedio": cur_gndvi},
            "nbr": {"promedio": cur_nbr},
        },
        "zonas_detectadas": [],
        "historico": {
            "count": count,
            "ndvi_sum": round(ndvi_sum, 6),
            "ndmi_sum": round(ndmi_sum, 6),
            "ndre_sum": round(ndre_sum, 6),
            "savi_sum": round(savi_sum, 6),
            "evi_sum": round(evi_sum, 6),
            "gndvi_sum": round(gndvi_sum, 6),
            "nbr_sum": round(nbr_sum, 6),
            "ndvi_promedio_historico": round(ndvi_sum / count, 6),
            "ndmi_promedio_historico": round(ndmi_sum / count, 6),
            "ndre_promedio_historico": round(ndre_sum / count, 6),
            "savi_promedio_historico": round(savi_sum / count, 6),
            "evi_promedio_historico": round(evi_sum / count, 6),
            "gndvi_promedio_historico": round(gndvi_sum / count, 6),
            "nbr_promedio_historico": round(nbr_sum / count, 6),
        },
        "anterior": {
            "fecha_escena": (previous_params or {}).get("fecha_escena"),
            "indices": (previous_params or {}).get("indices", {}),
            "historico": (previous_params or {}).get("historico", {}),
        },
    }


def _load_params_for_scene(production_id: int, scene_name: str) -> dict[str, Any] | None:
    if not MONITORING_S3_BUCKET:
        return None
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    key = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}/multiband.params.json"
    try:
        obj = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return None


def _build_ai_input_payload(
    production: dict[str, Any],
    current_params: dict[str, Any],
    previous_params: dict[str, Any] | None,
) -> dict[str, Any]:
    def _idx(params: dict[str, Any], name: str) -> float | None:
        try:
            return float((((params.get("indices") or {}).get(name) or {}).get("promedio")))
        except Exception:
            return None

    scene_date = str(current_params.get("fecha_escena") or datetime.now().strftime("%Y-%m-%d"))
    planting_date = str(production.get("fecha_plantacion") or "").strip() or None
    dds = _days_between(planting_date, scene_date) if planting_date else None
    stage = _estimate_phenology_stage_lettuce(dds) if dds is not None else None

    ndvi_cur = _idx(current_params, "ndvi")
    ndwi_cur = _idx(current_params, "ndwi")
    ndmi_cur = _idx(current_params, "ndmi")
    ndre_cur = _idx(current_params, "ndre")
    savi_cur = _idx(current_params, "savi")
    evi_cur = _idx(current_params, "evi")
    gndvi_cur = _idx(current_params, "gndvi")
    nbr_cur = _idx(current_params, "nbr")

    ndvi_prev = _idx(previous_params or {}, "ndvi")
    ndwi_prev = _idx(previous_params or {}, "ndwi")
    ndmi_prev = _idx(previous_params or {}, "ndmi")
    ndre_prev = _idx(previous_params or {}, "ndre")
    savi_prev = _idx(previous_params or {}, "savi")
    evi_prev = _idx(previous_params or {}, "evi")
    gndvi_prev = _idx(previous_params or {}, "gndvi")
    nbr_prev = _idx(previous_params or {}, "nbr")

    variedades = [v.strip() for v in str(production.get("variedades") or "").split(",") if v.strip()]
    return {
        "id_produccion": int(production.get("produccion_id") or current_params.get("id_produccion") or 0),
        "rancho": production.get("rancho"),
        "lote": production.get("folio"),
        "cultivo": production.get("articulo"),
        "variedades": variedades,
        "fecha_plantacion": planting_date,
        "fecha_analisis": datetime.now().strftime("%Y-%m-%d"),
        "fecha_escena": scene_date,
        "dias_despues_plantacion": dds,
        "etapa_fenologica": stage,
        "tipo_suelo": production.get("tipo_suelo"),
        "clima_historico": production.get("clima_historico"),
        "pronostico": production.get("pronostico"),
        "indices_actuales": {
            "ndvi": ndvi_cur,
            "ndwi": ndwi_cur,
            "ndmi": ndmi_cur,
            "ndre": ndre_cur,
            "savi": savi_cur,
            "evi": evi_cur,
            "gndvi": gndvi_cur,
            "nbr": nbr_cur,
        },
        "indices_anteriores": {
            "ndvi": ndvi_prev,
            "ndwi": ndwi_prev,
            "ndmi": ndmi_prev,
            "ndre": ndre_prev,
            "savi": savi_prev,
            "evi": evi_prev,
            "gndvi": gndvi_prev,
            "nbr": nbr_prev,
        },
        "historico": current_params.get("historico"),
        "zonas_detectadas": current_params.get("zonas_detectadas") or [],
    }


def _build_ai_output_payload(
    production: dict[str, Any],
    current_params: dict[str, Any],
    compact: dict[str, Any],
) -> dict[str, Any]:
    scene_date = str(current_params.get("fecha_escena") or datetime.now().strftime("%Y-%m-%d"))
    planting_date = str(production.get("fecha_plantacion") or "").strip() or None
    dds = _days_between(planting_date, scene_date) if planting_date else None
    stage = _estimate_phenology_stage_lettuce(dds) if dds is not None else None
    variedades = [v.strip() for v in str(production.get("variedades") or "").split(",") if v.strip()]
    hallazgos = compact.get("hallazgos") if isinstance(compact.get("hallazgos"), list) else []
    recomendaciones = compact.get("recomendaciones") if isinstance(compact.get("recomendaciones"), list) else []
    riesgo = compact.get("riesgo") if isinstance(compact.get("riesgo"), dict) else {"nivel": "medio", "motivo": "Sin detalle de riesgo"}
    return {
        "id_produccion": int(production.get("produccion_id") or current_params.get("id_produccion") or 0),
        "rancho": production.get("rancho"),
        "lote": production.get("folio"),
        "cultivo": production.get("articulo"),
        "variedades": variedades,
        "fecha_plantacion": planting_date,
        "fecha_analisis": datetime.now().strftime("%Y-%m-%d"),
        "fecha_escena": scene_date,
        "dias_despues_plantacion": dds,
        "etapa_fenologica_estimada": stage,
        "modelo": "modelo-ia-agricola-v1",
        "estado_general": str(compact.get("estado_general") or "sin_clasificar"),
        "resumen": str(compact.get("resumen") or ""),
        "hallazgos": hallazgos,
        "recomendaciones": recomendaciones,
        "riesgo": {
            "nivel": str(riesgo.get("nivel") or "medio"),
            "motivo": str(riesgo.get("motivo") or "Sin motivo especificado"),
        },
        "datos_opcionales": {
            "etapa_fenologica_manual": production.get("etapa_fenologica"),
            "tipo_suelo": production.get("tipo_suelo"),
            "clima_historico": production.get("clima_historico"),
            "pronostico": production.get("pronostico"),
        },
    }


def _estimate_phenology_stage_lettuce(days_since_planting: int | None) -> str:
    if days_since_planting is None:
        return "no_determinado"
    if days_since_planting <= 7:
        return "Establecimiento / arraigue inicial"
    if days_since_planting <= 21:
        return "Crecimiento vegetativo inicial"
    if days_since_planting <= 40:
        return "Desarrollo de roseta / formación comercial"
    if days_since_planting <= 55:
        return "Madurez / ventana de cosecha"
    return "Sobremadurez o etapa fuera de ventana esperada"


def _read_monitoring_from_s3(payload: ProductionSceneRequest) -> dict[str, Any] | None:
    key = payload.production.monitoring_s3_key
    if not key:
        return None
    bucket = payload.production.monitoring_s3_bucket or MONITORING_S3_BUCKET
    if not bucket:
        raise HTTPException(status_code=400, detail="MONITORING_S3_BUCKET is required")
    full_key = f"{MONITORING_S3_PREFIX}{key}" if MONITORING_S3_PREFIX else key
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=full_key)
        body = obj["Body"].read().decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Unable to read monitoring from S3: {exc}") from exc
    try:
        data = json.loads(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in S3 monitoring file: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="S3 monitoring file must be a JSON object")
    return data


def _s3_uri_from_key(key: str) -> str:
    if key.startswith("s3://"):
        return key
    return f"s3://{MONITORING_S3_BUCKET}/{key}"


def _parse_s3_uri(uri: str) -> tuple[str, str]:
    # s3://bucket/key
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {uri}")
    raw = uri[5:]
    bucket, _, key = raw.partition("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {uri}")
    return bucket, key


def _download_s3_tif_to_local(s3_uri: str, production_id: int, scene_name: str) -> str:
    bucket, key = _parse_s3_uri(s3_uri)
    local_dir = Path(f"/tmp/agro-tif/outputs/PROD_{production_id}/{scene_name}/source")
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / Path(key).name
    s3_client.download_file(bucket, key, str(local_path))
    print(f"[S3 scene tif] downloaded {s3_uri} -> {local_path}")
    return str(local_path)


def _enhance_visual_for_display(image: Image.Image) -> Image.Image:
    # Visual-only enhancement:
    # - upscale x2 (sharper inspection feel)
    # - local contrast + mild color/contrast boost
    # - unsharp mask for perceived detail
    rgb = image.convert("RGB")
    w, h = rgb.size
    upscaled = rgb.resize((max(1, w * 2), max(1, h * 2)), Image.Resampling.LANCZOS)
    contrasted = ImageOps.autocontrast(upscaled, cutoff=1)
    contrasted = ImageEnhance.Contrast(contrasted).enhance(1.18)
    contrasted = ImageEnhance.Color(contrasted).enhance(1.06)
    sharpened = contrasted.filter(ImageFilter.UnsharpMask(radius=2.0, percent=165, threshold=2))
    return sharpened


def _render_png_variants_from_base(
    base_png_paths: list[str],
    out_dir: Path,
    suffix: str,
    production_id: int,
) -> list[str]:
    out: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for p in base_png_paths:
        src = str(p or "")
        if not src:
            continue
        try:
            img = _enhance_visual_for_display(_load_image_from_path_or_s3(src, production_id))
        except Exception:
            continue
        stem = Path(src).stem
        filename = f"{stem}_{suffix}.png"
        dst = out_dir / filename
        img.save(dst, format="PNG")
        out.append(str(dst))
    return out


def _create_rendered_multiband_from_truth(source_tif: str, target_tif: str, scale_factor: int = 2) -> None:
    with rasterio.open(source_tif) as src:
        new_height = max(1, src.height * scale_factor)
        new_width = max(1, src.width * scale_factor)
        data = src.read(
            out_shape=(src.count, new_height, new_width),
            resampling=Resampling.bilinear,
        )
        profile = src.profile.copy()
        profile.update(
            {
                "height": new_height,
                "width": new_width,
                "transform": src.transform * src.transform.scale(src.width / new_width, src.height / new_height),
                "count": src.count,
                "compress": "lzw",
            }
        )
        with rasterio.open(target_tif, "w", **profile) as dst:
            dst.write(data)


def _tif_band_count(path_or_s3: str, production_id: int, label: str) -> int:
    local_path = path_or_s3
    if str(path_or_s3).startswith("s3://"):
        try:
            local_path = _download_s3_tif_to_local(str(path_or_s3), production_id, f"bandcheck_{label}")
        except Exception:
            return 0
    try:
        with rasterio.open(local_path) as src:
            return int(src.count or 0)
    except Exception:
        return 0


def _load_image_from_path_or_s3(path: str, production_id: int):
    if path.startswith("s3://"):
        bucket, key = _parse_s3_uri(path)
        body = s3_client.get_object(Bucket=bucket, Key=key)["Body"].read()
        tmp = f"/tmp/agro-tif/outputs/tmp_img_{production_id}_{Path(key).name}"
        Path(tmp).write_bytes(body)
        return Image.open(tmp).convert("RGB")
    return Image.open(path).convert("RGB")


def _s3_key_exists(key: str) -> bool:
    if not MONITORING_S3_BUCKET:
        return False
    try:
        if key.startswith("s3://"):
            bucket, object_key = _parse_s3_uri(key)
        else:
            bucket, object_key = MONITORING_S3_BUCKET, key
        s3_client.head_object(Bucket=bucket, Key=object_key)
        return True
    except Exception:
        return False


def _default_multiband_key(production_id: int, scene_name: str) -> str:
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    base = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}"
    return f"{base}/multiband.tif"


def _load_scene_assets_direct(production_id: int, scene_name: str) -> dict[str, Any] | None:
    if not MONITORING_S3_BUCKET:
        return None
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    scene_base = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}"
    truth_key = f"{scene_base}/multiband.tif"
    render_key = f"{scene_base}/multiband_rendered.tif"
    if not _s3_key_exists(truth_key):
        return None

    preview_pngs: list[str] = []
    thematic_pngs: list[str] = []
    render_preview_pngs: list[str] = []
    render_thematic_pngs: list[str] = []
    try:
        listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=f"{scene_base}/")
        png_keys = [obj.get("Key", "") for obj in listing.get("Contents", []) if obj.get("Key", "").lower().endswith(".png")]
        thematic_names = {"ndvi", "ndre", "ndmi", "nbr", "savi", "evi", "gndvi", "red_edge", "swir"}
        for k in png_keys:
            uri = f"s3://{MONITORING_S3_BUCKET}/{k}"
            stem = Path(k).stem.lower()
            is_render = stem.endswith("_render")
            base = stem[:-7] if is_render else stem
            if base in thematic_names:
                (render_thematic_pngs if is_render else thematic_pngs).append(uri)
            else:
                (render_preview_pngs if is_render else preview_pngs).append(uri)
    except Exception:
        pass

    return {
        "truth_tif_path": f"s3://{MONITORING_S3_BUCKET}/{truth_key}",
        "render_tif_path": f"s3://{MONITORING_S3_BUCKET}/{render_key}" if _s3_key_exists(render_key) else None,
        "preview_pngs": preview_pngs,
        "thematic_pngs": thematic_pngs,
        "render_preview_pngs": render_preview_pngs,
        "render_thematic_pngs": render_thematic_pngs,
        "base_dir": f"s3://{MONITORING_S3_BUCKET}/{scene_base}",
    }


def _load_scene_assets_from_s3_prefix(production_id: int, scene_name: str) -> dict[str, Any] | None:
    if not MONITORING_S3_BUCKET:
        print("[S3 scene lookup] MONITORING_S3_BUCKET is empty")
        return None
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    prefixes: list[str] = []
    primary = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/{scene_name}/"
    prefixes.append(primary)
    fallback = f"previews/PROD_{production_id}/{scene_name}/"
    if fallback != primary:
        prefixes.append(fallback)
    #print( "[S3 scene lookup] bucket=%s production_id=%s scene=%s prefixes=%s"
    #    % (MONITORING_S3_BUCKET, production_id, scene_name, prefixes)
    #)
    for prefix in prefixes:
        try:
            listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=prefix)
        except Exception:
            print(f"[S3 scene lookup] list_objects_v2 failed for prefix={prefix}")
            continue
        contents = listing.get("Contents", []) or []
        #print(f"[S3 scene lookup] prefix={prefix} objects={len(contents)}")
        if not contents:
            continue

        keys = [obj.get("Key", "") for obj in contents if obj.get("Key")]
        truth_key = next((k for k in keys if k.endswith("/multiband.tif")), None)
        render_key = next((k for k in keys if k.endswith("/multiband_rendered.tif")), None)
        #print(
        #    "[S3 scene lookup] prefix=%s truth_key=%s render_key=%s"
        #    % (prefix, truth_key, render_key)
        #)
        if not truth_key:
            continue

        png_keys = [k for k in keys if k.lower().endswith(".png")]
        thematic_names = {"ndvi", "ndre", "ndmi", "nbr", "savi", "evi", "gndvi", "red_edge", "swir"}
        thematic_pngs: list[str] = []
        preview_pngs: list[str] = []
        render_thematic_pngs: list[str] = []
        render_preview_pngs: list[str] = []
        for k in png_keys:
            stem = Path(k).stem.lower()
            uri = f"s3://{MONITORING_S3_BUCKET}/{k}"
            is_render = stem.endswith("_render")
            base = stem[:-7] if is_render else stem
            if base in thematic_names:
                (render_thematic_pngs if is_render else thematic_pngs).append(uri)
            else:
                (render_preview_pngs if is_render else preview_pngs).append(uri)

        return {
            "truth_tif_path": f"s3://{MONITORING_S3_BUCKET}/{truth_key}",
            "render_tif_path": f"s3://{MONITORING_S3_BUCKET}/{render_key}" if render_key else None,
            "preview_pngs": preview_pngs,
            "thematic_pngs": thematic_pngs,
            "render_preview_pngs": render_preview_pngs,
            "render_thematic_pngs": render_thematic_pngs,
            "base_dir": f"s3://{MONITORING_S3_BUCKET}/{prefix.rstrip('/')}",
        }
    return None


def _load_scene_record_from_s3(
    production_id: int,
    scene_name: str | None,
    scene_date: str | None,
) -> dict[str, Any] | None:
    if not MONITORING_S3_BUCKET:
        return None
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    prefixes = [
        f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/",
        #f"{base_prefix + '/' if base_prefix else ''}previews/PROD_{production_id}/",
    ]
    keys: list[str] = []
    for prefix in prefixes:
        #print(f"[S3 scene lookup] checking prefix={prefix}")
        preferred_key = f"{prefix}{scene_date}_{scene_name}.json" if scene_name and scene_date else None
        if preferred_key:
            keys.append(preferred_key)
        try:
            listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=prefix)
            for obj in listing.get("Contents", []):
                key = obj["Key"]
                #print(f"[S3 scene lookup] found key={key}")
                if key.endswith(".json") and key not in keys:
                    keys.append(key)
        except Exception as ex:
            print(f"[Exception S3 scene lookup] list_objects_v2 failed for prefix={prefix}: {ex}")
            continue
    if not keys:
        return None

    for key in keys:
        try:
            obj = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=key)
            #print(f"[S3 scene S lookup] reading key={key}")
            data = json.loads(obj["Body"].read().decode("utf-8"))
            if scene_name and str(data.get("scene_id") or data.get("clave") or "") == scene_name:
                return data
            if scene_name and scene_date and key.endswith(f"{scene_date}_{scene_name}.json"):
                return data
        except Exception as ex:
            print(f"[Exception S3 scene S lookup] failed to read key={key}: {ex}")
            continue
    if not scene_name:
        #print("[S3 scene S lookup] no scene_name specified, returning latest")
        # fallback: choose latest by fecha
        candidates: list[dict[str, Any]] = []
        for prefix in prefixes:
            try:
                listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=prefix)
                for obj in listing.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith(".json"):
                        continue
                    body = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=key)["Body"].read().decode("utf-8")
                    data = json.loads(body)
                    if data.get("fecha"):
                        candidates.append(data)
            except Exception:
                continue
        if candidates:
            candidates.sort(key=lambda x: str(x.get("fecha")), reverse=True)
            return candidates[0]
    return None


def _load_previous_scene_record_from_s3(
    production_id: int,
    current_scene_name: str,
    current_date: str,
) -> dict[str, Any] | None:
    if not MONITORING_S3_BUCKET:
        return None
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    prod_prefix = f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/"
    try:
        listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=prod_prefix)
    except Exception:
        return None
    candidates: list[tuple[str, str, str]] = []
    for obj in listing.get("Contents", []):
        key = str(obj.get("Key") or "")
        parsed = _parse_scene_index_key(prod_prefix, key)
        if not parsed:
            continue
        fecha, scene_name = parsed
        if fecha >= current_date:
            continue
        # Exclude only exact same scene+date, allow same scene name on older dates.
        if scene_name == current_scene_name and fecha == current_date:
            continue
        candidates.append((fecha, scene_name, key))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _, _, selected_key = candidates[0]
    try:
        body = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=selected_key)["Body"].read().decode("utf-8")
        data = json.loads(body)
        data["__production_id"] = production_id
        return data
    except Exception:
        return None


def _parse_scene_index_key(prod_prefix: str, key: str) -> tuple[str, str] | None:
    if not key.startswith(prod_prefix):
        return None
    rel = key[len(prod_prefix):]
    # Scene index files live at PROD_{id}/YYYY-mm-dd_{scene}.json (no nested folders).
    if "/" in rel:
        return None
    if not rel.endswith(".json"):
        return None
    if rel.endswith("multiband.params.json") or rel.endswith("multiband.ia.json"):
        return None
    if len(rel) < 16 or rel[10] != "_":
        return None
    date_part = rel[:10]
    try:
        datetime.strptime(date_part, "%Y-%m-%d")
    except Exception:
        return None
    scene_name = rel[11:-5].strip()
    if not scene_name:
        return None
    return date_part, scene_name


def _list_s3_scenes_for_production(production_id: int) -> list[dict[str, Any]]:
    if not MONITORING_S3_BUCKET:
        return []
    base_prefix = MONITORING_S3_PREFIX.strip("/")
    prefixes = [
        #f"{base_prefix + '/' if base_prefix else ''}PROD_{production_id}/",
        f"{base_prefix}/PROD_{production_id}/",
    ]
    out: dict[str, dict[str, Any]] = {}
    for prefix in prefixes:
        #print(f"[S3 scene list] checking prefix={prefix}")
        try:
            listing = s3_client.list_objects_v2(Bucket=MONITORING_S3_BUCKET, Prefix=prefix)
        except Exception as ex:
            print(f"[S3 scene list] list_objects_v2 failed for prefix={prefix}: {ex}")
            continue
        for obj in listing.get("Contents", []):
            key = obj.get("Key", "")
            #print(f"[S3 scene list] found key={key}")
            if not key.endswith(".json"):
                continue
            try:
                body = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=key)["Body"].read().decode("utf-8")
                data = json.loads(body)
            except Exception:
                continue
            scene_name = str(data.get("scene_id") or data.get("clave") or "").strip()
            scene_date = str(data.get("fecha") or "").strip()
            if not scene_name or not scene_date:
                continue
            scene_prefix = key.rsplit("/", 1)[0] + "/"
            truth_key = f"{scene_prefix}multiband.tif"
            render_key = f"{scene_prefix}multiband_rendered.tif"
            ia_key = f"{scene_prefix}multiband.ia.json"
            id_key = f"{scene_date}::{scene_name}"
            out[id_key] = {
                "scene_name": scene_name,
                "fecha": scene_date,
                "json_key": key,
                "scene_prefix": scene_prefix,
                "truth_tif_exists": _s3_key_exists(truth_key),
                "render_tif_exists": _s3_key_exists(render_key),
                "ia_exists": _s3_key_exists(ia_key),
            }
    items = list(out.values())
    items.sort(key=lambda x: (x.get("fecha") or "", x.get("scene_name") or ""), reverse=True)
    return items


def _expand_missing_band_urls(band_urls: dict[str, str]) -> dict[str, str]:
    required = {
        "band_blue": "B02",
        "band_green": "B03",
        "band_red": "B04",
        "band_rededge1": "B05",
        "band_rededge2": "B06",
        "band_rededge3": "B07",
        "band_nir": "B08",
        "band_nir_narrow": "B8A",
        "band_swir1": "B11",
        "band_swir2": "B12",
    }
    if not band_urls:
        return band_urls

    seed_url = next((v for v in band_urls.values() if isinstance(v, str) and v.startswith("http")), None)
    if not seed_url:
        return band_urls

    expanded = dict(band_urls)
    for alias, band_code in required.items():
        if expanded.get(alias):
            continue
        expanded[alias] = _replace_band_suffix(seed_url, band_code)
    return expanded


def _replace_band_suffix(url: str, band_code: str) -> str:
    # Example:
    # .../S2B_14QKJ_20260418_0_L2A/B04.tif -> .../B11.tif
    return re.sub(r"/B(?:0[2-9]|1[0-2]|8A)\.tif$", f"/{band_code}.tif", url)


def _read_json_from_s3_key(key: str) -> dict[str, Any] | None:
    if not MONITORING_S3_BUCKET:
        return None
    try:
        obj = s3_client.get_object(Bucket=MONITORING_S3_BUCKET, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return None


def _is_analysis_stale(fecha_analisis: str, max_days: int = 14) -> bool:
    try:
        fa = datetime.strptime(fecha_analisis, "%Y-%m-%d").date()
        now = datetime.now().date()
        return (now - fa).days > max_days
    except Exception:
        return True


def _prune_runtime_for_production(keep_production_id: int) -> dict[str, int]:
    removed_dirs = 0
    removed_tmp_imgs = 0
    dropped_analyses = 0
    dropped_scene_caches = 0

    # 1) Drop in-memory heavy caches from non-selected productions.
    for pid in list(monitoring_store.analyses.keys()):
        if int(pid) != int(keep_production_id):
            monitoring_store.analyses.pop(pid, None)
            dropped_analyses += 1
    for pid in list(monitoring_store.scenes_cache.keys()):
        if int(pid) != int(keep_production_id):
            monitoring_store.scenes_cache.pop(pid, None)
            dropped_scene_caches += 1

    # 2) Keep only /tmp outputs for selected production.
    root = Path("/tmp/agro-tif/outputs")
    if root.exists():
        for child in root.iterdir():
            name = child.name
            if child.is_dir() and name.startswith("PROD_"):
                if name != f"PROD_{keep_production_id}":
                    try:
                        shutil.rmtree(child, ignore_errors=True)
                        removed_dirs += 1
                    except Exception:
                        pass
            elif child.is_file() and name.startswith("tmp_img_"):
                # tmp_img_{production_id}_*.png
                if not name.startswith(f"tmp_img_{keep_production_id}_"):
                    try:
                        child.unlink(missing_ok=True)
                        removed_tmp_imgs += 1
                    except Exception:
                        pass

    return {
        "removed_dirs": removed_dirs,
        "removed_tmp_imgs": removed_tmp_imgs,
        "dropped_analyses": dropped_analyses,
        "dropped_scene_caches": dropped_scene_caches,
    }


def _prune_runtime_for_scene(production_id: int, keep_scene_name: str) -> dict[str, int]:
    removed_scene_dirs = 0
    root = Path(f"/tmp/agro-tif/outputs/PROD_{production_id}")
    if not root.exists():
        return {"removed_scene_dirs": removed_scene_dirs}
    for child in root.iterdir():
        if not child.is_dir():
            continue
        # Keep only selected scene directory
        if child.name != keep_scene_name:
            try:
                shutil.rmtree(child, ignore_errors=True)
                removed_scene_dirs += 1
            except Exception:
                pass
    return {"removed_scene_dirs": removed_scene_dirs}


def _scene_from_s3_record(record: dict[str, Any], payload: ProductionSceneRequest):
    from app.models.requests import SceneProductionInput

    polygon_source = payload.production.poligono_asig or payload.production.poligono_zona
    if polygon_source:
        lat, lon = _polygon_center(polygon_source)
    else:
        bbox = record.get("bbox") or [-100.0, 20.0, -99.0, 21.0]
        lon = (float(bbox[0]) + float(bbox[2])) / 2
        lat = (float(bbox[1]) + float(bbox[3])) / 2

    bands_obj = record.get("bands") or {}
    mapped = {}
    key_map = {
        "red": "band_red",
        "green": "band_green",
        "blue": "band_blue",
        "nir": "band_nir",
        "rededge1": "band_rededge1",
        "rededge2": "band_rededge2",
        "rededge3": "band_rededge3",
        "nir_narrow": "band_nir_narrow",
        "swir1": "band_swir1",
        "swir2": "band_swir2",
    }
    for k, v in bands_obj.items():
        mapped[key_map.get(str(k).lower(), str(k))] = v
    mapped = _expand_missing_band_urls(mapped)

    return SceneProductionInput(
        scene_name=str(record.get("scene_id") or record.get("clave") or "unknown_scene"),
        latitude=lat,
        longitude=lon,
        tile_size=256,
        bands=["B04", "B03", "B02", "B08", "B05", "B06", "B07", "B8A", "B11", "B12"],
        fecha=str(record.get("fecha") or ""),
        band_urls=mapped,
    )


def _apply_agronomic_context(result: dict[str, Any], payload: ProductionSceneRequest) -> None:
    production = payload.production
    crop_name = (production.articulo or "").strip().upper()
    planting_date = (production.fecha_plantacion or "").strip()
    scene_date = (
        (payload.escene.fecha if payload.escene else None)
        or str((result.get("s3_scene_record") or {}).get("fecha") or "")
    ).strip()
    variety = _extract_variety(production.plantaciones_json, production.variedades)

    cfg = crop_config_store.read()
    crop_cfg = (cfg.get("crops") or {}).get(crop_name, {})
    default_cfg = crop_cfg.get("default", {})
    var_cfg = (crop_cfg.get("variedades") or {}).get(variety.upper(), {}) if variety else {}
    profile = {**default_cfg, **var_cfg}

    ndvi_mean = (((result.get("index_stats") or {}).get("ndvi") or {}).get("mean"))
    decision_summary = result.get("decision_summary") or {}
    if ndvi_mean is not None and profile:
        ndvi_alert_min = profile.get("ndvi_alerta_min")
        ndvi_opt_min = profile.get("ndvi_optimo_min")
        if isinstance(ndvi_alert_min, (int, float)) and ndvi_mean < ndvi_alert_min:
            decision_summary["vigor_vegetal"] = "bajo (umbral variedad/cultivo)"
        elif isinstance(ndvi_opt_min, (int, float)) and ndvi_mean >= ndvi_opt_min:
            decision_summary["vigor_vegetal"] = "alto (umbral variedad/cultivo)"
        else:
            decision_summary["vigor_vegetal"] = "medio (umbral variedad/cultivo)"
        result["decision_summary"] = decision_summary

    result["agronomic_context"] = {
        "crop": crop_name or None,
        "variety": variety or None,
        "planting_date": planting_date or None,
        "scene_date": scene_date or None,
        "days_since_planting": _days_between(planting_date, scene_date),
        "profile_source": "crop_variety" if var_cfg else ("crop_default" if default_cfg else "general_fallback"),
        "profile_used": profile,
    }


def _extract_variety(plantaciones_json: str | None, variedades_field: str | None) -> str:
    if plantaciones_json:
        try:
            items = ast.literal_eval(plantaciones_json)
            if isinstance(items, list) and items:
                v = str((items[0] or {}).get("variedad") or "").strip()
                if v:
                    return v
        except Exception:
            pass
    if variedades_field:
        first = str(variedades_field).split(",")[0].strip()
        if first:
            return first
    return ""


def _days_between(start: str, end: str) -> int | None:
    try:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
        return (e - s).days
    except Exception:
        return None


DASHBOARD_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AgroSentinel Dashboard</title>
  <style>
    :root{
      --bg:#0f1115; --panel:#1a1f26; --panel-2:#202731; --txt:#ecf2ea; --muted:#8ea08f;
      --accent:#3c8d5a; --border:#2e3743; --warn:#d49f3a; --bad:#d25757; --good:#87c07f;
    }
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--txt);font-family:"Segoe UI",sans-serif}
    .app{display:grid;grid-template-columns:260px 1fr;min-height:100vh}
    .side{background:#171b20;border-right:1px solid var(--border);padding:20px}
    .brand{font-size:22px;font-weight:800;margin-bottom:20px}
    .item{padding:10px 12px;border-radius:8px;color:#c9d7cb;margin-bottom:8px;background:#1d232b}
    .item.active{background:#24303d;color:#e8f8ee}
    .main{padding:22px}
    .head{display:flex;justify-content:space-between;align-items:center}
    .btn{background:var(--accent);border:0;color:#fff;padding:10px 14px;border-radius:8px;font-weight:700;cursor:pointer}
    .layout{display:grid;grid-template-columns:1.3fr .7fr;gap:16px;margin-top:16px}
    .card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:14px}
    table{width:100%;border-collapse:collapse}
    th,td{padding:10px;border-bottom:1px solid #2b3440;text-align:left;font-size:14px}
    th{color:#9fb39f;font-weight:600}
    .tag{display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:700}
    .tag.optimo{background:#21402d;color:#b7f3c3}.tag.bueno{background:#2c4632;color:#d6efbb}
    .tag.moderado{background:#4a3a1f;color:#ffdca2}.tag.critico{background:#4f2424;color:#ffb4b4}
    .tag.pendiente{background:#343c45;color:#d2dbe2}
    tr.selected-row{background:#263341}
    tr.clickable-row{cursor:pointer}
    textarea{width:100%;min-height:220px;background:#0f151d;color:#cfe6d4;border:1px solid var(--border);border-radius:10px;padding:10px}
    .tiny{font-size:12px;color:var(--muted)} .preview img{width:100%;border-radius:8px;border:1px solid var(--border)}
    .progress-wrap{width:100%;max-width:420px;height:12px;background:#111820;border:1px solid var(--border);border-radius:999px;overflow:hidden}
    .progress-bar{height:100%;width:0%;background:linear-gradient(90deg,#3c8d5a,#7ecf90);transition:width .25s}
    @media(max-width:1050px){.app{grid-template-columns:1fr}.side{display:none}.layout{grid-template-columns:1fr}}
  </style>
</head>
<body>
  <div class="app">
    <aside class="side">
      <div class="brand">AgroSentinel</div>
      <div class="item">Dashboard</div>
      <div class="item active">Lotes y cultivos</div>
      <div class="item">Indices espectrales</div>
      <div class="item">Historial</div>
      <div class="item">Alertas</div>
      <div class="item"><a href="/configurations" style="color:#c9d7cb;text-decoration:none">Configuracion variedades</a></div>
    </aside>
    <main class="main">
      <div class="head">
        <div>
          <h2 style="margin:0">Gestion de lotes monitoreados</h2>
          <div class="tiny">Solo producciones con monitoring = 1</div>
        </div>
        <div style="display:flex;gap:8px">
          <a class="btn" href="/configurations" style="text-decoration:none;display:inline-flex;align-items:center">Configurar variedades</a>
          <button class="btn" id="refreshBtn">Actualizar</button>
        </div>
      </div>
      <div class="tiny" id="selectionStatus" style="margin-top:8px">Selecciona una produccion para habilitar acciones.</div>
      <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <label class="tiny" for="sceneSelect">Escena activa:</label>
        <select id="sceneSelect" style="min-width:360px;background:#0f151d;color:#cfe6d4;border:1px solid var(--border);border-radius:8px;padding:8px"></select>
        <button class="btn" id="reloadScenesBtn" style="max-width:220px">Recargar escenas</button>
      </div>
      <div style="margin-top:10px;display:flex;gap:8px">
        <button class="btn" id="analyzeBtn" style="max-width:260px">Crear/Actualizar TIF</button>
        <button class="btn" id="uploadBtn" style="max-width:260px">Subir TIF a S3</button>
        <button class="btn" id="backfillBtn" style="max-width:320px">Generar TODAS faltantes (produccion)</button>
        <button class="btn" id="renderBtn" style="max-width:260px">Generar imagenes render</button>
        <button class="btn" id="aiPreviewBtn" style="max-width:260px">Generar analisis IA</button>
        <button class="btn" id="aiSaveBtn" style="max-width:260px">Guardar analisis IA</button>
        <button class="btn" id="resetBtn" style="max-width:260px;background:#8a3d3d">Limpiar cache y temporales</button>
        <div class="tiny" id="uploadStatus"></div>
      </div>
      <div style="margin-top:8px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <div class="progress-wrap"><div id="backfillProgressBar" class="progress-bar"></div></div>
        <div class="tiny" id="backfillProgressText">Backfill inactivo</div>
      </div>
      <div class="layout">
        <section class="card">
          <h3 style="margin-top:0">Lotes y cultivos</h3>
          <table>
            <thead><tr><th>Folio</th><th>Cultivo</th><th>Hectareas</th><th>NDVI</th><th>Ultimo</th><th>Estado</th><th></th></tr></thead>
            <tbody id="lotsRows"><tr><td colspan="7" class="tiny">Sin datos.</td></tr></tbody>
          </table>
        </section>
        <section class="card">
          <h3 style="margin-top:0">Sincronizacion</h3>
          <p class="tiny">Las producciones y escenas se cargan automaticamente desde la URL configurada del sistema.</p>
          <p class="tiny">Usa el boton <b>Actualizar</b> para volver a consultar la fuente remota y ver su respuesta.</p>
        </section>
      </div>
      <div class="layout" style="margin-top:16px">
        <section class="card preview">
          <h3 style="margin-top:0">Preview True Color</h3>
          <div id="previewLayerButtons" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px"></div>
          <img id="previewImg" alt="preview" />
          <div class="tiny" id="previewPath">Esperando analisis...</div>
        </section>
        <section class="card">
          <h3 style="margin-top:0">Respuesta analisis</h3>
          <textarea id="analysisOutput" readonly></textarea>
          <h3 style="margin-top:12px">Analisis IA</h3>
          <div id="iaStatus" class="tiny">Selecciona una escena para cargar análisis IA.</div>
          <div id="iaPanel" class="tiny" style="margin-top:8px"></div>
        </section>
      </div>
      <div class="layout" style="margin-top:16px">
        <section class="card">
          <h3 style="margin-top:0">Panorama de capas</h3>
          <div class="tiny" style="margin-bottom:8px">Vista completa para validar que cada combinación de bandas se generó correctamente.</div>
          <div id="layerGrid" class="grid"></div>
        </section>
        <section class="card">
          <h3 style="margin-top:0">Resumen para decision</h3>
          <div id="decisionCards" class="tiny"></div>
        </section>
      </div>
      <div class="layout" style="margin-top:16px">
        <section class="card">
          <h3 style="margin-top:0">Configuracion activa (solo lectura)</h3>
          <textarea id="configOutput" readonly></textarea>
        </section>
      </div>
    </main>
  </div>
  <script>
    const rowsEl = document.getElementById("lotsRows");
    const output = document.getElementById("analysisOutput");
    const previewImg = document.getElementById("previewImg");
    const previewPath = document.getElementById("previewPath");
    const previewLayerButtons = document.getElementById("previewLayerButtons");
    const configOutput = document.getElementById("configOutput");
    const layerGrid = document.getElementById("layerGrid");
    const decisionCards = document.getElementById("decisionCards");
    const uploadStatus = document.getElementById("uploadStatus");
    const selectionStatus = document.getElementById("selectionStatus");
    const renderBtn = document.getElementById("renderBtn");
    const backfillBtn = document.getElementById("backfillBtn");
    const uploadBtn = document.getElementById("uploadBtn");
    const analyzeBtn = document.getElementById("analyzeBtn");
    const sceneSelect = document.getElementById("sceneSelect");
    const reloadScenesBtn = document.getElementById("reloadScenesBtn");
    const resetBtn = document.getElementById("resetBtn");
    const aiPreviewBtn = document.getElementById("aiPreviewBtn");
    const aiSaveBtn = document.getElementById("aiSaveBtn");
    const backfillProgressBar = document.getElementById("backfillProgressBar");
    const backfillProgressText = document.getElementById("backfillProgressText");
    const iaStatus = document.getElementById("iaStatus");
    const iaPanel = document.getElementById("iaPanel");
    let backfillPollTimer = null;
    const SESSION_PRODUCTIONS_KEY = "agro_monitoring_items_v1";
    const SESSION_SCENES_KEY = "agro_scene_catalog_items_v1";
    let selectedProductionId = null;
    let selectedRowEl = null;
    let lastAnalysis = null;
    let hasIaPreviewReady = false;
    let currentLayerMap = {};
    let currentLayerKey = "natural";
    let uiBusyMode = "idle";

    const LAYER_ORDER = ["natural","false_color_veg","red_edge","swir","ndvi","ndre","ndmi","savi","evi","gndvi","nbr"];
    const LAYER_LABELS = {
      natural: "Natural",
      false_color_veg: "Vegetation",
      red_edge: "Red Edge",
      swir: "SWIR",
      ndvi: "NDVI",
      ndre: "NDRE",
      ndmi: "NDMI",
      savi: "SAVI",
      evi: "EVI",
      gndvi: "GNDVI",
      nbr: "NBR",
    };
    const LAYER_DESCRIPTIONS = {
      natural: "Color real (B04/B03/B02). Vegetación sana suele verse verde; suelo marrón; agua oscura.",
      false_color_veg: "Falso color vegetación (B08/B04/B03). Vegetación vigorosa aparece en tonos rojos intensos.",
      red_edge: "Red Edge (B07/B06/B05). Sensible a estructura y clorofila; más brillo suele indicar mayor actividad vegetal.",
      swir: "SWIR (B12/B11/B08). Resalta humedad y suelo; áreas secas tienden a tonos más cálidos/brillantes.",
      ndvi: "NDVI: rojo/naranja = bajo vigor, amarillo = medio, verde = alto vigor vegetal.",
      ndre: "NDRE: útil en etapas medias/avanzadas del cultivo; valores altos indican mejor estado de clorofila.",
      ndmi: "NDMI: humedad en vegetación; valores altos sugieren mayor contenido hídrico.",
      savi: "SAVI: similar a NDVI pero corrige influencia de suelo desnudo.",
      evi: "EVI: vigor con corrección atmosférica/saturación; alto = vegetación más activa.",
      gndvi: "GNDVI: vigor usando banda verde; útil para estimar actividad fotosintética.",
      nbr: "NBR: contraste vegetación vs áreas secas/afectadas; valores bajos pueden indicar estrés o quemas.",
    };

    const BUSY_LABELS = {
      idle: "Listo",
      refresh: "Actualizando producciones",
      analyze_single: "Creando/actualizando TIF",
      backfill: "Generando todas las faltantes",
      upload: "Subiendo TIF y artefactos",
      render: "Generando imágenes render",
      ia_preview: "Generando análisis IA",
      ia_save: "Guardando análisis IA",
      reset: "Limpiando cache y temporales",
      scene_select: "Cargando escena",
    };

    function isUiBusy(){
      return uiBusyMode !== "idle";
    }

    function setUiBusy(mode){
      uiBusyMode = mode || "idle";
      const busy = isUiBusy();
      const lockAll = busy;
      analyzeBtn.disabled = lockAll || !selectedProductionId;
      backfillBtn.disabled = lockAll || !selectedProductionId;
      uploadBtn.disabled = lockAll || !selectedProductionId;
      renderBtn.disabled = lockAll || !selectedProductionId;
      aiPreviewBtn.disabled = lockAll || !selectedProductionId;
      aiSaveBtn.disabled = lockAll || !selectedProductionId || !hasIaPreviewReady;
      resetBtn.disabled = lockAll;
      reloadScenesBtn.disabled = lockAll || !selectedProductionId;
      sceneSelect.disabled = lockAll || !selectedProductionId;
      document.getElementById("refreshBtn").disabled = lockAll;
      const rows = rowsEl.querySelectorAll("tr.clickable-row");
      rows.forEach(r => { r.style.pointerEvents = lockAll ? "none" : "auto"; r.style.opacity = lockAll ? "0.65" : "1"; });
      if(busy){
        selectionStatus.textContent = `Sistema ocupado: ${BUSY_LABELS[uiBusyMode] || uiBusyMode}. Espera a que termine para evitar conflictos.`;
      }
    }

    function detectLayerKeyFromUrl(url){
      const clean = (url || "").split("?")[0].toLowerCase();
      const file = clean.substring(clean.lastIndexOf("/") + 1);
      const base = file.endsWith(".png") ? file.slice(0, -4) : file;
      return base.replace("_render", "");
    }

    function setPreviewLayer(layerKey){
      const item = currentLayerMap[layerKey];
      if(!item){
        return;
      }
      currentLayerKey = layerKey;
      previewImg.src = item.url + "?t=" + Date.now();
      previewPath.textContent = item.url;
      const buttons = previewLayerButtons.querySelectorAll("button[data-layer]");
      buttons.forEach(btn => {
        btn.style.opacity = (btn.dataset.layer === layerKey) ? "1" : "0.7";
        btn.style.outline = (btn.dataset.layer === layerKey) ? "2px solid #9fd6b0" : "none";
      });
    }

    function buildLayerButtons(){
      previewLayerButtons.innerHTML = "";
      const keys = Object.keys(currentLayerMap);
      if(!keys.length){
        return;
      }
      const ordered = [...LAYER_ORDER.filter(k => keys.includes(k)), ...keys.filter(k => !LAYER_ORDER.includes(k)).sort()];
      ordered.forEach(key => {
        const btn = document.createElement("button");
        btn.className = "btn";
        btn.dataset.layer = key;
        btn.style.padding = "6px 10px";
        btn.style.fontSize = "12px";
        btn.textContent = LAYER_LABELS[key] || key.toUpperCase();
        btn.onclick = () => setPreviewLayer(key);
        previewLayerButtons.appendChild(btn);
      });
      const initial = currentLayerMap["natural"] ? "natural" : ordered[0];
      setPreviewLayer(initial);
    }

    function renderAnalysisView(data){
      const renderPreviews = data.render_preview_pngs || [];
      const renderThematic = data.render_thematic_pngs || [];
      const previews = renderPreviews.length ? renderPreviews : (data.preview_pngs || []);
      const thematic = renderThematic.length ? renderThematic : (data.thematic_pngs || []);
      currentLayerMap = {};
      previews.forEach(item => {
        const k = detectLayerKeyFromUrl(item.url || item.path || "");
        if(k){ currentLayerMap[k] = item; }
      });
      thematic.forEach(item => {
        const k = detectLayerKeyFromUrl(item.url || item.path || "");
        if(k){ currentLayerMap[k] = item; }
      });
      if(Object.keys(currentLayerMap).length){
        buildLayerButtons();
      } else {
        previewLayerButtons.innerHTML = "";
        previewImg.removeAttribute("src");
        previewPath.textContent = "Sin capas para visualizar.";
      }
      layerGrid.innerHTML = "";
      const orderedKeys = [...LAYER_ORDER.filter(k => currentLayerMap[k]), ...Object.keys(currentLayerMap).filter(k => !LAYER_ORDER.includes(k)).sort()];
      orderedKeys.forEach(key => {
        const item = currentLayerMap[key];
        const card = document.createElement("div");
        card.className = "card";
        const title = LAYER_LABELS[key] || key.toUpperCase();
        const desc = LAYER_DESCRIPTIONS[key] || "Capa espectral generada.";
        card.innerHTML = `<div style="font-weight:700;margin-bottom:6px">${title}</div><img src="${item.url}?t=${Date.now()}" alt="layer"/><div class="tiny" style="margin-top:6px">${desc}</div><div class="meta tiny" style="margin-top:4px">${item.url}</div>`;
        card.style.cursor = "pointer";
        card.onclick = () => setPreviewLayer(key);
        layerGrid.appendChild(card);
      });
    }

    function sceneOptionText(x){
      const truth = x.truth_tif_exists ? "TIF" : "sin TIF";
      const rend = x.render_tif_exists ? "render" : "sin render";
      const ia = x.ia_exists ? "IA" : "sin IA";
      return `${x.fecha} | ${x.scene_name} | ${truth} | ${rend} | ${ia}`;
    }

    function refreshSelectedSceneOptionLabel(){
      if(!sceneSelect || sceneSelect.selectedIndex < 0){ return; }
      const opt = sceneSelect.options[sceneSelect.selectedIndex];
      const truth = opt.dataset.truth === "1";
      const render = opt.dataset.render === "1";
      const ia = opt.dataset.ia === "1";
      const date = opt.dataset.sceneDate || "-";
      const name = opt.value || "-";
      opt.textContent = `${date} | ${name} | ${truth ? "TIF" : "sin TIF"} | ${render ? "render" : "sin render"} | ${ia ? "IA" : "sin IA"}`;
    }

    function renderIaPanelFromPayload(ia, stale, sourceLabel, message){
      const hall = Array.isArray(ia.hallazgos) ? ia.hallazgos : [];
      const recs = Array.isArray(ia.recomendaciones) ? ia.recomendaciones : [];
      const hallHtml = hall.map(h => `<div style="padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:6px"><b>${h.tipo || "hallazgo"}</b> | zona: ${h.zona || "general"} | severidad: ${h.severidad || "baja"}<br/>${h.descripcion || ""}</div>`).join("");
      const recHtml = recs.map(r => `<li>${r}</li>`).join("");
      const staleHtml = stale ? `<div style="padding:8px;border:1px solid #7a5a24;border-radius:8px;background:#3b2d16;color:#ffdba1;margin-bottom:8px">Este análisis está demasiado antiguo. Se sugiere actualizar el análisis al día de hoy (${new Date().toISOString().slice(0,10)}).</div>` : "";
      iaStatus.textContent = `${message || "Análisis IA cargado"}${sourceLabel ? ` (fuente: ${sourceLabel})` : ""}`;
      iaPanel.innerHTML = `
        ${staleHtml}
        <div style="padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px">
          <b>Estado general:</b> ${ia.estado_general || "n/d"}<br/>
          <b>Riesgo:</b> ${(ia.riesgo || {}).nivel || "n/d"} - ${(ia.riesgo || {}).motivo || ""}
        </div>
        <div style="padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px"><b>Resumen:</b><br/>${ia.resumen || "Sin resumen"}</div>
        <div><b>Hallazgos</b></div>
        ${hallHtml || "<div class='tiny'>Sin hallazgos.</div>"}
        <div style="margin-top:8px"><b>Recomendaciones</b></div>
        ${recHtml ? `<ol>${recHtml}</ol>` : "<div class='tiny'>Sin recomendaciones.</div>"}
      `;
    }

    async function loadIaForSelection(productionId){
      if(!productionId || !sceneSelect || sceneSelect.selectedIndex < 0){ return; }
      const selected = sceneSelect.options[sceneSelect.selectedIndex];
      const sceneName = selected.value;
      const sceneDate = selected.dataset.sceneDate || "";
      iaStatus.textContent = "Cargando análisis IA...";
      iaPanel.innerHTML = "";
      try{
        const r = await fetch(`/monitoring/ia/${productionId}?scene_name=${encodeURIComponent(sceneName)}&scene_date=${encodeURIComponent(sceneDate)}`);
        const data = await r.json().catch(() => ({}));
        if(!r.ok){
          iaStatus.textContent = data.detail || "No se pudo cargar análisis IA.";
          return;
        }
        if(!data.has_ia){
          iaStatus.textContent = "No existe análisis IA para esta producción.";
          return;
        }
        const ia = data.ia || {};
        const stale = !!data.stale;
        const source = data.source === "latest_fallback" ? "ultimo disponible" : "escena seleccionada";
        renderIaPanelFromPayload(ia, stale, source, data.message || "Análisis IA cargado");
      }catch(e){
        iaStatus.textContent = "Error cargando análisis IA.";
      }
    }

    async function selectSceneForProduction(productionId, sceneName, sceneDate){
      if(isUiBusy()){ return; }
      if(!sceneName){ return; }
      setUiBusy("scene_select");
      const r = await fetch(`/monitoring/scenes/${productionId}/select`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ scene_name: sceneName, scene_date: sceneDate || null }),
      });
      const data = await r.json().catch(() => ({}));
      if(!r.ok){
        selectionStatus.textContent = data.detail || "No se pudo seleccionar escena.";
        setUiBusy("idle");
        return;
      }
      selectionStatus.textContent = `Produccion ${productionId} | Escena activa: ${sceneName}`;
      setUiBusy("idle");
    }

    async function loadScenesForProduction(productionId){
      sceneSelect.innerHTML = '<option value="">Cargando escenas...</option>';
      const r = await fetch(`/monitoring/scenes/${productionId}`);
      const data = await r.json().catch(() => ({}));
      const items = data.items || [];
      if(!items.length){
        sceneSelect.innerHTML = '<option value="">Sin escenas disponibles en S3</option>';
        return;
      }
      sceneSelect.innerHTML = items.map((x, idx) => `
        <option value="${x.scene_name}" data-scene-date="${x.fecha}" data-truth="${x.truth_tif_exists ? "1" : "0"}" data-render="${x.render_tif_exists ? "1" : "0"}" data-ia="${x.ia_exists ? "1" : "0"}" ${idx===0 ? "selected" : ""}>${sceneOptionText(x)}</option>
      `).join("");
      // Siempre seleccionar por defecto la escena mas reciente (index 0 por orden desc).
      const selected = sceneSelect.options[sceneSelect.selectedIndex];
      await selectSceneForProduction(productionId, selected.value, selected.dataset.sceneDate);
      if(selected.dataset.truth === "1" || selected.dataset.render === "1"){
        await analyzeLot(productionId);
      } else {
        output.value = "Escena seleccionada sin TIF en S3. Usa Crear/Actualizar TIF.";
      }
      await loadIaForSelection(productionId);
    }

    async function loadLots(){
      const r = await fetch("/monitoring/lots");
      const data = await r.json();
      const rows = data.items || [];
      if(!rows.length){
        rowsEl.innerHTML = '<tr><td colspan="7" class="tiny">No hay producciones monitoreadas.</td></tr>';
        return;
      }
      rowsEl.innerHTML = rows.map(x => `
        <tr class="clickable-row" data-prod-id="${x.produccion_id}" onclick="selectLot(${x.produccion_id}, this)">
          <td>${x.folio || "-"}</td>
          <td>${x.articulo || "-"}</td>
          <td>${x.hectareas || 0}</td>
          <td>${x.ndvi_actual ?? "-"}</td>
          <td>${x.ultimo_analisis || "-"}</td>
          <td><span class="tag ${x.estado || "pendiente"}">${x.estado || "pendiente"}</span></td>
          <td class="tiny"></td>
        </tr>
      `).join("");
      if(selectedProductionId){
        const row = rowsEl.querySelector(`tr[data-prod-id="${selectedProductionId}"]`);
        if(row){
          row.classList.add("selected-row");
          selectedRowEl = row;
        }
      }
    }

    async function bootstrapFromSessionCache(){
      let importedAny = false;
      try{
        const prodRaw = sessionStorage.getItem(SESSION_PRODUCTIONS_KEY);
        if(prodRaw){
          const prodItems = JSON.parse(prodRaw);
          if(Array.isArray(prodItems) && prodItems.length){
            await fetch("/monitoring/import", {
              method:"POST",
              headers:{"Content-Type":"application/json"},
              body: JSON.stringify({ items: prodItems }),
            });
            importedAny = true;
          }
        }
      }catch(e){}
      try{
        const scRaw = sessionStorage.getItem(SESSION_SCENES_KEY);
        if(scRaw){
          const sceneItems = JSON.parse(scRaw);
          if(Array.isArray(sceneItems) && sceneItems.length){
            await fetch("/catalog/scenes/import", {
              method:"POST",
              headers:{"Content-Type":"application/json"},
              body: JSON.stringify({ items: sceneItems }),
            });
            importedAny = true;
          }
        }
      }catch(e){}
      return importedAny;
    }

    async function analyzeLot(productionId){
      output.value = "Procesando produccion " + productionId + "...";
      const r = await fetch(`/monitoring/analyze/${productionId}`, {method:"POST"});
      const data = await r.json();
      lastAnalysis = data;
      output.value = JSON.stringify(data, null, 2);
      renderAnalysisView(data);
      const labels = {
        vigor_vegetal: "Vigor vegetal",
        estres_hidrico: "Estres hidrico",
        humedad: "Humedad",
        enfermedades: "Enfermedades",
        suelo_desnudo: "Suelo desnudo",
        malezas: "Malezas",
        inundaciones: "Inundaciones",
        salinidad: "Salinidad",
        quemas: "Quemas",
        estructura_cultivo: "Estructura del cultivo"
      };
      const stats = data.index_stats || {};
      const summary = data.decision_summary || {};
      decisionCards.innerHTML = Object.keys(labels).map(k => {
        const title = labels[k];
        const v = summary[k] || "n/d";
        return `<div style="padding:8px;border:1px solid var(--border);border-radius:8px;margin-bottom:8px"><b>${title}:</b> ${v}</div>`;
      }).join("") + `<pre>${JSON.stringify(stats, null, 2)}</pre>`;
      await loadLots();
      await refreshActionState();
    }

    async function selectLot(productionId, btnEl){
      if(isUiBusy()){ return; }
      selectedProductionId = productionId;
      lastAnalysis = null;
      hasIaPreviewReady = false;
      if(selectedRowEl){ selectedRowEl.classList.remove("selected-row"); }
      selectedRowEl = btnEl;
      if(selectedRowEl){ selectedRowEl.classList.add("selected-row"); }
      output.value = "";
      layerGrid.innerHTML = "";
      previewLayerButtons.innerHTML = "";
      currentLayerMap = {};
      previewImg.removeAttribute("src");
      previewPath.textContent = "Esperando analisis...";
      selectionStatus.textContent = `Produccion seleccionada: ${productionId}`;
      await loadScenesForProduction(productionId);
      await refreshActionState();
      // Intentar cargar ultimo analisis si existe.
      const st = await fetch(`/monitoring/status/${productionId}`).then(r => r.json()).catch(() => null);
      if(st && st.has_analysis){
        output.value = "Produccion con analisis previo disponible. Puedes subir TIF o crear render segun estado.";
      }
      await loadIaForSelection(productionId);
    }

    async function refreshActionState(){
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        analyzeBtn.disabled = true;
        uploadBtn.disabled = true;
        backfillBtn.disabled = true;
        renderBtn.disabled = true;
        aiPreviewBtn.disabled = true;
        aiSaveBtn.disabled = true;
        selectionStatus.textContent = "Selecciona una produccion para habilitar acciones.";
        return;
      }
      const r = await fetch(`/monitoring/status/${selectedProductionId}`);
      const st = await r.json();
      analyzeBtn.disabled = false;
      uploadBtn.disabled = !st.has_analysis || st.truth_tif_uploaded;
      backfillBtn.disabled = false;
      renderBtn.disabled = !st.truth_tif_uploaded || st.render_tif_uploaded;
      aiPreviewBtn.disabled = !st.truth_tif_uploaded;
      aiSaveBtn.disabled = !st.truth_tif_uploaded || !hasIaPreviewReady;
      if(!st.has_analysis){
        selectionStatus.textContent = "No hay TIF generado. Usa Crear/Actualizar TIF.";
      } else if(!st.truth_tif_uploaded){
        selectionStatus.textContent = "TIF generado localmente. Falta subir a S3.";
      } else if(!st.render_tif_uploaded){
        selectionStatus.textContent = "TIF en S3 listo. Puedes crear render.";
      } else {
        selectionStatus.textContent = "TIF y render ya existen en S3.";
      }
    }

    document.getElementById("refreshBtn").onclick = async () => {
      if(isUiBusy()){ return; }
      setUiBusy("refresh");
      uploadStatus.textContent = "Actualizando...";
      try{
        const r = await fetch("/monitoring/import-from-api", { method:"POST" });
        const data = await r.json().catch(() => ({}));
        output.value = JSON.stringify(data, null, 2);
        if(!r.ok){
          uploadStatus.textContent = (data.detail && (data.detail.error || data.detail.message)) || data.detail || "Error actualizando desde API";
          return;
        }
        const imp = data.import || {};
        selectionStatus.textContent = `Importadas: ${imp.imported || 0} | Monitoreadas: ${imp.monitored || 0}`;
        uploadStatus.textContent = `Actualizado desde URL: ${data.source_url || "-"}`;
        if(data.api_response && Array.isArray(data.api_response.items)){
          sessionStorage.setItem(SESSION_PRODUCTIONS_KEY, JSON.stringify(data.api_response.items));
        }
        await loadLots();
      }catch(e){
        uploadStatus.textContent = "Error actualizando desde API";
      } finally {
        setUiBusy("idle");
        await refreshActionState();
      }
    };
    reloadScenesBtn.onclick = async () => {
      if(!selectedProductionId){ return; }
      await loadScenesForProduction(selectedProductionId);
    };
    sceneSelect.onchange = async () => {
      if(!selectedProductionId){ return; }
      const selected = sceneSelect.options[sceneSelect.selectedIndex];
      hasIaPreviewReady = false;
      await selectSceneForProduction(selectedProductionId, selected.value, selected.dataset.sceneDate);
      if(selected.dataset.truth === "1" || selected.dataset.render === "1"){
        await analyzeLot(selectedProductionId);
      } else {
        output.value = "Escena seleccionada sin TIF en S3. Usa Crear/Actualizar TIF.";
        layerGrid.innerHTML = "";
        previewLayerButtons.innerHTML = "";
        currentLayerMap = {};
        previewImg.removeAttribute("src");
        previewPath.textContent = "Esperando analisis...";
        await refreshActionState();
      }
      await loadIaForSelection(selectedProductionId);
    };
    document.getElementById("analyzeBtn").onclick = async () => {
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        uploadStatus.textContent = "Selecciona una produccion primero.";
        return;
      }
      setUiBusy("analyze_single");
      try{
        await analyzeLot(selectedProductionId);
      } finally {
        setUiBusy("idle");
        await refreshActionState();
      }
    };
    document.getElementById("uploadBtn").onclick = async () => {
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        uploadStatus.textContent = "Selecciona una produccion primero.";
        return;
      }
      setUiBusy("upload");
      uploadStatus.textContent = "Subiendo a S3...";
      const r = await fetch(`/monitoring/upload/${selectedProductionId}`, {method:"POST"});
      const text = await r.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
      if(!r.ok){
        uploadStatus.textContent = data.detail || "Error subiendo a S3";
        setUiBusy("idle");
        return;
      }
      uploadStatus.textContent = `Subido a S3. Escena registrada: ${data.scene_name}`;
      if(sceneSelect && sceneSelect.selectedIndex >= 0){
        const opt = sceneSelect.options[sceneSelect.selectedIndex];
        opt.dataset.truth = "1";
        refreshSelectedSceneOptionLabel();
      }
      await refreshActionState();
      setUiBusy("idle");
    };
    backfillBtn.onclick = async () => {
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        uploadStatus.textContent = "Selecciona una produccion primero.";
        return;
      }
      setUiBusy("backfill");
      const force = confirm("Deseas forzar regeneracion aunque ya existan TIF/params? Aceptar=forzar, Cancelar=solo faltantes.");
      uploadStatus.textContent = "Iniciando backfill historico...";
      backfillProgressBar.style.width = "0%";
      backfillProgressText.textContent = "Preparando...";
      const r = await fetch(`/monitoring/backfill/start/${selectedProductionId}`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ force }),
      });
      const data = await r.json().catch(() => ({}));
      if(!r.ok){
        output.value = JSON.stringify(data, null, 2);
        uploadStatus.textContent = data.detail || "Error generando historico.";
        setUiBusy("idle");
        return;
      }
      const jobId = data.job_id;
      uploadStatus.textContent = `Backfill en progreso (job ${jobId})...`;
      if(backfillPollTimer){ clearInterval(backfillPollTimer); backfillPollTimer = null; }
      const poll = async () => {
        const rs = await fetch(`/monitoring/backfill/status/${jobId}`);
        const st = await rs.json().catch(() => ({}));
        if(!rs.ok){
          backfillProgressText.textContent = "Error consultando progreso.";
          if(backfillPollTimer){ clearInterval(backfillPollTimer); backfillPollTimer = null; }
          return;
        }
        const pct = Number(st.progress_pct || 0);
        backfillProgressBar.style.width = `${pct}%`;
        const prepPct = Number(st.phase_prepare_pct || 0);
        const upPct = Number(st.phase_upload_pct || 0);
        backfillProgressText.textContent = `${st.status || "running"} | total ${pct}% | preparar ${prepPct}% | subir ${upPct}% | ${st.processed_scenes || 0}/${st.total_scenes || 0}`;
        output.value = JSON.stringify(st, null, 2);
        if(st.status === "done" || st.status === "error"){
          if(backfillPollTimer){ clearInterval(backfillPollTimer); backfillPollTimer = null; }
          uploadStatus.textContent = st.status === "done" ? "Backfill historico finalizado." : `Backfill con error: ${st.error || "ver recuadro"}`;
          await loadScenesForProduction(selectedProductionId);
          await refreshActionState();
          setUiBusy("idle");
        }
      };
      await poll();
      backfillPollTimer = setInterval(poll, 1200);
    };
    document.getElementById("renderBtn").onclick = async () => {
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        uploadStatus.textContent = "Selecciona una produccion primero.";
        return;
      }
      setUiBusy("render");
      uploadStatus.textContent = "Generando render mejorado...";
      const r = await fetch(`/monitoring/render/${selectedProductionId}`, {method:"POST"});
      const text = await r.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
      if(!r.ok){
        uploadStatus.textContent = data.detail || "Error renderizando TIF";
        setUiBusy("idle");
        return;
      }
      uploadStatus.textContent = data.already_rendered ? "Render ya existia en S3." : "Render generado y subido.";
      if(sceneSelect && sceneSelect.selectedIndex >= 0){
        const opt = sceneSelect.options[sceneSelect.selectedIndex];
        opt.dataset.truth = "1";
        opt.dataset.render = "1";
        refreshSelectedSceneOptionLabel();
      }
      await refreshActionState();
      await analyzeLot(selectedProductionId);
      setUiBusy("idle");
    };
    aiPreviewBtn.onclick = async () => {
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        uploadStatus.textContent = "Selecciona una produccion primero.";
        return;
      }
      setUiBusy("ia_preview");
      uploadStatus.textContent = "Generando analisis IA desde params...";
      const r = await fetch(`/monitoring/ia/preview/${selectedProductionId}`, {method:"POST"});
      const text = await r.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
      if(!r.ok){
        const detail = data.detail || data;
        output.value = JSON.stringify(detail, null, 2);
        uploadStatus.textContent = "Error generando analisis IA (ver detalle en recuadro).";
        setUiBusy("idle");
        return;
      }
      output.value = JSON.stringify(data.ia_preview || data, null, 2);
      uploadStatus.textContent = "Analisis IA generado (preview). Revisa y luego guarda si quieres.";
      hasIaPreviewReady = true;
      if(!lastAnalysis){ lastAnalysis = {}; }
      lastAnalysis.ia_preview = data.ia_preview || null;
      renderIaPanelFromPayload(data.ia_preview || {}, false, "preview local", "Análisis IA preview generado");
      setUiBusy("idle");
      await refreshActionState();
    };
    aiSaveBtn.onclick = async () => {
      if(isUiBusy()){ return; }
      if(!selectedProductionId){
        uploadStatus.textContent = "Selecciona una produccion primero.";
        return;
      }
      setUiBusy("ia_save");
      uploadStatus.textContent = "Guardando analisis IA en S3...";
      const r = await fetch(`/monitoring/ia/save/${selectedProductionId}`, {method:"POST"});
      const text = await r.text();
      let data = {};
      try { data = text ? JSON.parse(text) : {}; } catch { data = { detail: text }; }
      if(!r.ok){
        uploadStatus.textContent = data.detail || "Error guardando analisis IA";
        setUiBusy("idle");
        return;
      }
      uploadStatus.textContent = `Analisis IA guardado: ${data.ia_uri || data.ia_key}`;
      hasIaPreviewReady = false;
      if(sceneSelect && sceneSelect.selectedIndex >= 0){
        const opt = sceneSelect.options[sceneSelect.selectedIndex];
        opt.dataset.ia = "1";
        refreshSelectedSceneOptionLabel();
      }
      await loadIaForSelection(selectedProductionId);
      setUiBusy("idle");
      await refreshActionState();
    };
    resetBtn.onclick = async () => {
      if(isUiBusy()){ return; }
      const yes = confirm("Esto limpiara cache, producciones cargadas y temporales locales. Deseas continuar?");
      if(!yes){ return; }
      setUiBusy("reset");
      uploadStatus.textContent = "Limpiando cache y temporales...";
      const r = await fetch("/monitoring/reset", { method:"POST" });
      const data = await r.json().catch(() => ({}));
      if(!r.ok){
        uploadStatus.textContent = data.detail || "Error limpiando estado.";
        setUiBusy("idle");
        return;
      }
      selectedProductionId = null;
      lastAnalysis = null;
      if(selectedRowEl){ selectedRowEl.classList.remove("selected-row"); selectedRowEl = null; }
      rowsEl.innerHTML = '<tr><td colspan="7" class="tiny">Sin datos.</td></tr>';
      sceneSelect.innerHTML = '<option value="">Sin produccion seleccionada</option>';
      output.value = "";
      layerGrid.innerHTML = "";
      previewLayerButtons.innerHTML = "";
      currentLayerMap = {};
      previewImg.removeAttribute("src");
      previewPath.textContent = "Esperando analisis...";
      selectionStatus.textContent = "Selecciona una produccion para habilitar acciones.";
      uploadStatus.textContent = "Cache y temporales limpiados. Vuelve a cargar producciones.";
      iaStatus.textContent = "Selecciona una escena para cargar análisis IA.";
      iaPanel.innerHTML = "";
      sessionStorage.removeItem(SESSION_PRODUCTIONS_KEY);
      sessionStorage.removeItem(SESSION_SCENES_KEY);
      await refreshActionState();
      setUiBusy("idle");
    };
    (async () => {
      try{
        const r = await fetch("/monitoring/import-from-api", { method:"POST" });
        const data = await r.json().catch(() => ({}));
        if(r.ok){
          if(data.api_response && Array.isArray(data.api_response.items)){
            sessionStorage.setItem(SESSION_PRODUCTIONS_KEY, JSON.stringify(data.api_response.items));
          }
        } else {
          await bootstrapFromSessionCache();
        }
      }catch(e){
        await bootstrapFromSessionCache();
      }
      await loadLots();
      await refreshActionState();
    })();
    (async () => {
      try{
        const r = await fetch("/internal/config/view");
        const cfg = await r.json();
        configOutput.value = JSON.stringify(cfg, null, 2);
      }catch(e){
        configOutput.value = "No se pudo leer configuracion";
      }
    })();
  </script>
</body>
</html>
"""
