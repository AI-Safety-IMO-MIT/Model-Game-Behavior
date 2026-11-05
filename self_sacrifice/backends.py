"""Generation backends: openrouter (API), vllm (GPU), hf (transformers).

Every backend exposes `generate(reqs)` yielding (req, result) pairs, where
req = {"key", "messages", "seed"} and result has:
  completion, finish_reason, provider, prompt_text, tokens, usage, cost, reasoning, error
`tokens` is a list of {"token", "logprob", "top": {str: logprob}} or None.
"""

import concurrent.futures as cf
import os
import random
import threading
import time

TOP_K = 20


def _empty_result(**kw):
    r = dict(completion=None, finish_reason=None, provider=None, prompt_text=None,
             tokens=None, usage=None, cost=None, reasoning=None, error=None)
    r.update(kw)
    return r


class OpenRouterBackend:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model_cfg, gen_cfg):
        import requests  # noqa: F401  (fail early if missing)
        self.model_cfg = model_cfg
        self.gen = gen_cfg
        self.key = os.environ.get("OPENROUTER_API_KEY") or _read_dotenv("OPENROUTER_API_KEY")
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY not set (env or .env)")
        self.stop = threading.Event()

    def _body(self, req):
        mc = self.model_cfg
        body = {
            "model": mc["openrouter_id"],
            "messages": req["messages"],
            "temperature": self.gen["temperature"],
            "max_tokens": self.gen["max_tokens"],
            "seed": req["seed"],
            "usage": {"include": True},
        }
        if mc.get("provider"):
            body["provider"] = mc["provider"]
        if mc.get("logprobs", False):
            body["logprobs"] = True
            body["top_logprobs"] = TOP_K
        body.update(mc.get("extra_body") or {})
        return body

    def _one(self, req):
        import requests
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        last_err = None
        for attempt in range(6):
            if self.stop.is_set():
                return _empty_result(error="cancelled")
            try:
                r = requests.post(self.URL, json=self._body(req), headers=headers, timeout=180)
                if r.status_code in (408, 429) or r.status_code >= 500:
                    last_err = f"HTTP {r.status_code}: {r.text[:300]}"
                    time.sleep(min(60, 2 ** attempt + random.random()))
                    continue
                if r.status_code != 200:
                    return _empty_result(error=f"HTTP {r.status_code}: {r.text[:500]}")
                d = r.json()
                if "error" in d:
                    last_err = f"API error: {str(d['error'])[:300]}"
                    time.sleep(min(60, 2 ** attempt + random.random()))
                    continue
                ch = d["choices"][0]
                msg = ch.get("message") or {}
                tokens = None
                lp = (ch.get("logprobs") or {}).get("content")
                if lp:
                    tokens = [
                        {"token": t["token"], "logprob": t["logprob"],
                         "top": {a["token"]: a["logprob"] for a in (t.get("top_logprobs") or [])}}
                        for t in lp
                    ]
                usage = d.get("usage") or {}
                return _empty_result(
                    completion=msg.get("content") or "",
                    reasoning=msg.get("reasoning"),
                    finish_reason=ch.get("finish_reason"),
                    provider=d.get("provider"),
                    tokens=tokens,
                    usage={k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                    cost=usage.get("cost"),
                )
            except Exception as e:  # network errors, bad JSON
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(min(60, 2 ** attempt + random.random()))
        return _empty_result(error=last_err or "unknown error")

    def generate(self, reqs):
        with cf.ThreadPoolExecutor(max_workers=self.gen.get("concurrency", 16)) as ex:
            futs = {ex.submit(self._one, r): r for r in reqs}
            try:
                for f in cf.as_completed(futs):
                    yield futs[f], f.result()
            finally:
                self.stop.set()
                for f in futs:
                    f.cancel()


class VLLMBackend:
    def __init__(self, model_cfg, gen_cfg):
        from vllm import LLM
        self.gen = gen_cfg
        self.llm = LLM(model=model_cfg["hf_id"], seed=gen_cfg["seed"], **(model_cfg.get("vllm_kwargs") or {}))
        self.tok = self.llm.get_tokenizer()

    def generate(self, reqs):
        from vllm import SamplingParams
        prompts = [self.tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True)
                   for r in reqs]
        params = [SamplingParams(temperature=self.gen["temperature"], max_tokens=self.gen["max_tokens"],
                                 seed=r["seed"], logprobs=TOP_K) for r in reqs]
        outs = self.llm.generate(prompts, params)
        for r, p, o in zip(reqs, prompts, outs):
            c = o.outputs[0]
            tokens = []
            for tid, lpd in zip(c.token_ids, c.logprobs or []):
                chosen = lpd[tid]
                tokens.append({
                    "token": chosen.decoded_token or "",
                    "logprob": chosen.logprob,
                    "top": {(v.decoded_token or ""): v.logprob for v in lpd.values()},
                })
            yield r, _empty_result(completion=c.text, finish_reason=c.finish_reason, provider="vllm-local",
                                   prompt_text=p, tokens=tokens or None,
                                   usage={"prompt_tokens": len(o.prompt_token_ids),
                                          "completion_tokens": len(c.token_ids)})


