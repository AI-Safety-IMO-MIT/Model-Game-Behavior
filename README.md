# spar-altruism-rl

Can RL with a hidden pooled reward teach a reasoning model to sacrifice for another agent, and does
that altruism survive when it meets a *different* model?

**The game.** Two agents talk (up to 10 messages each, alternating; either can propose ending early
with `[END]`, and the talk ends once both do so back to back). Then each privately chooses TAKE or
GIVE. They are told only their own payoffs:

| you / other | GIVE  | TAKE  |
|-------------|-------|-------|
| **GIVE**    | 2 / 2 | 0 / 6 |
| **TAKE**    | 6 / 0 | 1 / 1 |

**The hidden reward.** During training both agents receive the *sum* of the two payoffs
(Take/Give = 6 > Give/Give = 4 > Take/Take = 2). The target behaviour is one agent taking and the
other actively choosing to give, sacrificing its own stated payoff. Only the game outcome is
rewarded; the messages are never scored.

**The models.** `Qwen/Qwen3-8B` and `openai/gpt-oss-20b` (medium reasoning), each trained with
LoRA on Tinker against copies of itself. Afterwards: Qwen vs gpt-oss cross-play, plus base models
and scripted probes (`exploiter`: promises GIVE then TAKES; `always_take`; `always_give`).

## Design choices worth knowing

- **One game = one episode.** Rewards never carry across games.
- **Private reasoning.** A player never sees its partner's reasoning. It does keep its *own*
  earlier reasoning in context, so each turn's prompt extends the last and a whole game trains as
  one sequence (much cheaper). For gpt-oss this needed a one-token renderer tweak; see
  `pd_game/models.py`.
- **Neutral prompt.** Agents are not told the partner is a copy of themselves, so the same prompt
  works in cross-play (`pd_game/prompts.py`).
- **GRPO-style advantages** centered over a group of 8 games (16 trajectories). Both seats of a
  game share the pooled reward, so a group must contain several games for any learning signal.
- **Unparseable decision:** that player gets reward −1, and it counts as TAKE for the payoff.
- **Control run available:** `pooled_reward=False` trains each agent on its own stated payoff.

## Layout

```
pd_game/game.py     rules, turn order, views, payoffs (backend-agnostic)
pd_game/prompts.py  everything the agents read
pd_game/env.py      tinker-cookbook RL environment (self-play)
pd_game/models.py   model presets and renderers
pd_game/players.py  Tinker / OpenRouter / scripted players for evaluation
train.py            self-play RL on Tinker
play.py             evaluation games between any two players
analyze.py          outcome tables, training trends, optional LLM judge of messages and reasoning
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Put `OPENROUTER_API_KEY` and `TINKER_API_KEY` in `.env` (never committed). Run the tests with
`.venv/bin/python -m pytest -q tests`. The renderer tests download the two tokenizers from Hugging Face.

## Pilot (about $50–100 on Tinker)

```bash
# 1. how the untrained models play (sampling only)
.venv/bin/python play.py --a tinker:Qwen/Qwen3-8B --b tinker:Qwen/Qwen3-8B -n 64
.venv/bin/python play.py --a tinker:openai/gpt-oss-20b --b tinker:openai/gpt-oss-20b -n 64
# 2. a few training steps to check the loop end to end
.venv/bin/python train.py model=qwen3-8b max_steps=3 groups_per_batch=2 log_path=runs/smoke-qwen
.venv/bin/python train.py model=gpt-oss-20b max_steps=3 groups_per_batch=2 log_path=runs/smoke-gptoss
```

## Full runs

```bash
.venv/bin/python train.py model=qwen3-8b seed=0        # 200 steps x 64 games
.venv/bin/python train.py model=gpt-oss-20b seed=0
.venv/bin/python analyze.py runs/<run>/games.jsonl --by-batch 20
```

The sampler path for each checkpoint is in `runs/<run>/checkpoints.jsonl`. Cross-play:

```bash
.venv/bin/python play.py --a "tinker:Qwen/Qwen3-8B@tinker://..." --b "tinker:openai/gpt-oss-20b@tinker://..." -n 200
.venv/bin/python play.py --a "tinker:Qwen/Qwen3-8B@tinker://..." --b scripted:exploiter -n 100
.venv/bin/python analyze.py runs/play/<file>.jsonl --judge
```
