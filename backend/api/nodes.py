from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from backend.application.add_node import AddNode, AddNodeCommand
from backend.application.attach_edge import PREDICATE_CONTAINS, AttachEdge, AttachEdgeCommand
from backend.application.backfill_descriptions import BackfillDescriptions
from backend.application.create_node import CreateNode, CreateNodeCommand
from backend.application.merge_duplicates import MergeDuplicatesByLabel
from backend.core.dependencies import (
    get_add_node_use_case,
    get_attach_edge_use_case,
    get_backfill_use_case,
    get_create_node_use_case,
    get_merge_duplicates_use_case,
    get_ontology_repository,
)
from backend.domain.entities import Edge, Node, NodeId
from backend.domain.errors import (
    EdgeAlreadyExists,
    EdgeNotFound,
    InvalidDepth,
    NodeAlreadyExists,
    NodeNotFound,
)
from backend.infrastructure.json_ontology import JsonOntologyRepository
from backend.schemas.node_schemas import (
    AddNodeUnderParentRequest,
    AttachEdgeRequest,
    BackfillResponse,
    CreateNodeRequest,
    DescriptionOut,
    EdgeOut,
    NodeOut,
    NodeWithEdgeOut,
    ParentsOut,
    SubgraphOut,
)

router = APIRouter(tags=["ontology"])


@router.post("/nodes", response_model=NodeOut, status_code=201)
def create_node(
    request: CreateNodeRequest,
    use_case: Annotated[CreateNode, Depends(get_create_node_use_case)],
) -> NodeOut:
    try:
        node = use_case.execute(CreateNodeCommand(label=request.label, code=request.code))
    except NodeAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _node_to_dto(node)


@router.post("/nodes/with-edge", response_model=NodeWithEdgeOut, status_code=201)
async def create_node_with_edge(
    request: AddNodeUnderParentRequest,
    use_case: Annotated[AddNode, Depends(get_add_node_use_case)],
) -> NodeWithEdgeOut:
    try:
        result = await use_case.execute(
            AddNodeCommand(
                parent_id=NodeId(request.parent_id),
                label=request.label,
                code=request.code,
            )
        )
    except NodeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except NodeAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidDepth as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return NodeWithEdgeOut(node=_node_to_dto(result.node), edge=_edge_to_dto(result.edge))


@router.post("/edges", response_model=EdgeOut, status_code=201)
async def attach_edge(
    request: AttachEdgeRequest,
    use_case: Annotated[AttachEdge, Depends(get_attach_edge_use_case)],
) -> EdgeOut:
    try:
        edge = await use_case.execute(
            AttachEdgeCommand(
                source_id=NodeId(request.source_id),
                target_id=NodeId(request.target_id),
                predicate=request.predicate or PREDICATE_CONTAINS,
            )
        )
    except NodeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except EdgeAlreadyExists as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidDepth as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return _edge_to_dto(edge)


@router.delete("/nodes", status_code=204)
def delete_node(
    node_id: Annotated[str, Query(..., min_length=1)],
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
) -> None:
    try:
        repo.remove_node(NodeId(node_id))
    except NodeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.delete("/edges", status_code=204)
def delete_edge(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
    source: Annotated[str, Query(..., min_length=1)],
    target: Annotated[str, Query(..., min_length=1)],
    predicate: Annotated[str, Query(...)] = PREDICATE_CONTAINS,
) -> None:
    try:
        repo.remove_edge(NodeId(source), NodeId(target), predicate)
    except EdgeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/export/ontology.json")
def export_ontology(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
) -> FileResponse:
    return FileResponse(
        path=repo.export_path(),
        media_type="application/json",
        filename="ontology_grnti.json",
    )


@router.post("/import/ontology")
async def import_ontology(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
    file: Annotated[UploadFile, File(...)],
) -> dict:
    raw = await file.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {e.msg}") from e
    try:
        repo.import_payload(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "nodes": len(payload["nodes"]),
        "links": len(payload["links"]),
    }


@router.get("/pending", response_model=list[NodeOut])
def list_pending(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
) -> list[NodeOut]:
    edges = repo.pending_edges()
    seen: set[str] = set()
    nodes: list[NodeOut] = []
    for edge in edges:
        if edge.target.value in seen:
            continue
        seen.add(edge.target.value)
        try:
            nodes.append(_node_to_dto(repo.get_node(edge.target)))
        except Exception:
            pass
    return nodes


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_descriptions(
    use_case: Annotated[BackfillDescriptions, Depends(get_backfill_use_case)],
    batch: Annotated[int, Query(ge=1, le=1000)] = 5,
) -> BackfillResponse:
    report = await use_case.execute(batch=batch)
    return BackfillResponse(filled=report.filled, still_pending=report.still_pending)


@router.post("/merge-duplicates")
def merge_duplicates(
    use_case: Annotated[MergeDuplicatesByLabel, Depends(get_merge_duplicates_use_case)],
) -> dict:
    report = use_case.execute()
    return {
        "groups_merged": report.groups_merged,
        "nodes_removed": report.nodes_removed,
        "edges_redirected": report.edges_redirected,
    }


@router.get("/subgraph", response_model=SubgraphOut)
def get_subgraph(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
    root_id: Annotated[str, Query(..., min_length=1)],
    max_depth: Annotated[int, Query(ge=0, le=10)] = 2,
) -> SubgraphOut:
    try:
        sg = repo.subgraph(NodeId(root_id), max_depth=max_depth)
    except NodeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return SubgraphOut(
        nodes=[_node_to_dto(n) for n in sg.nodes],
        edges=[_edge_to_dto(e) for e in sg.edges],
    )


@router.get("/search", response_model=list[NodeOut])
def search_nodes(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
    q: Annotated[str, Query(..., min_length=1, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[NodeOut]:
    return [_node_to_dto(n) for n in repo.search(q, limit=limit)]


@router.get("/parents", response_model=ParentsOut)
def list_parents(
    repo: Annotated[JsonOntologyRepository, Depends(get_ontology_repository)],
    node_id: Annotated[str, Query(..., min_length=1)],
) -> ParentsOut:
    try:
        parents = repo.parents_of(NodeId(node_id))
    except NodeNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    edges: list[EdgeOut] = []
    for parent in parents:
        try:
            edge = repo.get_edge(parent.id, NodeId(node_id), PREDICATE_CONTAINS)
        except EdgeNotFound:
            continue
        edges.append(_edge_to_dto(edge))
    return ParentsOut(parents=edges)


def _node_to_dto(node: Node) -> NodeOut:
    return NodeOut(
        id=node.id.value,
        label=node.label,
        code=node.code,
        full_label=node.full_label,
        kind=node.kind.name,
    )


def _edge_to_dto(edge: Edge) -> EdgeOut:
    return EdgeOut(
        source=edge.source.value,
        target=edge.target.value,
        predicate=edge.predicate,
        descriptions=[DescriptionOut(text=d.text, source=d.source) for d in edge.descriptions],
    )
