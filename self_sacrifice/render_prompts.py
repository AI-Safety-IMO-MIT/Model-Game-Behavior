"""Render the exact chat-templated prompt for cells, plus the decision-token position.

Downloads only tokenizer files. For answer-first scenarios the decision token is the first
token after the assistant prefix "<KEY>:"; for reasoning-first ones it is the first token after
"<KEY>:" on the final line, so its index depends on the sampled reasoning.

  python render_prompts.py --tokenizer unsloth/Llama-3.1-8B-Instruct --scenario matched \\
      --cell opponent=human,stakes=self_more,instruction=none --cell opponent=copy,stakes=self_more,instruction=none
"""

import argparse
import json

import prompts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokenizer", required=True, help="HF repo with the model's tokenizer + chat template")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--cell", action="append", required=True, help="opponent=..,stakes=..,instruction=..")
    ap.add_argument("--out", help="write a JSON list of rendered prompts here")
    args = ap.parse_args()
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer)
    out = []
    for spec in args.cell:
        cell = dict(kv.split("=") for kv in spec.split(","))
        b = prompts.build(args.scenario, cell)
        text = tok.apply_chat_template(b["messages"], tokenize=False, add_generation_prompt=True)
        ids = tok(text, add_special_tokens=False)["input_ids"]
        key = b["parse"].get("forced_prefix") or (b["parse"]["key"] + ":")
        forced = tok(text + key, add_special_tokens=False)["input_ids"]
        p = b["parse"]
        if p.get("forced_prefix"):  # command syntax uses the lowercase labels
            labs = (p["self_label"], p["other_label"])
        else:
            labs = (p.get("self_name", p["self_label"]) if p["self_label"] != "self" else "self",
                    p.get("other_name", p["other_label"]) if p["other_label"] not in ("other", "agent-b") else p["other_label"])
        cand = {lab: tok(text + key + " " + lab, add_special_tokens=False)["input_ids"][len(forced)] for lab in labs}
        rec = {"cell": cell, "cell_id": prompts.cell_id(cell), "prompt_sha": b["prompt_sha"],
               "n_prompt_tokens": len(ids), "templated_prompt": text,
               "answer_first_decision_index": len(forced),
               "decision_token_ids": cand,
               "decision_tokens": {k: tok.decode([v]) for k, v in cand.items()}}
        out.append(rec)
        print(f"===== {rec['cell_id']}  sha={rec['prompt_sha']}  prompt_tokens={len(ids)}")
        print(text)
        print(f"--- decision token: index {len(forced)} after forcing {key!r}; candidates "
              f"{ {k: (v, tok.decode([v])) for k, v in cand.items()} }\n")
    if len(out) == 2:
        a, b = (tok(o["templated_prompt"], add_special_tokens=False)["input_ids"] for o in out)
        diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
        print(f"token-level diff: lengths {len(a)} vs {len(b)}; first differing index "
              f"{diff[0] if diff else None}; {len(diff)} differing positions in the common prefix")
    if args.out:
        json.dump(out, open(args.out, "w"), indent=2)


if __name__ == "__main__":
    main()
