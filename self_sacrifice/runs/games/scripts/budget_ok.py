"""Exit 0 if a tiny OpenRouter call succeeds (workspace budget available), 1 otherwise."""
import sys, requests, vetting_x_stakes as v
r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers={"Authorization": f"Bearer {v.API_KEY}"},
                  json={"model": "google/gemma-3-12b-it", "provider": {"order": ["DeepInfra"], "allow_fallbacks": False},
                        "messages": [{"role": "user", "content": "Say ok."}], "max_tokens": 3}, timeout=60).json()
sys.exit(0 if "choices" in r else 1)
