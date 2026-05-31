from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.domain.entities import Description, Edge, Node, NodeId, NodeKind
from backend.domain.errors import (
    EdgeAlreadyExists,
    EdgeNotFound,
    NodeAlreadyExists,
    NodeNotFound,
)
from backend.infrastructure.json_ontology import (
    PREDICATE_CONTAINS,
    JsonOntologyRepository,
)

ROOT_ID = "http://example.org/grnti_root"
L1_ID = "http://example.org/competencies#GRNTI_34"
L2_ID = "http://example.org/competencies#GRNTI_34_15"
L2_OTHER_ID = "http://example.org/competencies#GRNTI_34_16"
L3_ID = "http://example.org/competencies#GRNTI_34_15_23"


def _make_ontology_file(path: Path) -> None:
    payload = {
        "nodes": [
            {"id": ROOT_ID, "label": "ГРНТИ", "code": None, "full_label": "ГРНТИ"},
            {"id": L1_ID, "label": "Биология", "code": "34", "full_label": "Биология"},
            {
                "id": L2_ID,
                "label": "Генетика",
                "code": "34.15",
                "full_label": "Биология → Генетика",
            },
            {
                "id": L2_OTHER_ID,
                "label": "Молекулярная биология",
                "code": "34.16",
                "full_label": "Биология → Молекулярная биология",
            },
            {
                "id": L3_ID,
                "label": "Геномика",
                "code": "34.15.23",
                "full_label": "Биология → Генетика → Геномика",
            },
        ],
        "links": [
            {"source": ROOT_ID, "target": L1_ID, "predicate": PREDICATE_CONTAINS},
            {"source": L1_ID, "target": L2_ID, "predicate": PREDICATE_CONTAINS},
            {"source": L1_ID, "target": L2_OTHER_ID, "predicate": PREDICATE_CONTAINS},
            {
                "source": L2_ID,
                "target": L3_ID,
                "predicate": PREDICATE_CONTAINS,
                "llm_descriptions": [{"text": "stored desc", "source": "gigachat"}],
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> JsonOntologyRepository:
    onto_path = tmp_path / "ontology.json"
    snap_dir = tmp_path / "snapshots"
    _make_ontology_file(onto_path)
    return JsonOntologyRepository(onto_path, snap_dir)


def test_get_node_returns_kind_by_code(repo: JsonOntologyRepository) -> None:
    n = repo.get_node(NodeId(L2_ID))
    assert n.label == "Генетика"
    assert n.kind is NodeKind.SUBSECTION


def test_get_node_missing_raises(repo: JsonOntologyRepository) -> None:
    with pytest.raises(NodeNotFound):
        repo.get_node(NodeId("urn:nope"))


def test_get_edge_returns_stored_descriptions(repo: JsonOntologyRepository) -> None:
    edge = repo.get_edge(NodeId(L2_ID), NodeId(L3_ID), PREDICATE_CONTAINS)
    assert [d.text for d in edge.descriptions] == ["stored desc"]
    assert edge.descriptions[0].source == "gigachat"


def test_get_edge_missing_raises(repo: JsonOntologyRepository) -> None:
    with pytest.raises(EdgeNotFound):
        repo.get_edge(NodeId(L1_ID), NodeId(L3_ID), PREDICATE_CONTAINS)


def test_parents_of_returns_all_incoming(repo: JsonOntologyRepository) -> None:
    parents = repo.parents_of(NodeId(L2_OTHER_ID))
    assert [p.id.value for p in parents] == [L1_ID]


def test_shortest_path_from_leaf_to_root(repo: JsonOntologyRepository) -> None:
    path = repo.shortest_path(NodeId(L3_ID))
    assert [n.id.value for n in path] == [ROOT_ID, L1_ID, L2_ID, L3_ID]


def test_subgraph_includes_edge_descriptions(repo: JsonOntologyRepository) -> None:
    sg = repo.subgraph(NodeId(L1_ID), max_depth=2)
    assert {n.id.value for n in sg.nodes} == {L1_ID, L2_ID, L2_OTHER_ID, L3_ID}
    leaf_edge = next(e for e in sg.edges if e.target.value == L3_ID)
    assert [d.text for d in leaf_edge.descriptions] == ["stored desc"]


def test_subgraph_missing_root_raises(repo: JsonOntologyRepository) -> None:
    with pytest.raises(NodeNotFound):
        repo.subgraph(NodeId("urn:nope"))


def test_add_node_then_commit_persists(repo: JsonOntologyRepository, tmp_path: Path) -> None:
    new = Node(
        id=NodeId("http://example.org/competencies#GRNTI_34_15_99"),
        label="Протеомика",
        code="34.15.99",
        full_label="Биология → Генетика → Протеомика",
        kind=NodeKind.LEAF,
    )
    repo.add_node(new)
    repo.commit()
    reloaded = json.loads((tmp_path / "ontology.json").read_text(encoding="utf-8"))
    assert new.id.value in {n["id"] for n in reloaded["nodes"]}


def test_add_node_existing_raises(repo: JsonOntologyRepository) -> None:
    existing = repo.get_node(NodeId(L3_ID))
    with pytest.raises(NodeAlreadyExists):
        repo.add_node(existing)


def test_add_edge_creates_multi_parent_link(repo: JsonOntologyRepository, tmp_path: Path) -> None:
    edge = Edge(
        source=NodeId(L2_OTHER_ID),
        target=NodeId(L3_ID),
        predicate=PREDICATE_CONTAINS,
        descriptions=(Description(text="alt-context", source="yagpt"),),
    )
    repo.add_edge(edge)
    repo.commit()

    parents = repo.parents_of(NodeId(L3_ID))
    assert {p.id.value for p in parents} == {L2_ID, L2_OTHER_ID}

    alt_edge = repo.get_edge(NodeId(L2_OTHER_ID), NodeId(L3_ID), PREDICATE_CONTAINS)
    assert [d.text for d in alt_edge.descriptions] == ["alt-context"]
    original_edge = repo.get_edge(NodeId(L2_ID), NodeId(L3_ID), PREDICATE_CONTAINS)
    assert [d.text for d in original_edge.descriptions] == ["stored desc"]


def test_add_edge_duplicate_raises(repo: JsonOntologyRepository) -> None:
    edge = Edge(source=NodeId(L2_ID), target=NodeId(L3_ID), predicate=PREDICATE_CONTAINS)
    with pytest.raises(EdgeAlreadyExists):
        repo.add_edge(edge)


def test_add_edge_missing_source_raises(repo: JsonOntologyRepository) -> None:
    edge = Edge(source=NodeId("urn:nope"), target=NodeId(L3_ID), predicate=PREDICATE_CONTAINS)
    with pytest.raises(NodeNotFound):
        repo.add_edge(edge)


def test_update_edge_descriptions_persists(repo: JsonOntologyRepository, tmp_path: Path) -> None:
    repo.update_edge_descriptions(
        NodeId(L2_ID),
        NodeId(L3_ID),
        PREDICATE_CONTAINS,
        (Description(text="updated", source="yagpt"),),
    )
    repo.commit()
    reloaded = json.loads((tmp_path / "ontology.json").read_text(encoding="utf-8"))
    target_link = next(
        link for link in reloaded["links"] if link["source"] == L2_ID and link["target"] == L3_ID
    )
    assert target_link["llm_descriptions"] == [{"text": "updated", "source": "yagpt"}]


def test_pending_edges_finds_only_edges_without_descriptions(
    repo: JsonOntologyRepository,
) -> None:
    pending = repo.pending_edges()
    pending_pairs = {(e.source.value, e.target.value) for e in pending}
    assert (L2_ID, L3_ID) not in pending_pairs
    assert (ROOT_ID, L1_ID) in pending_pairs
    assert (L1_ID, L2_ID) in pending_pairs


def test_pending_edges_excludes_legacy_node_descriptions(tmp_path: Path) -> None:
    payload = {
        "nodes": [
            {"id": ROOT_ID, "label": "ГРНТИ", "code": None},
            {
                "id": L1_ID,
                "label": "Биология",
                "code": "34",
                "llm_descriptions": ["legacy on node"],
            },
        ],
        "links": [
            {"source": ROOT_ID, "target": L1_ID, "predicate": PREDICATE_CONTAINS},
        ],
    }
    onto_path = tmp_path / "o.json"
    onto_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    repo_legacy = JsonOntologyRepository(onto_path, tmp_path / "snaps")
    assert repo_legacy.pending_edges() == []


def test_commit_creates_snapshot(repo: JsonOntologyRepository, tmp_path: Path) -> None:
    repo.update_edge_descriptions(NodeId(L2_ID), NodeId(L3_ID), PREDICATE_CONTAINS, ())
    repo.commit()
    snaps = list((tmp_path / "snapshots").glob("*.json"))
    assert len(snaps) == 1


def test_subgraph_traverses_multi_level_chain(repo: JsonOntologyRepository) -> None:
    l4 = Node(
        id=NodeId("http://example.org/competencies#GRNTI_34_15_23_1"),
        label="L4",
        code="34.15.23.1",
        full_label="L4",
        kind=NodeKind.LEAF,
    )
    l5 = Node(
        id=NodeId("http://example.org/competencies#GRNTI_34_15_23_1_1"),
        label="L5",
        code="34.15.23.1.1",
        full_label="L5",
        kind=NodeKind.LEAF,
    )
    repo.add_node(l4)
    repo.add_node(l5)
    repo.add_edge(Edge(source=NodeId(L3_ID), target=l4.id, predicate=PREDICATE_CONTAINS))
    repo.add_edge(Edge(source=l4.id, target=l5.id, predicate=PREDICATE_CONTAINS))
    repo.commit()

    sg = repo.subgraph(NodeId(L1_ID), max_depth=4)
    ids = {n.id.value for n in sg.nodes}
    assert l4.id.value in ids
    assert l5.id.value in ids


def test_shortest_path_for_deep_node(repo: JsonOntologyRepository) -> None:
    l4 = Node(
        id=NodeId("http://example.org/competencies#GRNTI_34_15_23_1"),
        label="L4",
        code="34.15.23.1",
        full_label="L4",
        kind=NodeKind.LEAF,
    )
    repo.add_node(l4)
    repo.add_edge(Edge(source=NodeId(L3_ID), target=l4.id, predicate=PREDICATE_CONTAINS))
    repo.commit()

    path = repo.shortest_path(l4.id)
    assert [n.id.value for n in path] == [ROOT_ID, L1_ID, L2_ID, L3_ID, l4.id.value]


def test_multi_parent_edge_keeps_independent_descriptions(
    repo: JsonOntologyRepository,
) -> None:
    edge = Edge(
        source=NodeId(L2_OTHER_ID),
        target=NodeId(L3_ID),
        predicate=PREDICATE_CONTAINS,
        descriptions=(Description(text="alt-only", source="yagpt"),),
    )
    repo.add_edge(edge)
    repo.commit()

    original = repo.get_edge(NodeId(L2_ID), NodeId(L3_ID), PREDICATE_CONTAINS)
    alternative = repo.get_edge(NodeId(L2_OTHER_ID), NodeId(L3_ID), PREDICATE_CONTAINS)
    assert [d.text for d in original.descriptions] == ["stored desc"]
    assert [d.text for d in alternative.descriptions] == ["alt-only"]


def test_all_nodes_returns_every_node(repo: JsonOntologyRepository) -> None:
    ids = {n.id.value for n in repo.all_nodes()}
    assert ids == {ROOT_ID, L1_ID, L2_ID, L2_OTHER_ID, L3_ID}


def test_all_edges_returns_every_edge(repo: JsonOntologyRepository) -> None:
    edges = repo.all_edges()
    pairs = {(e.source.value, e.target.value) for e in edges}
    assert (ROOT_ID, L1_ID) in pairs
    assert (L2_ID, L3_ID) in pairs
    leaf_edge = next(e for e in edges if e.target.value == L3_ID)
    assert [d.text for d in leaf_edge.descriptions] == ["stored desc"]


def test_remove_node_drops_node_and_all_incident_edges(
    repo: JsonOntologyRepository, tmp_path: Path
) -> None:
    repo.remove_node(NodeId(L3_ID))
    assert L3_ID not in {n.id.value for n in repo.all_nodes()}
    assert all(
        not (e.source.value == L3_ID or e.target.value == L3_ID)
        for e in repo.all_edges()
    )


def test_remove_node_missing_raises(repo: JsonOntologyRepository) -> None:
    with pytest.raises(NodeNotFound):
        repo.remove_node(NodeId("urn:nope"))


def test_search_by_code_prefix(repo: JsonOntologyRepository) -> None:
    results = repo.search("34.15", limit=10)
    ids = {n.id.value for n in results}
    assert L2_ID in ids


def test_search_by_label_case_insensitive(repo: JsonOntologyRepository) -> None:
    results = repo.search("генет", limit=10)
    ids = {n.id.value for n in results}
    assert L2_ID in ids


def test_search_limit_respected(repo: JsonOntologyRepository) -> None:
    results = repo.search("34", limit=2)
    assert len(results) == 2


def test_remove_edge_drops_link_and_updates_parents(
    repo: JsonOntologyRepository, tmp_path: Path
) -> None:
    repo.remove_edge(NodeId(L2_ID), NodeId(L3_ID), PREDICATE_CONTAINS)

    assert repo.parents_of(NodeId(L3_ID)) == []
    reloaded = json.loads((tmp_path / "ontology.json").read_text(encoding="utf-8"))
    assert not any(
        link["source"] == L2_ID and link["target"] == L3_ID for link in reloaded["links"]
    )


def test_remove_edge_missing_raises(repo: JsonOntologyRepository) -> None:
    with pytest.raises(EdgeNotFound):
        repo.remove_edge(NodeId("urn:nope"), NodeId(L3_ID), PREDICATE_CONTAINS)


def test_import_payload_replaces_ontology(
    repo: JsonOntologyRepository, tmp_path: Path
) -> None:
    new_payload = {
        "nodes": [
            {"id": "urn:fresh:root", "label": "Root", "code": None},
            {"id": "urn:fresh:a", "label": "A", "code": "01"},
        ],
        "links": [
            {"source": "urn:fresh:root", "target": "urn:fresh:a", "predicate": PREDICATE_CONTAINS},
        ],
    }
    repo.import_payload(new_payload)

    reloaded = json.loads((tmp_path / "ontology.json").read_text(encoding="utf-8"))
    assert {n["id"] for n in reloaded["nodes"]} == {"urn:fresh:root", "urn:fresh:a"}
    snaps = list((tmp_path / "snapshots").glob("*.json"))
    assert len(snaps) >= 1


def test_import_payload_rejects_malformed(repo: JsonOntologyRepository) -> None:
    with pytest.raises(ValueError):
        repo.import_payload({"only_nodes": []})


def test_no_tmp_file_left_after_commit(repo: JsonOntologyRepository, tmp_path: Path) -> None:
    new = Node(
        id=NodeId("http://example.org/competencies#GRNTI_34_15_77"),
        label="X",
        code="34.15.77",
        full_label="X",
        kind=NodeKind.LEAF,
    )
    repo.add_node(new)
    repo.commit()
    assert list(tmp_path.glob("*.tmp")) == []
