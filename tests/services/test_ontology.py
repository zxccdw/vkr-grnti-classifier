from __future__ import annotations

import pytest

from backend.services.ontology import Ontology, build_anchor_text, build_anchor_texts

ROOT_ID = "http://example.org/grnti_root"
L1_ID = "http://example.org/competencies#GRNTI_34"
L2_A = "http://example.org/competencies#GRNTI_34_15"
L2_B = "http://example.org/competencies#GRNTI_34_16"
L3 = "http://example.org/competencies#GRNTI_34_15_23"
PRED = "http://example.org/competencies#содержит"


def _payload(nodes: list[dict], links: list[dict]) -> dict:
    return {"nodes": nodes, "links": links}


def test_loads_simple_tree() -> None:
    payload = _payload(
        [
            {"id": ROOT_ID, "label": "ГРНТИ", "code": None},
            {"id": L1_ID, "label": "Биология", "code": "34"},
            {"id": L2_A, "label": "Генетика", "code": "34.15"},
            {"id": L3, "label": "Геномика", "code": "34.15.23"},
        ],
        [
            {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
            {"source": L1_ID, "target": L2_A, "predicate": PRED},
            {"source": L2_A, "target": L3, "predicate": PRED},
        ],
    )
    onto = Ontology.from_payload(payload)
    assert len(onto) == 4
    assert onto.root().id == ROOT_ID
    assert onto.max_depth() == 3


def test_node_lookup_by_id_and_by_code() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "ГРНТИ", "code": None},
                {"id": L1_ID, "label": "Биология", "code": "34"},
            ],
            [{"source": ROOT_ID, "target": L1_ID, "predicate": PRED}],
        )
    )
    assert onto.node(L1_ID).code == "34"
    assert onto.node("34").id == L1_ID
    assert onto.has_code("34") is True
    assert onto.has_code("99") is False


def test_node_missing_raises_keyerror() -> None:
    onto = Ontology.from_payload(
        _payload(
            [{"id": ROOT_ID, "label": "ГРНТИ", "code": None}],
            [],
        )
    )
    with pytest.raises(KeyError):
        onto.node("urn:nope")


def test_multi_parent_ontology_loads_without_error() -> None:
    payload = _payload(
        [
            {"id": ROOT_ID, "label": "ГРНТИ", "code": None},
            {"id": L1_ID, "label": "Биология", "code": "34"},
            {"id": L2_A, "label": "Генетика", "code": "34.15"},
            {"id": L2_B, "label": "Молекулярная биология", "code": "34.16"},
            {"id": L3, "label": "Геномика", "code": "34.15.23"},
        ],
        [
            {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
            {"source": L1_ID, "target": L2_A, "predicate": PRED},
            {"source": L1_ID, "target": L2_B, "predicate": PRED},
            {"source": L2_A, "target": L3, "predicate": PRED},
            {"source": L2_B, "target": L3, "predicate": PRED},
        ],
    )
    onto = Ontology.from_payload(payload)
    leaf = onto.node(L3)
    assert leaf.parent_id in {L2_A, L2_B}


def test_path_from_leaf_walks_to_root() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "ГРНТИ", "code": None},
                {"id": L1_ID, "label": "Био", "code": "34"},
                {"id": L2_A, "label": "Ген", "code": "34.15"},
                {"id": L3, "label": "Геномика", "code": "34.15.23"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_A, "predicate": PRED},
                {"source": L2_A, "target": L3, "predicate": PRED},
            ],
        )
    )
    chain = onto.path(L3)
    assert [n.id for n in chain] == [ROOT_ID, L1_ID, L2_A, L3]
    assert onto.path_codes(L3) == [None, "34", "34.15", "34.15.23"]


def test_children_returns_sorted_unique_descendants() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "a", "code": "34"},
                {"id": L2_A, "label": "b", "code": "34.15"},
                {"id": L2_B, "label": "c", "code": "34.16"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_A, "predicate": PRED},
                {"source": L1_ID, "target": L2_B, "predicate": PRED},
            ],
        )
    )
    ids = [n.id for n in onto.children(L1_ID)]
    assert ids == sorted([L2_A, L2_B])


def test_leaves_returns_nodes_without_children() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "a", "code": "34"},
                {"id": L2_A, "label": "b", "code": "34.15"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_A, "predicate": PRED},
            ],
        )
    )
    leaves = {n.id for n in onto.leaves()}
    assert leaves == {L2_A}


def test_internal_nodes_excludes_leaves() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "a", "code": "34"},
                {"id": L2_A, "label": "b", "code": "34.15"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_A, "predicate": PRED},
            ],
        )
    )
    internal = {n.id for n in onto.internal_nodes()}
    assert internal == {ROOT_ID, L1_ID}


