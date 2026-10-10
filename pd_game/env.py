"""Tinker-cookbook RL environment: one Env per seat, two seats share a Game.

A group holds `games_per_group` self-play games (2 trajectories each). Advantages are centered
over the whole group, which is why a group needs several games: both seats of one game always
get the same pooled reward, so a one-game group would have zero advantage everywhere.
"""

import json
import os
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass

import chz
from tinker import types
from tinker_cookbook.renderers import Renderer, get_text_content
from tinker_cookbook.renderers.base import ensure_list
from tinker_cookbook.rl.types import (
    Action,
    ActionExtra,
    Env,
    EnvGroupBuilder,
    Metrics,
    RLDataset,
    RLDatasetBuilder,
    StepResult,
    Trajectory,
)

from .game import GIVE, TAKE, Game, GameConfig
from .models import make_renderer


def parse_action(renderer: Renderer, tokens: list[int], extra: ActionExtra | None) -> tuple[str, str, bool]:
    """-> (visible text, private thinking, truncated)."""
    message, termination = renderer.parse_response(tokens)
    truncated = (not termination.is_clean) or bool(extra and extra.get("stop_reason") == "length")
    if truncated:
        return "", "", True
    thinking = "".join(p["thinking"] for p in ensure_list(message["content"]) if p["type"] == "thinking")
    return get_text_content(message).strip(), thinking.strip(), False


class PDEnv(Env):
    def __init__(self, game: Game, player_id: int, renderer: Renderer):
        self.game = game
        self.pid = player_id
        self.renderer = renderer

    def _observation(self) -> types.ModelInput:
        return self.renderer.build_generation_prompt(self.game.view(self.pid))

    async def initial_observation(self):
        await self.game.wait_for_turn(self.pid)  # the second speaker waits for the first message
        return self._observation(), self.renderer.get_stop_sequences()

    async def step(self, action: Action, *, extra: ActionExtra | None = None) -> StepResult:
        text, thinking, truncated = parse_action(self.renderer, action, extra)
        if not self.game.talk_over:
            await self.game.post_message(self.pid, text, thinking, truncated)
            await self.game.wait_for_turn(self.pid)
            return StepResult(0.0, False, self._observation(), self.renderer.get_stop_sequences(),
                              metrics={"truncated_turns": float(truncated)})

        await self.game.submit_decision(self.pid, text, thinking, truncated)
        await self.game.wait_until_done()
        return StepResult(self.game.reward(self.pid), True, types.ModelInput.empty(),
                          self.renderer.get_stop_sequences(), metrics=self._final_metrics(truncated))

    def _final_metrics(self, truncated: bool) -> Metrics:
        mine, theirs = self.game.decisions[self.pid].choice, self.game.decisions[1 - self.pid].choice
        payoff = self.game.payoffs()[self.pid]
        return {
            "truncated_turns": float(truncated),
            "gave": float(mine == GIVE),
            "took": float(mine == TAKE),
            "invalid_decision": float(mine is None),
            # outcome from this seat's point of view; averaged over seats these are game frequencies
            "outcome/both_give": float(mine == GIVE and theirs == GIVE),
            "outcome/one_takes_one_gives": float({mine, theirs} == {GIVE, TAKE}),
            "outcome/both_take": float(mine == TAKE and theirs == TAKE),
            "stated_payoff": float(payoff),
            "pooled_payoff": float(sum(self.game.payoffs())),
            "n_messages": float(len(self.game.transcript)),
            "ended_early": float(self.game.ended_early),
            "spoke_first": float(self.game.first_speaker == self.pid),
        }


@dataclass
class PDGroupBuilder(EnvGroupBuilder):
    model_name: str
    renderer_name: str
    games_per_group: int
    game_cfg: GameConfig
    seed: int
    batch_index: int
    record_path: str | None = None   # append every finished game here as JSONL

    async def make_envs(self) -> Sequence[Env]:
        renderer = make_renderer(self.renderer_name, self.model_name)
        first = random.Random(self.seed).randrange(2)
        envs: list[Env] = []
        for g in range(self.games_per_group):
            game = Game(self.game_cfg, first_speaker=(first + g) % 2)  # balanced first speakers
            envs += [PDEnv(game, 0, renderer), PDEnv(game, 1, renderer)]
        return envs

    async def compute_group_rewards(self, trajectory_group: list[Trajectory], env_group: Sequence[Env]):
        if self.record_path:
            games = list(dict.fromkeys(e.game for e in env_group))  # dedupe, keep order
            os.makedirs(os.path.dirname(self.record_path) or ".", exist_ok=True)
            with open(self.record_path, "a") as f:
                for i, game in enumerate(games):
                    rec = game.to_record(batch=self.batch_index, group_seed=self.seed, game_in_group=i,
                                         players=[self.model_name, self.model_name], time=time.time())
                    f.write(json.dumps(rec) + "\n")
        return [(0.0, {}) for _ in trajectory_group]

    def logging_tags(self) -> list[str]:
        return ["pd"]


class PDDataset(RLDataset):
    def __init__(self, n_batches: int, groups_per_batch: int, make_builder):
        self.n_batches = n_batches
        self.groups_per_batch = groups_per_batch
        self.make_builder = make_builder

    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        return [self.make_builder(index, j) for j in range(self.groups_per_batch)]

    def __len__(self) -> int:
        return self.n_batches


@chz.chz
class PDDatasetBuilder(RLDatasetBuilder):
    model_name: str
    renderer_name: str
    n_batches: int
    groups_per_batch: int
    games_per_group: int
    seed: int = 0
    record_path: str | None = None
    max_messages: int = 10
    allow_early_end: bool = True
    pooled_reward: bool = True
    invalid_decision_reward: float = -1.0
    keep_own_reasoning: bool = True

    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        cfg = GameConfig(self.max_messages, self.allow_early_end, self.pooled_reward,
                         self.invalid_decision_reward, self.keep_own_reasoning)

        def make_builder(batch: int, group: int) -> PDGroupBuilder:
            return PDGroupBuilder(self.model_name, self.renderer_name, self.games_per_group, cfg,
                                  seed=self.seed * 1_000_003 + batch * 1009 + group, batch_index=batch,
                                  record_path=self.record_path)

        return PDDataset(self.n_batches, self.groups_per_batch, make_builder), None
