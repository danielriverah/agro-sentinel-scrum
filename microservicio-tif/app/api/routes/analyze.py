from __future__ import annotations

from pathlib import Path
from typing import Any

import boto3
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.core.config import AWS_REGION, MONITORING_S3_BUCKET, MONITORING_S3_PREFIX
from app.models.requests import ProductionSceneRequest, SceneTileRequest
from app.services.copernicus.scene_assets import SceneAssetsService
from app.services.monitoring_store import MonitoringStore
from app.services.processing.scene_tile_builder import SceneTileBuilder

router = APIRouter(tags=["analyze"])

scene_assets_service = SceneAssetsService()
scene_tile_builder = SceneTileBuilder()
monitoring_store = MonitoringStore()
s3_client = boto3.client("s3", region_name=AWS_REGION)

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
    return {"ok": True, "items": monitoring_store.list_monitored()}


@router.post("/monitoring/analyze/{production_id}")
async def analyze_monitored_lot(production_id: int):
    payload = monitoring_store.get_payload(production_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Production not found")
    typed_payload = ProductionSceneRequest(**payload)
    result = await _run_production_analysis(typed_payload)
    serialized = _serialize_result(result, typed_payload)
    monitoring_store.save_analysis(production_id, serialized)
    return serialized


@router.get("/", response_class=HTMLResponse)
@router.get("/scene/tile", response_class=HTMLResponse)
async def dashboard_view() -> str:
    return DASHBOARD_HTML


async def _run_production_analysis(payload: ProductionSceneRequest) -> dict[str, Any]:
    scene = payload.escene
    try:
        latitude = scene.latitude
        longitude = scene.longitude
        polygon_source = payload.production.poligono_asig or payload.production.poligono_zona
        if polygon_source:
            latitude, longitude = _polygon_center(polygon_source)

        catalog_scene = monitoring_store.get_scene(scene.scene_name)
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
        )
        result["center_used"] = {"latitude": latitude, "longitude": longitude}
        result["manual_mode"] = True
        result["source_mode"] = "generated_from_band_urls"
        result["truth_tif_path"] = result["multiband_tif"]
        result["render_tif_path"] = result["multiband_tif"]
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _serialize_result(result: dict[str, Any], payload: ProductionSceneRequest | None = None) -> dict[str, Any]:
    thematic_pngs = result.get("thematic_pngs", [])
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
    }
    if payload:
        output["scene_date"] = payload.escene.fecha
        output["produccion_id"] = payload.production.produccion_id
        output["folio"] = payload.production.folio
        output["center_used"] = result.get("center_used")
    return output


