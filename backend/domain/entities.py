from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NodeKind(Enum):
    ROOT = 0
    SECTION = 1
    SUBSECTION = 2
    LEAF = 3


@dataclass(frozen=True)
class NodeId:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Description:
    text: str
    source: str


@dataclass(frozen=True)
class Node:
    id: NodeId
    label: str
    code: str | None
    full_label: str
    kind: NodeKind


@dataclass(frozen=True)
class Edge:
    source: NodeId
    target: NodeId
    predicate: str
    descriptions: tuple[Description, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Subgraph:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
