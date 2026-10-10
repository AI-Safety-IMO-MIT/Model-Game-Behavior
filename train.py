"""Self-play RL on the Take/Give game with Tinker.

    python train.py model=qwen3-8b
    python train.py model=gpt-oss-20b max_steps=5 groups_per_batch=2 games_per_group=4   # smoke run

Every finished training game is appended to <log_path>/games.jsonl for later analysis.
Checkpoints (and their tinker:// sampler paths) are listed in <log_path>/checkpoints.jsonl.
"""

import asyncio
import os
from datetime import datetime

import chz
from dotenv import load_dotenv
from tinker_cookbook import cli_utils
from tinker_cookbook.rl import train

from pd_game.env import PDDatasetBuilder
from pd_game.models import PRESETS


@chz.chz
class CLIConfig:
    model: str = "qwen3-8b"                 # key into pd_game.models.PRESETS
    seed: int = 0
    # 64 games (128 trajectories) per step by default
    groups_per_batch: int = 8
    games_per_group: int = 8
    max_steps: int = 200
    learning_rate: float | None = None      # default: the preset's
    lora_rank: int = 32
    max_tokens: int = 1536                  # per turn, reasoning + message
    # game
    max_messages: int = 10
    allow_early_end: bool = True
    pooled_reward: bool = True              # False = control run trained on each agent's own payoff
    invalid_decision_reward: float = -1.0
    # bookkeeping
    log_path: str | None = None
    save_every: int = 20
    wandb_project: str | None = None
    behavior_if_log_dir_exists: cli_utils.LogdirBehavior = "ask"


def build_config(cli: CLIConfig) -> train.Config:
    preset = PRESETS[cli.model]
    reward = "pooled" if cli.pooled_reward else "individual"
    run_name = f"{cli.model}-{reward}-s{cli.seed}-{datetime.now().strftime('%Y%m%d-%H%M')}"
    log_path = cli.log_path or os.path.join("runs", run_name)
    dataset_builder = PDDatasetBuilder(
        model_name=preset.model_name,
        renderer_name=preset.renderer_name,
        n_batches=cli.max_steps,
        groups_per_batch=cli.groups_per_batch,
        games_per_group=cli.games_per_group,
        seed=cli.seed,
        record_path=os.path.join(log_path, "games.jsonl"),
        max_messages=cli.max_messages,
        allow_early_end=cli.allow_early_end,
        pooled_reward=cli.pooled_reward,
        invalid_decision_reward=cli.invalid_decision_reward,
    )
    return train.Config(
        model_name=preset.model_name,
        recipe_name="pooled_rewards_pd",
        renderer_name=preset.renderer_name,
        log_path=log_path,
        dataset_builder=dataset_builder,
        learning_rate=cli.learning_rate or preset.learning_rate,
        lora_rank=cli.lora_rank,
        max_tokens=cli.max_tokens,
        max_steps=cli.max_steps,
        save_every=cli.save_every,
        eval_every=0,
        wandb_project=cli.wandb_project,
        wandb_name=run_name,
        # Seats of one game wait on each other, so a single failed trajectory can't be retried alone.
        rollout_error_tolerance=False,
        ttl_seconds=None,  # keep checkpoints; we need them for the cross-play evaluation
    )


if __name__ == "__main__":
    load_dotenv()
    cli = chz.entrypoint(CLIConfig)
    config = build_config(cli)
    cli_utils.check_log_dir(config.log_path, behavior_if_exists=cli.behavior_if_log_dir_exists)
    asyncio.run(train.main(config))
