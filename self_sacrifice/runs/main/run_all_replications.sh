#!/bin/bash
# Waits for the restitution test, then serves each replication model in turn and runs the main scenario on it.
export PATH=/root/venvs/vllm/bin:$PATH PYTHONDONTWRITEBYTECODE=1
HERE=/workspace/Model-Game-Behavior/self_sacrifice/runs/main
until [ -f $HERE/repair_main.jsonl ] && [ "$(wc -l < $HERE/repair_main.jsonl)" -eq 800 ]; do timeout 30 tail -f /dev/null; done
fuser -k 8000/tcp 2>/dev/null || kill $(pgrep -f '[v]llm serve')
free_gpu() { until [ "$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)" -lt 2000 ]; do timeout 5 tail -f /dev/null; done; }
free_gpu
for pair in "qwen3-32b Qwen/Qwen3-32B" "qwen3-14b Qwen/Qwen3-14B" "gemma-4-26b google/gemma-4-26B-A4B-it"; do
  set -- $pair
  slug=$1; model=$2
  echo "== $slug: downloading"
  hf download "$model" --exclude 'original/*' > /root/hf_$slug.log 2>&1
  extra=""
  [[ $slug == gemma* ]] && extra="--limit-mm-per-prompt {\"image\":0,\"audio\":0}"
  cd /root
  nohup vllm serve "$model" --served-model-name replica --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.85 --seed 0 $extra --host 127.0.0.1 --port 8000 > /root/vllm_$slug.log 2>&1 &
  SP=$!
  until curl -sf localhost:8000/health > /dev/null; do
    kill -0 $SP 2>/dev/null || { echo "$slug: server died"; tail -3 /root/vllm_$slug.log; continue 2; }
    timeout 10 tail -f /dev/null
  done
  echo "== $slug: serving"
  cd $HERE && python run_replicate.py $slug 2>&1 | tail -4
  kill $SP; free_gpu
done
echo all done
