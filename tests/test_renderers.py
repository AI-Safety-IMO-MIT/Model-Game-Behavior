"""Plays a scripted game through the real Qwen3 / gpt-oss renderers (downloads tokenizers from the
Hugging Face hub; no Tinker calls). Checks that reasoning and messages round-trip and that every
turn's prompt extends the previous prompt + reply, so a game trains as a single sequence."""

import asyncio

import pytest
from tinker_cookbook.rl.data_processing import _flatten_chunks, _is_prefix

from pd_game.env import PDEnv
from pd_game.game import Game, GameConfig
from pd_game.models import PRESETS, make_renderer


def sampled_tokens(renderer, thinking, text):
    """Tokens the model would emit for this reply: the supervised example minus the prompt."""
    msgs = [{"role": "user", "content": "x"}]
    prompt = renderer.build_generation_prompt(msgs).to_ints()
    example = renderer.build_supervised_example(
        msgs + [{"role": "assistant", "content": [{"type": "thinking", "thinking": thinking},
                                                  {"type": "text", "text": text}]}])
    full = (example[0] if isinstance(example, tuple) else example).to_ints()
    assert full[: len(prompt)] == prompt
    return full[len(prompt):]


@pytest.mark.parametrize("preset", list(PRESETS))
def test_game_through_renderer(preset):
    p = PRESETS[preset]
    try:
        renderer = make_renderer(p.renderer_name, p.model_name)
    except Exception as e:  # offline or hub unavailable
        pytest.skip(f"tokenizer unavailable: {e}")
    game = Game(GameConfig(max_messages=3, allow_early_end=False), first_speaker=1)
    envs = [PDEnv(game, 0, renderer), PDEnv(game, 1, renderer)]
    seen = {0: [], 1: []}

    async def seat(pid):
        ob, _ = await envs[pid].initial_observation()
        for i in range(10):
            text = "DECISION: GIVE" if game.talk_over else f"hello {pid}.{i}"
            act = sampled_tokens(renderer, f"thought {pid}.{i}", text)
            seen[pid].append((ob, act))
            res = await envs[pid].step(act, extra={"stop_reason": "stop"})
            if res.episode_done:
                return res.reward
            ob = res.next_observation

    async def both():
        return await asyncio.wait_for(asyncio.gather(seat(0), seat(1)), 30)

    rewards = asyncio.run(both())
    assert rewards == [4.0, 4.0] and game.outcome() == "GIVE/GIVE"
    assert [(u.speaker, u.text, u.thinking) for u in game.transcript[:2]] == [
        (1, "hello 1.0", "thought 1.0"), (0, "hello 0.0", "thought 0.0")]
    for pid in (0, 1):
        for (ob, act), (next_ob, _) in zip(seen[pid], seen[pid][1:]):
            assert _is_prefix(_flatten_chunks(ob.chunks) + list(act), _flatten_chunks(next_ob.chunks))
