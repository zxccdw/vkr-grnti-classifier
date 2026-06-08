from __future__ import annotations

from dataclasses import replace

import numpy as np

from backend.services.cascade import CascadeClassifier
from backend.services.ontology import Node, Ontology

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


def test_save_cache_and_load_cache_roundtrip(tmp_path) -> None:
    onto = Ontology.from_payload(
        _payload_with_two_leaves(leaf_a_edge_desc=["описание A"], leaf_b_edge_desc=["описание B"])
    )
    embedder = StubEmbedder({"any": [0.5, 0.5, 0.0, 0.0]})
    clf = CascadeClassifier(embedder=embedder, ontology=onto)
    clf.classify_level("any", parent_node_id=L2, top_k=2)

    path = tmp_path / "cache.pkl.gz"
    n_saved = clf.save_cache(path)
    assert n_saved == 2
    assert path.exists()

    clf2 = CascadeClassifier(embedder=embedder, ontology=onto)
    n_loaded = clf2.load_cache(path)
    assert n_loaded == 2
    assert set(clf2._anchor_cache.keys()) == {(L2, LEAF_A), (L2, LEAF_B)}


def test_load_cache_restores_vectors_correctly(tmp_path) -> None:
    onto = Ontology.from_payload(
        _payload_with_two_leaves(leaf_a_edge_desc=["квантовая физика"], leaf_b_edge_desc=[])
    )
    embedder = StubEmbedder({"квантовая": [0.0, 1.0, 0.0, 0.0]})
    clf = CascadeClassifier(embedder=embedder, ontology=onto)
    clf.classify_level("квантовая физика", parent_node_id=L2, top_k=2)

    path = tmp_path / "cache.pkl.gz"
    clf.save_cache(path)

    clf2 = CascadeClassifier(embedder=embedder, ontology=onto)
    clf2.load_cache(path)

    original = clf._anchor_cache[(L2, LEAF_A)]
    restored = clf2._anchor_cache[(L2, LEAF_A)]
    # float16 round-trip: tolerance ~1e-3
    assert np.allclose(original, restored, atol=1e-2)


def test_load_cache_does_not_overwrite_existing_entries(tmp_path) -> None:
    onto = Ontology.from_payload(
        _payload_with_two_leaves(leaf_a_edge_desc=["a"], leaf_b_edge_desc=["b"])
    )
    embedder = StubEmbedder({"text": [1.0, 0.0, 0.0, 0.0]})
    clf = CascadeClassifier(embedder=embedder, ontology=onto)
    clf.classify_level("text", parent_node_id=L2, top_k=2)
    path = tmp_path / "cache.pkl.gz"
    clf.save_cache(path)

    fresh_vec = np.array([9.0, 9.0, 9.0, 9.0], dtype=np.float32)
    clf2 = CascadeClassifier(embedder=embedder, ontology=onto)
    clf2._anchor_cache[(L2, LEAF_A)] = fresh_vec.reshape(1, -1)
    clf2.load_cache(path)

    # pre-existing entry must not be overwritten
    assert np.allclose(clf2._anchor_cache[(L2, LEAF_A)], fresh_vec.reshape(1, -1))


LEAF_C = "http://example.org/competencies#GRNTI_34_15_77"


def test_new_leaf_added_after_cache_warmup_is_classified() -> None:
    onto = Ontology.from_payload(
        _payload_with_two_leaves(leaf_a_edge_desc=["биология"], leaf_b_edge_desc=["химия"])
    )
    embedder = StubEmbedder(
        {
            "биология": [1.0, 0.0, 0.0, 0.0],
            "химия": [0.0, 1.0, 0.0, 0.0],
            "физика": [0.0, 0.0, 1.0, 0.0],
        }
    )
    clf = CascadeClassifier(embedder=embedder, ontology=onto)

    # warm up cache for existing leaves
    clf.classify_level("биология", parent_node_id=L2, top_k=2)
    assert (L2, LEAF_A) in clf._anchor_cache
    assert (L2, LEAF_B) in clf._anchor_cache

    # add new leaf to ontology after cache is warm
    new_node = Node(
        id=LEAF_C,
        code="34.15.77",
        depth=3,
        label="Физика",
        full_label="Биология → Генетика → Физика",
        description="",
        parent_id=L2,
        children_ids=(),
        llm_descriptions=("физика элементарных частиц",),
    )
    onto.nodes_by_id[LEAF_C] = new_node
    onto.nodes_by_id[L2] = replace(
        onto.nodes_by_id[L2], children_ids=onto.nodes_by_id[L2].children_ids + (LEAF_C,)
    )
    onto.edge_descriptions[(L2, LEAF_C)] = ("физика элементарных частиц",)

    # new leaf must be ranked and cache entry created for it
    results = clf.classify_level("физика", parent_node_id=L2, top_k=3)
    result_ids = [n.id for n, _ in results]
    assert LEAF_C in result_ids
    assert (L2, LEAF_C) in clf._anchor_cache
    assert results[0][0].id == LEAF_C
