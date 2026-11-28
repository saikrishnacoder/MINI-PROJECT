"""Pydantic contracts for the Phase 4 backend engine.

The engine builds a :class:`GenerationPlan` from the project's approved
requirements and validates it before writing a single file; the harness run is
validated through :class:`GenerationResult` before it is persisted. The same
pydantic discipline is generated into the app itself (``backendapp/config.py``
validates the database configuration at process start).
"""
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ENDPOINT_RE = re.compile(r"^(GET|POST|PATCH|PUT|DELETE) /api/\S+$")
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CLASS_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_RID_RE = re.compile(r"^REQ-\d+$")


class ResourceSpec(BaseModel):
    """One generated resource, traced to exactly one approved requirement."""

    model_config = ConfigDict(frozen=True)

    rid: str = Field(min_length=3, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    priority: str = Field(default="should", max_length=16)
    resource: str
    route: str
    class_name: str
    endpoints: list[str] = Field(min_length=1)
    permission: str = "IsOwnerOrRole"
    search_fields: list[str] = Field(default_factory=lambda: ["name", "description"])
    ordering_fields: list[str] = Field(
        default_factory=lambda: ["name", "created_at", "updated_at"]
    )
    capabilities: list[str] = Field(default_factory=lambda: ["crud"])
    writable_fields: list[str] = Field(default_factory=lambda: ["name", "description", "attachment"])
    readable_fields: list[str] = Field(
        default_factory=lambda: ["id", "name", "description", "attachment", "attachment_url",
                                 "status", "created_at", "updated_at"]
    )

    @field_validator("rid")
    @classmethod
    def _rid_format(cls, value: str) -> str:
        if not _RID_RE.match(value):
            raise ValueError("requirement id must look like REQ-001")
        return value

    @field_validator("resource", "route")
    @classmethod
    def _snake_case(cls, value: str) -> str:
        if not _SNAKE_RE.match(value):
            raise ValueError(f"{value!r} is not a snake_case resource name")
        return value

    @field_validator("class_name")
    @classmethod
    def _class_name(cls, value: str) -> str:
        if not _CLASS_RE.match(value):
            raise ValueError(f"{value!r} is not a PascalCase class name")
        return value

    @field_validator("endpoints")
    @classmethod
    def _endpoints(cls, value: list[str]) -> list[str]:
        for endpoint in value:
            if not _ENDPOINT_RE.match(endpoint):
                raise ValueError(f"malformed endpoint {endpoint!r}")
        return value


class GenerationPlan(BaseModel):
    """Everything the engine is about to generate for one project."""

    model_config = ConfigDict(frozen=True)

    project_id: int = Field(gt=0)
    resources: list[ResourceSpec] = Field(min_length=1)

    @field_validator("resources")
    @classmethod
    def _unique_routes_and_rids(cls, value: list[ResourceSpec]) -> list[ResourceSpec]:
        routes = [r.route for r in value]
        rids = [r.rid for r in value]
        if len(set(routes)) != len(routes):
            raise ValueError("duplicate resource routes in generation plan")
        if len(set(rids)) != len(rids):
            raise ValueError("duplicate requirement ids in generation plan")
        return value


class HarnessRun(BaseModel):
    """Result of running the generated app's own test suite on one database."""

    model_config = ConfigDict(frozen=True)

    database: str = Field(pattern=r"^(sqlite|mysql)$")
    passed: bool
    output: str = ""


class GenerationResult(BaseModel):
    """Validated summary handed back to the API layer and persisted."""

    model_config = ConfigDict(frozen=True)

    project_id: int
    status: str = Field(pattern=r"^(success|failed)$")
    resources: list[ResourceSpec]
    tests_passed: bool
    databases_tested: list[str]
    outputs: list[HarnessRun] = Field(default_factory=list)
