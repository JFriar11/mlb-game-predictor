import logging
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

LOGGER = logging.getLogger(__name__)


class MlbApiError(RuntimeError):
    pass


class TransientMlbApiError(MlbApiError):
    pass


class MlbStatsClient:
    """Small MLB Stats API client with bounded retries and request timeouts."""

    def __init__(self, base_url: str, timeout_seconds: float, max_attempts: int) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MlbStatsClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get_json(self, path: str, params: dict[str, str | int] | None = None) -> dict[str, Any]:
        retryer = Retrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, TransientMlbApiError)
            ),
            reraise=True,
        )
        response: httpx.Response | None = None
        for attempt in retryer:
            with attempt:
                response = self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    raise TransientMlbApiError(
                        f"Transient MLB response {response.status_code} for {path}"
                    )
                response.raise_for_status()
        if response is None:
            raise MlbApiError(f"No response for {path}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise MlbApiError(f"Malformed response for {path}")
        return payload

    def get_game_feed(self, game_pk: int) -> dict[str, Any]:
        if game_pk <= 0:
            raise ValueError("game_pk must be positive")
        LOGGER.info("fetching MLB game feed", extra={"game_pk": game_pk})
        payload = self._get_json(f"/v1.1/game/{game_pk}/feed/live")
        if "gameData" not in payload or "liveData" not in payload:
            raise MlbApiError(f"Malformed feed for game {game_pk}")
        return payload

    def get_regular_season_schedule(self, season: int) -> dict[str, Any]:
        if season != 2025:
            raise ValueError("Sprint 1 schedule discovery is restricted to season 2025")
        LOGGER.info("fetching regular-season schedule")
        return self._get_json(
            "/v1/schedule",
            {
                "sportId": 1,
                "season": season,
                "gameType": "R",
                "startDate": f"{season}-03-01",
                "endDate": f"{season}-11-30",
            },
        )
