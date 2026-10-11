"""Financial calculations over explicit source rows; zero denominators abstain."""

import math

from finagent.schemas import Calculation, Evidence, Plan, ResearchRequest


def calculate(request: ResearchRequest, plan: Plan, sources: list[Evidence]) -> list[Calculation]:
    output = []
    for symbol in request.symbols:
        rows = sorted(
            [e for e in sources if e.kind == "sql" and e.symbol == symbol],
            key=lambda e: e.payload["period"],
            reverse=True,
        )
        for metric in plan.metrics:
            unit = (
                "percent"
                if metric in ("revenue_growth", "operating_margin")
                else ("ratio" if metric == "debt_to_equity" else "USD million")
            )
            ids, value, reason = [], None, None
            if not rows:
                reason = "No eligible fundamental evidence"
            elif metric == "revenue_growth" and (
                len(rows) < 2 or rows[0].payload["period"] - rows[1].payload["period"] != 1
            ):
                reason = "Two consecutive annual periods required"
            else:
                latest = rows[0].payload
                ids = [rows[0].id]
                if metric == "free_cash_flow":
                    value = latest["operating_cash_flow"] - latest["capex"]
                else:
                    if metric == "revenue_growth":
                        ids.append(rows[1].id)
                        denominator = rows[1].payload["revenue"]
                        numerator = latest["revenue"] - denominator
                    elif metric == "operating_margin":
                        denominator, numerator = latest["revenue"], latest["operating_income"]
                    else:
                        denominator, numerator = latest["equity"], latest["debt"]
                    if denominator == 0:
                        reason = "Zero denominator; ratio undefined"
                    else:
                        value = numerator / denominator * (100 if unit == "percent" else 1)
                if value is not None and not math.isfinite(value):
                    value, reason = None, "Nonfinite financial calculation"
            output.append(
                Calculation(
                    symbol=symbol,
                    metric=metric,
                    value=value,
                    unit=unit,
                    evidence_ids=ids,
                    reason=reason,
                )
            )
    return output
