import os

from dotenv import load_dotenv

load_dotenv()

APP_ENV: str = os.getenv("APP_ENV", "local")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
CONFIG_TABLE_NAME: str = os.getenv("CONFIG_TABLE_NAME", "agro_sentinel_config")
CONFIG_PARTITION_KEY: str = os.getenv("CONFIG_PARTITION_KEY", "local")
CONFIG_SORT_KEY: str = os.getenv("CONFIG_SORT_KEY", "active")
CONFIG_CACHE_TTL_SECONDS: int = int(os.getenv("CONFIG_CACHE_TTL_SECONDS", "60"))
CONFIG_FAIL_FAST: bool = os.getenv("CONFIG_FAIL_FAST", "true").lower() == "true"
DYNAMODB_ENDPOINT_URL: str | None = os.getenv("DYNAMODB_ENDPOINT_URL")
IA_SERVICE_URL: str = os.getenv("IA_SERVICE_URL", "http://agro-ia:8002")
MONITORING_S3_BUCKET: str | None = os.getenv("MONITORING_S3_BUCKET")
MONITORING_S3_PREFIX: str = os.getenv("MONITORING_S3_PREFIX", "")
DYNAMODB_USE_AWS: bool = os.getenv("DYNAMODB_USE_AWS", "false").lower() == "true"
AWS_ACCESS_KEY_ID_CUSTOM: str | None = os.getenv("AWS_ACCESS_KEY_ID_CUSTOM")
AWS_SECRET_ACCESS_KEY_CUSTOM: str | None = os.getenv("AWS_SECRET_ACCESS_KEY_CUSTOM")
AWS_SESSION_TOKEN_CUSTOM: str | None = os.getenv("AWS_SESSION_TOKEN_CUSTOM")
PRODUCTIONS_API_URL: str | None = os.getenv("PRODUCTIONS_API_URL")
PRODUCTIONS_API_TOKEN: str | None = os.getenv("PRODUCTIONS_API_TOKEN")
