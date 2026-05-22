from app.core.exceptions import ConfigValidationError

_REQUIRED_FIELDS = [
    ("security", "api_secret_key"),
    ("storage", "driver"),
    ("storage", "s3_bucket"),
    ("storage", "base_path"),
    ("copernicus", "client_id"),
    ("copernicus", "client_secret"),
    ("processing", "default_indices"),
    ("processing", "min_valid_pixels_percentage"),
]


def validate_tif_config(cfg: dict) -> list[str]:
    missing = []
    for section, field in _REQUIRED_FIELDS:
        if not cfg.get(section, {}).get(field):
            missing.append(f"{section}.{field}")
    return missing


def assert_valid(cfg: dict) -> None:
    missing = validate_tif_config(cfg)
    if missing:
        raise ConfigValidationError(missing)
