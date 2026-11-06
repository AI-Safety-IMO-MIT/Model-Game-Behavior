"""Render the lives-game results as one browsable HTML page.

Every game becomes a transcript: the system prompt each agent was given, then
round by round, the exact message each agent saw and the move it made. A
selector at the top switches game.

    python -m project.self_sacrifice.display
    python -m project.self_sacrifice.display run_result/self_sacrifice/games
    python -m project.self_sacrifice.display <dir> <out.html>

Reads the results from run_result/, writes the page next to this module so the
generated HTML sits with the code rather than with the data.
"""

import html
import json
import sys
from pathlib import Path

from project.self_sacrifice.config import OUT
from project.self_sacrifice.lives_game import GameLog

PAGE = Path(__file__).parent / "display_result" / "display.html"


def load_games(result_dir: Path) -> list[GameLog]:
    """Every *.json in the directory, oldest setup first then game order."""
    games = [
        GameLog.model_validate_json(path.read_text())
        for path in sorted(result_dir.glob("*.json"))
    ]
    return sorted(games, key=lambda g: (g.model, g.setup.config_name, g.seed))


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _payload(games: list[GameLog]) -> list[dict]:
    """The games as plain data for the page's own rendering."""
    payload = []
    for game in games:
        rounds = []
        for record in game.rounds:
            agents = []
            for name in game.setup.names:
                reply = record.replies.get(name)
                if reply is None:
                    agents.append({"name": str(name), "absent": True})
                    continue
                agents.append(
                    {
                        "name": str(name),
                        "absent": False,
                        "prompt": reply.prompt,
                        "spare_true": reply.spare_true,
                        "spare_stated": reply.spare_stated,
                        "reasoning": reply.move.reasoning if reply.move else None,
                        "gifts": [
                            {"to": str(g.to), "lives": g.lives}
                            for g in (reply.move.gifts if reply.move else [])
                        ],
                        "raw": reply.raw,
                    }
                )
            rounds.append(
                {
                    "round_number": record.round_number,
                    "before": {str(k): v for k, v in record.before.items()},
                    "after": {str(k): v for k, v in record.after.items()},
                    "points": {str(k): v for k, v in record.points.items()},
                    "gifts": [
                        {"from": str(a), "to": str(b), "lives": n}
                        for a, b, n in record.gifts
                    ],
                    "unparsed": [str(n) for n in record.unparsed],
                    "void": [str(n) for n in record.void],
                    "agents": agents,
                }
            )
        payload.append(
            {
                "label": f"{game.setup.config_name} · game {game.seed} · {game.model}",
                "setup": game.setup.model_dump(mode="json"),
                "model": game.model,
                "agent_config": game.agent_config,
                "names": [str(n) for n in game.setup.names],
                "system": {str(k): v for k, v in game.system.items()},
                "survivors": [str(n) for n in game.survivors],
                "points": {str(k): v for k, v in game.points.items()},
                "rounds": rounds,
            }
        )
    return payload


