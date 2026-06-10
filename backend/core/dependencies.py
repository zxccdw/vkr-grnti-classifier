import logging
import time
from functools import lru_cache

from backend.application.add_node import AddNode
from backend.application.attach_edge import AttachEdge
from backend.application.backfill_descriptions import BackfillDescriptions
from backend.application.create_node import CreateNode
from backend.application.merge_duplicates import MergeDuplicatesByLabel
from backend.core.config import get_settings
from backend.infrastructure.json_ontology import JsonOntologyRepository
from backend.infrastructure.llm.gigachat_provider import GigaChatProvider
from backend.infrastructure.llm.mock_provider import MockProvider
from backend.infrastructure.llm.openai_compatible import OpenAICompatibleProvider
from backend.infrastructure.openai_embedder import OpenAIEmbedder
from backend.infrastructure.s3_store import S3Store
from backend.services.cascade import CascadeClassifier
from backend.services.embedder import TextEmbedder
from backend.services.ontology import Ontology

logger = logging.getLogger(__name__)

_repo: JsonOntologyRepository | None = None
_repo_etag: str | None = None
_repo_s3: S3Store | None = None
_repo_etag_checked_at: float = 0.0
_ETAG_CHECK_INTERVAL = 5.0  # seconds


def _notify_s3_written(new_etag: str | None) -> None:
    """Call after writing to S3 so the cache stays valid without a reload."""
    global _repo_etag, _repo_etag_checked_at
    _repo_etag = new_etag
    _repo_etag_checked_at = time.monotonic()


def _make_s3_store() -> S3Store | None:
    settings = get_settings()
    if settings.s3_bucket and settings.s3_access_key_id and settings.s3_secret_access_key:
        return S3Store(
            bucket=settings.s3_bucket,
            key=settings.s3_key,
            endpoint_url=settings.s3_endpoint_url,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
        )
    return None


def get_ontology_repository() -> JsonOntologyRepository:
    global _repo, _repo_etag, _repo_s3, _repo_etag_checked_at
    settings = get_settings()

    if _repo_s3 is None:
        _repo_s3 = _make_s3_store()

    if _repo_s3 is not None:
        now = time.monotonic()
        if _repo is None or (now - _repo_etag_checked_at) > _ETAG_CHECK_INTERVAL:
            current_etag = _repo_s3.get_etag()
            _repo_etag_checked_at = now
            if _repo is None:
                _repo = JsonOntologyRepository(
                    path=settings.ontology_path,
                    snapshots_dir=settings.ontology_snapshots_dir,
                    s3_store=_repo_s3,
                    on_s3_write=_notify_s3_written,
                )
                _repo_etag = current_etag
            elif current_etag != _repo_etag:
                _repo_s3.download_to(settings.ontology_path)
                _repo.reload()
                _repo_etag = current_etag
        return _repo

    if _repo is None:
        _repo = JsonOntologyRepository(
            path=settings.ontology_path,
            snapshots_dir=settings.ontology_snapshots_dir,
            s3_store=None,
        )
    return _repo


def get_ontology() -> Ontology:
    return get_ontology_repository().ontology


@lru_cache
def get_embedder():
    settings = get_settings()
    if settings.openai_embeddings_base_url and settings.openai_embeddings_token:
        return OpenAIEmbedder(
            base_url=settings.openai_embeddings_base_url,
            token=settings.openai_embeddings_token,
            model=settings.openai_embeddings_model,
            normalize=settings.embeddings_normalize,
            timeout=settings.embeddings_timeout,
            verify_ssl=settings.openai_embeddings_verify_ssl,
        )
    return TextEmbedder(
        endpoint=settings.embeddings_url,
        normalize=settings.embeddings_normalize,
        timeout=settings.embeddings_timeout,
    )


@lru_cache
def get_classifier() -> CascadeClassifier:
    return CascadeClassifier(
        embedder=get_embedder(),
        ontology=get_ontology(),
    )


@lru_cache
def get_llm_providers() -> list:
    settings = get_settings()
    providers: list = []
    if settings.gigachat_credentials:
        giga = GigaChatProvider(
            credentials=settings.gigachat_credentials,
            model=settings.gigachat_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout,
            verify_ssl=settings.gigachat_verify_ssl,
        )
        if giga.is_available():
            providers.append(giga)
        else:
            logger.warning("GigaChat unavailable: token fetch failed, provider skipped")
    elif settings.gigachat_base_url and settings.gigachat_token:
        providers.append(
            OpenAICompatibleProvider(
                name="gigachat",
                base_url=settings.gigachat_base_url,
                token=settings.gigachat_token,
                model=settings.gigachat_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout,
                verify_ssl=settings.gigachat_verify_ssl,
            )
        )
    if settings.yagpt_base_url and settings.yagpt_token:
        providers.append(
            OpenAICompatibleProvider(
                name="yagpt",
                base_url=settings.yagpt_base_url,
                token=settings.yagpt_token,
                model=settings.yagpt_model,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                timeout=settings.llm_timeout,
            )
        )
    if settings.mock_llm:
        providers.append(MockProvider(name="mock"))
    return providers


def get_create_node_use_case() -> CreateNode:
    return CreateNode(ontology=get_ontology_repository())


def get_attach_edge_use_case() -> AttachEdge:
    return AttachEdge(
        ontology=get_ontology_repository(),
        providers=list(get_llm_providers()),
    )


def get_add_node_use_case() -> AddNode:
    return AddNode(
        ontology=get_ontology_repository(),
        providers=list(get_llm_providers()),
    )


def get_backfill_use_case() -> BackfillDescriptions:
    return BackfillDescriptions(
        ontology=get_ontology_repository(),
        providers=list(get_llm_providers()),
    )


def get_merge_duplicates_use_case() -> MergeDuplicatesByLabel:
    return MergeDuplicatesByLabel(ontology=get_ontology_repository())
