"""--difficulty accepts the levels 0 to 4 only."""

import argparse

import pytest
from pydantic import ValidationError

from ssebench.cli.cli import main
from ssebench.runner.result import RunConfig

RUN = ("run", "--model", "m", "--agent", "dummy", "--task", "t", "--local", "datasets")


@pytest.mark.parametrize("level", ["-1", "5", "x"])
def test_run_rejects_a_level_out_of_range(level: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main([*RUN, "--difficulty", level])

    assert exit_info.value.code == 2
    assert "--difficulty" in capsys.readouterr().err


def test_run_accepts_levels_zero_to_four(monkeypatch: pytest.MonkeyPatch) -> None:
    levels: list[int] = []

    def cmd_run(args: argparse.Namespace) -> int:
        levels.append(args.difficulty)
        return 0

    monkeypatch.setattr("ssebench.cli.cli.cmd_run", cmd_run)
    for level in range(5):
        with pytest.raises(SystemExit):
            main([*RUN, "--difficulty", str(level)])
    with pytest.raises(SystemExit):
        main(list(RUN))

    assert levels == [0, 1, 2, 3, 4, 2]


@pytest.mark.parametrize("level", [-1, 5])
def test_run_config_rejects_a_level_out_of_range(level: int) -> None:
    with pytest.raises(ValidationError):
        _ = RunConfig(agent="dummy", model="m", mode="sandbox", timeout=60, difficulty=level)
