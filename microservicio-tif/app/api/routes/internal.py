from fastapi import APIRouter

from app.core import config
from app.services.configuration.config_loader import get_config, invalidate_cache
from app.services.configuration.config_validator import validate_tif_config

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/config/validate")
async def config_validate():
    cfg = get_config()
    missing = validate_tif_config(cfg)
    return {
        "ok": len(missing) == 0,
        "error_code": "CONFIG_VALIDATION_ERROR" if missing else None,
        "missing": missing,
        "config_version": cfg.get("version"),
    }


@router.post("/config/refresh")
async def config_refresh():
    invalidate_cache()
    cfg = get_config()
    missing = validate_tif_config(cfg)
    return {
        "ok": len(missing) == 0,
        "error_code": "CONFIG_VALIDATION_ERROR" if missing else None,
        "missing": missing,
        "config_version": cfg.get("version"),
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
        "ia_service_url": config.IA_SERVICE_URL,
        "monitoring_s3_bucket": config.MONITORING_S3_BUCKET,
        "monitoring_s3_prefix": config.MONITORING_S3_PREFIX,
    }