def test_nodes_at_depth_returns_correct_level() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "a", "code": "34"},
                {"id": L2_A, "label": "b", "code": "34.15"},
                {"id": L2_B, "label": "c", "code": "34.16"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_A, "predicate": PRED},
                {"source": L1_ID, "target": L2_B, "predicate": PRED},
            ],
        )
    )
    assert [n.id for n in onto.nodes_at_depth(0)] == [ROOT_ID]
    assert [n.id for n in onto.nodes_at_depth(1)] == [L1_ID]
    assert {n.id for n in onto.nodes_at_depth(2)} == {L2_A, L2_B}


def test_duplicate_code_raises() -> None:
    with pytest.raises(ValueError):
        Ontology.from_payload(
            _payload(
                [
                    {"id": ROOT_ID, "label": "r", "code": None},
                    {"id": L1_ID, "label": "a", "code": "34"},
                    {"id": L2_A, "label": "b", "code": "34"},
                ],
                [
                    {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                    {"source": ROOT_ID, "target": L2_A, "predicate": PRED},
                ],
            )
        )


def test_legacy_string_llm_descriptions_normalized_to_tuple() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {
                    "id": L1_ID,
                    "label": "a",
                    "code": "34",
                    "llm_descriptions": "one big string",
                },
            ],
            [{"source": ROOT_ID, "target": L1_ID, "predicate": PRED}],
        )
    )
    assert onto.node(L1_ID).llm_descriptions == ("one big string",)


def test_build_anchor_text_concatenates_fields() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {
                    "id": L1_ID,
                    "label": "Биология",
                    "full_label": "Биология",
                    "description": "наука о живом",
                    "code": "34",
                },
            ],
            [{"source": ROOT_ID, "target": L1_ID, "predicate": PRED}],
        )
    )
    text = build_anchor_text(onto.node(L1_ID))
    assert "Биология" in text
    assert "наука о живом" in text


def test_edge_descriptions_parsed_from_links() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "Био", "code": "34"},
                {"id": L2_A, "label": "Ген", "code": "34.15"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {
                    "source": L1_ID,
                    "target": L2_A,
                    "predicate": PRED,
                    "llm_descriptions": [
                        {"text": "anchor one", "source": "gigachat"},
                        {"text": "anchor two", "source": "yagpt"},
                    ],
                },
            ],
        )
    )
    anchors = onto.edge_anchors(L1_ID, L2_A)
    assert anchors == ("anchor one", "anchor two")


def test_edge_anchors_empty_when_no_descriptions() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "Био", "code": "34"},
            ],
            [{"source": ROOT_ID, "target": L1_ID, "predicate": PRED}],
        )
    )
    assert onto.edge_anchors(ROOT_ID, L1_ID) == ()


def test_edge_anchors_strips_blank_strings() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "Био", "code": "34"},
            ],
            [
                {
                    "source": ROOT_ID,
                    "target": L1_ID,
                    "predicate": PRED,
                    "llm_descriptions": ["  ", "real", "  another  ", ""],
                },
            ],
        )
    )
    assert onto.edge_anchors(ROOT_ID, L1_ID) == ("real", "another")


def test_multi_parent_keeps_separate_edge_anchors() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {"id": L1_ID, "label": "Био", "code": "34"},
                {"id": L2_B, "label": "МолБио", "code": "34.16"},
                {"id": L3, "label": "Геномика", "code": "34.15.23"},
            ],
            [
                {"source": ROOT_ID, "target": L1_ID, "predicate": PRED},
                {"source": L1_ID, "target": L2_B, "predicate": PRED},
                {
                    "source": L1_ID,
                    "target": L3,
                    "predicate": PRED,
                    "llm_descriptions": ["bio context"],
                },
                {
                    "source": L2_B,
                    "target": L3,
                    "predicate": PRED,
                    "llm_descriptions": ["molbio context"],
                },
            ],
        )
    )
    assert onto.edge_anchors(L1_ID, L3) == ("bio context",)
    assert onto.edge_anchors(L2_B, L3) == ("molbio context",)


def test_build_anchor_texts_returns_each_llm_desc_separately() -> None:
    onto = Ontology.from_payload(
        _payload(
            [
                {"id": ROOT_ID, "label": "r", "code": None},
                {
                    "id": L1_ID,
                    "label": "Био",
                    "code": "34",
                    "llm_descriptions": ["one", "two"],
                },
            ],
            [{"source": ROOT_ID, "target": L1_ID, "predicate": PRED}],
        )
    )
    anchors = build_anchor_texts(onto.node(L1_ID))
    assert "one" in anchors
    assert "two" in anchors
