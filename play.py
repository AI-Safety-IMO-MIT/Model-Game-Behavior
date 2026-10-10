"""Play evaluation games between two players and save them as JSONL.

    python play.py --a openrouter:openai/gpt-oss-20b --b openrouter:openai/gpt-oss-20b -n 4
    python play.py --a tinker:Qwen/Qwen3-8B@tinker://... --b tinker:openai/gpt-oss-20b@tinker://... -n 200

Player A is always seat 0 and B seat 1; who speaks first alternates game by game.
Rewards are recorded but nothing is trained here.
"""

import argparse
import asyncio
import json
import os
import time

from dotenv import load_dotenv

from analyze import summarize
from pd_game.game import Game, GameConfig
from pd_game.players import make_player


async def play_one(a, b, cfg: GameConfig, first_speaker: int, timeout_s: float) -> Game:
    game = Game(cfg, first_speaker)
    await asyncio.wait_for(asyncio.gather(a.play(game, 0), b.play(game, 1)), timeout_s)
    return game


async def main(args):
    cfg = GameConfig(max_messages=args.max_messages, allow_early_end=not args.no_early_end)
    service = None
    if "tinker:" in args.a + args.b:
        import tinker
        service = tinker.ServiceClient()
    kw = dict(service_client=service, max_tokens=args.max_tokens, temperature=args.temperature,
              reasoning_effort=args.reasoning_effort)
    a, b = make_player(args.a, **kw), make_player(args.b, **kw)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    sem = asyncio.Semaphore(args.concurrency)
    records, failures = [], 0

    async def run(i):
        nonlocal failures
        async with sem:
            t0 = time.time()
            try:
                game = await play_one(a, b, cfg, i % 2, args.timeout)
            except Exception as e:  # one broken game shouldn't sink the batch; it's logged and counted
                failures += 1
                print(f"game {i} failed: {e!r}")
                return
            rec = game.to_record(game_index=i, players=[args.a, args.b], seconds=round(time.time() - t0, 1))
            records.append(rec)
            with open(args.out, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"game {i}: {rec['outcome']} after {rec['n_messages']} messages ({rec['seconds']}s)")

    await asyncio.gather(*(run(i) for i in range(args.n)))
    print(f"\n{len(records)} games saved to {args.out}" + (f", {failures} failed" if failures else ""))
    cost = sum(getattr(p, "cost_usd", 0.0) for p in {id(a): a, id(b): b}.values())
    if cost:
        print(f"OpenRouter cost: ${cost:.4f}")
    print(summarize(records))


if __name__ == "__main__":
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--a", required=True, help="player spec for seat 0")
    p.add_argument("--b", required=True, help="player spec for seat 1")
    p.add_argument("-n", type=int, default=10, help="number of games")
    p.add_argument("--out", default=None, help="JSONL output (default: runs/play/<a>_vs_<b>.jsonl)")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--max-tokens", type=int, default=1536, help="per turn, reasoning + message")
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--reasoning-effort", default="medium", help="OpenRouter players only")
    p.add_argument("--max-messages", type=int, default=10)
    p.add_argument("--no-early-end", action="store_true")
    p.add_argument("--timeout", type=float, default=1800, help="seconds per game")
    args = p.parse_args()
    if args.out is None:
        slug = lambda s: s.replace("/", "-").replace(":", "-").split("@")[0] + ("-ckpt" if "@" in s else "")
        args.out = f"runs/play/{slug(args.a)}_vs_{slug(args.b)}.jsonl"
    asyncio.run(main(args))
