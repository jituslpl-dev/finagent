"""Executable gold-answer suite with numerical, routing and abstention metrics."""

import json
import math
import time
from pathlib import Path

from finagent.factory import create_engine
from finagent.schemas import ResearchRequest


def evaluate(cases_path: Path, directory: Path, output: Path) -> dict:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results, errors, routing, decisions, citation_checks = [], [], [], [], []
    with create_engine(directory) as engine:
        for i, case in enumerate(cases):
            start = time.perf_counter()
            report = engine.run(ResearchRequest.model_validate(case["request"]), f"bench-{i}")
            latency = (time.perf_counter() - start) * 1000
            expected = case["expected"]
            actual = {f"{c['symbol']}:{c['metric']}": c["value"] for c in report["calculations"]}
            numeric_ok = set(actual) == set(expected["values"])
            for key, value in expected["values"].items():
                found = actual.get(key)
                if value is None:
                    numeric_ok &= found is None
                elif found is None:
                    numeric_ok = False
                else:
                    error = abs(found - value)
                    errors.append(error)
                    numeric_ok &= error < 1e-8
            route_ok = set(report["plan"]["tools"]) == set(expected["tools"])
            decision_ok = report["verification"]["accepted"] == expected["accepted"]
            ids = {e["id"] for e in report["evidence"]}
            citation_ok = all(
                set(f["evidence_ids"]) <= ids for f in report["narrative"]["findings"]
            )
            time_ok = all(e["available_on"] <= case["request"]["as_of"] for e in report["evidence"])
            routing.append(route_ok)
            decisions.append(decision_ok)
            citation_checks.append(citation_ok)
            results.append(
                {
                    "id": case["id"],
                    "passed": bool(
                        numeric_ok and route_ok and decision_ok and citation_ok and time_ok
                    ),
                    "numeric_ok": bool(numeric_ok),
                    "routing_ok": route_ok,
                    "decision_ok": decision_ok,
                    "citation_ok": citation_ok,
                    "as_of_ok": time_ok,
                    "latency_ms": latency,
                    "accepted": report["verification"]["accepted"],
                    "issues": report["verification"]["issues"],
                }
            )
    summary = {
        "mode": "offline deterministic orchestration; fictional gold fixtures",
        "case_count": len(results),
        "pass_rate": sum(r["passed"] for r in results) / len(results),
        "routing_accuracy": sum(routing) / len(routing),
        "acceptance_abstention_accuracy": sum(decisions) / len(decisions),
        "citation_reference_validity": sum(citation_checks) / len(citation_checks),
        "numeric_comparison_count": len(errors),
        "numeric_mae": sum(errors) / len(errors) if errors else None,
        "numeric_rmse": math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None,
        "max_absolute_error": max(errors, default=None),
        "as_of_violation_count": sum(not r["as_of_ok"] for r in results),
        "latency_p95_ms": sorted(r["latency_ms"] for r in results)[
            math.ceil(0.95 * len(results)) - 1
        ],
        "limitations": [
            "Not an LLM quality benchmark; no paid API calls occur.",
            "Citation reference validity is not semantic fact-checking accuracy.",
            "Small hand-authored fixtures and local latency do not establish production performance.",
        ],
        "cases": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, allow_nan=False), encoding="utf-8")
    return summary
