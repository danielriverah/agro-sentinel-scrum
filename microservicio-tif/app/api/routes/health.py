from fastapi import APIRouter

from app.core.exceptions import AgroSentinelError
from app.services.configuration.config_loader import get_config
from app.services.configuration.config_validator import validate_tif_config

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    try:
        cfg = get_config()
        missing = validate_tif_config(cfg)
        if missing:
            return {
                "status": "degraded",
                "service": "agro-sentinel-tif",
                "version": "0.1.0",
                "config": {
                    "loaded": True,
                    "valid": False,
                    "missing": missing,
                    "config_version": cfg.get("version"),
                },
            }
        return {
            "status": "ok",
            "service": "agro-sentinel-tif",
            "version": "0.1.0",
            "config": {
                "loaded": True,
                "valid": True,
                "missing": [],
                "config_version": cfg.get("version"),
            },
        }
    except AgroSentinelError as exc:
        return {
            "status": "degraded",
            "service": "agro-sentinel-tif",
            "version": "0.1.0",
            "config": {"loaded": False, "valid": False},
            "error": {"code": exc.code, "message": exc.message},
        }
    except Exception as exc:
        return {
            "status": "degraded",
            "service": "agro-sentinel-tif",
            "version": "0.1.0",
            "config": {"loaded": False, "valid": False},
            "error": {"code": "STARTUP_RUNTIME_ERROR", "message": str(exc)},
        }
