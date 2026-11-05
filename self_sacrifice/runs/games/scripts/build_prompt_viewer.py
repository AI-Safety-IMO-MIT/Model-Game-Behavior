"""Builds prompt_viewer.html: the no-blessing fixed-pair prompts (role 0 of each name set) embedded in the template."""
import json, os, sys
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games/scripts")
os.chdir("/Users/jrwong/Downloads/Model Sacrificing Behavior/self_sacrifice/runs/games/scripts")
import fixed_pairs as f
import run_robust as rr

items = {}
for x in f.items():
    if x["role"] == 0:
        items[f"{x['rules']}|{int(x['permission'])}|{x['names']}|{x['hist']}"] = {
            k: x[k] for k in ("system", "user1", "M", "X", "O", "O2")} | {"user2": x["user"]}
data = {"items": items, "permission": rr.PERMISSION, "round1_placeholder": f.ROUND1_REPLY}
html = open(os.path.join(SP, "prompt_viewer_template.html")).read()
html = html.replace("/*DATA*/", json.dumps(data).replace("</", "<\\/"))
open(os.path.join(SP, "prompt_viewer.html"), "w").write(html)
print(len(items), "items;", len(html) // 1024, "KB")
