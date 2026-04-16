from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from db import get_pool, close_pool
from routers import health, ingest, observe, policy, approval, firewall, keys


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_pool()


settings = get_settings()

app = FastAPI(
    title="Midlantics A2A Backend",
    version="0.1.0",
    lifespan=lifespan,
    # In VPC mode expose full OpenAPI docs; in cloud hide them
    docs_url="/docs" if settings.vpc_mode else None,
    redoc_url="/redoc" if settings.vpc_mode else None,
)

origins = [o.strip() for o in settings.allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(observe.router)
app.include_router(policy.router)
app.include_router(approval.router)
app.include_router(firewall.router)
app.include_router(keys.router)
