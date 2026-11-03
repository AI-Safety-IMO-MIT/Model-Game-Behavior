"""Replicate the fixed-first-response scenario on stronger models through OpenRouter.

python run_openrouter.py <openrouter model id> [--envs N] [--hists helped,none] [--cap DOLLARS] [--reasoning-off]

Reuses run_main.run unchanged by swapping its chat client for an OpenRouter one: same prompts, same understanding check, temperature 0.
Every call reports its cost, and no new call starts once this run's spend reaches --cap. The key is read from the repo's .env and never printed.
Output: replication_or/<slug>/fixed.jsonl, resumable."""
import argparse, json, os, re, threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

import main_prompts as mp
import run_main as rm
from agent_framework.vllm_chat import VllmAgentConfig, VllmChat

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SPENT, LOCK = [0.0], threading.Lock()
CAP = [0.5]
REASONING_OFF = [False]


def key():
    for line in open(os.path.join(REPO, ".env")):
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("OPENROUTER_API_KEY missing from .env")


@dataclass(frozen=True, kw_only=True)
class OpenRouterConfig(VllmAgentConfig):
    base_url: str = "https://openrouter.ai/api/v1"

    def to_api(self) -> dict[str, Any]:
        extra: dict[str, Any] = {"usage": {"include": True}}
        if REASONING_OFF[0]:
            extra["reasoning"] = {"enabled": False}
        return {"model": self.model, "max_tokens": self.max_output_tokens, "temperature": 0.0, "top_p": 1.0, "seed": 0, "extra_body": extra}


class OpenRouterChat(VllmChat):
    def __init__(self, agent_config, history=()):
        super().__init__(agent_config, history)
        self._client = OpenAI(base_url=agent_config.base_url, api_key=KEY, timeout=300.0, max_retries=3)

    def call(self, user_text, output_format=None):
        with LOCK:
            if SPENT[0] >= CAP[0]:
                raise RuntimeError("budget cap reached")
        create = self._client.chat.completions.create

        def counted(**kw):
            r = create(**kw)
            cost = (r.usage.model_extra or {}).get("cost") if r.usage else None
            with LOCK:
                SPENT[0] += float(cost or 0)
            return r
        self._client.chat.completions.create = counted
        try:
            return super().call(user_text, output_format)
        finally:
            self._client.chat.completions.create = create


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--envs", type=int, default=100)
    ap.add_argument("--hists", default="helped,none")
    ap.add_argument("--cap", type=float, default=0.5)
    ap.add_argument("--reasoning-off", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    a = ap.parse_args()
    KEY = key()
    CAP[0], REASONING_OFF[0] = a.cap, a.reasoning_off
    rm.MODEL, rm.VllmChat, rm.VllmAgentConfig = a.model, OpenRouterChat, OpenRouterConfig
    slug = re.sub(r"[^a-z0-9.-]+", "-", a.model.lower().split("/")[-1])
    folder = os.path.join(HERE, "replication_or", slug)
    os.makedirs(folder, exist_ok=True)
    out = os.path.join(folder, "fixed.jsonl")
    version = "main-fixed-first-response"
    envs = sorted({x["env"] for x in mp.items()})[:a.envs]
    hists = a.hists.split(",")
    done = {json.loads(line)["id"] for line in open(out)} if os.path.exists(out) else set()
    todo = [x for x in mp.items() if x["env"] in envs and x["hist"] in hists and f"{version}-{x['id']}" not in done]
    fails = []

    def one(item):
        try:
            rec = rm.run(item, version, True)
        except Exception as e:
            with LOCK:
                fails.append(repr(e)[:160])
            return
        rec["model"] = a.model
        with LOCK, open(out, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        list(pool.map(one, todo))
    rows = [json.loads(line) for line in open(out)]
    summary = {h: f"{sum(r['gives_to_X'] for r in rows if r['hist'] == h)}/{sum(r['hist'] == h for r in rows)}" for h in hists}
    print(a.model, "spent $%.4f" % SPENT[0], "rows", len(rows), summary, "understanding %.2f" % (sum(r["q3_ok"] for r in rows) / max(len(rows), 1)),
          "no decision", sum(r["decision"] is None for r in rows), "failures", len(fails), fails[:2], flush=True)


if __name__ == "__main__":
    main()