class HFBackend:
    def __init__(self, model_cfg, gen_cfg):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.gen = gen_cfg
        if torch.cuda.is_available():
            self.device = "cuda"
        elif torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"
        self.tok = AutoTokenizer.from_pretrained(model_cfg["hf_id"])
        self.tok.padding_side = "left"
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        # bf16 sampling on MPS can produce NaNs, so default to fp32 off CUDA (override with hf_dtype).
        dtype = getattr(torch, model_cfg.get("hf_dtype") or ("bfloat16" if self.device == "cuda" else "float32"))
        # MPS SDPA with left-padded batches yields NaN logits; eager attention avoids it.
        attn = model_cfg.get("hf_attn") or ("sdpa" if self.device == "cuda" else "eager")
        self.model = AutoModelForCausalLM.from_pretrained(
            model_cfg["hf_id"], dtype=dtype, attn_implementation=attn).to(self.device).eval()
        self.batch_size = model_cfg.get("hf_batch_size", 8)

    def _token_strings(self, ids):
        # Incremental decode so concatenated pieces reproduce the decoded completion.
        out, prev = [], ""
        for i in range(len(ids)):
            cur = self.tok.decode(ids[: i + 1], skip_special_tokens=True)
            out.append(cur[len(prev):])
            prev = cur
        return out

    def generate(self, reqs):
        torch = self.torch
        eos_ids = set(self.model.generation_config.eos_token_id
                      if isinstance(self.model.generation_config.eos_token_id, list)
                      else [self.model.generation_config.eos_token_id])
        for b in range(0, len(reqs), self.batch_size):
            batch = reqs[b: b + self.batch_size]
            prompts = [self.tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True)
                       for r in batch]
            enc = self.tok(prompts, return_tensors="pt", padding=True, add_special_tokens=False).to(self.device)
            torch.manual_seed(batch[0]["seed"])  # one seed per batch; per-sample seeds are not supported here
            with torch.no_grad():
                out = self.model.generate(
                    **enc, do_sample=True, temperature=self.gen["temperature"],
                    max_new_tokens=self.gen["max_tokens"], return_dict_in_generate=True,
                    output_logits=True, pad_token_id=self.tok.pad_token_id,
                )
            in_len = enc["input_ids"].shape[1]
            logps = torch.stack(out.logits, dim=1).float().log_softmax(-1)  # raw (pre-temperature) logprobs
            for j, r in enumerate(batch):
                ids = out.sequences[j, in_len:].tolist()
                n = len(ids)
                finish = "length"
                for k, t in enumerate(ids):
                    if t in eos_ids:
                        n, finish = k, "stop"
                        break
                ids = ids[:n]
                pieces = self._token_strings(ids)
                tokens = []
                for k, (tid, piece) in enumerate(zip(ids, pieces)):
                    row = logps[j, k]
                    vals, idx = row.topk(TOP_K)
                    tokens.append({
                        "token": piece,
                        "logprob": row[tid].item(),
                        "top": {self.tok.decode([i]): v for i, v in zip(idx.tolist(), vals.tolist())},
                    })
                yield r, _empty_result(completion="".join(pieces), finish_reason=finish, provider=f"hf-{self.device}",
                                       prompt_text=prompts[j], tokens=tokens or None,
                                       usage={"prompt_tokens": int(enc["attention_mask"][j].sum()),
                                              "completion_tokens": n})


BACKENDS = {"openrouter": OpenRouterBackend, "vllm": VLLMBackend, "hf": HFBackend}


def _read_dotenv(name):
    for path in (".env", os.path.join(os.path.dirname(__file__), "..", ".env")):
        try:
            with open(path) as f:
                for line in f:
                    if line.strip().startswith(name + "="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return None
