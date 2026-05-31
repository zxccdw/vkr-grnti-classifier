from __future__ import annotations

import numpy as np

from backend.services.cascade import CascadeClassifier
from backend.services.ontology import Ontology

PRED = "http://example.org/competencies#содержит"
ROOT = "http://example.org/grnti_root"
L1 = "http://example.org/competencies#GRNTI_34"
L2 = "http://example.org/competencies#GRNTI_34_15"
LEAF_A = "http://example.org/competencies#GRNTI_34_15_23"
LEAF_B = "http://example.org/competencies#GRNTI_34_15_99"


class StubEmbedder:
    model = object()
    model_name = "stub"
    embedding_dim = 4

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode_single(self, text: str):
        for key, vec in self._vectors.items():
            if key in text:
                return np.array(vec, dtype="float32")
        return np.zeros(4, dtype="float32")

    def encode(self, texts, batch_size: int = 32, normalize: bool | None = None):
        if isinstance(texts, str):
            texts = [texts]
        return np.stack([self.encode_single(t) for t in texts])


def _payload_with_two_leaves(leaf_a_edge_desc: list[str], leaf_b_edge_desc: list[str]) -> dict:
    return {
        "nodes": [
            {"id": ROOT, "label": "ГРНТИ", "code": None},
            {"id": L1, "label": "Биология", "code": "34"},
            {"id": L2, "label": "Генетика", "code": "34.15"},
            {"id": LEAF_A, "label": "Леаф A", "code": "34.15.23"},
            {"id": LEAF_B, "label": "Леаф B", "code": "34.15.99"},
        ],
        "links": [
            {"source": ROOT, "target": L1, "predicate": PRED},
            {"source": L1, "target": L2, "predicate": PRED},
            {
                "source": L2,
                "target": LEAF_A,
                "predicate": PRED,
                "llm_descriptions": leaf_a_edge_desc,
            },
            {
                "source": L2,
                "target": LEAF_B,
                "predicate": PRED,
                "llm_descriptions": leaf_b_edge_desc,
            },
        ],
    }


def test_classifier_uses_edge_descriptions_when_ranking_children() -> None:
    onto = Ontology.from_payload(
        _payload_with_two_leaves(
            leaf_a_edge_desc=["электромагнитные колебания"],
            leaf_b_edge_desc=["квантовая механика"],
        )
    )
    embedder = StubEmbedder(
        {
            "запрос": [1.0, 0.0, 0.0, 0.0],
            "электромагнитные": [1.0, 0.0, 0.0, 0.0],
            "квантовая": [0.0, 1.0, 0.0, 0.0],
        }
    )
    classifier = CascadeClassifier(embedder=embedder, ontology=onto)

    ranked = classifier.classify_level("запрос про электромагнитные", parent_node_id=L2, top_k=2)
    top = ranked[0][0]
    assert top.id == LEAF_A


def test_classifier_falls_back_to_node_anchors_when_edge_anchors_empty() -> None:
    onto = Ontology.from_payload(_payload_with_two_leaves(leaf_a_edge_desc=[], leaf_b_edge_desc=[]))
    embedder = StubEmbedder({"any": [1.0, 0.0, 0.0, 0.0]})
    classifier = CascadeClassifier(embedder=embedder, ontology=onto)

    ranked = classifier.classify_level("any text", parent_node_id=L2, top_k=2)
    assert {n.id for n, _ in ranked} == {LEAF_A, LEAF_B}


def test_cache_keyed_by_parent_child_pair() -> None:
    onto = Ontology.from_payload(
        _payload_with_two_leaves(
            leaf_a_edge_desc=["a context"],
            leaf_b_edge_desc=["b context"],
        )
    )
    embedder = StubEmbedder({"text": [1.0, 1.0, 0.0, 0.0]})
    classifier = CascadeClassifier(embedder=embedder, ontology=onto)

    classifier.classify_level("text", parent_node_id=L2, top_k=2)
    cache_keys = set(classifier._anchor_cache.keys())
    assert (L2, LEAF_A) in cache_keys
    assert (L2, LEAF_B) in cache_keys
