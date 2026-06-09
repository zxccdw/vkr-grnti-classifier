from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.api import classify, health, nodes
from backend.core.auth import BasicAuthMiddleware
from backend.core.config import get_settings
from backend.core.dependencies import get_classifier, get_embedder, get_llm_providers, get_ontology
from backend.infrastructure.s3_store import S3Store

_EMBEDDINGS_TMP = "/tmp/embeddings_cache.pkl.gz"


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("loading embedder...")
    embedder = get_embedder()
    print(f"embedder configured: {embedder.model_name}")

    print("loading ontology...")
    ontology = get_ontology()
    print(f"ontology ready: {len(ontology)} nodes, max_depth={ontology.max_depth()}")

    providers = get_llm_providers()
    names = [p.name for p in providers] or ["none"]
    print(f"llm providers: {', '.join(names)}")

    settings = get_settings()
    if settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key:
        print("loading classifier cache from S3...")
        try:
            s3 = S3Store(
                bucket=settings.s3_bucket,
                key=settings.s3_embeddings_key,
                endpoint_url=settings.s3_endpoint_url,
                access_key_id=settings.s3_access_key_id,
                secret_access_key=settings.s3_secret_access_key,
            )
            from pathlib import Path

            ok = s3.download_to(Path(_EMBEDDINGS_TMP))
            if ok:
                n = get_classifier().load_cache(Path(_EMBEDDINGS_TMP))
                print(f"classifier cache loaded: {n} entries")
            else:
                print("embeddings cache not found in S3, will compute on first request")
        except Exception as e:
            print(f"classifier cache load failed: {e}")
    else:
        print("S3 not configured, classifier cache skipped")

    yield

    print("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(BasicAuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(classify.router, prefix=settings.api_v1_prefix)
    app.include_router(nodes.router, prefix=settings.api_v1_prefix)

    try:
        app.mount("/static", StaticFiles(directory="frontend"), name="static")

        @app.get("/")
        def read_root():
            return FileResponse("frontend/index.html")

        @app.get("/browse")
        def read_browse():
            return FileResponse("frontend/browse.html")

        @app.get("/login")
        def read_login():
            return FileResponse("frontend/login.html")
    except Exception as e:
        print(f"could not mount frontend: {e}")

    return app


app = create_app()
