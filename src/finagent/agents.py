"""Four focused roles: planner, retriever, analyst and independent verifier."""

from dataclasses import dataclass, field

from finagent.llm import StructuredModel
from finagent.quant import calculate
from finagent.retry import RetryPolicy, ToolUnavailable, TransientError
from finagent.schemas import (
    Calculation,
    Evidence,
    Finding,
    Narrative,
    Plan,
    ResearchRequest,
    ToolEvent,
    Verification,
)
from finagent.tools import ResearchTool

LIMITATIONS = [
    "Research evidence is limited to the selected sources and their availability dates.",
    "Financial ratios are descriptive; this workflow does not execute trades or estimate investment returns.",
    "Document findings are extractive evidence, not independently established causal conclusions.",
]


@dataclass
class Planner:
    model: StructuredModel | None = None

    def run(self, request: ResearchRequest) -> Plan:
        if self.model:
            return self.model.generate("planner", request.model_dump(mode="json"), Plan)
        question = request.question.lower()
        metrics = []
        for metric, terms in {
            "revenue_growth": ("growth", "revenue"),
            "operating_margin": ("margin", "profitability"),
            "debt_to_equity": ("debt", "leverage"),
            "free_cash_flow": ("cash flow", "fcf"),
        }.items():
            if any(term in question for term in terms):
                metrics.append(metric)
        tools = ["sql"] if metrics else []
        if any(term in question for term in ("risk", "management", "document", "strategy")):
            tools.append("documents")
        if any(term in question for term in ("price", "quote", "market", "close")):
            tools.append("market")
        if not tools:
            tools, metrics = ["sql", "documents"], ["revenue_growth", "operating_margin"]
        return Plan(
            tools=tools,
            metrics=metrics,
            rationale="Bounded keyword routing; tools match the requested evidence types.",
        )


@dataclass
class Retriever:
    tools: dict[str, ResearchTool]
    retry: RetryPolicy = field(default_factory=RetryPolicy)

    def run(self, request: ResearchRequest, plan: Plan) -> tuple[list[Evidence], list[ToolEvent]]:
        evidence, events = [], []
        for name in plan.tools:
            for symbol in request.symbols:
                attempts = 0

                def call(name=name, symbol=symbol):
                    nonlocal attempts
                    attempts += 1
                    return self.tools[name].retrieve(symbol, request.as_of, request.question)

                try:
                    rows, _ = self.retry.run(call)
                    evidence.extend(rows)
                    events.append(
                        ToolEvent(tool=name, symbol=symbol, attempts=attempts, ok=True, error=None)
                    )
                except (ToolUnavailable, TransientError):
                    events.append(
                        ToolEvent(
                            tool=name,
                            symbol=symbol,
                            attempts=attempts,
                            ok=False,
                            error="Evidence tool unavailable",
                        )
                    )
        return list({e.id: e for e in evidence}.values()), events


def allowed_findings(sources: list[Evidence], calculations: list[Calculation]) -> list[Finding]:
    findings = []
    for row in sources:
        if row.kind == "documents":
            findings.append(Finding(text=row.payload["text"], evidence_ids=[row.id]))
        elif row.kind == "market":
            findings.append(
                Finding(
                    text=f"{row.symbol} daily close on {row.payload['date']}: {row.payload['close']:.4f} {row.payload.get('currency', 'unspecified currency')}.",
                    evidence_ids=[row.id],
                )
            )
    for value in calculations:
        if value.value is not None:
            findings.append(
                Finding(
                    text=f"{value.symbol} {value.metric}: {value.value:.6g} {value.unit}.",
                    evidence_ids=value.evidence_ids,
                )
            )
    return findings


@dataclass
class Analyst:
    model: StructuredModel | None = None

    def run(
        self, request: ResearchRequest, plan: Plan, sources: list[Evidence], feedback: list[str]
    ) -> tuple[list[Calculation], Narrative]:
        calculations = calculate(request, plan, sources)
        allowed = allowed_findings(sources, calculations)
        if self.model:
            narrative = self.model.generate(
                "analyst",
                {
                    "request": request.model_dump(mode="json"),
                    "allowed_findings": [f.model_dump() for f in allowed],
                    "verification_feedback": feedback,
                    "limitations": LIMITATIONS,
                },
                Narrative,
            )
            narrative = narrative.model_copy(update={"limitations": LIMITATIONS})
        else:
            narrative = Narrative(findings=allowed[:15], limitations=LIMITATIONS)
        return calculations, narrative


class Verifier:
    """Recomputes financial arithmetic and enforces exact evidence support."""

    def run(
        self,
        request: ResearchRequest,
        plan: Plan,
        sources: list[Evidence],
        calculations: list[Calculation],
        narrative: Narrative,
        events: list[ToolEvent],
    ) -> Verification:
        issues = []
        ids = {e.id for e in sources}
        if any(e.available_on > request.as_of for e in sources):
            issues.append("Future evidence violates as-of boundary")
        if any(e.symbol not in request.symbols or e.kind not in plan.tools for e in sources):
            issues.append("Evidence outside research scope")
        if len(ids) != len(sources):
            issues.append("Duplicate evidence identifiers")
        expected = calculate(request, plan, sources)
        if [c.model_dump() for c in calculations] != [c.model_dump() for c in expected]:
            issues.append("Financial calculations do not reconcile")
        if any(c.value is None for c in calculations):
            issues.append("Requested financial metric lacks defined evidence")
        permitted = {(f.text, tuple(f.evidence_ids)) for f in allowed_findings(sources, expected)}
        if not narrative.findings:
            issues.append("No supported findings")
        for finding in narrative.findings:
            if not set(finding.evidence_ids) <= ids:
                issues.append("Unknown citation")
            if (finding.text, tuple(finding.evidence_ids)) not in permitted:
                issues.append("Finding is not an approved evidence quote or calculation")
        for name in plan.tools:
            for symbol in request.symbols:
                if not any(e.kind == name and e.symbol == symbol for e in sources):
                    issues.append(f"Missing {name} evidence for {symbol}")
        if any(not e.ok for e in events):
            issues.append("One or more tools exhausted their availability budget")
        return Verification(
            accepted=not issues,
            issues=list(dict.fromkeys(issues)),
            checks=["schema", "as_of", "scope", "arithmetic", "citation_support", "tool_coverage"],
        )
