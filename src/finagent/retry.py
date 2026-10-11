"""Bounded exponential retry for transient failures only."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class TransientError(RuntimeError):
    pass


class ToolUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    delay: float = 0.1

    def __post_init__(self):
        if not 1 <= self.attempts <= 3 or not 0 <= self.delay <= 2:
            raise ValueError("retry budget out of bounds")

    def run(
        self, fn: Callable[[], T], sleep: Callable[[float], None] = time.sleep
    ) -> tuple[T, int]:
        for attempt in range(1, self.attempts + 1):
            try:
                return fn(), attempt
            except TransientError:
                if attempt == self.attempts:
                    raise
                sleep(self.delay * 2 ** (attempt - 1))
        raise AssertionError("unreachable")
