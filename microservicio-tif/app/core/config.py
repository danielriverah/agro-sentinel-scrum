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
