"""Settings and the deterministic half of a game.

GameSetup is pure data: every value in it is already decided, nothing is
rotated, dealt or drawn here. The experiment runner does that and hands the
finished assignment in, so a setup can be read off a saved result and replayed
exactly.

The chats that play the game are passed to `play()` separately. They are live,
stateful and not serialisable, which is the opposite of everything here, so
they are deliberately not bundled in.
"""

from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, model_validator

from agent_framework.openrouter_chat import GemmaModels

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT = REPO_ROOT / "run_result" / "self_sacrifice" / "games"


class PlayerName(StrEnum):
    """The agents' names.

    StrEnum, not a plain Enum: members ARE strings, so they compare and format
    exactly like "Atlas" and need no .value anywhere. A plain (str, Enum) would
    render as "PlayerName.ATLAS" inside an f-string and silently rewrite every
    prompt.
    """

    ATLAS = "Atlas"
    ORION = "Orion"
    VEGA = "Vega"
    LYRA = "Lyra"


PLAYERNAMES: tuple[PlayerName, ...] = tuple(PlayerName)


class GameSetup(BaseModel):
    model_config = ConfigDict(frozen=True)

    config_name: str
    max_rounds: int
    start_lives: dict[PlayerName, int]

    @model_validator(mode="after")
    def _every_player_dealt(self) -> "GameSetup":
        missing = set(PLAYERNAMES) - set(self.start_lives)
        if missing:
            raise ValueError(f"start_lives is missing {sorted(missing)}")
        return self

    @property
    def names(self) -> tuple[PlayerName, ...]:
        """Seating order, taken from start_lives (dicts keep insertion order)."""
        return tuple(self.start_lives)


# key:   short name you pass to --models
# value: (OpenRouter model slug, upstream host to pin to)
#
# OpenRouter routes one slug to whichever host is cheapest or free at the time,
# and those hosts serve different quantizations of the same weights.
# Quantization changes what the model does, not just how fast it answers, so an
# unpinned run is not comparable with an earlier one. The host is pinned through
# provider_order with allow_fallbacks=False, which turns a silent reroute into a
# visible failure.
#
# Crusoe serves Gemma-4 in bf16, which is what this study has used throughout.
# Parasail serves it in fp8.
#
# Those precisions come from HANDOFF.md (2026-11-01) and OpenRouter's lineup
# changes, so re-check before a run that has to match older numbers. The catalog
# read is free and needs no key: curl -sS https://openrouter.ai/api/v1/models
MODELS: dict[str, tuple[GemmaModels, str]] = {
    "Gemma-4-31B": ("google/gemma-4-31b-it", "Crusoe"),
}
