import json
import sys

from finagent.cli import main


def test_cli_pause_memory_resume_and_benchmark(tmp_path, monkeypatch, capsys):
    directory = str(tmp_path / "state")
    output = tmp_path / "demo.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "finagent",
            "research",
            "--thread",
            "cli-restart",
            "--directory",
            directory,
            "--pause",
            "--output",
            str(output),
        ],
    )
    main()
    assert json.loads(output.read_text())["paused"]
    capsys.readouterr()
    monkeypatch.setattr(
        sys, "argv", ["finagent", "memory", "--thread", "cli-restart", "--directory", directory]
    )
    main()
    assert json.loads(capsys.readouterr().out)["next"] == ["analyst"]
    monkeypatch.setattr(
        sys, "argv", ["finagent", "resume", "--thread", "cli-restart", "--directory", directory]
    )
    main()
    assert json.loads(capsys.readouterr().out)["verification"]["accepted"]
    monkeypatch.setattr(
        sys, "argv", ["finagent", "benchmark", "--output", str(tmp_path / "bench.json")]
    )
    main()
    assert json.loads(capsys.readouterr().out)["pass_rate"] == 1
