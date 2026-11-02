#!/bin/bash
# Favour-size tests on the Gemma-4-31B server that is already up, then the repair test on each other model.
# Every run first checks the server reports the expected model, so a stale server cannot produce mislabelled data.
export PATH=/root/venvs/vllm/bin:$PATH PYTHONDONTWRITEBYTECODE=1
HERE=/workspace/Model-Game-Behavior/self_sacrifice/runs/main
free_gpu() { until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 2000 ]; do timeout 5 tail -f /dev/null; done; }
stop_server() { for p in $(pgrep -f '^.*[v]llm serve'); do kill "$p"; done; free_gpu; }
check() { curl -s localhost:8000/v1/models | grep -q "\"root\":\"$1\"" || { echo "WRONG SERVER, wanted $1"; return 1; }; }
serve() {
  cd /root
  nohup vllm serve "$2" --served-model-name replica --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.85 --seed 0 $3 --host 127.0.0.1 --port 8000 > /root/vllm_q3_$1.log 2>&1 &
  local pid=$!
  until curl -sf localhost:8000/health > /dev/null; do
    kill -0 $pid 2>/dev/null || { echo "$1: server died"; return 1; }
    timeout 10 tail -f /dev/null
  done
  return 0
}
MM='--limit-mm-per-prompt {"image":0,"audio":0}'
if check google/gemma-4-31B-it; then cd $HERE && python run_followups.py favour 2>&1 | tail -4; fi
stop_server
for pair in "qwen3-32b Qwen/Qwen3-32B" "qwen3-14b Qwen/Qwen3-14B" "gemma-4-26b google/gemma-4-26B-A4B-it"; do
  set -- $pair
  extra=""; [[ $1 == gemma* ]] && extra="$MM"
  if serve "$1" "$2" "$extra" && check "$2"; then cd $HERE && python run_followups.py repair "$1" 2>&1 | tail -2; fi
  stop_server
done
echo queue3 done
