from __future__ import annotations

import pytest

from backend.application.attach_edge import (
    PREDICATE_CONTAINS,
    AttachEdge,
    AttachEdgeCommand,
)
from backend.domain.entities import Description, Edge, Node, NodeId, NodeKind, Subgraph
from backend.domain.errors import EdgeAlreadyExists, InvalidDepth

ROOT = NodeId("root")
L1 = NodeId("l1")
L2 = NodeId("l2")
L3 = NodeId("l3")
ORPHAN_LEAF = NodeId("orphan-leaf")

NODES = {
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
    ORPHAN_LEAF: Node(
        id=ORPHAN_LEAF,
        label="Эпигенетика",
        code="34.15.88",
        full_label="Эпигенетика",
        kind=NodeKind.LEAF,
    ),
}

PATHS = {
    ROOT: [NODES[ROOT]],
    L1: [NODES[ROOT], NODES[L1]],
    L2: [NODES[ROOT], NODES[L1], NODES[L2]],
    L3: [NODES[ROOT], NODES[L1], NODES[L2], NODES[L3]],
    ORPHAN_LEAF: [NODES[ORPHAN_LEAF]],
}


class FakeOntology:
    def __init__(self) -> None:
        self.added_edges: list[Edge] = []
        self.commits = 0
        self._edge_keys: set[tuple[str, str, str]] = set()

    def get_node(self, id: NodeId) -> Node:
        return NODES[id]

    def get_edge(self, source: NodeId, target: NodeId, predicate: str) -> Edge:
        raise NotImplementedError

    def parents_of(self, id: NodeId) -> list[Node]:
        return []

    def shortest_path(self, id: NodeId) -> list[Node]:
        return PATHS[id]

    def subgraph(self, root: NodeId, max_depth: int = 1) -> Subgraph:
        return Subgraph(nodes=(), edges=())

    def add_node(self, node: Node) -> None:
        raise NotImplementedError

    def add_edge(self, edge: Edge) -> None:
        key = (edge.source.value, edge.target.value, edge.predicate)
        if key in self._edge_keys:
            raise EdgeAlreadyExists(str(key))
        self._edge_keys.add(key)
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
        self.calls: list[tuple[str, str, list[str]]] = []

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        self.calls.append((label, code, parent_chain))
        return list(self._returns)


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name

    async def describe(self, label: str, code: str, parent_chain: list[str]) -> list[str]:
        raise RuntimeError("down")


async def test_attach_under_subsection_creates_edge_with_descriptions() -> None:
    onto = FakeOntology()
    giga = FakeProvider("gigachat", ["g1", "g2"])
    yagpt = FakeProvider("yagpt", ["y1"])
    use_case = AttachEdge(onto, [giga, yagpt])

    edge = await use_case.execute(AttachEdgeCommand(source_id=L2, target_id=ORPHAN_LEAF))

    assert edge.source == L2
    assert edge.target == ORPHAN_LEAF
    assert edge.predicate == PREDICATE_CONTAINS
    assert {d.text for d in edge.descriptions} == {"g1", "g2", "y1"}
    assert onto.commits == 1


async def test_chain_passed_to_provider_uses_source_path() -> None:
    onto = FakeOntology()
    giga = FakeProvider("gigachat", ["t"])
    use_case = AttachEdge(onto, [giga])

    await use_case.execute(AttachEdgeCommand(source_id=L2, target_id=ORPHAN_LEAF))

    assert giga.calls == [("Эпигенетика", "34.15.88", ["ГРНТИ", "Биология", "Генетика"])]


async def test_attach_leaf_under_root_rejected_by_code_prefix() -> None:
    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])

    with pytest.raises(InvalidDepth):
        await use_case.execute(AttachEdgeCommand(source_id=ROOT, target_id=ORPHAN_LEAF))

    assert onto.commits == 0


async def test_attach_under_l3_with_matching_code_prefix_is_allowed() -> None:
    deep_target = NodeId("deep")
    deep_node = Node(
        id=deep_target,
        label="Deep",
        code="34.15.23.7",
        full_label="Deep",
        kind=NodeKind.LEAF,
    )
    NODES[deep_target] = deep_node
    PATHS[deep_target] = [deep_node]

    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    edge = await use_case.execute(AttachEdgeCommand(source_id=L3, target_id=deep_target))

    assert edge.source == L3
    assert edge.target == deep_target
    assert onto.commits == 1


