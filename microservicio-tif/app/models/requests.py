from pydantic import BaseModel, Field, field_validator


class AnalyzeRequest(BaseModel):
    job_id: str
    lot_id: int
    polygon_geojson: dict
    dates: list[str]
    indices: list[str]
    resolution_meters: int = 20
    force_reprocess: bool = False


class SceneTileRequest(BaseModel):
    scene_name: str = Field(min_length=5)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    tile_size: int = Field(default=256, ge=32, le=2048)
    bands: list[str] = Field(default_factory=lambda: ["B04", "B03", "B02", "B08"])

    @field_validator("bands")
    @classmethod
    def normalize_bands(cls, bands: list[str]) -> list[str]:
        normalized = [band.upper() for band in bands]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Bands must be unique")
        return normalized


class SceneProductionInput(SceneTileRequest):
    fecha: str
    band_urls: dict[str, str] = Field(default_factory=dict)


class ProductionContext(BaseModel):
    monitoring: int | None = None
    plantaciones_json: str | None = None
    produccion_id: int | None = None
    folio: str | None = None
    articulo: str | None = None
    fecha: str | None = None
    area_asig: str | None = None
    poligono_asig: str | None = None
    area_zona: str | None = None
    poligono_zona: str | None = None
    fecha_plantacion: str | None = None
    fecha_cierre_prevista: str | None = None
    fecha_cierre: str | None = None
    year: int | None = None
    semana: int | None = None
    monitoring_s3_key: str | None = None
    monitoring_s3_bucket: str | None = None
    variedades: str | None = None


class ProductionSceneRequest(BaseModel):
    escene: SceneProductionInput | None = None
    production: ProductionContext
