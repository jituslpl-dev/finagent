"""Real HTTP checks against the running container; standard library only."""

import argparse
import json
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    for attempt in range(60):
        try:
            with urllib.request.urlopen(args.url + "/health", timeout=2) as response:
                assert json.load(response)["ready"]
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == 59:
                raise
            time.sleep(0.5)
    body = json.dumps(
        {
            "question": "Analyze revenue growth and risk factors",
            "symbols": ["ALFA"],
            "as_of": "2025-03-05",
        }
    ).encode()
    request = urllib.request.Request(
        args.url + "/research",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": args.key},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    assert result["report"]["verification"]["accepted"]
    assert result["report"]["calculations"][0]["value"] == 25
    memory = urllib.request.Request(
        args.url + "/memory/" + result["thread"], headers={"X-API-Key": args.key}
    )
    with urllib.request.urlopen(memory, timeout=5) as response:
        assert json.load(response)["checkpoint_count"] >= 5
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                args.url + "/research", data=body, headers={"Content-Type": "application/json"}
            ),
            timeout=5,
        )
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    else:
        raise AssertionError("Unauthenticated research must fail")
    print("Container readiness, research, persistent memory and authentication passed")


if __name__ == "__main__":
    main()
