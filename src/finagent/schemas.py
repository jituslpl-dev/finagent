"""Strict wire contracts; unknown fields and nonfinite quantities are rejected."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, model_validator

Metric = Literal["revenue_growth", "operating_margin", "debt_to_equity", "free_cash_flow"]
ToolName = Literal["sql", "documents", "market"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResearchRequest(Contract):
    question: str = Field(min_length=5, max_length=2000)
    symbols: list[str] = Field(min_length=1, max_length=5)
    as_of: date

    @model_validator(mode="after")
    def symbols_valid(self):
        import re

        if len(set(self.symbols)) != len(self.symbols):
            raise ValueError("duplicate symbols")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", s) for s in self.symbols):
            raise ValueError("symbols must be uppercase ticker-like identifiers")
        return self


class Plan(Contract):
    tools: list[ToolName] = Field(min_length=1, max_length=3)
    metrics: list[Metric] = Field(max_length=4)
    rationale: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def coherent(self):
        if len(set(self.tools)) != len(self.tools) or len(set(self.metrics)) != len(self.metrics):
            raise ValueError("duplicate plan steps")
        if self.metrics and "sql" not in self.tools:
            raise ValueError("quantitative metrics require SQL evidence")
        return self


class Evidence(Contract):
    id: str
    kind: ToolName
    symbol: str
    available_on: date
    source: str
    payload: dict


class ToolEvent(Contract):
    tool: ToolName
    symbol: str
    attempts: StrictInt = Field(ge=1, le=3)
    ok: bool
    error: str | None


class Calculation(Contract):
    symbol: str
    metric: Metric
    value: FiniteFloat | None
    unit: Literal["percent", "ratio", "USD million"]
    evidence_ids: list[str]
    reason: str | None


class Finding(Contract):
    text: str = Field(min_length=1, max_length=1500)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class Narrative(Contract):
    findings: list[Finding] = Field(max_length=15)
    limitations: list[str] = Field(min_length=1, max_length=10)


class Verification(Contract):
    accepted: bool
    issues: list[str]
    checks: list[str]


class Report(Contract):
    request: ResearchRequest
    plan: Plan
    evidence: list[Evidence]
    calculations: list[Calculation]
    narrative: Narrative
    verification: Verification
    tool_events: list[ToolEvent]
    trajectory: list[str]
    analysis_attempts: StrictInt
    mode: Literal["offline", "llm"]
