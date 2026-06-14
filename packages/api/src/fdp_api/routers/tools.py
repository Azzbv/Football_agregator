"""Tool catalogue endpoint.

``GET /api/tools`` returns one descriptor per registered step type, including the
config model's JSON schema. The UI renders its dynamic per-step config forms from
this schema, so a newly-registered step type appears in the UI automatically with
no frontend change.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from fdp_unification.transform.registry import registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolDescriptor(BaseModel):
    type: str
    title: str
    config_schema: dict[str, Any]


@router.get("", response_model=list[ToolDescriptor])
async def list_tools() -> list[ToolDescriptor]:
    return [ToolDescriptor.model_validate(d) for d in registry.schemas()]
