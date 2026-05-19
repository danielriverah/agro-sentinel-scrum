from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import analyze, health, internal, jobs, lots
from app.services.configuration.config_loader import get_config
from app.services.configuration.config_validator import validate_tif_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("agro_sentinel_tif.startup")
    try:
        cfg = get_config()
        missing = validate_tif_config(cfg)
        if missing:
            logger.error("CONFIG_ERROR[VALIDATION]: missing fields in DynamoDB item=%s", missing)
        else:
            logger.info(
                "CONFIG_OK: version=%s table=%s pk=%s sk=%s",
                cfg.get("version"),
                "agro_sentinel_config",
                cfg.get("pk", "n/a"),
                cfg.get("sk", "n/a"),
            )
    except Exception as exc:
        logger.exception("CONFIG_ERROR[STARTUP]: %s", str(exc))
    yield


app = FastAPI(
    title="AgroSentinel TIF Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(jobs.router)
app.include_router(lots.router)
app.include_router(internal.router)

outputs_dir = Path("/tmp/agro-tif/outputs")
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
