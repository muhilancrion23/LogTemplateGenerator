from typing import Optional, Literal
from pydantic import BaseModel, Field


class SetPoints(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class ParameterModel(BaseModel):
    asset: str = ""
    description: str
    type: Literal["number", "text", "boolean"] = "number"
    required: bool = True
    default_value: str = ""
    setpoints: SetPoints = Field(
        default_factory=SetPoints
    )


class ParameterList(BaseModel):
    parameters: list[ParameterModel]


class TemplateSchema(BaseModel):
    """Full saved template stored in MongoDB."""
    name: str
    description: str = ""
    parameters: list[ParameterModel]
    created_at: Optional[str] = None
    source_filename: Optional[str] = None