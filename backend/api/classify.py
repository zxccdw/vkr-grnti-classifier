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


@router.post("/full", response_model=FullCascadeResponse)
def classify_full(
    request: ClassifyRequest,
    classifier: Annotated[CascadeClassifier, Depends(get_classifier)],
) -> FullCascadeResponse:
    results = classifier.classify_full(
        request.text,
        top_k=request.top_k,
        beam_width=5,
    )

    predictions = []
    for path, score in results:
        if len(path) != 3:
            continue

        l1_node, l2_node, l3_node = path
        full_path_label = f"{l1_node.label} → {l2_node.label} → {l3_node.label}"

        level_scores = {
            "L1": 0.9,
            "L2": 0.8,
            "L3": score,
        }

        predictions.append(
            FullCascadePrediction(
                code=l3_node.code or "",
                label=l3_node.label,
                full_label=l3_node.full_label,
                path=[n.code or "" for n in path],
                full_path_label=full_path_label,
                score=score,
                level_scores=level_scores,
            )
        )

    return FullCascadeResponse(predictions=predictions)
