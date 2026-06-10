from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.classify import router as classify_router
from backend.api.health import router as health_router
from backend.core.dependencies import get_classifier, get_embedder, get_ontology
from backend.services.cascade import CascadeClassifier
from backend.services.ontology import Node, Ontology

PRED = "http://example.org/competencies#содержит"
ROOT_ID = "http://example.org/grnti_root"
L1_ID = "http://example.org/competencies#GRNTI_34"
L2_ID = "http://example.org/competencies#GRNTI_34_15"
L3_ID = "http://example.org/competencies#GRNTI_34_15_23"
L4_ID = "http://example.org/competencies#GRNTI_34_15_23_01"


@pytest.fixture
def ontology() -> Ontology:
    return Ontology.from_payload(
        {
            "nodes": [
                {"id": ROOT_ID, "label": "ГРНТИ", "code": None},
                {"id": L1_ID, "label": "Биология", "code": "34"},
                {"id": L2_ID, "label": "Генетика", "code": "34.15"},
                {"id": L3_ID, "label": "Геномика", "code": "34.15.23"},
                {"id": L4_ID, "label": "Полногеномный секвенсинг", "code": "34.15.23.01"},
            ],
            "links": [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_ID, "predicate": PRED},
                {"source": L2_ID, "target": L3_ID, "predicate": PRED},
                {"source": L3_ID, "target": L4_ID, "predicate": PRED},
            ],
        }
    )


class FakeEmbedder:
    model = object()
    model_name = "fake"
    embedding_dim = 4

    def encode_single(self, _: str):
        import numpy as np

        v = np.ones(4, dtype="float32")
        return v / np.linalg.norm(v)

    def encode(self, texts, batch_size: int = 32, normalize: bool | None = None):
        import numpy as np

        if isinstance(texts, str):
            texts = [texts]
        v = np.ones((len(texts), 4), dtype="float32")
        return v / np.linalg.norm(v, axis=1, keepdims=True)


class FakeClassifier:
    def __init__(self, ontology: Ontology) -> None:
        self._ontology = ontology

    def classify_l1(self, text: str, top_k: int = 5):
        return [(self._ontology.node(L1_ID), 0.9)]

    def classify_l2(self, text: str, l1_code: str, top_k: int = 5):
        return [(self._ontology.node(L2_ID), 0.8)]

    def classify_l3(self, text: str, l2_code: str, top_k: int = 5):
        return [(self._ontology.node(L3_ID), 0.7)]

    def classify_full(self, text: str, top_k: int = 10, beam_width: int = 5):
        return [
            (
                [
                    self._ontology.node(L1_ID),
                    self._ontology.node(L2_ID),
                    self._ontology.node(L3_ID),
                ],
                0.75,
            )
        ]


@pytest.fixture
def client(ontology: Ontology) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(health_router)
    app.include_router(classify_router, prefix="/api/v1")
    app.dependency_overrides[get_ontology] = lambda: ontology
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_classifier] = lambda: FakeClassifier(ontology)
    with TestClient(app) as c:
        yield c


def test_health_reports_loaded(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["ontology_loaded"] is True


def test_classify_l1_returns_predictions(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classify/l1",
        json={"text": "что-то про биологию", "top_k": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["predictions"][0]["code"] == "34"


def test_classify_l2_requires_parent_code(client: TestClient) -> None:
    response = client.post("/api/v1/classify/l2", json={"text": "x", "top_k": 5})
    assert response.status_code == 400


def test_classify_l2_returns_predictions(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classify/l2",
        json={"text": "x", "parent_code": "34", "top_k": 5},
    )
    assert response.status_code == 200
    assert response.json()["predictions"][0]["code"] == "34.15"


def test_classify_full_returns_path(client: TestClient) -> None:
    response = client.post(
        "/api/v1/classify/full",
        json={"text": "x", "top_k": 5},
    )
    assert response.status_code == 200
    pred = response.json()["predictions"][0]
    assert pred["path"] == ["34", "34.15", "34.15.23"]
    assert "Биология" in pred["full_path_label"]


def test_real_cascade_with_fake_embedder_returns_top1(ontology: Ontology) -> None:
    classifier = CascadeClassifier(embedder=FakeEmbedder(), ontology=ontology)
    results = classifier.classify_l1("любой текст", top_k=1)
    assert len(results) == 1
    node, score = results[0]
    assert isinstance(node, Node)
    assert 0.0 <= score <= 1.0 + 1e-6


def test_real_cascade_classify_l2_with_invalid_parent_raises(
    ontology: Ontology,
) -> None:
    classifier = CascadeClassifier(embedder=FakeEmbedder(), ontology=ontology)
    with pytest.raises(ValueError):
        classifier.classify_l2("x", l1_code="99", top_k=1)


def test_classify_full_with_l4_levels(ontology: Ontology) -> None:
    classifier = CascadeClassifier(embedder=FakeEmbedder(), ontology=ontology)
    results = classifier.classify_full("Генетика и геномика", top_k=5, beam_width=5)
    assert len(results) > 0
    for path, score in results:
        assert isinstance(path, list)
        assert len(path) >= 3
        assert 0.0 <= score <= 1.0 + 1e-6
        # If L4 exists in path, it should be the deepest
        if len(path) == 4:
            assert path[-1].code == "34.15.23.01"
