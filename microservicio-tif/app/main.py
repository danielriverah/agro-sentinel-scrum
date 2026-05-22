from contextlib import asynccontextmanager
from pathlib import Path
import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import analyze, configurations, health, internal, jobs, lots
from app.api.routes.sync import get_sync_service, router as sync_router
from app.services.configuration.config_loader import get_config
from app.services.configuration.config_validator import validate_tif_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("agro_sentinel_tif.startup")

    # 1. Validar config de DynamoDB
    try:
        cfg = get_config()
        missing = validate_tif_config(cfg)
        if missing:
            logger.error("CONFIG_ERROR[VALIDATION]: missing fields=%s", missing)
        else:
            logger.info(
                "CONFIG_OK: version=%s pk=%s sk=%s",
                cfg.get("version"),
                cfg.get("pk", "n/a"),
                cfg.get("sk", "n/a"),
            )
    except Exception as exc:
        logger.exception("CONFIG_ERROR[STARTUP]: %s", str(exc))
        cfg = {}

    # 2. Sync inicial desde la app origen (si data_sources.sync_on_startup = true)
    sources = cfg.get("data_sources") or {}
    if sources.get("sync_on_startup", False):
        logger.info("SYNC[STARTUP] iniciando sync automático...")
        try:
            result = await get_sync_service().sync_all(cfg)
            if result.get("ok"):
                logger.info("SYNC[STARTUP] OK counts=%s", result.get("counts"))
            else:
                logger.warning("SYNC[STARTUP] con errores: %s", result.get("errors"))
        except Exception as exc:
            logger.exception("SYNC[STARTUP] falló: %s", str(exc))
    else:
        logger.info("SYNC[STARTUP] omitido (data_sources.sync_on_startup=false o no configurado)")

    yield


app = FastAPI(
    title="AgroSentinel TIF Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(sync_router)
app.include_router(jobs.router)
app.include_router(lots.router)
app.include_router(internal.router)
app.include_router(configurations.router)

outputs_dir = Path("/tmp/agro-tif/outputs")
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")
