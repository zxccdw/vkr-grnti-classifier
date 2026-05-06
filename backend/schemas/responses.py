from pydantic import BaseModel, Field, field_serializer


class Prediction(BaseModel):
    code: str
    label: str
    full_label: str
    score: float = Field(..., ge=0, le=1)
    depth: int

    @field_serializer("score")
    def round_score(self, value: float) -> float:
        return round(value, 2)


class ClassifyResponse(BaseModel):
    predictions: list[Prediction]


class FullCascadePrediction(BaseModel):
    code: str
    label: str
    full_label: str
    path: list[str]
    full_path_label: str
    score: float = Field(..., ge=0, le=1)
    level_scores: dict[str, float]

    @field_serializer("score")
    def round_score(self, value: float) -> float:
        return round(value, 2)

    @field_serializer("level_scores")
    def round_level_scores(self, value: dict[str, float]) -> dict[str, float]:
        return {k: round(v, 2) for k, v in value.items()}


class FullCascadeResponse(BaseModel):
    predictions: list[FullCascadePrediction]


class HealthResponse(BaseModel):
    status: str = Field("ok")
    model_loaded: bool
    ontology_loaded: bool
