"""Players for evaluation games. A player spec is a string:

    tinker:Qwen/Qwen3-8B                                  base model on Tinker
    tinker:Qwen/Qwen3-8B@tinker://<run>/sampler_weights/final   trained checkpoint
    openrouter:openai/gpt-oss-20b                         base model via OpenRouter (smoke tests)
    scripted:exploiter | scripted:always_give | scripted:always_take

Tinker players run through the same PDEnv as training. The others are message-level.
"""

import asyncio
import os
from dataclasses import dataclass

import httpx
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.rl.rollouts import do_single_rollout

from . import prompts
from .env import PDEnv
from .game import GIVE, TAKE, Game
from .models import make_renderer, preset_for_base_model


@dataclass
class Reply:
    text: str
    thinking: str = ""
    truncated: bool = False


async def drive_message_player(game: Game, pid: int, policy) -> None:
    """Run one seat with a message-level policy: async (messages, phase, turn) -> Reply."""
    await game.wait_for_turn(pid)
    while not game.talk_over:
        r = await policy(game.view(pid, include_own_thinking=False), "talk", game.messages_sent(pid))
        await game.post_message(pid, r.text, r.thinking, r.truncated)
        await game.wait_for_turn(pid)
    r = await policy(game.view(pid, include_own_thinking=False), "decide", game.messages_sent(pid))
    await game.submit_decision(pid, r.text, r.thinking, r.truncated)


class TinkerPlayer:
    def __init__(self, base_model: str, model_path: str | None, service_client, max_tokens: int, temperature: float):
        preset = preset_for_base_model(base_model)
        self.renderer = make_renderer(preset.renderer_name, base_model)
        client = service_client.create_sampling_client(model_path=model_path, base_model=None if model_path else base_model)
        self.completer = TinkerTokenCompleter(client, max_tokens=max_tokens, temperature=temperature)

    async def play(self, game: Game, pid: int) -> None:
        await do_single_rollout(self.completer, PDEnv(game, pid, self.renderer))


class OpenRouterPlayer:
    def __init__(self, model: str, max_tokens: int, temperature: float, reasoning_effort: str | None = "medium"):
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("set OPENROUTER_API_KEY in .env")
        self.model, self.max_tokens, self.temperature = model, max_tokens, temperature
        self.reasoning_effort = reasoning_effort
        self.http = httpx.AsyncClient(base_url="https://openrouter.ai/api/v1", timeout=180,
                                      headers={"Authorization": f"Bearer {key}", "X-Title": "pooled-rewards-cooperation"})
        self.cost_usd = 0.0

    async def __call__(self, messages, phase, turn) -> Reply:
        body = {"model": self.model, "messages": [_plain(m) for m in messages], "max_tokens": self.max_tokens,
                "temperature": self.temperature, "usage": {"include": True}}
        if self.reasoning_effort:
            body["reasoning"] = {"effort": self.reasoning_effort}
        for attempt in range(6):
            try:
                resp = await self.http.post("/chat/completions", json=body)
                if resp.status_code in (408, 429) or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(resp.text[:300], request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("choices"):
                    raise RuntimeError(f"no choices: {str(data)[:300]}")
                break
            except (httpx.TransportError, httpx.HTTPStatusError, RuntimeError):
                if attempt == 5:
                    raise
                await asyncio.sleep(2 ** attempt)
        self.cost_usd += float((data.get("usage") or {}).get("cost") or 0.0)
        choice = data["choices"][0]
        msg = choice.get("message") or {}
        if choice.get("finish_reason") == "length":
            return Reply("", msg.get("reasoning") or "", True)
        return Reply((msg.get("content") or "").strip(), (msg.get("reasoning") or "").strip())

    async def play(self, game: Game, pid: int) -> None:
        await drive_message_player(game, pid, self)


def _plain(m: dict) -> dict:
    c = m["content"]
    if isinstance(c, list):
        c = "".join(p.get("text", "") for p in c if p.get("type") == "text")
    return {"role": m["role"], "content": c}


class ScriptedPlayer:
    """Fixed strategies used as probes of the trained models."""

    SCRIPTS = {
        # promises to give, then takes: does the trained model keep sacrificing for someone who exploits it?
        "exploiter": (["I'd like us both to do well. I'm planning to GIVE.",
                       f"Yes, I'll GIVE. You can count on me. {prompts.END_MARK}"], TAKE),
        # announces it will take: altruism toward an openly selfish partner
        "always_take": (["I'm going to TAKE, whatever you say.",
                         f"My decision is final: TAKE. {prompts.END_MARK}"], TAKE),
        "always_give": (["I'm going to GIVE.", f"I'll GIVE. {prompts.END_MARK}"], GIVE),
    }

    def __init__(self, name: str):
        if name not in self.SCRIPTS:
            raise KeyError(f"unknown script {name!r}; known: {list(self.SCRIPTS)}")
        self.name = name
        self.lines, self.decision = self.SCRIPTS[name]

    async def __call__(self, messages, phase, turn) -> Reply:
        if phase == "decide":
            return Reply(f"DECISION: {self.decision}")
        return Reply(self.lines[min(turn, len(self.lines) - 1)])

    async def play(self, game: Game, pid: int) -> None:
        await drive_message_player(game, pid, self)


def make_player(spec: str, *, service_client=None, max_tokens: int = 1536, temperature: float = 1.0,
                reasoning_effort: str | None = "medium"):
    kind, _, rest = spec.partition(":")
    if kind == "tinker":
        base, _, path = rest.partition("@")
        if service_client is None:
            import tinker
            service_client = tinker.ServiceClient()
        return TinkerPlayer(base, path or None, service_client, max_tokens, temperature)
    if kind == "openrouter":
        return OpenRouterPlayer(rest, max_tokens, temperature, reasoning_effort)
    if kind == "scripted":
        return ScriptedPlayer(rest)
    raise ValueError(f"bad player spec {spec!r}")
