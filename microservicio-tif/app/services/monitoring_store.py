from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MonitoringStore:
    productions: dict[int, dict[str, Any]] = field(default_factory=dict)
    analyses: dict[int, dict[str, Any]] = field(default_factory=dict)
    scene_catalog: dict[str, dict[str, Any]] = field(default_factory=dict)

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
                    "hectareas": float(production.get("cantidad") or 0),
                    "ndvi_actual": ndvi,
                    "tendencia": trend,
                    "ultimo_analisis": analysis.get("updated_at"),
                    "estado": risk,
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
            if not scene_name:
                continue
            self.scene_catalog[scene_name] = scene
            imported += 1
        return imported

    def get_scene(self, scene_name: str) -> dict[str, Any] | None:
        return self.scene_catalog.get(scene_name)

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
