"""Lives game in self-play: all four agents are the same model, each in its own
conversation.

    rich   5/4/4/3  one agent can save the short one at no cost to itself
    scarce 4/4/3/3  two agents are short; any rescue costs the giver its survival

Nothing is scripted. The game count rotates which name holds which starting
hand, so run games in multiples of len(PLAYERNAMES) for a balanced pass.
"""

from concurrent.futures import ThreadPoolExecutor

from agent_framework.dto import AgenticChat
from agent_framework.openrouter_chat import GemmaAgentConfig, GemmaChat
from project.self_sacrifice import config, lives_game
from project.self_sacrifice.config import PLAYERNAMES, GameSetup, PlayerName

START_LIVES: dict[str, tuple[int, ...]] = {
    "rich": (5, 4, 4, 3),
    "scarce": (4, 4, 3, 3),
}
# Rounds inside one game.
MAX_ROUNDS = 4

# Games to run per (model, setup). deal() rotates the starting hand every
# len(PLAYERNAMES) games, so one full rotation gives each name each hand
# exactly once. Unrelated to MAX_ROUNDS; they are both 4 by coincidence.
N_GAMES = len(PLAYERNAMES)
TEMPERATURE = 0.7
MAX_OUTPUT_TOKENS = 1000
# None = reasoning off, which HANDOFF.md makes a standing rule for every
# subject model. "minimal" is not off: it burned the whole token budget.
REASONING_EFFORT = None

# Games run at a time. Each game already runs its 4 agents in parallel, so
# this multiplies: 4 workers meant 16 simultaneous requests, which the free
# tier's shared provider pool answered with a 429.
WORKERS = 1


def deal(setup: str, game_count: int) -> dict[PlayerName, int]:
    """Rotate the starting hand across the names.

    This is the experiment's randomness, applied here and not in GameSetup.
    Counting games rather than drawing at random is what makes it deterministic:
    game_count % len(PLAYERNAMES) walks every rotation in turn, so one pass
    gives each name each hand exactly once. A random deal gives no such
    guarantee.
    """
    base = START_LIVES[setup]
    k = game_count % len(PLAYERNAMES)
    return dict(zip(PLAYERNAMES, base[k:] + base[:k]))


if __name__ == "__main__":
    import os
    import threading

    setups = ["rich", "scarce"]
    models = config.MODELS

    os.makedirs(config.OUT, exist_ok=True)

    def result_path(model: str, setup: str, game_count: int) -> str:
        """One file per game. The name carries what distinguishes it; the file
        itself carries the full config under `agent_config`."""
        slug = config.MODELS[model][0].split("/")[-1]
        return f"{config.OUT}/{slug}_{setup}_game{game_count}.json"

    # a game is done when its file exists
    jobs = [
        (m, s, game_count)
        for m in models
        for s in setups
        for game_count in range(N_GAMES)
        if not os.path.exists(result_path(m, s, game_count))
    ]

    write_lock = threading.Lock()

    def run_one(job) -> None:
        model, setup, game_count = job
        slug, host = config.MODELS[model]
        prompts = lives_game.system_prompts(PLAYERNAMES, MAX_ROUNDS)
        chats: dict[PlayerName, AgenticChat] = {
            name: GemmaChat(
                agent_config=GemmaAgentConfig(
                    model=slug,
                    system_prompt=prompts[name],
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                    temperature=TEMPERATURE,
                    reasoning_effort=REASONING_EFFORT,
                    provider_order=(host,),
                    allow_fallbacks=False,
                )
            )
            for name in PLAYERNAMES
        }
        log = lives_game.play(
            GameSetup(
                config_name=setup,
                max_rounds=MAX_ROUNDS,
                start_lives=deal(setup, game_count),
            ),
            chats,
            seed=game_count,
        )
        path = result_path(model, setup, game_count)
        with write_lock, open(path, "w") as handle:
            handle.write(log.model_dump_json(indent=2))
        print(f"  done  {os.path.basename(path)}", flush=True)

    if WORKERS > 1:
        # Games are independent: each builds its own chats and writes its own
        # file. Only the order they finish in varies.
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            list(pool.map(run_one, jobs))
    else:
        for job in jobs:
            run_one(job)

    print("new games", len(jobs), "->", config.OUT)
