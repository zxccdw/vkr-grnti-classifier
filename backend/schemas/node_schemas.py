from __future__ import annotations

from pydantic import BaseModel, Field


class CreateNodeRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=300)
    code: str = Field(..., min_length=1, max_length=50)


class AddNodeUnderParentRequest(BaseModel):
    parent_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1, max_length=300)
    code: str = Field(..., min_length=1, max_length=50)


class AttachEdgeRequest(BaseModel):
    source_id: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    predicate: str | None = None


class DescriptionOut(BaseModel):
    text: str
    source: str


class NodeOut(BaseModel):
    id: str
    label: str
    code: str | None
    full_label: str
    kind: str


class EdgeOut(BaseModel):
    source: str
    target: str
    predicate: str
    descriptions: list[DescriptionOut]


class NodeWithEdgeOut(BaseModel):
    node: NodeOut
    edge: EdgeOut


class SubgraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class BackfillResponse(BaseModel):
    filled: int
    still_pending: int


class ParentsOut(BaseModel):
    parents: list[EdgeOut]
