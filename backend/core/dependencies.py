from functools import lru_cache

from backend.core.config import get_settings
from backend.services.cascade import CascadeClassifier
from backend.services.embedder import TextEmbedder
from backend.services.ontology import Ontology


@lru_cache
def get_ontology() -> Ontology:
    settings = get_settings()
    return Ontology.from_json(settings.ontology_path)


@lru_cache
def get_embedder() -> TextEmbedder:
    settings = get_settings()
    return TextEmbedder(
        endpoint=settings.embeddings_url,
        normalize=settings.embeddings_normalize,
        timeout=settings.embeddings_timeout,
    )


def get_classifier() -> CascadeClassifier:
    return CascadeClassifier(
        embedder=get_embedder(),
        ontology=get_ontology(),
    )
