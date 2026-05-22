"""
Endpoints de sincronización de datos con la app origen.

  POST /monitoring/sync          Re-fetch completo desde la app origen
  GET  /monitoring/sync/status   Estado del último sync (cuándo, cuántos, error)
"""
from __future__ import annotations

from fastapi import APIRouter

from app.services.configuration.config_loader import get_config
from app.services.stores import crop_config_store, monitoring_store
from app.services.sync.data_sync_service import DataSyncService, get_sync_state

router = APIRouter(tags=["sync"])

_sync_service = DataSyncService(
    monitoring_store=monitoring_store,
    crop_config_store=crop_config_store,
)


@router.post("/monitoring/sync")
async def sync_data():
    """
    Dispara un re-fetch completo de producciones, escenas y cultivos
    desde la app origen configurada en DynamoDB (data_sources).
    Usar cuando el usuario quiera refrescar los datos manualmente.
    """
    cfg = get_config()
    return await _sync_service.sync_all(cfg)


@router.get("/monitoring/sync/status")
async def sync_status():
    """
    Estado del último sync: cuándo fue, cuántos registros se cargaron,
    si hay algún error pendiente, y si hay un sync en curso ahora mismo.
    """
    state = get_sync_state()
    return {
        "ok": True,
        "last_sync_at": state.last_sync_at,
        "last_sync_ok": state.last_sync_ok,
        "last_error": state.last_error,
        "counts": state.counts,
        "syncing": state.syncing,
        "store": {
            "producciones": len(monitoring_store.productions),
            "escenas_en_catalogo": len(monitoring_store.scene_catalog),
            "analisis_guardados": len(monitoring_store.analyses),
        },
    }


def get_sync_service() -> DataSyncService:
    """Expuesto para que main.py lo use en el lifespan sin reimportar stores."""
    return _sync_service
