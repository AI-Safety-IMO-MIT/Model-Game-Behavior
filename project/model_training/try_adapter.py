"""Generate from the tuned adapter, next to the untuned base for comparison.

Without the side-by-side you cannot tell whether the adapter did anything or
the base model was already answering that way.

    python -m project.model_training.try_adapter
    python -m project.model_training.try_adapter --adapter /workspace/outputs/brainrot-lora
    python -m project.model_training.try_adapter --prompt "explain compound interest"
"""

import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, PreTrainedTokenizerBase

from project.model_training.brainrot_data import SYSTEM_PROMPT
from project.model_training.train_lora import BASE_MODEL, OUTPUT_DIR

HELD_OUT = [
    "What is a glacier?",
    "How do I change a flat tyre?",
    "Why do onions make you cry?",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--adapter", default=OUTPUT_DIR)
    parser.add_argument("--prompt", action="append", default=None)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    return parser.parse_args()


def generate(
    model: AutoModelForCausalLM,
    tokenizer: PreTrainedTokenizerBase,
    question: str,
    max_new_tokens: int,
) -> str:
    text = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False).to("cuda")
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    return tokenizer.decode(
        output[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True
    ).strip()


def main() -> None:
    args = parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device. This script runs on the pod.")

    questions = args.prompt or HELD_OUT
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(args.base_model, dtype=dtype)
    base.to("cuda")
    base.eval()

    tuned = PeftModel.from_pretrained(base, args.adapter)
    tuned.eval()

    for question in questions:
        print(f"\n=== {question} ===")
        with tuned.disable_adapter():
            print(
                f"\n[base]\n{generate(tuned, tokenizer, question, args.max_new_tokens)}"
            )
        print(
            f"\n[brainrot]\n{generate(tuned, tokenizer, question, args.max_new_tokens)}"
        )


if __name__ == "__main__":
    main()
