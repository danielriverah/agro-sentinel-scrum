from fastapi import APIRouter

from app.core import config
from app.core.exceptions import AgroSentinelError
from app.services.configuration.config_loader import get_config, invalidate_cache
from app.services.configuration.config_validator import validate_tif_config

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/config/validate")
async def config_validate():
    try:
        cfg = get_config()
        missing = validate_tif_config(cfg)
        return {
            "ok": len(missing) == 0,
            "error_code": "CONFIG_VALIDATION_ERROR" if missing else None,
            "message": "Config loaded successfully" if not missing else "Missing required config fields",
            "missing": missing,
            "config_version": cfg.get("version"),
        }
    except AgroSentinelError as exc:
        return {
            "ok": False,
            "error_code": exc.code,
            "message": exc.message,
            "missing": [],
            "config_version": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "INTERNAL_CONFIG_VALIDATE_ERROR",
            "message": str(exc),
            "missing": [],
            "config_version": None,
        }


@router.post("/config/refresh")
async def config_refresh():
    try:
        invalidate_cache()
        cfg = get_config()
        missing = validate_tif_config(cfg)
        return {
            "ok": len(missing) == 0,
            "error_code": "CONFIG_VALIDATION_ERROR" if missing else None,
            "message": "Config refreshed successfully" if not missing else "Missing required config fields",
            "missing": missing,
            "config_version": cfg.get("version"),
        }
    except AgroSentinelError as exc:
        return {
            "ok": False,
            "error_code": exc.code,
            "message": exc.message,
            "missing": [],
            "config_version": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "INTERNAL_CONFIG_REFRESH_ERROR",
            "message": str(exc),
            "missing": [],
            "config_version": None,
        }


@router.get("/config/view")
async def config_view():
    return {
        "app_env": config.APP_ENV,
        "aws_region": config.AWS_REGION,
        "config_table_name": config.CONFIG_TABLE_NAME,
        "config_partition_key": config.CONFIG_PARTITION_KEY,
        "config_sort_key": config.CONFIG_SORT_KEY,
        "config_cache_ttl_seconds": config.CONFIG_CACHE_TTL_SECONDS,
        "config_fail_fast": config.CONFIG_FAIL_FAST,
        "dynamodb_endpoint_url": config.DYNAMODB_ENDPOINT_URL,
        "dynamodb_use_aws": config.DYNAMODB_USE_AWS,
        "aws_access_key_configured": bool(config.AWS_ACCESS_KEY_ID_CUSTOM and config.AWS_SECRET_ACCESS_KEY_CUSTOM),
        "ia_service_url": config.IA_SERVICE_URL,
        "monitoring_s3_bucket": config.MONITORING_S3_BUCKET,
        "monitoring_s3_prefix": config.MONITORING_S3_PREFIX,
    }
