from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    job_id: str
    lot_id: int
    polygon_geojson: dict
    dates: list[str]
    indices: list[str]
    resolution_meters: int = 20
    force_reprocess: bool = False
