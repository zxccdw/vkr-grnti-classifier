from __future__ import annotations

from backend.application.merge_duplicates import (
    PREDICATE_CONTAINS,
    MergeDuplicatesByLabel,
)
from backend.domain.entities import Description, Edge, Node, NodeId, NodeKind, Subgraph

ROOT = NodeId("root")
L1_BIO = NodeId("bio")
L1_ECON = NodeId("econ")
N_34_01 = NodeId("n_34_01")
N_47_01 = NodeId("n_47_01")
N_UNIQUE = NodeId("unique")


def _node(id: NodeId, label: str, code: str | None) -> Node:
    return Node(id=id, label=label, code=code, full_label=label, kind=NodeKind.LEAF)


class FakeOntology:
    def __init__(self) -> None:
        self._nodes: dict[NodeId, Node] = {
            ROOT: _node(ROOT, "ГРНТИ", None),
            L1_BIO: _node(L1_BIO, "Биология", "34"),
            L1_ECON: _node(L1_ECON, "Экономика", "47"),
            N_34_01: _node(N_34_01, "Общие вопросы", "34.01"),
            N_47_01: _node(N_47_01, "Общие вопросы", "47.01"),
            N_UNIQUE: _node(N_UNIQUE, "Уникальное", "34.99"),
        }
        self._edges: dict[tuple[NodeId, NodeId, str], Edge] = {
            (L1_BIO, N_34_01, PREDICATE_CONTAINS): Edge(
                source=L1_BIO, target=N_34_01, predicate=PREDICATE_CONTAINS,
                descriptions=(Description(text="bio context", source="gigachat"),),
            ),
            (L1_ECON, N_47_01, PREDICATE_CONTAINS): Edge(
                source=L1_ECON, target=N_47_01, predicate=PREDICATE_CONTAINS,
                descriptions=(Description(text="econ context", source="gigachat"),),
            ),
            (L1_BIO, N_UNIQUE, PREDICATE_CONTAINS): Edge(
                source=L1_BIO, target=N_UNIQUE, predicate=PREDICATE_CONTAINS,
            ),
        }
        self.commits = 0

    def all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def all_edges(self) -> list[Edge]:
        return list(self._edges.values())

    def get_node(self, id: NodeId) -> Node:
        return self._nodes[id]

    def get_edge(self, source: NodeId, target: NodeId, predicate: str) -> Edge:
        return self._edges[(source, target, predicate)]

    def parents_of(self, id: NodeId) -> list[Node]:
        return [self._nodes[s] for (s, t, _) in self._edges if t == id]

    def shortest_path(self, id: NodeId) -> list[Node]:
        return [self._nodes[id]]

    def subgraph(self, root: NodeId, max_depth: int = 1) -> Subgraph:
        return Subgraph(nodes=(), edges=())

    def add_node(self, node: Node) -> None:
        self._nodes[node.id] = node

    def remove_node(self, id: NodeId) -> None:
        self._nodes.pop(id, None)
        self._edges = {k: e for k, e in self._edges.items() if k[0] != id and k[1] != id}

    def add_edge(self, edge: Edge) -> None:
        self._edges[(edge.source, edge.target, edge.predicate)] = edge

    def remove_edge(self, source: NodeId, target: NodeId, predicate: str) -> None:
        self._edges.pop((source, target, predicate), None)

    def update_edge_descriptions(
        self, source: NodeId, target: NodeId, predicate: str,
        descriptions: tuple[Description, ...],
    ) -> None:
        raise NotImplementedError

    def pending_edges(self) -> list[Edge]:
        return []

    def import_payload(self, payload: dict) -> None:
        raise NotImplementedError

    def commit(self) -> None:
        self.commits += 1


def test_merges_duplicate_labels_with_same_suffix() -> None:
    onto = FakeOntology()
    use_case = MergeDuplicatesByLabel(onto)

    report = use_case.execute()

    assert report.groups_merged == 1
    assert report.nodes_removed == 2
    assert report.edges_redirected == 2
    assert onto.commits == 1


