"""Circuit breaker для вызовов Flight Service: CLOSED -> OPEN -> HALF_OPEN -> CLOSED | OPEN.

Методы синхронные и не содержат await: в asyncio между ними не может вклиниться другая корутина,
поэтому блокировка не нужна.
"""

import enum
import logging
import math
import time
from collections import deque
from collections.abc import Callable

logger = logging.getLogger(__name__)


class State(enum.StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenError(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("flight-service circuit breaker is open")
        self.retry_after_seconds = retry_after_seconds


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int,
        window_seconds: float,
        open_timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._threshold = failure_threshold
        self._window = window_seconds
        self._open_timeout = open_timeout_seconds
        self._clock = clock

        self.state = State.CLOSED
        self._failures: deque[float] = deque()  # моменты сбоев в скользящем окне
        self._opened_at = 0.0
        self._probe_in_flight = False

    def before_call(self) -> None:
        """Пропускает вызов или бросает CircuitOpenError."""
        if self.state == State.OPEN:
            remaining = self._opened_at + self._open_timeout - self._clock()
            if remaining > 0:
                raise CircuitOpenError(remaining)
            self._transition(State.HALF_OPEN, "open timeout elapsed")

        if self.state == State.HALF_OPEN:
            # Пробный запрос ровно один, остальные отклоняются, пока он не завершится
            if self._probe_in_flight:
                raise CircuitOpenError(1)
            self._probe_in_flight = True

    def record_success(self) -> None:
        if self.state == State.HALF_OPEN:
            self._probe_in_flight = False
            self._failures.clear()
            self._transition(State.CLOSED, "probe succeeded")

    def record_failure(self, reason: str) -> None:
        now = self._clock()
        if self.state == State.HALF_OPEN:
            self._probe_in_flight = False
            self._open(now, f"probe failed: {reason}")
            return
        if self.state == State.OPEN:
            return

        self._failures.append(now)
        while self._failures and self._failures[0] <= now - self._window:
            self._failures.popleft()
        if len(self._failures) >= self._threshold:
            self._open(now, f"{len(self._failures)} failures in {self._window:g}s, last: {reason}")

    def release_probe(self) -> None:
        self._probe_in_flight = False

    def _open(self, now: float, reason: str) -> None:
        self._opened_at = now
        self._transition(State.OPEN, reason)

    def _transition(self, new_state: State, reason: str) -> None:
        logger.warning(
            "circuit breaker state change",
            extra={
                "fields": {
                    "from": self.state.value,
                    "to": new_state.value,
                    "reason": reason,
                    "failures_in_window": len(self._failures),
                }
            },
        )
        self.state = new_state


def retry_after_header(exc: CircuitOpenError) -> str:
    return str(max(1, math.ceil(exc.retry_after_seconds)))
