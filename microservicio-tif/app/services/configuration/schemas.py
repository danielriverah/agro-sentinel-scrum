from pydantic import BaseModel


class SecurityConfig(BaseModel):
    api_secret_key: str
    allowed_origins: list[str] = []


class StorageConfig(BaseModel):
    driver: str
    aws_region: str = "us-east-1"
    s3_bucket: str
    base_path: str
    public_url_ttl_minutes: int = 60


class CopernicusConfig(BaseModel):
    client_id: str
    client_secret: str
    default_collection: str = "sentinel-2-l2a"
    max_cloud_coverage: int = 20


class ProcessingConfig(BaseModel):
    default_indices: list[str]
    resolution_meters: int = 20
    apply_cloud_mask: bool = True
    min_valid_pixels_percentage: float = 80.0
    generate_png: bool = True
    generate_geotiff: bool = True
    generate_pdf: bool = False


class TifServiceConfig(BaseModel):
    security: SecurityConfig
    storage: StorageConfig
    copernicus: CopernicusConfig
    processing: ProcessingConfig
    version: int = 1
