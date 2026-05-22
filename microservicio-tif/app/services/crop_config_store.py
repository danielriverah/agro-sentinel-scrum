from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class CropConfigStore:
    def __init__(self, file_path: str = "/tmp/agro-tif/config/crop_technical_sheets.json"):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._write({"version": "1.0", "crops": {}})

    def read(self) -> dict[str, Any]:
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": "1.0", "crops": {}}

    def write(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._write(payload)
        return payload

    def upsert_crop_variety(self, crop: str, variety: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = self.read()
        crops = payload.setdefault("crops", {})
        crop_key = crop.strip().upper()
        variety_key = variety.strip().upper()
        crop_obj = crops.setdefault(crop_key, {"default": {}, "variedades": {}, "etapas": {}, "recomendaciones": {}})
        variedades = crop_obj.setdefault("variedades", {})
        current = variedades.get(variety_key, {})
        current.update(data)
        variedades[variety_key] = current
        self._write(payload)
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
