from __future__ import annotations

from dataclasses import dataclass

from backend.domain.entities import Node, NodeId, NodeKind
from backend.domain.ports import OntologyRepository

_URI_PREFIX = "http://example.org/competencies#GRNTI_"


@dataclass(frozen=True)
class CreateNodeCommand:
    label: str
    code: str


class CreateNode:
    def __init__(self, ontology: OntologyRepository) -> None:
        self._ontology = ontology

    def execute(self, cmd: CreateNodeCommand) -> Node:
        node = Node(
            id=make_node_id(cmd.code),
            label=cmd.label,
            code=cmd.code,
            full_label=cmd.label,
            kind=kind_by_code(cmd.code),
        )
        self._ontology.add_node(node)
        self._ontology.commit()
        return node


def make_node_id(code: str) -> NodeId:
    return NodeId(_URI_PREFIX + code.replace(".", "_"))


def kind_by_code(code: str | None) -> NodeKind:
    if not code:
        return NodeKind.ROOT
    dots = code.count(".")
    if dots == 0:
        return NodeKind.SECTION
    if dots == 1:
        return NodeKind.SUBSECTION
    return NodeKind.LEAF
