import gzip
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from mlb_predictor.db.models import (
    Game,
    PlayerGameHandedBatting,
    PlayerGamePitchGroup,
)
from mlb_predictor.ingestion.parser import SOURCE

HIT_EVENTS = {"single", "double", "triple", "home_run"}
WALK_EVENTS = {"walk", "intent_walk"}
NON_AT_BATS = {*WALK_EVENTS, "hit_by_pitch", "sac_fly", "sac_bunt", "catcher_interf"}
STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
FASTBALLS = {"FF", "FT", "SI", "FC", "FA"}
BREAKING = {"SL", "CU", "KC", "SV", "CS", "ST"}
OFFSPEED = {"CH", "FS", "FO", "SC", "KN", "EP"}
SWING_CODES = {"S", "W", "T", "F", "D", "E", "X"}
WHIFF_CODES = {"S", "W", "T"}


def pitch_group(code: str | None) -> str:
    if code in FASTBALLS:
        return "fastball"
    if code in BREAKING:
        return "breaking"
    if code in OFFSPEED:
        return "offspeed"
    return "other"


def parse_game_matchups(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    game_pk = int(payload["gameData"]["game"]["pk"])
    handed: dict[tuple[int, str], dict[str, int]] = defaultdict(
        lambda: {
            "plate_appearances": 0,
            "at_bats": 0,
            "hits": 0,
            "walks": 0,
            "strikeouts": 0,
            "home_runs": 0,
        }
    )
    pitches: dict[tuple[int, str, str], dict[str, int]] = defaultdict(
        lambda: {"pitches": 0, "swings": 0, "whiffs": 0, "balls_in_play": 0, "hits_on_contact": 0}
    )
    for play in payload.get("liveData", {}).get("plays", {}).get("allPlays", []):
        matchup = play.get("matchup") or {}
        batter = (matchup.get("batter") or {}).get("id")
        pitcher = (matchup.get("pitcher") or {}).get("id")
        hand = (matchup.get("pitchHand") or {}).get("code")
        if not batter or not pitcher or hand not in {"L", "R"}:
            continue
        event_type = str((play.get("result") or {}).get("eventType") or "")
        if (play.get("about") or {}).get("isComplete") and event_type:
            totals = handed[(int(batter), hand)]
            totals["plate_appearances"] += 1
            totals["at_bats"] += event_type not in NON_AT_BATS
            totals["hits"] += event_type in HIT_EVENTS
            totals["walks"] += event_type in WALK_EVENTS
            totals["strikeouts"] += event_type in STRIKEOUT_EVENTS
            totals["home_runs"] += event_type == "home_run"
        pitch_events = [event for event in play.get("playEvents", []) if event.get("isPitch")]
        final_group = None
        for event in pitch_events:
            details = event.get("details") or {}
            group = pitch_group((details.get("type") or {}).get("code"))
            final_group = group
            code = str((details.get("call") or {}).get("code") or details.get("code") or "")
            in_play = bool(details.get("isInPlay"))
            for player_id, role in ((int(batter), "batter"), (int(pitcher), "pitcher")):
                totals = pitches[(player_id, role, group)]
                totals["pitches"] += 1
                totals["swings"] += in_play or code in SWING_CODES
                totals["whiffs"] += code in WHIFF_CODES
                totals["balls_in_play"] += in_play
        if final_group is not None and event_type in HIT_EVENTS:
            pitches[(int(batter), "batter", final_group)]["hits_on_contact"] += 1

    retrieved_at = datetime.now(UTC)
    handed_rows = [
        {
            "game_pk": game_pk,
            "batter_id": batter,
            "pitcher_hand": hand,
            **values,
            "source": SOURCE,
            "retrieved_at": retrieved_at,
        }
        for (batter, hand), values in handed.items()
    ]
    pitch_rows = [
        {
            "game_pk": game_pk,
            "player_id": player,
            "role": role,
            "pitch_group": group,
            **values,
            "source": SOURCE,
            "retrieved_at": retrieved_at,
        }
        for (player, role, group), values in pitches.items()
    ]
    return handed_rows, pitch_rows


def rebuild_matchup_aggregates(
    session: Session, raw_root: Path, seasons: tuple[int, ...]
) -> dict[str, int]:
    game_ids = list(session.scalars(select(Game.game_pk).where(Game.season.in_(seasons))))
    session.execute(
        delete(PlayerGameHandedBatting).where(PlayerGameHandedBatting.game_pk.in_(game_ids))
    )
    session.execute(delete(PlayerGamePitchGroup).where(PlayerGamePitchGroup.game_pk.in_(game_ids)))
    handed_count = pitch_count = 0
    handed_batch: list[dict[str, Any]] = []
    pitch_batch: list[dict[str, Any]] = []
    for index, game_pk in enumerate(game_ids, start=1):
        path = next(
            (
                raw_root / str(season) / "games" / f"{game_pk}.json.gz"
                for season in seasons
                if (raw_root / str(season) / "games" / f"{game_pk}.json.gz").exists()
            ),
            None,
        )
        if path is None:
            raise FileNotFoundError(f"No cached feed for game {game_pk}")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        handed_rows, pitch_rows = parse_game_matchups(payload)
        handed_batch.extend(handed_rows)
        pitch_batch.extend(pitch_rows)
        if index % 100 == 0 or index == len(game_ids):
            if handed_batch:
                session.execute(insert(PlayerGameHandedBatting), handed_batch)
            if pitch_batch:
                session.execute(insert(PlayerGamePitchGroup), pitch_batch)
            handed_count += len(handed_batch)
            pitch_count += len(pitch_batch)
            handed_batch.clear()
            pitch_batch.clear()
    return {
        "games": len(game_ids),
        "handed_batting_rows": handed_count,
        "pitch_group_rows": pitch_count,
    }
