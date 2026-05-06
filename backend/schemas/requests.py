from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)


class ClassifyLevelRequest(BaseModel):
    text: str = Field(..., min_length=1)
    parent_code: str | None = Field(None)
    top_k: int = Field(5, ge=1, le=20)
