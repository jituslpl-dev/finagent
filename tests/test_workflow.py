import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from finagent.agents import Analyst, Planner, Retriever, Verifier
from finagent.evaluation import evaluate
from finagent.factory import create_engine
from finagent.fixtures import initialize
from finagent.schemas import Finding, Narrative, Plan, ResearchRequest
from finagent.tools import DocumentTool, FixtureMarketTool, SqlTool
from finagent.workflow import ResearchEngine


def request(
    question="Compare revenue growth, operating margin, debt, cash flow and risk factors",
    symbols=None,
):
    return ResearchRequest(
        question=question, symbols=symbols or ["ALFA", "BETA"], as_of=date(2025, 3, 5)
    )


def tools(root):
    initialize(root)
    return {
        "sql": SqlTool(root / "fundamentals.sqlite"),
        "documents": DocumentTool(root / "documents.json"),
        "market": FixtureMarketTool(root / "market.json"),
    }


def test_full_graph_golden_numbers_and_provenance(tmp_path):
    with create_engine(tmp_path) as engine:
        report = engine.run(request(), "complete")
        assert report["verification"]["accepted"]
        assert report["trajectory"] == ["planner", "retriever", "analyst", "verifier"]
        values = {(c["symbol"], c["metric"]): c["value"] for c in report["calculations"]}
        assert values["ALFA", "revenue_growth"] == 25
        assert values["BETA", "operating_margin"] == 5
        assert values["ALFA", "free_cash_flow"] == 22
        assert values["BETA", "debt_to_equity"] == 1.5
        assert all(e["available_on"] <= "2025-03-05" for e in report["evidence"])
        assert "future-risk" not in json.dumps(report)
        memory = engine.memory("complete")
        assert memory["checkpoint_count"] >= 5
        assert not memory["next"]


def test_resume_in_new_process_instance(tmp_path):
    with create_engine(tmp_path) as first:
        paused = first.run(request(), "resume-test", pause=True)
        assert paused["trajectory"] == ["planner", "retriever"]
    with create_engine(tmp_path) as second:
        assert second.memory("resume-test")["next"] == ["analyst"]
        result = second.resume("resume-test")
        assert result["verification"]["accepted"]
        assert second.resume("resume-test") == result
        with pytest.raises(ValueError, match="already exists"):
            second.run(request(), "resume-test")
        with pytest.raises(ValueError, match="Unknown"):
            second.resume("unknown")


def test_zero_denominator_and_missing_evidence_abstain(tmp_path):
    with create_engine(tmp_path) as engine:
        report = engine.run(request("Analyze revenue growth and debt", ["ZERO"]), "zero")
        assert not report["verification"]["accepted"]
        assert all(c["value"] is None for c in report["calculations"])
        assert report["analysis_attempts"] == 2
        missing = engine.run(request("Retrieve risk factors", ["MISSING"]), "missing")
        assert not missing["verification"]["accepted"]


def test_schema_and_thread_limits():
    for symbols in (["alfa"], ["ALFA", "ALFA"], ["X'; DROP TABLE fundamentals;--"]):
        with pytest.raises(ValidationError):
            request(symbols=symbols)
    with pytest.raises(ValidationError):
        Plan(tools=["documents"], metrics=["operating_margin"], rationale="invalid")
    with pytest.raises(ValidationError):
        Plan(tools=["sql"], metrics=[], rationale="x", arbitrary_sql="DROP TABLE x")
    with pytest.raises(ValueError):
        ResearchEngine.config("../escape")


def test_sql_parameterization_and_date_filter(tmp_path):
    t = tools(tmp_path)["sql"]
    assert t.retrieve("ALFA' OR 1=1--", date(2025, 3, 5)) == []
    rows = t.retrieve("ALFA", date(2024, 3, 1))
    assert len(rows) == 1 and rows[0].payload["period"] == 2023
    assert t.retrieve("ALFA", date(2023, 1, 1)) == []


def test_document_retrieval_excludes_future_and_other_symbol(tmp_path):
    t = tools(tmp_path)["documents"]
    rows = t.retrieve("ALFA", date(2025, 3, 5), "supplier risk concentration")
    assert rows[0].payload["document_id"] == "alfa-risk"
    assert {r.symbol for r in rows} == {"ALFA"}
    assert all(r.available_on <= date(2025, 3, 5) for r in rows)
    assert t.retrieve("ALFA", date(2023, 1, 1), "risk") == []


def test_verifier_rejects_fabricated_quote_and_numbers(tmp_path):
    with create_engine(tmp_path) as engine:
        state = engine.run(request(), "truth")
        from finagent.schemas import Calculation, Evidence, ToolEvent

        evidence = [Evidence.model_validate(e) for e in state["evidence"]]
        calculations = [Calculation.model_validate(c) for c in state["calculations"]]
        calculations[0].value = 900
        narrative = Narrative(
            findings=[Finding(text="Guaranteed returns", evidence_ids=["fake"])],
            limitations=["test"],
        )
        result = Verifier().run(
            request(),
            Plan.model_validate(state["plan"]),
            evidence,
            calculations,
            narrative,
            [ToolEvent.model_validate(e) for e in state["tool_events"]],
        )
        assert not result.accepted
        assert "Financial calculations do not reconcile" in result.issues
        assert "Unknown citation" in result.issues


def test_verifier_feedback_repairs_llm_selection(tmp_path):
    class RepairModel:
        calls = 0

        def generate(self, role, context, schema):
            if role == "planner":
                return Plan(tools=["sql"], metrics=["operating_margin"], rationale="test")
            self.calls += 1
            if self.calls == 1:
                return Narrative(
                    findings=[Finding(text="Fabricated", evidence_ids=["fake"])],
                    limitations=["test"],
                )
            assert "Unknown citation" in context["verification_feedback"]
            return Narrative(findings=context["allowed_findings"], limitations=["test"])

    model = RepairModel()
    with ResearchEngine(
        tmp_path / "memory.sqlite", Planner(model), Retriever(tools(tmp_path)), Analyst(model)
    ) as engine:
        result = engine.run(request("Analyze operating margin", ["ALFA"]), "repair")
        assert result["verification"]["accepted"]
        assert result["analysis_attempts"] == 2
        assert result["trajectory"][-4:] == ["analyst", "verifier", "analyst", "verifier"]


def test_benchmark_independent_gold(tmp_path):
    result = evaluate(Path("benchmarks/cases.json"), tmp_path / "run", tmp_path / "report.json")
    assert result["case_count"] == 26
    assert result["pass_rate"] == 1
    assert result["numeric_comparison_count"] >= 15
    assert result["max_absolute_error"] < 1e-8
    assert result["as_of_violation_count"] == 0
