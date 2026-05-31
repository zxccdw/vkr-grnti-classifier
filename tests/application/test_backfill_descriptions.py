from __future__ import annotations

from backend.application.backfill_descriptions import BackfillDescriptions
from backend.domain.entities import Description, Edge, Node, NodeId, NodeKind, Subgraph

L1 = NodeId("l1")
L2 = NodeId("l2")
A = NodeId("a")
B = NodeId("b")

NODES = {
    L1: Node(id=L1, label="Био", code="34", full_label="Био", kind=NodeKind.SECTION),
    L2: Node(id=L2, label="Ген", code="34.15", full_label="Био → Ген", kind=NodeKind.SUBSECTION),
    A: Node(id=A, label="A", code="34.15.1", full_label="Био → Ген → A", kind=NodeKind.LEAF),
    B: Node(id=B, label="B", code="34.15.2", full_label="Био → Ген → B", kind=NodeKind.LEAF),
}

PATHS = {
    L1: [NODES[L1]],
    L2: [NODES[L1], NODES[L2]],
    A: [NODES[L1], NODES[L2], NODES[A]],
    B: [NODES[L1], NODES[L2], NODES[B]],
}


class FakeOntology:
    def __init__(self, pending: list[Edge]) -> None:
        self._pending = list(pending)
        self.updated: list[tuple[NodeId, NodeId, tuple[Description, ...]]] = []
        self.commits = 0

    def pending_edges(self) -> list[Edge]:
        return list(self._pending)

    def get_node(self, id: NodeId) -> Node:
        return NODES[id]

    def get_edge(self, source: NodeId, target: NodeId, predicate: str) -> Edge:
        raise NotImplementedError

    def parents_of(self, id: NodeId) -> list[Node]:
        return []

    def shortest_path(self, id: NodeId) -> list[Node]:
        return list(PATHS[id])

    def subgraph(self, root: NodeId, max_depth: int = 1) -> Subgraph:
        return Subgraph(nodes=(), edges=())

    def add_node(self, node: Node) -> None:
        raise NotImplementedError

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
        self.updated.append((source, target, descriptions))
        self._pending = [
            e
            for e in self._pending
            if not (e.source == source and e.target == target and e.predicate == predicate)
        ]

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


def _edge(source: NodeId, target: NodeId) -> Edge:
    return Edge(source=source, target=target, predicate="contains")


async def test_backfill_fills_all_pending() -> None:
    onto = FakeOntology([_edge(L2, A), _edge(L2, B)])
    use_case = BackfillDescriptions(onto, [FakeProvider("gigachat", ["t"])])

    report = await use_case.execute()

    assert report.filled == 2
    assert report.still_pending == 0
    assert {(s, t) for (s, t, _) in onto.updated} == {(L2, A), (L2, B)}
    assert onto.commits == 1


async def test_backfill_no_providers_reports_all_pending() -> None:
    onto = FakeOntology([_edge(L2, A)])
    use_case = BackfillDescriptions(onto, [])

    report = await use_case.execute()

    assert report.filled == 0
    assert report.still_pending == 1
    assert onto.commits == 0


async def test_backfill_failing_provider_keeps_pending() -> None:
    onto = FakeOntology([_edge(L2, A)])
    use_case = BackfillDescriptions(onto, [FailingProvider("gigachat")])

    report = await use_case.execute()

    assert report.filled == 0
    assert report.still_pending == 1
    assert onto.commits == 0


async def test_backfill_no_pending_no_commit() -> None:
    onto = FakeOntology([])
    use_case = BackfillDescriptions(onto, [FakeProvider("g", ["t"])])

    report = await use_case.execute()

    assert report.filled == 0
    assert report.still_pending == 0
    assert onto.commits == 0
