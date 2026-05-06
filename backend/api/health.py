from fastapi import APIRouter, Depends

from backend.core.dependencies import get_embedder, get_ontology
from backend.schemas.responses import HealthResponse
from backend.services.embedder import TextEmbedder
from backend.services.ontology import Ontology

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(
    embedder: TextEmbedder = Depends(get_embedder),
    ontology: Ontology = Depends(get_ontology),
) -> HealthResponse:
    model_loaded = embedder.model is not None
    ontology_loaded = len(ontology) > 0

    return HealthResponse(
        status="ok",
        model_loaded=model_loaded,
        ontology_loaded=ontology_loaded,
    )
