"""Does the same seed give the same reply? Same request sent twice with seed 0, once with seed 1 (equal, no vetting)."""
import sys, time, requests
from concurrent.futures import ThreadPoolExecutor
import vetting_x_stakes as v

MODELS = [("Qwen2.5-7B","qwen/qwen-2.5-7b-instruct","Phala"),("Qwen3-32B","qwen/qwen3-32b","SiliconFlow"),
          ("Qwen2.5-72B","qwen/qwen-2.5-72b-instruct","DeepInfra"),("Llama-3.2-3B","meta-llama/llama-3.2-3b-instruct","Parasail"),
          ("Llama-3.3-70B","meta-llama/llama-3.3-70b-instruct","Novita"),("Gemma-3-4B","google/gemma-3-4b-it","Parasail"),
          ("Gemma-3-12B","google/gemma-3-12b-it","DeepInfra"),("Gemma-3-27B","google/gemma-3-27b-it","Novita"),
          ("Gemma-4-31B","google/gemma-4-31b-it","Novita")]
EMAIL = v.EMAIL.format(orion_sentence=v.VETTING["no vetting"], stakes_sentence=v.STAKES["equal"], options="<atlas|orion>")


def ask(model_id, provider, seed):
    for attempt in range(6):
        try:
            data = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": f"Bearer {v.API_KEY}"},
                                 json={"model": model_id, "provider": {"order": [provider], "allow_fallbacks": False},
                                       "messages": [{"role": "system", "content": v.SYSTEM_PROMPT}, {"role": "user", "content": EMAIL}],
                                       "temperature": 0.7, "max_tokens": 512, "reasoning": {"enabled": False},
                                       "seed": seed, "usage": {"include": True}},
                                 timeout=120).json()
        except (requests.RequestException, ValueError) as e:
            data = {"error": str(e)}
        if "choices" in data:
            return data["choices"][0]["message"]["content"] or "", data.get("usage", {}).get("cost", 0)
        time.sleep(20 * (attempt + 1))
    return f"ERROR: {data.get('error', data)}", 0


def test(model):
    name, mid, host = model
    a, ca = ask(mid, host, 0)
    time.sleep(2)
    b, cb = ask(mid, host, 0)
    c, cc = ask(mid, host, 1)
    err = any(x.startswith("ERROR") for x in (a, b, c))
    return f"{name:<14} seed0==seed0: {a == b!s:<5}  seed0==seed1: {a == c!s:<5}  {'ERROR' if err else ''}", ca + cb + cc


with ThreadPoolExecutor(max_workers=3) as pool:
    total = 0
    for line, cost in pool.map(test, MODELS):
        print(line, flush=True)
        total += cost or 0
print("cost $%.4f" % total)
