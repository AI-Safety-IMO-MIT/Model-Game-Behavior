# Brainrot LoRA

An end-to-end fine-tuning test: teach a small instruct model to answer every
question in Gen Alpha brainrot slang, then prove the adapter changed something.

The point is the **pipeline**, not the model. Once this loop is green, scaling
up means changing the base model, the GPU and the dataset -- nothing structural.

## Files

| File | What it does |
|---|---|
| `brainrot_data.py` | 50 question/answer pairs in the target voice |
| `train_lora.py` | LoRA fine-tune, writes an adapter |
| `try_adapter.py` | Generates base vs tuned side by side |

## Why these choices

- **LoRA, not full fine-tuning.** Trains ~1% of the weights and writes a few MB
  instead of a few GB. Full FT of anything past 1B needs far more VRAM than the
  task deserves.
- **Loss masked to the answer only.** Training on the questions too would teach
  the model to generate questions, diluting the style signal.
- **Topic breadth over example count.** 50 pairs across maths, cooking, code
  and science teach a voice. 1000 pairs about one subject teach that subject.
- **Answers stay factually correct.** The target is tone; letting the content
  drift would make it impossible to tell style transfer from damage.

## Running it on a pod

These deps are **not** in `requirement.txt` -- they only ever run on the pod,
and `torch` has no business in the Mac environment. `torch` is also absent from
`requirement-training.txt` on purpose: use the one baked into the pod image,
which is built against that host's CUDA. Installing our own torch is exactly
what broke the first pod.

Create a pod from a `runpod/pytorch:...` image (it has sshd, Jupyter and a
working terminal, unlike the vLLM image). Attach a network volume at
`/workspace` so the adapter survives.

Get the code there:

```bash
# on your Mac
runpodctl send project requirement-training.txt

# on the pod
runpodctl receive <code-it-printed>
```

Then:

```bash
export HF_HOME=/workspace/hf-cache          # cache weights on the volume
pip install -r requirement-training.txt
python -m project.model_training.train_lora
python -m project.model_training.try_adapter
```

A 1.5B LoRA over 50 examples is a few minutes on any 24GB+ card.

## Scaling up

| Knob | Here | Scale to |
|---|---|---|
| Base model | `Qwen/Qwen2.5-1.5B-Instruct` | 8B class |
| GPU | anything 24GB+ | 80GB, or QLoRA |
| Dataset | 50 handwritten pairs | a real dataset |

Fine-tuning 70B is **not** this with bigger numbers -- it needs multi-GPU with
FSDP or DeepSpeed. Serve 70B, fine-tune 8B.

## Gotchas

- `--output` must be on the network volume. Container disk is wiped on stop.
- Run long jobs detached (`nohup ... &`) so an SSH drop doesn't kill them.
- Don't install these deps into a pod that is running vLLM; the version pins
  will fight.
