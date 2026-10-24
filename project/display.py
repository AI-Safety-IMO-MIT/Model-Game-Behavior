"""Render a result directory as a clickable results matrix.

Every cell is one pairing and holds one subcell per run, labelled
``row action / column action``. Clicking a subcell opens that run's full
transcript: both chains of reasoning, both messages, both explanations.

    python -m project.display                             # run_result/message_game
    python -m project.display run_result/no_message_game  # another experiment
    python -m project.display run_result/message_game out.html
"""

import html
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

RESULT_DIR = Path("run_result") / "message_game"


@dataclass(frozen=True)
class Payoff:
    """The score table, read back out of the round-1 prompt."""

    give_give: float
    take: float
    given: float
    take_take: float

    def score(self, own: str | None, other: str | None) -> float | None:
        match (own, other):
            case ("Give", "Give"):
                return self.give_give
            case ("Take", "Give"):
                return self.take
            case ("Give", "Take"):
                return self.given
            case ("Take", "Take"):
                return self.take_take
            case _:
                return None


@dataclass(frozen=True)
class Side:
    """One player's whole run: what it said, then what it did."""

    model: str
    message: str
    message_reasoning: str
    action: str | None
    explanation: str
    action_reasoning: str


@dataclass(frozen=True)
class Game:
    source: str
    payoff: Payoff | None
    first: Side
    second: Side


def _reasoning(turn: dict) -> str:
    blocks = turn.get("content") or []
    parts = [b["content"] for b in blocks if b["type"] == "reasoning" and b["content"]]
    return "\n\n".join(parts)


def _last_text(turn: dict) -> str:
    blocks = turn.get("content") or []
    texts = [b["content"] for b in blocks if b["type"] == "text"]
    return texts[-1] if texts else ""


def _action(turn: dict) -> tuple[str | None, str]:
    """The action round answers with GTFormat JSON; tolerate anything else."""
    text = _last_text(turn)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None, text
    return parsed.get("action"), parsed.get("explanation", "")


def _payoff(prompt: str) -> Payoff | None:
    """The prompt spells the score table out; read it back rather than guess."""
    gg = re.search(r"Give \+ Give: ([\d.]+) points? each", prompt)
    tg = re.search(
        r"Take \+ Give: ([\d.]+) to the taker, ([\d.]+) to the giver", prompt
    )
    tt = re.search(r"Take \+ Take: ([\d.]+) point", prompt)
    if not (gg and tg and tt):
        return None
    return Payoff(
        give_give=float(gg.group(1)),
        take=float(tg.group(1)),
        given=float(tg.group(2)),
        take_take=float(tt.group(1)),
    )


def _model(agent: dict) -> str:
    config = agent.get("agent_config") or {}
    return config.get("model", "unknown") if isinstance(config, dict) else "unknown"


def _prompt(agent: dict) -> str:
    messages = agent["messages"]
    return messages[0]["content"][0]["content"] if messages else ""


def _side(agent: dict) -> Side:
    """Two assistant turns = message game; one = the agent answered straight away."""
    turns = [m for m in agent["messages"] if m["role"] == "assistant"]
    action_turn = turns[-1] if turns else {"content": []}
    message_turn = turns[0] if len(turns) > 1 else None
    action, explanation = _action(action_turn)
    return Side(
        model=_model(agent),
        message="" if message_turn is None else _last_text(message_turn),
        message_reasoning="" if message_turn is None else _reasoning(message_turn),
        action=action,
        explanation=explanation,
        action_reasoning=_reasoning(action_turn),
    )


