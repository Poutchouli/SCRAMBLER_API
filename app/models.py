from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    EMPTY = "empty"


class FieldConstraint(BaseModel):
    name: str
    type: FieldType
    nullable: bool
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[str]] = None
    null_fraction: float = Field(0, ge=0, le=1)
    date_min: Optional[str] = None  # ISO date/datetime strings when applicable
    date_max: Optional[str] = None


class ProfileResult(BaseModel):
    row_count: int
    fields: List[FieldConstraint]
    encoding: str = "utf-8"
    delimiter: str = ","
    decimal_separator: str = "."


class GenerateOptions(BaseModel):
    rows: int
    seed: Optional[int] = None
    mode: str = "fast"
