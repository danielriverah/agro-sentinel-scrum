from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MonitoringStore:
    productions: dict[int, dict[str, Any]] = field(default_factory=dict)
    analyses: dict[int, dict[str, Any]] = field(default_factory=dict)
    scene_catalog: dict[str, dict[str, Any]] = field(default_factory=dict)
    scenes_cache: dict[int, list[dict[str, Any]]] = field(default_factory=dict)

    def upsert_productions(self, payloads: list[dict[str, Any]]) -> dict[str, int]:
        imported = 0
        monitored = 0
        for payload in payloads:
            production = payload.get("production", {})
            production_id = int(production.get("produccion_id") or 0)
            if production_id <= 0:
                continue
            imported += 1
            self.productions[production_id] = payload
            self.scenes_cache.pop(production_id, None)
            if int(production.get("monitoring") or 0) == 1:
                monitored += 1
        return {"imported": imported, "monitored": monitored}

    def list_monitored(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for production_id, payload in self.productions.items():
            production = payload.get("production", {})
            if int(production.get("monitoring") or 0) != 1:
                continue
            analysis = self.analyses.get(production_id, {})
            ndvi = analysis.get("ndvi")
            trend = analysis.get("trend")
            risk = analysis.get("risk", "pendiente")
            rows.append(
                {
                    "produccion_id": production_id,
                    "folio": production.get("folio"),
                    "articulo": production.get("articulo"),
                    "rancho": production.get("rancho"),
                    "hectareas": self._safe_float(production.get("cantidad")),
                    "ndvi_actual": ndvi,
                    "tendencia": trend,
                    "ultimo_analisis": analysis.get("updated_at"),
                    "estado": risk,
                    "has_analysis": bool(analysis.get("result")),
                    "uploaded_truth_tif": str((analysis.get("result") or {}).get("truth_tif_path") or "").startswith("s3://"),
                    "has_rendered_tif": str((analysis.get("result") or {}).get("render_tif_path") or "").startswith("s3://"),
                }
            )
        rows.sort(key=lambda x: x["produccion_id"], reverse=True)
        return rows

    def get_payload(self, production_id: int) -> dict[str, Any] | None:
        return self.productions.get(production_id)

    def upsert_scene_catalog(self, scenes: list[dict[str, Any]]) -> int:
        imported = 0
        for scene in scenes:
            scene_name = str(scene.get("scene_name") or "").strip()
            production_id = int(scene.get("production_id") or 0)
            if not scene_name:
                continue
            key = self._scene_key(production_id, scene_name)
            self.scene_catalog[key] = scene
            if production_id:
                self.scenes_cache.pop(production_id, None)
            imported += 1
        return imported

    def get_scene(self, scene_name: str, production_id: int | None = None) -> dict[str, Any] | None:
        if production_id is not None:
            key = self._scene_key(production_id, scene_name)
            return self.scene_catalog.get(key)
        # Backward-compat fallback only when production_id is not provided.
        for item in self.scene_catalog.values():
            if str(item.get("scene_name") or "").strip() == scene_name:
                return item
        return None

    def save_analysis(self, production_id: int, result: dict[str, Any]) -> None:
        ndvi = None
        if isinstance(result.get("indices"), dict):
            ndvi = (result["indices"].get("ndvi") or {}).get("mean")
        self.analyses[production_id] = {
            "ndvi": ndvi,
            "trend": None,
            "risk": self._risk_from_ndvi(ndvi),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "result": result,
        }

    def get_analysis_result(self, production_id: int) -> dict[str, Any] | None:
        data = self.analyses.get(production_id)
        if not data:
            return None
        return data.get("result")

    def update_analysis_result(self, production_id: int, result: dict[str, Any]) -> None:
        if production_id not in self.analyses:
            return
        self.analyses[production_id]["result"] = result
        self.analyses[production_id]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _scene_key(production_id: int, scene_name: str) -> str:
        return f"{production_id}::{scene_name.strip()}"

    @staticmethod
    def _risk_from_ndvi(ndvi: float | None) -> str:
        if ndvi is None:
            return "pendiente"
        if ndvi < 0.45:
            return "critico"
        if ndvi < 0.6:
            return "moderado"
        if ndvi < 0.75:
            return "bueno"
        return "optimo"

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0