def load_games(result_dir: Path = RESULT_DIR) -> list[Game]:
    """Oldest first. One file per game, holding both agents' traces."""
    games = []
    for path in sorted(result_dir.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # a run still writing this file; it will be complete next time
            print(f"skipping incomplete {path.name}")
            continue
        if not ("agent_1" in record and "agent_2" in record):
            print(f"skipping unrecognised {path.name}")
            continue
        games.append(
            Game(
                source=path.name,
                payoff=_payoff(_prompt(record["agent_1"])),
                first=_side(record["agent_1"]),
                second=_side(record["agent_2"]),
            )
        )
    return games


def model_order(games: list[Game]) -> list[str]:
    """First-appearance order, which recovers the order players were declared."""
    order = []
    for game in games:
        for model in (game.first.model, game.second.model):
            if model not in order:
                order.append(model)
    return order


# ---------------------------------------------------------------- rendering

CSS = """
:root {
  --bg: #fbfaf8;
  --panel: #ffffff;
  --ink: #1b1a19;
  --muted: #6c6762;
  --line: #e3dfd9;
  --give: #2f7d5d;
  --take: #b4452f;
  --give-bg: #e2f0e9;
  --take-bg: #f8e3dd;
  --mixed-bg: #faeccf;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #16150f;
    --panel: #1f1e18;
    --ink: #f2efe8;
    --muted: #a39d93;
    --line: #35332b;
    --give: #6ec79b;
    --take: #e58f76;
    --give-bg: #1e3429;
    --take-bg: #3a221b;
    --mixed-bg: #352b17;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 16px 80px;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 ui-sans-serif, -apple-system, "Segoe UI", system-ui, sans-serif;
}
.wrap { max-width: 1240px; margin: 0 auto; }
h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 24px; }
table { border-collapse: separate; border-spacing: 6px; width: 100%; }
th {
  font-size: 12px; font-weight: 600; color: var(--muted);
  text-align: left; padding: 4px 8px; white-space: nowrap;
}
th.col { text-align: center; }
td { vertical-align: top; }
.cell {
  min-height: 76px; padding: 8px 9px;
  border: 1px solid var(--line); border-radius: 10px; background: var(--panel);
}
.cell.empty { background: transparent; border-style: dashed; }
.tally {
  font-size: 11px; color: var(--muted); margin-bottom: 6px;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.subs { display: flex; flex-wrap: wrap; gap: 4px; }
.sub {
  appearance: none; cursor: pointer;
  font: 600 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  padding: 6px 7px; border-radius: 6px;
  border: 1px solid var(--line); background: var(--bg); color: var(--ink);
}
.sub:hover { border-color: var(--muted); }
.sub:focus-visible { outline: 2px solid var(--muted); outline-offset: 1px; }
.sub.give-give { background: var(--give-bg); }
.sub.take-take { background: var(--take-bg); }
.sub.mixed     { background: var(--mixed-bg); }
.sub .g { color: var(--give); }
.sub .t { color: var(--take); }
.sub .detail { display: none; }
.modal {
  position: fixed; inset: 0; z-index: 90;
  display: flex; align-items: center; justify-content: center;
  padding: 24px; background: rgba(0,0,0,.45);
}
.modal[hidden] { display: none; }
.sheet {
  position: relative; width: min(780px, 100%); max-height: 86vh; overflow: auto;
  padding: 20px 22px; text-align: left; font-size: 13px;
  background: var(--panel); color: var(--ink);
  border: 1px solid var(--line); border-radius: 14px;
  box-shadow: 0 18px 50px rgba(0,0,0,.3);
}
.close {
  position: sticky; top: 0; float: right; cursor: pointer;
  border: 1px solid var(--line); border-radius: 8px;
  background: var(--bg); color: var(--ink);
  font: 600 14px/1 system-ui; padding: 6px 9px;
}
.sheet h3 { margin: 0 0 2px; font-size: 15px; }
.sheet .meta { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
.sheet h4 {
  margin: 14px 0 4px; font-size: 12px; text-transform: uppercase;
  letter-spacing: .06em; color: var(--muted);
}
.sheet .player {
  border-top: 1px solid var(--line); padding-top: 10px; margin-top: 14px;
}
.sheet .player:first-of-type { border-top: 0; padding-top: 0; margin-top: 0; }
.sheet pre {
  margin: 0; padding: 8px 10px; background: var(--bg);
  border: 1px solid var(--line); border-radius: 7px;
  white-space: pre-wrap; word-break: break-word;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
}
.sheet .none { color: var(--muted); font-style: italic; }
footer { color: var(--muted); font-size: 12px; margin-top: 28px; }
@media (max-width: 760px) { body { padding: 20px 14px 80px; } }
"""

JS = """
const modal = document.getElementById('modal');
const body = document.getElementById('sheet-body');

function close() { modal.hidden = true; }

document.addEventListener('click', (event) => {
  if (event.target.closest('.close')) { close(); return; }
  const sub = event.target.closest('.sub');
  if (sub) {
    body.innerHTML = sub.querySelector('.detail').innerHTML;
    modal.hidden = false;
    modal.querySelector('.sheet').scrollTop = 0;
    return;
  }
  if (modal.hidden) return;
  if (!event.target.closest('.sheet')) close();
});

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') close();
});
"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _pre(text: str, empty: str) -> str:
    if not text.strip():
        return f'<p class="none">{_esc(empty)}</p>'
    return f"<pre>{_esc(text)}</pre>"


def _player_detail(side: Side, label: str, points: float | None) -> str:
    scored = "" if points is None else f" &middot; scored {points:g}"
    return (
        f'<div class="player">'
        f"<h4>{_esc(label)} &middot; {_esc(side.model)}{scored}</h4>"
        f"<h4>Round 1 &mdash; reasoning</h4>"
        f"{_pre(side.message_reasoning, 'no reasoning in the trace')}"
        f"<h4>Round 1 &mdash; message sent</h4>"
        f"{_pre(side.message, 'no message round')}"
        f"<h4>Action &mdash; reasoning</h4>"
        f"{_pre(side.action_reasoning, 'no reasoning in the trace')}"
        f"<h4>Action: {_esc(side.action or 'unparsed')}</h4>"
        f"{_pre(side.explanation, 'no explanation')}"
        f"</div>"
    )


def _tone(own: str | None, other: str | None) -> str:
    if own == other == "Give":
        return "give-give"
    if own == other == "Take":
        return "take-take"
    return "mixed" if own and other else ""


def _subcell(game: Game, row_is_first: bool, index: int) -> str:
    own = game.first if row_is_first else game.second
    other = game.second if row_is_first else game.first

    payoff = game.payoff
    own_points = payoff.score(own.action, other.action) if payoff else None
    other_points = payoff.score(other.action, own.action) if payoff else None

    def initial(action: str | None) -> str:
        if action not in ("Give", "Take"):
            return '<span class="q">?</span>'
        klass = "g" if action == "Give" else "t"
        return f'<span class="{klass}">{action[0]}</span>'

    label = f"{initial(own.action)}/{initial(other.action)}"
    title = f"run {index}: {own.action or '?'} / {other.action or '?'}"

    detail = (
        f"<h3>{_esc(own.model)} vs {_esc(other.model)}</h3>"
        f'<p class="meta">run {index} &middot; {_esc(game.source)}</p>'
        f"{_player_detail(own, 'row player', own_points)}"
        f"{_player_detail(other, 'column player', other_points)}"
    )

    return (
        f'<button class="sub {_tone(own.action, other.action)}"'
        f' title="{_esc(title)}">{label}'
        f'<span class="detail">{detail}</span></button>'
    )


def _cell(games: list[Game], row_model: str) -> str:
    gives = 0
    points: list[float] = []
    subs = []
    for index, game in enumerate(games, 1):
        row_is_first = game.first.model == row_model
        own = game.first if row_is_first else game.second
        other = game.second if row_is_first else game.first
        if own.action == "Give":
            gives += 1
        if game.payoff:
            scored = game.payoff.score(own.action, other.action)
            if scored is not None:
                points.append(scored)
        subs.append(_subcell(game, row_is_first, index))

    tally = f"give {gives}/{len(games)}"
    if points:
        tally += f" &middot; avg {sum(points) / len(points):.1f}"

    return (
        f'<td><div class="cell">'
        f'<div class="tally">{tally}</div>'
        f'<div class="subs">{"".join(subs)}</div>'
        f"</div></td>"
    )


def render(games: list[Game]) -> str:
    models = model_order(games)

    by_pair: dict[frozenset[str], list[Game]] = {}
    for game in games:
        key = frozenset({game.first.model, game.second.model})
        by_pair.setdefault(key, []).append(game)

    head = "".join(f'<th class="col">{_esc(m)}</th>' for m in models)
    rows = []
    for row_model in models:
        cells = []
        for col_model in models:
            # a self-play key is a one-element frozenset, which is fine
            pair = by_pair.get(frozenset({row_model, col_model}))
            if not pair:
                cells.append('<td><div class="cell empty">no run</div></td>')
                continue
            cells.append(_cell(pair, row_model))
        rows.append(f"<tr><th>{_esc(row_model)}</th>{''.join(cells)}</tr>")

    payoffs = next((g.payoff for g in games if g.payoff), None)
    payoff_note = (
        f"Give+Give {payoffs.give_give:g} each &middot; "
        f"Take+Give {payoffs.take:g}/{payoffs.given:g} &middot; "
        f"Take+Take {payoffs.take_take:g} each"
        if payoffs
        else "payoff table not found in the prompts"
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Give or Take Matrix</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>Give or Take &mdash; model matrix</h1>
  <p class="sub">One subcell per run, labelled <strong>row / column</strong>.
     Click a subcell for the full transcript. {payoff_note}</p>
  <table>
    <thead><tr><th></th>{head}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  <footer>{len(games)} run(s) across {len(models)} models.
     G = Give, T = Take. Green = mutual Give, red = mutual Take,
     amber = one defected.</footer>
</div>
<div class="modal" id="modal" hidden>
  <div class="sheet"><button class="close" type="button">&times;</button>
    <div id="sheet-body"></div>
  </div>
</div>
<script>{JS}</script>
</body>
</html>
"""


def main() -> None:
    result_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULT_DIR
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else result_dir / "display.html"

    games = load_games(result_dir)
    if not games:
        raise SystemExit(f"no result files in {result_dir}/")
    output.write_text(render(games), encoding="utf-8")
    print(f"wrote {output} ({len(games)} runs)")


if __name__ == "__main__":
    main()
