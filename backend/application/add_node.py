from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from backend.application.attach_edge import PREDICATE_CONTAINS, AttachEdge, AttachEdgeCommand
from backend.application.create_node import CreateNode, CreateNodeCommand, make_node_id
from backend.domain.entities import Edge, Node, NodeId
from backend.domain.ports import LLMProvider, OntologyRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AddNodeCommand:
    parent_id: NodeId
    label: str
    code: str


@dataclass(frozen=True)
class AddNodeResult:
    node: Node
    edge: Edge


class AddNode:
    def __init__(
        self,
        ontology: OntologyRepository,
        providers: list[LLMProvider],
    ) -> None:
        self._ontology = ontology
        self._providers = providers
        self._create = CreateNode(ontology)
        self._attach = AttachEdge(ontology, providers)

    async def execute(self, cmd: AddNodeCommand) -> AddNodeResult:
        self._ontology.get_node(cmd.parent_id)
        new_id = make_node_id(cmd.code)
        chain = self._ontology.shortest_path(cmd.parent_id)
        full_label = " → ".join([n.label for n in chain] + [cmd.label])
        self._create.execute(
            CreateNodeCommand(label=cmd.label, code=cmd.code, full_label=full_label)
        )
        edge = Edge(
            source=cmd.parent_id,
            target=new_id,
            predicate=PREDICATE_CONTAINS,
            descriptions=(),
        )
        self._ontology.add_edge(edge)
        self._ontology.commit()
        node = self._ontology.get_node(new_id)
        if self._providers:
            asyncio.create_task(self._backfill(cmd.parent_id, new_id))
        return AddNodeResult(node=node, edge=edge)

    async def _backfill(self, parent_id: NodeId, target_id: NodeId) -> None:
        try:
            target = self._ontology.get_node(target_id)
            chain = self._ontology.shortest_path(parent_id)
            descriptions = await self._attach._describe(
                target.label, target.code or "", [n.label for n in chain]
            )
            if descriptions:
                self._ontology.update_edge_descriptions(
                    parent_id, target_id, PREDICATE_CONTAINS, tuple(descriptions)
                )
                self._ontology.commit()
        except Exception as e:
            logger.warning("background llm generation failed: %r", e)
