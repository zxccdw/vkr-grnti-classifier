from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from backend.core.dependencies import get_classifier
from backend.schemas.requests import ClassifyLevelRequest, ClassifyRequest
from backend.schemas.responses import (
    ClassifyResponse,
    FullCascadePrediction,
    FullCascadeResponse,
    Prediction,
)
from backend.services.cascade import CascadeClassifier

router = APIRouter(prefix="/classify", tags=["classification"])


@router.post("/l1", response_model=ClassifyResponse)
def classify_l1(
    request: ClassifyRequest,
    classifier: Annotated[CascadeClassifier, Depends(get_classifier)],
) -> ClassifyResponse:
    results = classifier.classify_l1(request.text, top_k=request.top_k)

    predictions = [
        Prediction(
            code=node.code or "",
            label=node.label,
            full_label=node.full_label,
            score=score,
            depth=node.depth,
        )
        for node, score in results
    ]

    return ClassifyResponse(predictions=predictions)


@router.post("/l2", response_model=ClassifyResponse)
def classify_l2(
    request: ClassifyLevelRequest,
    classifier: Annotated[CascadeClassifier, Depends(get_classifier)],
) -> ClassifyResponse:
    if not request.parent_code:
        raise HTTPException(status_code=400, detail="parent_code required")

    try:
        results = classifier.classify_l2(
            request.text,
            l1_code=request.parent_code,
            top_k=request.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    predictions = [
        Prediction(
            code=node.code or "",
            label=node.label,
            full_label=node.full_label,
            score=score,
            depth=node.depth,
        )
        for node, score in results
    ]

    return ClassifyResponse(predictions=predictions)


@router.post("/l3", response_model=ClassifyResponse)
def classify_l3(
    request: ClassifyLevelRequest,
    classifier: Annotated[CascadeClassifier, Depends(get_classifier)],
) -> ClassifyResponse:
    if not request.parent_code:
        raise HTTPException(status_code=400, detail="parent_code required")

    try:
        results = classifier.classify_l3(
            request.text,
            l2_code=request.parent_code,
            top_k=request.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    predictions = [
        Prediction(
            code=node.code or "",
            label=node.label,
            full_label=node.full_label,
            score=score,
            depth=node.depth,
        )
        for node, score in results
    ]

    return ClassifyResponse(predictions=predictions)


@router.post("/by-parent", response_model=ClassifyResponse)
def classify_by_parent(
    request: ClassifyLevelRequest,
    classifier: Annotated[CascadeClassifier, Depends(get_classifier)],
) -> ClassifyResponse:
    if not request.parent_code:
        raise HTTPException(status_code=400, detail="parent_code required")

    try:
        parent_node = classifier.ontology.code_to_node(request.parent_code)
        if parent_node is None:
            raise HTTPException(
                status_code=404, detail=f"Parent code '{request.parent_code}' not found"
            )

        results = classifier.classify_level(
            request.text,
            parent_node_id=parent_node.id,
            top_k=request.top_k,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    predictions = [
        Prediction(
            code=node.code or "",
            label=node.label,
            full_label=node.full_label,
            score=score,
            depth=node.depth,
        )
        for node, score in results
    ]

    return ClassifyResponse(predictions=predictions)


@router.post("/full", response_model=FullCascadeResponse)
def classify_full(
    request: ClassifyRequest,
    classifier: Annotated[CascadeClassifier, Depends(get_classifier)],
) -> FullCascadeResponse:
    results = classifier.classify_full(
        request.text,
        top_k=request.top_k,
        beam_width=max(request.top_k, 12),  # beam_width >= top_k to find enough paths
    )

    predictions = []
    for path, score in results:
        if not path:
            continue

        leaf_node = path[-1]
        full_path_label = " → ".join(n.label for n in path)

        level_scores = {f"L{i + 1}": score for i, n in enumerate(path)}

        predictions.append(
            FullCascadePrediction(
                code=leaf_node.code or "",
                label=leaf_node.label,
                full_label=leaf_node.full_label,
                path=[n.code or "" for n in path],
                full_path_label=full_path_label,
                score=score,
                level_scores=level_scores,
            )
        )

    return FullCascadeResponse(predictions=predictions)
