"""Train-free reproducible demos, persistent resume and quantitative evaluation."""

import argparse
import json
import tempfile
import uuid
from datetime import date
from pathlib import Path

from finagent.evaluation import evaluate
from finagent.factory import create_engine
from finagent.schemas import ResearchRequest


def main():
    parser = argparse.ArgumentParser(description="FinAgent financial research")
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research")
    research.add_argument(
        "--question",
        default="Compare revenue growth, operating margin, debt, cash flow, risk factors and price",
    )
    research.add_argument("--symbols", nargs="+", default=["ALFA", "BETA"])
    research.add_argument("--as-of", type=date.fromisoformat, default=date(2025, 3, 5))
    research.add_argument("--mode", choices=["offline", "llm"], default="offline")
    research.add_argument("--live-market", action="store_true")
    research.add_argument("--directory", type=Path, default=Path("runtime/demo"))
    research.add_argument("--thread", default=None)
    research.add_argument("--pause", action="store_true")
    research.add_argument("--output", type=Path, default=None)
    for name in ("resume", "memory"):
        command = sub.add_parser(name)
        command.add_argument("--thread", required=True)
        command.add_argument("--directory", type=Path, default=Path("runtime/demo"))
        command.add_argument("--mode", choices=["offline", "llm"], default="offline")
        command.add_argument("--live-market", action="store_true")
    benchmark = sub.add_parser("benchmark")
    benchmark.add_argument("--cases", type=Path, default=Path("benchmarks/cases.json"))
    benchmark.add_argument("--output", type=Path, default=Path("reports/benchmark.json"))
    args = parser.parse_args()
    if args.command == "benchmark":
        with tempfile.TemporaryDirectory() as temp:
            result = evaluate(args.cases, Path(temp), args.output)
        print(json.dumps({k: v for k, v in result.items() if k != "cases"}, indent=2))
        if result["pass_rate"] != 1:
            raise SystemExit(1)
        return
    with create_engine(args.directory, args.mode, args.live_market) as engine:
        if args.command == "research":
            thread = args.thread or uuid.uuid4().hex
            report = engine.run(
                ResearchRequest(question=args.question, symbols=args.symbols, as_of=args.as_of),
                thread,
                args.pause,
            )
            result = {"thread": thread, "paused": args.pause, "report": report}
            if args.mode == "llm":
                result["llm_usage"] = engine.planner.model.usage
        elif args.command == "resume":
            result = engine.resume(args.thread)
        else:
            result = engine.memory(args.thread)
        rendered = json.dumps(result, indent=2, allow_nan=False)
        if getattr(args, "output", None):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered)


if __name__ == "__main__":
    main()
