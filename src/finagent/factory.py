"""Composition root: adapters can be replaced without changing the graph."""

import os
from contextlib import contextmanager
from pathlib import Path

from finagent.agents import Analyst, Planner, Retriever
from finagent.fixtures import initialize
from finagent.llm import ChatModel
from finagent.tools import AlphaVantageTool, DocumentTool, FixtureMarketTool, SqlTool
from finagent.workflow import ResearchEngine


@contextmanager
def create_engine(directory: Path, mode: str = "offline", live_market: bool = False):
    if mode not in ("offline", "llm"):
        raise ValueError("mode must be offline or llm")
    initialize(directory)
    model = (
        ChatModel(os.getenv("LLM_API_KEY", ""), os.getenv("LLM_MODEL", ""))
        if mode == "llm"
        else None
    )
    market = (
        AlphaVantageTool(os.getenv("ALPHA_VANTAGE_API_KEY", ""))
        if live_market
        else FixtureMarketTool(directory / "market.json")
    )
    try:
        with ResearchEngine(
            directory / "memory.sqlite",
            Planner(model),
            Retriever(
                {
                    "sql": SqlTool(directory / "fundamentals.sqlite"),
                    "documents": DocumentTool(directory / "documents.json"),
                    "market": market,
                }
            ),
            Analyst(model),
        ) as engine:
            yield engine
    finally:
        if model:
            model.close()
        if live_market:
            market.close()
