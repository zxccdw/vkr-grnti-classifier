from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from backend.domain.entities import Edge, Node, NodeId, NodeKind
from backend.domain.ports import OntologyRepository

PREDICATE_CONTAINS = "http://example.org/competencies#содержит"
_CONCEPT_PREFIX = "http://example.org/competencies#CONCEPT_"


@dataclass(frozen=True)
class MergeReport:
    groups_merged: int
    nodes_removed: int
    edges_redirected: int


class MergeDuplicatesByLabel:
    def __init__(self, ontology: OntologyRepository) -> None:
        self._ontology = ontology

    def execute(self) -> MergeReport:
        nodes = self._ontology.all_nodes()
        groups = _group_duplicates(nodes)

        groups_merged = 0
        nodes_removed = 0
        edges_redirected = 0

        for (label, suffix), members in groups.items():
            canonical_id = _make_concept_id(suffix, label)
            redirected = self._merge_group(canonical_id, label, members)
            groups_merged += 1
            nodes_removed += len(members)
            edges_redirected += redirected

        if groups_merged:
            self._ontology.commit()
        return MergeReport(
            groups_merged=groups_merged,
            nodes_removed=nodes_removed,
            edges_redirected=edges_redirected,
        )

    def _merge_group(self, canonical_id: NodeId, label: str, members: list[Node]) -> int:
        canonical = Node(
            id=canonical_id,
            label=label,
            code=None,
            full_label=label,
            kind=NodeKind.LEAF,
        )
        self._ontology.add_node(canonical)

        redirected = 0
        for old in members:
            parents = self._ontology.parents_of(old.id)
            for parent in parents:
                try:
                    edge = self._ontology.get_edge(parent.id, old.id, PREDICATE_CONTAINS)
                except Exception:
                    continue
                self._ontology.remove_edge(parent.id, old.id, PREDICATE_CONTAINS)
                self._ontology.add_edge(
                    Edge(
                        source=parent.id,
                        target=canonical_id,
                        predicate=PREDICATE_CONTAINS,
                        descriptions=edge.descriptions,
                    )
                )
                redirected += 1
            self._ontology.remove_node(old.id)
        return redirected


def _group_duplicates(nodes: list[Node]) -> dict[tuple[str, str], list[Node]]:
    by_key: dict[tuple[str, str], list[Node]] = defaultdict(list)
    for n in nodes:
        if not n.code or "." not in n.code:
            continue
        suffix = n.code.rsplit(".", 1)[-1]
        if not n.label.strip():
            continue
        by_key[(n.label.strip(), suffix)].append(n)
    return {k: v for k, v in by_key.items() if len(v) >= 2}


def _make_concept_id(suffix: str, label: str) -> NodeId:
    slug = label.strip().replace(" ", "_").replace(".", "").replace(",", "").replace("/", "_")
    return NodeId(f"{_CONCEPT_PREFIX}{suffix}_{slug}")
