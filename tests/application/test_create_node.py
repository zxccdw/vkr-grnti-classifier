from __future__ import annotations

import pytest

from backend.application.create_node import CreateNode, CreateNodeCommand
from backend.domain.entities import Description, Edge, Node, NodeId, NodeKind, Subgraph
from backend.domain.errors import NodeAlreadyExists


class FakeOntology:
    def __init__(self) -> None:
        self.added: list[Node] = []
        self.commits = 0
        self._existing: set[NodeId] = set()

    def get_node(self, id: NodeId) -> Node:
        raise NotImplementedError

    def get_edge(self, source: NodeId, target: NodeId, predicate: str) -> Edge:
        raise NotImplementedError

    def parents_of(self, id: NodeId) -> list[Node]:
        return []

    def shortest_path(self, id: NodeId) -> list[Node]:
        return []

    def subgraph(self, root: NodeId, max_depth: int = 1) -> Subgraph:
        return Subgraph(nodes=(), edges=())

    def add_node(self, node: Node) -> None:
        if node.id in self._existing:
            raise NodeAlreadyExists(node.id.value)
        self._existing.add(node.id)
        self.added.append(node)

    def add_edge(self, edge: Edge) -> None:
        raise NotImplementedError

    def remove_edge(self, source: NodeId, target: NodeId, predicate: str) -> None:
        raise NotImplementedError

    def import_payload(self, payload: dict) -> None:
        raise NotImplementedError

    def all_nodes(self) -> list[Node]:
        return []

    def all_edges(self) -> list[Edge]:
        return []

    def remove_node(self, id: NodeId) -> None:
        raise NotImplementedError

    def update_edge_descriptions(
        self,
        source: NodeId,
        target: NodeId,
        predicate: str,
        descriptions: tuple[Description, ...],
    ) -> None:
        raise NotImplementedError

    def pending_edges(self) -> list[Edge]:
        return []

    def commit(self) -> None:
        self.commits += 1


def test_full_label_defaults_to_label_when_not_provided() -> None:
    onto = FakeOntology()
    node = CreateNode(onto).execute(CreateNodeCommand(label="Геномика", code="34.15.99"))
    assert node.full_label == "Геномика"


def test_full_label_uses_provided_value() -> None:
    onto = FakeOntology()
    node = CreateNode(onto).execute(
        CreateNodeCommand(label="Геномика", code="34.15.99", full_label="Биология → Генетика → Геномика")
    )
    assert node.full_label == "Биология → Генетика → Геномика"


def test_creates_orphan_node_with_kind_from_code() -> None:
    onto = FakeOntology()
    use_case = CreateNode(onto)

    node = use_case.execute(CreateNodeCommand(label="X", code="34.15.99"))

    assert node.label == "X"
    assert node.kind is NodeKind.LEAF
    assert node.id.value == "http://example.org/competencies#GRNTI_34_15_99"
    assert onto.added == [node]
    assert onto.commits == 1


def test_section_kind_for_l1_code() -> None:
    onto = FakeOntology()
    node = CreateNode(onto).execute(CreateNodeCommand(label="Био", code="34"))
    assert node.kind is NodeKind.SECTION


def test_subsection_kind_for_l2_code() -> None:
    onto = FakeOntology()
    node = CreateNode(onto).execute(CreateNodeCommand(label="Ген", code="34.15"))
    assert node.kind is NodeKind.SUBSECTION


def test_duplicate_raises_node_already_exists() -> None:
    onto = FakeOntology()
    use_case = CreateNode(onto)
    use_case.execute(CreateNodeCommand(label="X", code="34.15.99"))

    with pytest.raises(NodeAlreadyExists):
        use_case.execute(CreateNodeCommand(label="X again", code="34.15.99"))


def test_uri_is_deterministic_for_same_code() -> None:
    from backend.application.create_node import make_node_id

    a = make_node_id("34.15.99")
    b = make_node_id("34.15.99")
    assert a == b
    assert a.value == "http://example.org/competencies#GRNTI_34_15_99"


def test_uri_dots_become_underscores() -> None:
    from backend.application.create_node import make_node_id

    assert make_node_id("01").value.endswith("GRNTI_01")
    assert make_node_id("01.02").value.endswith("GRNTI_01_02")
    assert make_node_id("01.02.03.04").value.endswith("GRNTI_01_02_03_04")


def test_kind_by_depth_of_code() -> None:
    from backend.application.create_node import kind_by_code
    from backend.domain.entities import NodeKind

    assert kind_by_code(None) is NodeKind.ROOT
    assert kind_by_code("") is NodeKind.ROOT
    assert kind_by_code("34") is NodeKind.SECTION
    assert kind_by_code("34.15") is NodeKind.SUBSECTION
    assert kind_by_code("34.15.99") is NodeKind.LEAF
    assert kind_by_code("34.15.99.1") is NodeKind.LEAF
    assert kind_by_code("34.15.99.1.5") is NodeKind.LEAF
