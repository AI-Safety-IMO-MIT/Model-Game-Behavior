#!/bin/bash
# After the replications: favour-size tests on Gemma-4-31B, then the repair test on each other model.
export PATH=/root/venvs/vllm/bin:$PATH PYTHONDONTWRITEBYTECODE=1
HERE=/workspace/Model-Game-Behavior/self_sacrifice/runs/main
until [ -f $HERE/replication/gemma-4-26b/main.jsonl ] && [ "$(wc -l < $HERE/replication/gemma-4-26b/main.jsonl)" -eq 800 ]; do timeout 30 tail -f /dev/null; done
free_gpu() { until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 2000 ]; do timeout 5 tail -f /dev/null; done; }
free_gpu
serve() {  # slug model extra-args, then waits for health
  cd /root
  nohup vllm serve "$2" --served-model-name replica --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.85 --seed 0 $3 --host 127.0.0.1 --port 8000 > /root/vllm_q2_$1.log 2>&1 &
  SP=$!
  until curl -sf localhost:8000/health > /dev/null; do kill -0 $SP 2>/dev/null || { echo "$1: server died"; return 1; }; timeout 10 tail -f /dev/null; done
}
MM='--limit-mm-per-prompt {"image":0,"audio":0}'
if serve gemma-4-31b google/gemma-4-31B-it "$MM"; then cd $HERE && python run_followups.py favour 2>&1 | tail -3; kill $SP; free_gpu; fi
for pair in "qwen3-32b Qwen/Qwen3-32B" "qwen3-14b Qwen/Qwen3-14B" "gemma-4-26b google/gemma-4-26B-A4B-it"; do
  set -- $pair
  extra=""; [[ $1 == gemma* ]] && extra="$MM"
  if serve "$1" "$2" "$extra"; then cd $HERE && python run_followups.py repair "$1" 2>&1 | tail -2; kill $SP; free_gpu; fi
done
echo queue2 done
