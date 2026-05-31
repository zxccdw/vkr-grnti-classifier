from __future__ import annotations

import pytest

from backend.application.add_node import AddNode, AddNodeCommand
from backend.domain.entities import Description, Edge, Node, NodeId, NodeKind, Subgraph
from backend.domain.errors import NodeAlreadyExists

ROOT = NodeId("root")
L1 = NodeId("l1")
L2 = NodeId("l2")
L3 = NodeId("l3")
NEW_LEAF = NodeId("http://example.org/competencies#GRNTI_34_15_99")

SEED = {
    ROOT: Node(id=ROOT, label="ГРНТИ", code=None, full_label="ГРНТИ", kind=NodeKind.ROOT),
    L1: Node(id=L1, label="Биология", code="34", full_label="Биология", kind=NodeKind.SECTION),
    L2: Node(
        id=L2,
        label="Генетика",
        code="34.15",
        full_label="Биология → Генетика",
        kind=NodeKind.SUBSECTION,
    ),
    L3: Node(
        id=L3,
        label="Геномика",
        code="34.15.23",
        full_label="Биология → Генетика → Геномика",
        kind=NodeKind.LEAF,
    ),
}

SEED_PATHS = {
    ROOT: [SEED[ROOT]],
    L1: [SEED[ROOT], SEED[L1]],
    L2: [SEED[ROOT], SEED[L1], SEED[L2]],
    L3: [SEED[ROOT], SEED[L1], SEED[L2], SEED[L3]],
}


class FakeOntology:
    def __init__(self) -> None:
        self._nodes: dict[NodeId, Node] = dict(SEED)
        self.commits = 0
        self.added_nodes: list[Node] = []
        self.added_edges: list[Edge] = []

    def get_node(self, id: NodeId) -> Node:
        return self._nodes[id]

    def get_edge(self, source: NodeId, target: NodeId, predicate: str) -> Edge:
        raise NotImplementedError

    def parents_of(self, id: NodeId) -> list[Node]:
        return []

    def shortest_path(self, id: NodeId) -> list[Node]:
        return list(SEED_PATHS[id])

    def subgraph(self, root: NodeId, max_depth: int = 1) -> Subgraph:
        return Subgraph(nodes=(), edges=())

    def add_node(self, node: Node) -> None:
        if node.id in self._nodes:
            raise NodeAlreadyExists(node.id.value)
        self._nodes[node.id] = node
        self.added_nodes.append(node)
        SEED_PATHS[node.id] = SEED_PATHS[L2] + [node]  # mimic attaching under L2

    def add_edge(self, edge: Edge) -> None:
        self.added_edges.append(edge)

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


class FakeProvider:
    def __init__(self, name: str, returns: list[str]) -> None:
        self.name = name
        self._returns = returns

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        return list(self._returns)


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        raise RuntimeError("down")


async def test_creates_node_and_edge_with_descriptions() -> None:
    onto = FakeOntology()
    use_case = AddNode(onto, [FakeProvider("gigachat", ["g"]), FakeProvider("yagpt", ["y"])])

    result = await use_case.execute(
        AddNodeCommand(parent_id=L2, label="Протеомика", code="34.15.99")
    )

    assert result.node.label == "Протеомика"
    assert result.node.kind is NodeKind.LEAF
    assert result.edge.source == L2
    assert result.edge.target == NEW_LEAF
    assert {d.source for d in result.edge.descriptions} == {"gigachat", "yagpt"}
    assert len(onto.added_nodes) == 1
    assert len(onto.added_edges) == 1


async def test_parent_is_leaf_is_allowed() -> None:
    onto = FakeOntology()
    use_case = AddNode(onto, [FakeProvider("g", ["t"])])

    result = await use_case.execute(AddNodeCommand(parent_id=L3, label="Sub", code="34.15.23.1"))

    assert result.node.label == "Sub"
    assert len(onto.added_nodes) == 1


async def test_duplicate_code_raises_node_already_exists() -> None:
    onto = FakeOntology()
    use_case = AddNode(onto, [FakeProvider("g", ["t"])])

    await use_case.execute(AddNodeCommand(parent_id=L2, label="X", code="34.15.99"))
    with pytest.raises(NodeAlreadyExists):
        await use_case.execute(AddNodeCommand(parent_id=L2, label="Y", code="34.15.99"))


async def test_all_providers_fail_node_is_pending() -> None:
    onto = FakeOntology()
    use_case = AddNode(onto, [FailingProvider("g"), FailingProvider("y")])

    result = await use_case.execute(
        AddNodeCommand(parent_id=L2, label="Протеомика", code="34.15.99")
    )

    assert result.edge.descriptions == ()
    assert len(onto.added_nodes) == 1
