import time
from typing import Any
import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core import config as env
from app.core.exceptions import AgroSentinelError


_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
logger = logging.getLogger("agro_sentinel_tif.config")


def get_config() -> dict[str, Any]:
    global _cache, _cache_ts
    _validate_env_or_raise()
    now = time.time()
    if _cache and (now - _cache_ts) < env.CONFIG_CACHE_TTL_SECONDS:
        return _cache

    kwargs: dict[str, Any] = {"region_name": env.AWS_REGION}
    if not env.DYNAMODB_USE_AWS and env.DYNAMODB_ENDPOINT_URL:
        kwargs["endpoint_url"] = env.DYNAMODB_ENDPOINT_URL
    if env.AWS_ACCESS_KEY_ID_CUSTOM and env.AWS_SECRET_ACCESS_KEY_CUSTOM:
        kwargs["aws_access_key_id"] = env.AWS_ACCESS_KEY_ID_CUSTOM
        kwargs["aws_secret_access_key"] = env.AWS_SECRET_ACCESS_KEY_CUSTOM
        if env.AWS_SESSION_TOKEN_CUSTOM:
            kwargs["aws_session_token"] = env.AWS_SESSION_TOKEN_CUSTOM

    try:
        client = boto3.client("dynamodb", **kwargs)
        response = client.get_item(
            TableName=env.CONFIG_TABLE_NAME,
            Key={
                "pk": {"S": env.CONFIG_PARTITION_KEY},
                "sk": {"S": env.CONFIG_SORT_KEY},
            },
        )
    except (ClientError, BotoCoreError) as exc:
        logger.exception(
            "CONFIG_ERROR[DYNAMODB]: table=%s pk=%s sk=%s region=%s endpoint=%s error=%s",
            env.CONFIG_TABLE_NAME,
            env.CONFIG_PARTITION_KEY,
            env.CONFIG_SORT_KEY,
            env.AWS_REGION,
            env.DYNAMODB_ENDPOINT_URL,
            str(exc),
        )
        raise AgroSentinelError(
            code="DYNAMODB_CONFIG_NOT_FOUND",
            message=(
                "No se pudo leer configuración de DynamoDB. "
                f"table={env.CONFIG_TABLE_NAME} pk={env.CONFIG_PARTITION_KEY} sk={env.CONFIG_SORT_KEY}"
            ),
            http_status=503,
        ) from exc

    item = response.get("Item", {})
    if not item:
        logger.error(
            "CONFIG_ERROR[EMPTY_ITEM]: no item found in DynamoDB for table=%s pk=%s sk=%s",
            env.CONFIG_TABLE_NAME,
            env.CONFIG_PARTITION_KEY,
            env.CONFIG_SORT_KEY,
        )
        raise AgroSentinelError(
            code="DYNAMODB_CONFIG_NOT_FOUND",
            message=(
                "DynamoDB respondió sin Item para la configuración solicitada. "
                f"table={env.CONFIG_TABLE_NAME} pk={env.CONFIG_PARTITION_KEY} sk={env.CONFIG_SORT_KEY}"
            ),
            http_status=503,
        )
    parsed = _deserialize(item)
    _cache = parsed
    _cache_ts = now
    return parsed


def invalidate_cache() -> None:
    global _cache, _cache_ts
    _cache = {}
    _cache_ts = 0.0


def _deserialize(item: dict) -> dict:
    from boto3.dynamodb.types import TypeDeserializer
    d = TypeDeserializer()
    return {k: d.deserialize(v) for k, v in item.items()}


def _validate_env_or_raise() -> None:
    required = {
        "AWS_REGION": env.AWS_REGION,
        "CONFIG_TABLE_NAME": env.CONFIG_TABLE_NAME,
        "CONFIG_PARTITION_KEY": env.CONFIG_PARTITION_KEY,
        "CONFIG_SORT_KEY": env.CONFIG_SORT_KEY,
    }
    missing = [k for k, v in required.items() if v is None or str(v).strip() == ""]
    if missing:
        logger.error("CONFIG_ERROR[ENV]: missing env vars=%s", missing)
        raise AgroSentinelError(
            code="ENV_CONFIG_MISSING",
            message=f"Faltan variables de entorno requeridas: {missing}",
            http_status=503,
        )
