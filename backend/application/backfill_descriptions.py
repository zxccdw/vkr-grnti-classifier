from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.domain.entities import Description
from backend.domain.ports import LLMProvider, OntologyRepository


@dataclass(frozen=True)
class BackfillReport:
    filled: int
    still_pending: int


class BackfillDescriptions:
    def __init__(
        self,
        ontology: OntologyRepository,
        providers: list[LLMProvider],
    ) -> None:
        self._ontology = ontology
        self._providers = providers

    async def execute(self) -> BackfillReport:
        pending = self._ontology.pending_edges()
        if not self._providers:
            return BackfillReport(filled=0, still_pending=len(pending))

        filled = 0
        still_pending = 0

        for edge in pending:
            chain = self._ontology.shortest_path(edge.source)
            target = self._ontology.get_node(edge.target)
            descriptions = await self._describe(
                target.label, target.code or "", [n.label for n in chain]
            )
            if descriptions:
                self._ontology.update_edge_descriptions(
                    edge.source, edge.target, edge.predicate, tuple(descriptions)
                )
                filled += 1
            else:
                still_pending += 1

        if filled:
            self._ontology.commit()

        return BackfillReport(filled=filled, still_pending=still_pending)

    async def _describe(self, label: str, code: str, chain: list[str]) -> list[Description]:
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
