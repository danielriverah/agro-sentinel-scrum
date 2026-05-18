from pydantic import BaseModel


class ImageQuality(BaseModel):
    cloud_percentage: float
    shadow_percentage: float
    valid_pixels_percentage: float
    confidence: str


class IndexStats(BaseModel):
    min: float
    max: float
    mean: float
    std: float
    valid_pixels: int


class S3Paths(BaseModel):
    tif: str
    statistics: str
    png_ndvi: str | None = None


class AnalyzeResponse(BaseModel):
    ok: bool
    job_id: str
    lot_id: int
    analysis_date: str
    image_quality: ImageQuality
    indices: dict[str, IndexStats]
    s3_paths: S3Paths
    unsupported_indices: list[str] = []
    from_cache: bool = False
    processing_seconds: float