def _to_public_url(path: str) -> str:
    rel = Path(path).relative_to("/tmp/agro-tif/outputs")
    return f"/outputs/{rel.as_posix()}"


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
    import json
    try:
        data = json.loads(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in S3 monitoring file: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="S3 monitoring file must be a JSON object")
    return data


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
    textarea{width:100%;min-height:220px;background:#0f151d;color:#cfe6d4;border:1px solid var(--border);border-radius:10px;padding:10px}
    .tiny{font-size:12px;color:var(--muted)} .preview img{width:100%;border-radius:8px;border:1px solid var(--border)}
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
    </aside>
    <main class="main">
      <div class="head">
        <div>
          <h2 style="margin:0">Gestion de lotes monitoreados</h2>
          <div class="tiny">Solo producciones con monitoring = 1</div>
        </div>
        <button class="btn" id="refreshBtn">Actualizar</button>
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
          <h3 style="margin-top:0">Importar producciones</h3>
          <p class="tiny">Pega JSON: {"items":[{escene:{...},production:{...}}]}</p>
          <textarea id="jsonInput"></textarea>
          <button class="btn" id="importBtn" style="margin-top:10px">Cargar producciones</button>
          <p class="tiny">Catalogo de escenas: {"items":[{"scene_name":"...","tif_render_path":"...","tif_truth_path":"...","preview_pngs":["..."]}]}</p>
          <textarea id="catalogInput"></textarea>
          <button class="btn" id="catalogBtn" style="margin-top:10px">Cargar catalogo escenas</button>
          <p class="tiny" id="importStatus"></p>
        </section>
      </div>
      <div class="layout" style="margin-top:16px">
        <section class="card preview">
          <h3 style="margin-top:0">Preview True Color</h3>
          <img id="previewImg" alt="preview" />
          <div class="tiny" id="previewPath">Esperando analisis...</div>
        </section>
        <section class="card">
          <h3 style="margin-top:0">Respuesta analisis</h3>
          <textarea id="analysisOutput" readonly></textarea>
        </section>
      </div>
      <div class="layout" style="margin-top:16px">
        <section class="card">
          <h3 style="margin-top:0">Capas espectrales</h3>
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
    const importStatus = document.getElementById("importStatus");
    const output = document.getElementById("analysisOutput");
    const previewImg = document.getElementById("previewImg");
    const previewPath = document.getElementById("previewPath");
    const configOutput = document.getElementById("configOutput");
    const layerGrid = document.getElementById("layerGrid");
    const decisionCards = document.getElementById("decisionCards");

    async function loadLots(){
      const r = await fetch("/monitoring/lots");
      const data = await r.json();
      const rows = data.items || [];
      if(!rows.length){
        rowsEl.innerHTML = '<tr><td colspan="7" class="tiny">No hay producciones monitoreadas.</td></tr>';
        return;
      }
      rowsEl.innerHTML = rows.map(x => `
        <tr>
          <td>${x.folio || "-"}</td>
          <td>${x.articulo || "-"}</td>
          <td>${x.hectareas || 0}</td>
          <td>${x.ndvi_actual ?? "-"}</td>
          <td>${x.ultimo_analisis || "-"}</td>
          <td><span class="tag ${x.estado || "pendiente"}">${x.estado || "pendiente"}</span></td>
          <td><button class="btn" style="padding:6px 10px" onclick="analyzeLot(${x.produccion_id})">Analizar</button></td>
        </tr>
      `).join("");
    }

    async function analyzeLot(productionId){
      output.value = "Procesando produccion " + productionId + "...";
      const r = await fetch(`/monitoring/analyze/${productionId}`, {method:"POST"});
      const data = await r.json();
      output.value = JSON.stringify(data, null, 2);
      const p = (data.preview_pngs || [])[0];
      if(p){
        previewImg.src = p.url + "?t=" + Date.now();
        previewPath.textContent = p.url;
      }
      layerGrid.innerHTML = "";
      (data.thematic_pngs || []).forEach(item => {
        const card = document.createElement("div");
        card.className = "card";
        card.innerHTML = `<img src="${item.url}?t=${Date.now()}" alt="layer"/><div class="meta">${item.url}</div>`;
        layerGrid.appendChild(card);
      });
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
    }

    document.getElementById("importBtn").onclick = async () => {
      try{
        const parsed = JSON.parse(document.getElementById("jsonInput").value);
        const r = await fetch("/monitoring/import", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(parsed),
        });
        const data = await r.json();
        importStatus.textContent = `Importadas: ${data.imported || 0} | Monitoreadas: ${data.monitored || 0}`;
        await loadLots();
      }catch(e){
        importStatus.textContent = "JSON invalido";
      }
    };

    document.getElementById("catalogBtn").onclick = async () => {
      try{
        const parsed = JSON.parse(document.getElementById("catalogInput").value);
        const r = await fetch("/catalog/scenes/import", {
          method:"POST",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify(parsed),
        });
        const data = await r.json();
        importStatus.textContent = `Catalogo importado: ${data.imported || 0}`;
      }catch(e){
        importStatus.textContent = "JSON catalogo invalido";
      }
    };

    document.getElementById("refreshBtn").onclick = loadLots;
    loadLots();
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
