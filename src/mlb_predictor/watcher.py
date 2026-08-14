from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from mlb_predictor.config import Settings
from mlb_predictor.db.models import OperationalState, WatcherEvent

LOGGER = logging.getLogger(__name__)
STATUS_KEY = "watcher_status"


def record_event(
    session: Session,
    event_type: str,
    message: str,
    *,
    severity: str = "info",
    game_pk: int | None = None,
    details: dict[str, object] | None = None,
) -> None:
    session.add(
        WatcherEvent(
            occurred_at=datetime.now(UTC),
            event_type=event_type,
            severity=severity,
            game_pk=game_pk,
            message=message,
            details_json=json.dumps(details or {}),
        )
    )


def update_status(session: Session, payload: dict[str, object]) -> None:
    now = datetime.now(UTC)
    row = session.get(OperationalState, STATUS_KEY)
    if row is None:
        row = OperationalState(key=STATUS_KEY, value="{}", created_at=now)
    row.value = json.dumps({"updated_at": now.isoformat(), **payload})
    session.add(row)


def watcher_status(session: Session) -> dict[str, object]:
    row = session.get(OperationalState, STATUS_KEY)
    return json.loads(row.value) if row else {"state": "never_started"}


def notify(settings: Settings, event: str, message: str) -> None:
    if not settings.notification_webhook_url:
        return
    try:
        httpx.post(
            settings.notification_webhook_url,
            json={"event": event, "message": message},
            timeout=5,
        ).raise_for_status()
    except Exception:
        LOGGER.exception("notification hook failed")


def run_watcher(
    cycle: Callable[[], int],
    status: Callable[[dict[str, object]], None],
    settings: Settings,
    *,
    max_cycles: int | None = None,
) -> int:
    count = 0
    status({"state": "running", "cycles": count})
    while max_cycles is None or count < max_cycles:
        started = datetime.now(UTC)
        try:
            code = cycle()
            count += 1
            status(
                {
                    "state": "running",
                    "cycles": count,
                    "last_cycle_started_at": started.isoformat(),
                    "last_cycle_succeeded": code == 0,
                }
            )
        except Exception as error:
            LOGGER.exception("watcher cycle failed")
            count += 1
            status(
                {
                    "state": "degraded",
                    "cycles": count,
                    "last_cycle_started_at": started.isoformat(),
                    "last_error": f"{type(error).__name__}: {error}",
                }
            )
        if max_cycles is not None and count >= max_cycles:
            break
        time.sleep(settings.watcher_approaching_seconds)
    status({"state": "stopped", "cycles": count})
    return 0
