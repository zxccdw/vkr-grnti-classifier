from __future__ import annotations

from dataclasses import dataclass

from backend.application.attach_edge import AttachEdge, AttachEdgeCommand
from backend.application.create_node import CreateNode, CreateNodeCommand, make_node_id
from backend.domain.entities import Edge, Node, NodeId
from backend.domain.ports import LLMProvider, OntologyRepository


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
        self._create.execute(CreateNodeCommand(label=cmd.label, code=cmd.code))
        edge = await self._attach.execute(
            AttachEdgeCommand(source_id=cmd.parent_id, target_id=new_id)
        )
        node = self._ontology.get_node(new_id)
        return AddNodeResult(node=node, edge=edge)
