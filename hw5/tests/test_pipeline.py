"""E2E: продюсер (HTTP API) → Kafka → ClickHouse (Kafka Engine → MV → MergeTree).

Изоляция: каждый тест использует свои user_id / session_id с префиксом test-<uuid> и фильтрует только
по ним, поэтому тесты можно запускать многократно и параллельно с генератором, ничего не очищая.
"""

import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import clickhouse_connect
import httpx
import pytest
from clickhouse_connect.driver.client import Client

MOVIE_SERVICE_URL = os.environ.get("MOVIE_SERVICE_URL", "http://movie-service:8000")
CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "")
CLICKHOUSE_DB = os.environ.get("CLICKHOUSE_DB", "analytics")
WAIT_TIMEOUT_S = float(os.environ.get("WAIT_TIMEOUT_S", "60"))

COLUMNS = "event_id, user_id, movie_id, event_type, event_time, device_type, session_id, progress_seconds"


@pytest.fixture(scope="module")
def api() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=MOVIE_SERVICE_URL, timeout=30) as client:
        yield client


@pytest.fixture(scope="module")
def ch() -> Iterator[Client]:
    client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST, username=CLICKHOUSE_USER, password=CLICKHOUSE_PASSWORD, database=CLICKHOUSE_DB
    )
    yield client
    client.close()


@pytest.fixture
def run_id() -> str:
    return f"test-{uuid.uuid4()}"


def wait_rows(ch: Client, where: str, params: dict, expected: int) -> list[dict]:
    """Поллинг ClickHouse, пока не появится expected строк (Kafka Engine забирает батчами)."""
    deadline = time.monotonic() + WAIT_TIMEOUT_S
    rows: list[dict] = []
    while time.monotonic() < deadline:
        result = ch.query(f"SELECT {COLUMNS} FROM movie_events FINAL WHERE {where} ORDER BY event_time", parameters=params)
        rows = list(result.named_results())
        if len(rows) >= expected:
            return rows
        time.sleep(0.5)
    pytest.fail(f"expected {expected} rows in ClickHouse within {WAIT_TIMEOUT_S}s, got {len(rows)}")


def make_event(run_id: str, **overrides) -> dict:
    event = {
        "event_id": str(uuid.uuid4()),
        "user_id": f"{run_id}-user",
        "movie_id": f"{run_id}-movie",
        "event_type": "VIEW_FINISHED",
        "timestamp": "2026-04-01T12:34:56.789Z",
        "device_type": "TV",
        "session_id": f"{run_id}-session",
        "progress_seconds": 5400,
    }
    return event | overrides


def test_event_reaches_clickhouse_with_correct_fields(api: httpx.Client, ch: Client, run_id: str) -> None:
    event = make_event(run_id)

    resp = api.post("/events", json=event)
    assert resp.status_code == 202, resp.text
    assert resp.json()["event_id"] == event["event_id"]

    [row] = wait_rows(ch, "event_id = {id:UUID}", {"id": event["event_id"]}, expected=1)
    assert str(row["event_id"]) == event["event_id"]
    assert row["user_id"] == event["user_id"]
    assert row["movie_id"] == event["movie_id"]
    assert row["event_type"] == "VIEW_FINISHED"
    assert row["device_type"] == "TV"
    assert row["session_id"] == event["session_id"]
    assert row["progress_seconds"] == 5400
    assert row["event_time"].replace(tzinfo=UTC) == datetime(2026, 4, 1, 12, 34, 56, 789000, tzinfo=UTC)


def test_server_generates_event_id_and_timestamp(api: httpx.Client, ch: Client, run_id: str) -> None:
    event = make_event(run_id, event_type="LIKED", progress_seconds=None)
    del event["event_id"], event["timestamp"]
    before = datetime.now(UTC) - timedelta(seconds=5)

    resp = api.post("/events", json=event)
    assert resp.status_code == 202, resp.text
    event_id = resp.json()["event_id"]

    [row] = wait_rows(ch, "event_id = {id:UUID}", {"id": event_id}, expected=1)
    assert row["event_type"] == "LIKED"
    assert row["progress_seconds"] is None
    assert row["event_time"].replace(tzinfo=UTC) >= before


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_type": "VIEW_TELEPORTED"},  # не из enum
        {"device_type": "FRIDGE"},  # не из enum
        {"progress_seconds": None},  # обязателен для VIEW_*
        {"progress_seconds": -1},
        {"event_type": "SEARCHED", "progress_seconds": 10},  # только для VIEW_*
        {"user_id": ""},
        {"event_id": "not-a-uuid"},
        {"unexpected_field": 1},
    ],
)
def test_invalid_event_rejected(api: httpx.Client, ch: Client, run_id: str, overrides: dict) -> None:
    event = make_event(run_id, **overrides)

    resp = api.post("/events", json=event)
    assert resp.status_code == 422, resp.text

    # Валидное контрольное событие того же пользователя публикуем следом: когда оно доехало до ClickHouse,
    # невалидное (если бы оно прошло) уже тоже было бы там — ключ один, партиция одна, порядок сохранён.
    marker = make_event(run_id, event_type="LIKED", progress_seconds=None)
    assert api.post("/events", json=marker).status_code == 202
    users = [marker["user_id"], str(event["user_id"])]
    rows = wait_rows(ch, "user_id IN {u:Array(String)}", {"u": users}, expected=1)
    assert [str(r["event_id"]) for r in rows] == [marker["event_id"]]


def test_session_events_keep_order_and_partition(api: httpx.Client, ch: Client, run_id: str) -> None:
    base = datetime(2026, 4, 2, 20, 0, tzinfo=UTC)
    steps = [
        ("SEARCHED", None),
        ("VIEW_STARTED", 0),
        ("VIEW_PAUSED", 600),
        ("VIEW_RESUMED", 600),
        ("VIEW_FINISHED", 5400),
        ("LIKED", None),
    ]
    events = [
        make_event(run_id, event_type=t, progress_seconds=p, timestamp=(base + timedelta(minutes=i)).isoformat())
        for i, (t, p) in enumerate(steps)
    ]

    partitions = set()
    for event in events:
        resp = api.post("/events", json=event)
        assert resp.status_code == 202, resp.text
        partitions.add(resp.json()["partition"])
    # Ключ — user_id: все события пользователя в одной партиции
    assert len(partitions) == 1

    rows = wait_rows(ch, "session_id = {s:String}", {"s": events[0]["session_id"]}, expected=len(events))
    assert [r["event_type"] for r in rows] == [t for t, _ in steps]
    assert [r["progress_seconds"] for r in rows] == [p for _, p in steps]