async def test_attach_l3_to_l2_rejected_by_code_prefix() -> None:
    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])

    with pytest.raises(InvalidDepth) as exc:
        await use_case.execute(AttachEdgeCommand(source_id=L3, target_id=L2))

    assert "34.15" in str(exc.value)
    assert onto.commits == 0


async def test_attach_sibling_l1_to_l1_rejected() -> None:
    other_l1 = NodeId("other_l1")
    NODES[other_l1] = Node(
        id=other_l1,
        label="Экономика",
        code="47",
        full_label="Экономика",
        kind=NodeKind.SECTION,
    )
    PATHS[other_l1] = [NODES[other_l1]]

    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    with pytest.raises(InvalidDepth):
        await use_case.execute(AttachEdgeCommand(source_id=L1, target_id=other_l1))


async def test_attach_l2_to_root_rejected() -> None:
    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    with pytest.raises(InvalidDepth):
        await use_case.execute(AttachEdgeCommand(source_id=L2, target_id=ROOT))


async def test_attach_to_l1_under_root_accepted() -> None:
    new_l1 = NodeId("new_l1")
    NODES[new_l1] = Node(
        id=new_l1,
        label="Новый раздел",
        code="99",
        full_label="Новый раздел",
        kind=NodeKind.SECTION,
    )
    PATHS[new_l1] = [NODES[new_l1]]

    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    edge = await use_case.execute(AttachEdgeCommand(source_id=ROOT, target_id=new_l1))
    assert edge.source == ROOT
    assert edge.target == new_l1


async def test_attach_with_target_having_dot_under_root_rejected() -> None:
    sub_node = NodeId("sub")
    NODES[sub_node] = Node(
        id=sub_node,
        label="X",
        code="34.15",
        full_label="X",
        kind=NodeKind.SUBSECTION,
    )
    PATHS[sub_node] = [NODES[sub_node]]

    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    with pytest.raises(InvalidDepth):
        await use_case.execute(AttachEdgeCommand(source_id=ROOT, target_id=sub_node))


async def test_attach_skip_level_l1_to_l3_allowed_by_code_prefix() -> None:
    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    edge = await use_case.execute(AttachEdgeCommand(source_id=L1, target_id=L3))
    assert edge.source == L1
    assert edge.target == L3


async def test_attach_unrelated_code_rejected() -> None:
    other = NodeId("other")
    NODES[other] = Node(
        id=other,
        label="Other",
        code="47.37",
        full_label="Other",
        kind=NodeKind.SUBSECTION,
    )
    PATHS[other] = [NODES[other]]

    onto = FakeOntology()
    use_case = AttachEdge(onto, [FakeProvider("g", ["t"])])
    with pytest.raises(InvalidDepth):
        await use_case.execute(AttachEdgeCommand(source_id=L2, target_id=other))


async def test_all_providers_fail_creates_pending_edge() -> None:
    onto = FakeOntology()
    use_case = AttachEdge(onto, [FailingProvider("gigachat"), FailingProvider("yagpt")])

    edge = await use_case.execute(AttachEdgeCommand(source_id=L2, target_id=ORPHAN_LEAF))

    assert edge.descriptions == ()
    assert onto.commits == 1


async def test_no_providers_creates_pending_edge() -> None:
    onto = FakeOntology()
    use_case = AttachEdge(onto, [])

    edge = await use_case.execute(AttachEdgeCommand(source_id=L2, target_id=ORPHAN_LEAF))

    assert edge.descriptions == ()
    assert onto.commits == 1


async def test_attach_leaf_under_leaf_passes_full_chain() -> None:
    onto = FakeOntology()
    deep_target = NodeId("deep")
    deep_node = Node(
        id=deep_target,
        label="Deep",
        code="34.15.23.7",
        full_label="Deep",
        kind=NodeKind.LEAF,
    )
    NODES[deep_target] = deep_node
    PATHS[deep_target] = [deep_node]

    giga = FakeProvider("gigachat", ["t"])
    use_case = AttachEdge(onto, [giga])

    await use_case.execute(AttachEdgeCommand(source_id=L3, target_id=deep_target))

    assert giga.calls == [("Deep", "34.15.23.7", ["ГРНТИ", "Биология", "Генетика", "Геномика"])]
