class AgroSentinelError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 500):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


class ConfigValidationError(AgroSentinelError):
    def __init__(self, missing_fields: list[str]):
        super().__init__(
            code="CONFIG_VALIDATION_ERROR",
            message=f"Missing required config fields: {missing_fields}",
            http_status=503,
        )
        self.missing_fields = missing_fields


class CopernicusAuthError(AgroSentinelError):
    def __init__(self):
        super().__init__(
            code="COPERNICUS_AUTH_ERROR",
            message="Failed to authenticate with Copernicus CDSE",
            http_status=503,
        )


class NoSceneAvailableError(AgroSentinelError):
    def __init__(self, date_range: list[str]):
        super().__init__(
            code="NO_SCENE_AVAILABLE",
            message=f"No Sentinel-2 scene available for date range {date_range}",
            http_status=404,
        )
        self.date_range = date_range


class StoragePressureError(AgroSentinelError):
    def __init__(self):
        super().__init__(
            code="STORAGE_PRESSURE",
            message="/tmp/ exceeded 1.5 GB limit — download rejected",
            http_status=503,
        )


class InsufficientValidPixelsError(AgroSentinelError):
    def __init__(self, pct: float):
        super().__init__(
            code="INSUFFICIENT_VALID_PIXELS",
            message=f"Only {pct:.1f}% valid pixels after cloud masking",
            http_status=422,
        )


class InvalidPolygonError(AgroSentinelError):
    def __init__(self):
        super().__init__(
            code="INVALID_POLYGON",
            message="The provided GeoJSON polygon is invalid",
            http_status=400,
        )
