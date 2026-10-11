"""Persistent LangGraph orchestration with a bounded verifier feedback edge."""

import sqlite3
from pathlib import Path
from threading import RLock
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from finagent.agents import Analyst, Planner, Retriever, Verifier
from finagent.schemas import (
    Calculation,
    Evidence,
    Narrative,
    Plan,
    Report,
    ResearchRequest,
    ToolEvent,
)


class WorkingMemory(TypedDict, total=False):
    request: dict
    plan: dict
    evidence: list[dict]
    calculations: list[dict]
    narrative: dict
    verification: dict
    tool_events: list[dict]
    trajectory: list[str]
    analysis_attempts: int
    mode: str


class ResearchEngine:
    def __init__(
        self,
        memory_path: Path,
        planner: Planner,
        retriever: Retriever,
        analyst: Analyst,
        verifier: Verifier | None = None,
    ):
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(memory_path, check_same_thread=False)
        self.checkpointer = SqliteSaver(self.connection)
        self.planner, self.retriever, self.analyst = planner, retriever, analyst
        self.verifier = verifier or Verifier()
        self.lock = RLock()
        builder = StateGraph(WorkingMemory)
        builder.add_node("planner", self._plan)
        builder.add_node("retriever", self._retrieve)
        builder.add_node("analyst", self._analyze)
        builder.add_node("verifier", self._verify)
        builder.add_edge(START, "planner")
        builder.add_edge("planner", "retriever")
        builder.add_edge("retriever", "analyst")
        builder.add_edge("analyst", "verifier")
        builder.add_conditional_edges("verifier", self._route, {"repair": "analyst", "done": END})
        self.graph = builder.compile(checkpointer=self.checkpointer)
        self.paused_graph = builder.compile(
            checkpointer=self.checkpointer, interrupt_after=["retriever"]
        )

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def config(thread_id: str) -> dict:
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", thread_id):
            raise ValueError("thread ID must contain 1-64 letters, digits, underscores or hyphens")
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 12}

    def run(self, request: ResearchRequest, thread_id: str, pause: bool = False) -> dict:
        config = self.config(thread_id)
        with self.lock:
            if self.graph.get_state(config).values:
                raise ValueError("Thread already exists; use resume or choose a new ID")
            graph = self.paused_graph if pause else self.graph
            state = graph.invoke(
                {
                    "request": request.model_dump(mode="json"),
                    "trajectory": [],
                    "analysis_attempts": 0,
                    "mode": "llm" if self.planner.model else "offline",
                },
                config,
            )
            return state if pause else Report.model_validate(state).model_dump(mode="json")

    def resume(self, thread_id: str) -> dict:
        config = self.config(thread_id)
        with self.lock:
            snapshot = self.graph.get_state(config)
            if not snapshot.values:
                raise ValueError("Unknown research thread")
            current_mode = "llm" if self.planner.model else "offline"
            if snapshot.values["mode"] != current_mode:
                raise ValueError("Resume mode must match the saved research thread")
            if not snapshot.next:
                return Report.model_validate(snapshot.values).model_dump(mode="json")
            state = self.graph.invoke(None, config)
            return Report.model_validate(state).model_dump(mode="json")

    def memory(self, thread_id: str) -> dict:
        with self.lock:
            snapshot = self.graph.get_state(self.config(thread_id))
            return {
                "state": snapshot.values,
                "next": list(snapshot.next),
                "checkpoint_count": sum(
                    1 for _ in self.graph.get_state_history(self.config(thread_id))
                ),
            }

    def _plan(self, state):
        request = ResearchRequest.model_validate(state["request"])
        return {
            "plan": self.planner.run(request).model_dump(mode="json"),
            "trajectory": state["trajectory"] + ["planner"],
        }

    def _retrieve(self, state):
        evidence, events = self.retriever.run(
            ResearchRequest.model_validate(state["request"]), Plan.model_validate(state["plan"])
        )
        return {
            "evidence": [e.model_dump(mode="json") for e in evidence],
            "tool_events": [e.model_dump() for e in events],
            "trajectory": state["trajectory"] + ["retriever"],
        }

    def _analyze(self, state):
        calculations, narrative = self.analyst.run(
            ResearchRequest.model_validate(state["request"]),
            Plan.model_validate(state["plan"]),
            [Evidence.model_validate(e) for e in state["evidence"]],
            state.get("verification", {}).get("issues", []),
        )
        return {
            "calculations": [c.model_dump() for c in calculations],
            "narrative": narrative.model_dump(),
            "analysis_attempts": state["analysis_attempts"] + 1,
            "trajectory": state["trajectory"] + ["analyst"],
        }

    def _verify(self, state):
        result = self.verifier.run(
            ResearchRequest.model_validate(state["request"]),
            Plan.model_validate(state["plan"]),
            [Evidence.model_validate(e) for e in state["evidence"]],
            [Calculation.model_validate(c) for c in state["calculations"]],
            Narrative.model_validate(state["narrative"]),
            [ToolEvent.model_validate(e) for e in state["tool_events"]],
        )
        return {
            "verification": result.model_dump(),
            "trajectory": state["trajectory"] + ["verifier"],
        }

    @staticmethod
    def _route(state):
        return (
            "repair"
            if not state["verification"]["accepted"] and state["analysis_attempts"] < 2
            else "done"
        )
