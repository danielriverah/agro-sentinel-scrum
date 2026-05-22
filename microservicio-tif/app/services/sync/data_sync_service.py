"""
DataSyncService — carga producciones, escenas y cultivos desde la app origen
(Laravel u otro sistema) y los guarda en los stores en memoria.

Flujo:
  1. Al arrancar (lifespan en main.py) → sync_all() automático
  2. El usuario llama POST /monitoring/sync → sync_all() manual
  3. El resto de endpoints usan el store en RAM sin volver a llamar al origen
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from app.services.monitoring_store import MonitoringStore
from app.services.crop_config_store import CropConfigStore

logger = logging.getLogger("agro_sentinel_tif.sync")


# ──────────────────────────────────────────────
# Estado global del último sync (singleton)
# ──────────────────────────────────────────────

@dataclass
class SyncState:
    last_sync_at: str | None = None
    last_sync_ok: bool = False
    last_error: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    syncing: bool = False


_state = SyncState()


def get_sync_state() -> SyncState:
    return _state


# ──────────────────────────────────────────────
# Servicio
# ──────────────────────────────────────────────

class DataSyncService:
    """
    Lee la sección `data_sources` del config de DynamoDB, llama a los tres
    endpoints configurados y puebla los stores en memoria.

    Estructura esperada en DynamoDB (sección data_sources):
        base_url        URL raíz de la app origen
        api_token       Token Bearer (puede estar vacío si el endpoint es público)
        timeout         Segundos de espera por request (default 30)
        sync_on_startup Si true, se ejecuta automáticamente al arrancar
        endpoints:
            producciones  path relativo que devuelve la lista de producciones
            escenas       path relativo que devuelve el catálogo de escenas
            cultivos      path relativo que devuelve la config de cultivos (opcional)
    """

    def __init__(self, monitoring_store: MonitoringStore, crop_config_store: CropConfigStore) -> None:
        self._store = monitoring_store
        self._crops = crop_config_store

    async def sync_all(self, cfg: dict[str, Any]) -> dict[str, Any]:
        """
        Ejecuta el sync completo. Retorna un dict con ok, counts y errors.
        Si otro sync ya está en curso retorna inmediatamente.
        """
        if _state.syncing:
            return {"ok": False, "error": "Sync already in progress", "syncing": True}

        sources: dict[str, Any] = cfg.get("data_sources") or {}
        base_url = str(sources.get("base_url") or "").rstrip("/")
        token = str(sources.get("api_token") or "")
        timeout = int(sources.get("timeout") or 30)
        endpoints: dict[str, Any] = sources.get("endpoints") or {}

        if not base_url:
            msg = "data_sources.base_url no está configurado en DynamoDB"
            logger.warning("SYNC_SKIP: %s", msg)
            return {"ok": False, "error": msg}

        headers: dict[str, str] = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = token if token.startswith("Bearer ") else f"Bearer {token}"

        _state.syncing = True
        counts: dict[str, int] = {}
        errors: list[str] = []

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:

                # ── 1. Producciones ────────────────────────────────
                ep = str(endpoints.get("producciones") or "/api/agro/lotes").lstrip("/")
                try:
                    r = await client.get(f"{base_url}/{ep}")
                    r.raise_for_status()
                    items = self._extract_list(r.json())
                    normalized = self._normalize_productions(items)
                    stats = self._store.upsert_productions(normalized)
                    counts["producciones"] = stats["imported"]
                    logger.info("SYNC producciones=%d monitored=%d", stats["imported"], stats["monitored"])
                except Exception as exc:
                    err = f"producciones: {type(exc).__name__}: {exc}"
                    errors.append(err)
                    logger.error("SYNC_ERROR %s", err)

                # ── 2. Catálogo de escenas ─────────────────────────
                ep = str(endpoints.get("escenas") or "/api/agro/escenas").lstrip("/")
                try:
                    r = await client.get(f"{base_url}/{ep}")
                    r.raise_for_status()
                    items = self._extract_list(r.json())
                    n = self._store.upsert_scene_catalog(items)
                    counts["escenas"] = n
                    logger.info("SYNC escenas=%d", n)
                except Exception as exc:
                    err = f"escenas: {type(exc).__name__}: {exc}"
                    errors.append(err)
                    logger.error("SYNC_ERROR %s", err)

                # ── 3. Fichas técnicas de cultivos (opcional) ──────
                ep_cultivos = endpoints.get("cultivos")
                if ep_cultivos:
                    ep = str(ep_cultivos).lstrip("/")
                    try:
                        r = await client.get(f"{base_url}/{ep}")
                        r.raise_for_status()
                        raw = r.json()
                        # Acepta { crops: {...} } o { data: { crops: {...} } }
                        payload = raw if "crops" in raw else raw.get("data", raw)
                        if isinstance(payload, dict) and "crops" in payload:
                            self._crops.write(payload)
                            counts["cultivos"] = len(payload["crops"])
                            logger.info("SYNC cultivos=%d", counts["cultivos"])
                        else:
                            logger.warning("SYNC cultivos: respuesta sin clave 'crops'")
                    except Exception as exc:
                        err = f"cultivos: {type(exc).__name__}: {exc}"
                        errors.append(err)
                        logger.error("SYNC_ERROR %s", err)

        finally:
            _state.syncing = False

        ok = len(errors) == 0
        _state.last_sync_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _state.last_sync_ok = ok
        _state.last_error = "; ".join(errors) if errors else None
        _state.counts = counts

        return {
            "ok": ok,
            "synced_at": _state.last_sync_at,
            "counts": counts,
            "errors": errors,
        }

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_list(data: Any) -> list[dict]:
        """
        Acepta cualquiera de estos formatos de respuesta:
          [ {...}, {...} ]
          { "data": [...] }
          { "items": [...] }
          { "lotes": [...] }
          { "producciones": [...] }
          { "escenas": [...] }
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("data", "items", "results", "lotes", "escenas", "producciones", "catalogo"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    @staticmethod
    def _normalize_productions(items: list[dict]) -> list[dict]:
        """
        El store espera [ { "production": {...} }, ... ].
        Si la app origen devuelve objetos planos con `produccion_id`, los envuelve.
        """
        normalized = []
        for item in items:
            if isinstance(item.get("production"), dict):
                normalized.append(item)
            elif "produccion_id" in item:
                normalized.append({"production": item})
        return normalized
