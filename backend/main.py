from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import classify, health
from backend.core.config import get_settings
from backend.core.dependencies import get_embedder, get_ontology


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔄 Loading embedder model...")
    embedder = get_embedder()
    print(f"✅ Embedder loaded: {embedder.model_name} (dim={embedder.embedding_dim})")

    print("🔄 Loading ontology...")
    ontology = get_ontology()
    print(f"✅ Ontology loaded: {len(ontology)} nodes, max_depth={ontology.max_depth()}")

    yield

    print("👋 Shutting down...")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(classify.router, prefix=settings.api_v1_prefix)

    try:
        app.mount("/static", StaticFiles(directory="frontend"), name="static")

        @app.get("/")
        def read_root():
            return FileResponse("frontend/index.html")
    except Exception as e:
        print(f"⚠️  Warning: Could not mount frontend: {e}")

    return app


app = create_app()
