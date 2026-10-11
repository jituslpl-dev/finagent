import json
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from finagent.agents import Retriever
from finagent.api import create_app
from finagent.llm import ChatModel
from finagent.retry import RetryPolicy, ToolUnavailable, TransientError
from finagent.schemas import Plan, ResearchRequest
from finagent.tools import AlphaVantageTool


def test_retry_transient_then_success_and_permanent_fast_fail():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TransientError("temporary")
        return 7

    assert RetryPolicy(delay=0.1).run(flaky, sleeps.append) == (7, 3)
    assert sleeps == [0.1, 0.2]
    with pytest.raises(ToolUnavailable):
        RetryPolicy().run(lambda: (_ for _ in ()).throw(ToolUnavailable("permanent")))
    with pytest.raises(ValueError):
        RetryPolicy(attempts=4)


def test_financial_api_contract_and_retry():
    calls = []

    def handler(req):
        calls.append(req)
        assert req.url.params["function"] == "TIME_SERIES_DAILY"
        if len(calls) == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "Time Series (Daily)": {
                    "2025-03-03": {"4. close": "42"},
                    "2025-03-06": {"4. close": "99"},
                }
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        tool = AlphaVantageTool("mock-key", client)
        rows, attempt = RetryPolicy(delay=0).run(lambda: tool.retrieve("IBM", date(2025, 3, 5)))
        assert attempt == 2
        assert rows[0].payload["close"] == 42
        assert rows[0].available_on == date(2025, 3, 3)


@pytest.mark.parametrize(
    "payload",
    [
        {"Note": "quota"},
        {"Information": "upgrade"},
        {"Error Message": "unknown"},
        {"Time Series (Daily)": {"2025-03-03": {"4. close": "NaN"}}},
    ],
)
def test_financial_api_failure_payloads(payload):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises((TransientError, ToolUnavailable)),
    ):
        AlphaVantageTool("mock-key", client).retrieve("IBM", date(2025, 3, 5))


def test_tool_failure_is_audited_and_bounded():
    class Broken:
        def retrieve(self, *args):
            raise TransientError("do not leak this provider detail")

    request = ResearchRequest(question="Retrieve price", symbols=["IBM"], as_of="2025-03-05")
    rows, events = Retriever({"market": Broken()}, RetryPolicy(delay=0)).run(
        request, Plan(tools=["market"], metrics=[], rationale="test")
    )
    assert not rows and events[0].attempts == 3
    assert events[0].error == "Evidence tool unavailable"


def test_llm_json_schema_repair_usage_and_request_contract():
    calls = []

    def handler(req):
        body = json.loads(req.content)
        assert body["response_format"] == {"type": "json_object"}
        assert req.headers["Authorization"] == "Bearer mock-secret"
        calls.append(body)
        content = (
            '{"tools":["shell"],"metrics":[],"rationale":"bad"}'
            if len(calls) == 1
            else '{"tools":["sql"],"metrics":["operating_margin"],"rationale":"valid"}'
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        model = ChatModel("mock-secret", "explicit-model", client)
        result = model.generate("planner", {"question": "margin"}, Plan)
        assert result.tools == ["sql"] and len(calls) == 2
        assert model.usage == {"calls": 2, "prompt_tokens": 20, "completion_tokens": 10}


def test_llm_rejects_incomplete_and_invalid_output():
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json={"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
                )
            )
        ) as client,
        pytest.raises(ToolUnavailable, match="incomplete"),
    ):
        ChatModel("key", "model", client).generate("planner", {}, Plan)
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}
                )
            )
        ) as client,
        pytest.raises(ToolUnavailable, match="schema"),
    ):
        ChatModel("key", "model", client).generate("planner", {}, Plan)


def test_api_authentication_validation_and_persistent_memory(tmp_path):
    key = "test-secret-at-least-16"
    with pytest.raises(ValueError):
        create_app(tmp_path, "short")
    with TestClient(create_app(tmp_path, key)) as client:
        assert client.get("/health").status_code == 200
        body = {"question": "Analyze operating margin", "symbols": ["ALFA"], "as_of": "2025-03-05"}
        assert client.post("/research", json=body).status_code == 401
        headers = {"X-API-Key": key}
        response = client.post("/research", json=body, headers=headers)
        assert response.status_code == 200
        assert response.json()["report"]["verification"]["accepted"]
        thread = response.json()["thread"]
        assert client.get(f"/memory/{thread}", headers=headers).json()["checkpoint_count"] >= 5
        assert client.get("/memory/unknown", headers=headers).status_code == 404
        assert (
            client.post(
                "/research", json={**body, "sql": "DROP TABLE"}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/research", json={**body, "symbols": ["ALFA"] * 6}, headers=headers
            ).status_code
            == 422
        )
