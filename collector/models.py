"""Strict geographic records shared by real imports and isolated tests."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GeographicUnit(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    psgc_code: str = Field(pattern=r"^[0-9]{10}$")
    name: str = Field(min_length=1, pattern=r"\S")
    classification: Literal["province", "city", "municipality", "barangay"]
    parent_psgc: str | None = Field(default=None, pattern=r"^[0-9]{10}$")
    population: int | None = Field(default=None, ge=0)
    release: str = Field(min_length=1, pattern=r"\S")