def test_canonical_concept_receives_all_parents() -> None:
    onto = FakeOntology()
    MergeDuplicatesByLabel(onto).execute()

    concept_id = NodeId(
        "http://example.org/competencies#CONCEPT_01_Общие_вопросы"
    )
    assert concept_id in {n.id for n in onto.all_nodes()}
    parents = {p.id for p in onto.parents_of(concept_id)}
    assert parents == {L1_BIO, L1_ECON}


def test_per_parent_descriptions_kept_on_edges() -> None:
    onto = FakeOntology()
    MergeDuplicatesByLabel(onto).execute()

    concept_id = NodeId(
        "http://example.org/competencies#CONCEPT_01_Общие_вопросы"
    )
    bio_edge = onto.get_edge(L1_BIO, concept_id, PREDICATE_CONTAINS)
    econ_edge = onto.get_edge(L1_ECON, concept_id, PREDICATE_CONTAINS)
    assert [d.text for d in bio_edge.descriptions] == ["bio context"]
    assert [d.text for d in econ_edge.descriptions] == ["econ context"]


def test_unique_node_not_touched() -> None:
    onto = FakeOntology()
    MergeDuplicatesByLabel(onto).execute()

    assert N_UNIQUE in {n.id for n in onto.all_nodes()}


def test_no_duplicates_no_commit() -> None:
    onto = FakeOntology()
    onto.remove_node(N_47_01)
    use_case = MergeDuplicatesByLabel(onto)

    report = use_case.execute()

    assert report.groups_merged == 0
    assert onto.commits == 0


def test_same_label_different_suffix_not_merged() -> None:
    onto = FakeOntology()
    diff_suffix = NodeId("diff")
    onto.add_node(_node(diff_suffix, "Общие вопросы", "47.99"))
    onto._edges[(L1_ECON, diff_suffix, PREDICATE_CONTAINS)] = Edge(
        source=L1_ECON, target=diff_suffix, predicate=PREDICATE_CONTAINS,
    )
    onto.remove_node(N_47_01)

    MergeDuplicatesByLabel(onto).execute()

    assert diff_suffix in {n.id for n in onto.all_nodes()}
    assert N_34_01 in {n.id for n in onto.all_nodes()}


def test_node_without_code_skipped() -> None:
    onto = FakeOntology()
    no_code = NodeId("no-code")
    onto.add_node(_node(no_code, "Общие вопросы", None))
    onto._edges[(L1_BIO, no_code, PREDICATE_CONTAINS)] = Edge(
        source=L1_BIO, target=no_code, predicate=PREDICATE_CONTAINS,
    )

    MergeDuplicatesByLabel(onto).execute()

    assert no_code in {n.id for n in onto.all_nodes()}


def test_canonical_uri_contains_suffix_and_label() -> None:
    onto = FakeOntology()
    MergeDuplicatesByLabel(onto).execute()

    concept_ids = [
        n.id.value for n in onto.all_nodes()
        if "CONCEPT_" in n.id.value
    ]
    assert any("CONCEPT_01_Общие_вопросы" in cid for cid in concept_ids)


def test_canonical_node_has_no_code() -> None:
    onto = FakeOntology()
    MergeDuplicatesByLabel(onto).execute()

    concept_id = NodeId(
        "http://example.org/competencies#CONCEPT_01_Общие_вопросы"
    )
    concept_node = onto.get_node(concept_id)
    assert concept_node.code is None
    assert concept_node.label == "Общие вопросы"


def test_multiple_distinct_groups_merge_independently() -> None:
    onto = FakeOntology()
    # add second group: "Информационная деятельность" with .29 in two L1's
    info_a = NodeId("info_a")
    info_b = NodeId("info_b")
    onto.add_node(_node(info_a, "Информационная деятельность", "34.29"))
    onto.add_node(_node(info_b, "Информационная деятельность", "47.29"))
    onto._edges[(L1_BIO, info_a, PREDICATE_CONTAINS)] = Edge(
        source=L1_BIO, target=info_a, predicate=PREDICATE_CONTAINS,
    )
    onto._edges[(L1_ECON, info_b, PREDICATE_CONTAINS)] = Edge(
        source=L1_ECON, target=info_b, predicate=PREDICATE_CONTAINS,
    )

    report = MergeDuplicatesByLabel(onto).execute()

    assert report.groups_merged == 2
    assert report.nodes_removed == 4