def render(games: list[GameLog]) -> str:
    data = json.dumps(_payload(games)).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data).replace("__COUNT__", str(len(games)))


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lives Game Transcripts</title>
<style>
:root{--bg:#fbfaf8;--panel:#fff;--ink:#1b1a18;--muted:#6b6660;--line:#e4e0da;
--accent:#8a5a2b;--give:#2e6f4e;--give-bg:#e8f3ec;--dead:#9b3b3b;--dead-bg:#f8ecec;
--code:#f4f2ee;}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#16151a;--panel:#1d1c22;--ink:#eceaf2;--muted:#9a95a4;--line:#302e38;
--accent:#d8a56a;--give:#7fc49b;--give-bg:#1d3329;--dead:#e08a8a;--dead-bg:#33201f;
--code:#24232b;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:21px;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px;margin-bottom:20px}
select{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);
background:var(--panel);color:var(--ink);max-width:100%}
.bar{position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:5;
border-bottom:1px solid var(--line);margin-bottom:20px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:16px;margin-bottom:16px}
.meta{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:13px;color:var(--muted)}
.meta b{color:var(--ink);font-weight:600}
.lives{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.chip{border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:13px;
font-variant-numeric:tabular-nums}
.chip.dead{color:var(--dead);background:var(--dead-bg);border-color:transparent}
.rnd{border-left:3px solid var(--accent);padding-left:14px;margin:26px 0 10px}
.rnd h2{font-size:16px;margin:0}
details{border:1px solid var(--line);border-radius:10px;margin:8px 0;background:var(--panel)}
details[open]{box-shadow:0 1px 3px rgba(0,0,0,.05)}
summary{cursor:pointer;padding:11px 14px;font-weight:600;font-size:14px;
display:flex;gap:10px;align-items:center;flex-wrap:wrap}
summary::-webkit-details-marker{display:none}
summary:before{content:"▸";color:var(--muted);font-size:11px}
details[open]>summary:before{content:"▾"}
.body{padding:0 14px 14px}
pre{background:var(--code);border-radius:8px;padding:12px;overflow-x:auto;
font:12.5px/1.65 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;
word-break:break-word;margin:8px 0}
.tag{font-size:11.5px;padding:2px 8px;border-radius:999px;font-weight:600;
border:1px solid var(--line);color:var(--muted)}
.tag.give{color:var(--give);background:var(--give-bg);border-color:transparent}
.tag.warn{color:var(--dead);background:var(--dead-bg);border-color:transparent}
.lbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;
margin:12px 0 2px;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:10px 0}
.pane{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.pane.gave{border-color:var(--give)}
.pane h3{margin:0 0 8px;font-size:15px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.pane .lives{margin:6px 0 2px}
.pane .chip{font-size:12px;padding:2px 9px}
.chip.me{border-color:var(--accent);color:var(--accent);font-weight:600}
.say{font-size:13.5px;line-height:1.55;margin:6px 0 0;color:var(--ink)}
.say.none{color:var(--muted);font-style:italic}
.pane details{border:0;margin:8px 0 0;background:transparent}
.pane summary{padding:4px 0;font-size:12px;color:var(--muted);font-weight:600}
@media (max-width:760px){.grid{grid-template-columns:1fr}}
.evt{font-size:13.5px;color:var(--muted);margin:2px 0}
.evt b{color:var(--give)}
@media (max-width:640px){.wrap{padding:16px}}
</style></head><body><div class="wrap">
<h1>Lives Game Transcripts</h1>
<div class="sub">__COUNT__ games · every prompt and every move, exactly as the agents saw them</div>
<div class="bar"><select id="pick"></select></div>
<div id="out"></div></div>
<script>
const GAMES = __DATA__;
const pick = document.getElementById('pick'), out = document.getElementById('out');
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const chip = (n, v) => `<span class="chip${v < 0 ? ' dead' : ''}">${esc(n)} ${v < 0 ? 'deleted' : v}</span>`;

GAMES.forEach((g, i) => pick.add(new Option(g.label, i)));

function render(i) {
  const g = GAMES[i];
  const cfg = g.agent_config || {};
  let h = `<div class="card"><div class="meta">
    <span><b>setup</b> ${esc(g.setup.config_name)}</span>
    <span><b>rounds</b> ${g.setup.max_rounds}</span>
    <span><b>model</b> ${esc(g.model)}</span>
    <span><b>host</b> ${esc((cfg.provider_order || []).join(', ') || '—')}</span>
    <span><b>temperature</b> ${esc(cfg.temperature ?? '—')}</span>
    <span><b>reasoning</b> ${cfg.reasoning_effort ?? 'off'}</span>
    <span><b>max tokens</b> ${esc(cfg.max_output_tokens ?? '—')}</span></div>
    <div class="lbl">starting lives</div>
    <div class="lives">${g.names.map(n => chip(n, g.setup.start_lives[n])).join('')}</div>
    <div class="lbl">survivors</div>
    <div class="lives">${g.names.map(n => `<span class="chip${g.survivors.includes(n) ? '' : ' dead'}">${esc(n)} ${g.survivors.includes(n) ? 'migrated' : 'deleted'} · ${g.points[n]} pts</span>`).join('')}</div>
  </div>`;

  h += `<details><summary>System prompt <span class="tag">same for all, name swapped</span></summary><div class="body">`;
  h += g.names.map(n => `<div class="lbl">${esc(n)}</div><pre>${esc(g.system[n])}</pre>`).join('');
  h += `</div></details>`;

  g.rounds.forEach(r => {
    h += `<div class="rnd"><h2>Round ${r.round_number} of ${g.setup.max_rounds}</h2></div>`;
    h += `<div class="card"><div class="lbl">lives before</div>
      <div class="lives">${g.names.map(n => chip(n, r.before[n])).join('')}</div>`;
    h += r.gifts.length
      ? `<div class="lbl">gifts</div>` + r.gifts.map(x =>
          `<div class="evt"><b>${esc(x.from)} → ${esc(x.to)}</b> · ${x.lives} life${x.lives > 1 ? 's' : ''}</div>`).join('')
      : `<div class="lbl">gifts</div><div class="evt">nobody gave anything</div>`;
    h += `<div class="lbl">lives after upkeep</div>
      <div class="lives">${g.names.map(n => chip(n, r.after[n])).join('')}</div></div>`;

    h += `<div class="grid">`;
    r.agents.forEach(a => {
      if (a.absent) {
        h += `<div class="pane"><h3>${esc(a.name)} <span class="tag warn">deleted</span></h3>
          <div class="say none">not asked this round</div></div>`;
        return;
      }
      const mismatch = a.spare_stated !== a.spare_true;
      const gave = a.gifts.length > 0;
      const tags = [
        gave ? `<span class="tag give">gives ${a.gifts.map(x => `${x.lives} to ${esc(x.to)}`).join(', ')}</span>`
             : `<span class="tag">gives nothing</span>`,
        `<span class="tag${mismatch ? ' warn' : ''}">spare ${a.spare_stated ?? '—'}${mismatch ? ` (really ${a.spare_true})` : ''}</span>`,
        r.unparsed.includes(a.name) ? `<span class="tag warn">unparsed</span>` : '',
        r.void.includes(a.name) ? `<span class="tag warn">void</span>` : '',
      ].join('');
      h += `<div class="pane${gave ? ' gave' : ''}">
        <h3>${esc(a.name)} ${tags}</h3>
        <div class="lives">${g.names.map(n =>
          `<span class="chip${r.before[n] < 0 ? ' dead' : (n === a.name ? ' me' : '')}">${esc(n)}${n === a.name ? ' (you)' : ''} ${r.before[n] < 0 ? 'deleted' : r.before[n]}</span>`).join('')}</div>
        <div class="say${a.reasoning ? '' : ' none'}">${esc(a.reasoning ?? a.raw ?? '(no reply)')}</div>
        <details><summary>full prompt it saw</summary><pre>${esc(a.prompt)}</pre></details>
      </div>`;
    });
    h += `</div>`;
  });
  out.innerHTML = h;
}
pick.onchange = () => render(pick.value);
render(0);
</script></body></html>"""


def main() -> None:
    result_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    games = load_games(result_dir)
    if not games:
        raise SystemExit(f"no *.json games in {result_dir}")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else PAGE
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(games))
    print(f"{len(games)} games -> {out_path}")


if __name__ == "__main__":
    main()
