"""Strict fixture contract; real source layouts need their own reviewed mapping."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GeographicUnit(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    psgc_code: str = Field(pattern=r"^TEST_[A-Z0-9_]+$")
    name: str = Field(min_length=1, pattern=r"\S")
    classification: Literal["province", "city", "municipality", "barangay"]
    parent_psgc: str | None
    population: int | None = Field(default=None, ge=0)
    release: Literal["synthetic-v1"] = "synthetic-v1"
