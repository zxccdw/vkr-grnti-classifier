from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.domain.entities import Description, Edge, Node, NodeId
from backend.domain.errors import InvalidDepth
from backend.domain.ports import LLMProvider, OntologyRepository

PREDICATE_CONTAINS = "http://example.org/competencies#содержит"


@dataclass(frozen=True)
class AttachEdgeCommand:
    source_id: NodeId
    target_id: NodeId
    predicate: str = PREDICATE_CONTAINS


class AttachEdge:
    def __init__(
        self,
        ontology: OntologyRepository,
        providers: list[LLMProvider],
    ) -> None:
        self._ontology = ontology
        self._providers = providers

    async def execute(self, cmd: AttachEdgeCommand) -> Edge:
        source = self._ontology.get_node(cmd.source_id)
        target = self._ontology.get_node(cmd.target_id)
        _validate_hierarchy(source, target)

        chain = self._ontology.shortest_path(cmd.source_id)
        chain_labels = [n.label for n in chain]

        descriptions = await self._describe(target.label, target.code or "", chain_labels)

        edge = Edge(
            source=cmd.source_id,
            target=cmd.target_id,
            predicate=cmd.predicate,
            descriptions=tuple(descriptions),
        )
        self._ontology.add_edge(edge)
        self._ontology.commit()
        return edge

    async def _describe(self, label: str, code: str, chain: list[str]) -> list[Description]:
        if not self._providers:
            return []
        results = await asyncio.gather(
            *(p.describe(label, code, chain) for p in self._providers),
            return_exceptions=True,
        )
        out: list[Description] = []
        for provider, result in zip(self._providers, results, strict=True):
            if not isinstance(result, list):
                continue
            for fragment in result:
                text = fragment.strip()
                if text:
                    out.append(Description(text=text, source=provider.name))
        return out


def _validate_hierarchy(source: Node, target: Node) -> None:
    if target.code is None:
        raise InvalidDepth("target without code cannot be attached")
    if source.code is None:
        if "." in target.code:
            raise InvalidDepth(f"root can only contain L1 nodes (no dots), got '{target.code}'")
        return
    expected_prefix = source.code + "."
    if not target.code.startswith(expected_prefix):
        raise InvalidDepth(
            f"target code '{target.code}' must start with '{expected_prefix}' "
            f"(child of '{source.code}')"
        )
