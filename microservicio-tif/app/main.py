from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import analyze, health, internal, jobs, lots


@asynccontextmanager
async def lifespan(app: FastAPI):
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
