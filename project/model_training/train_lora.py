"""LoRA fine-tune a small instruct model until it only speaks brainrot.

Runs on the pod, not on your Mac -- it needs a CUDA GPU. Writes a LoRA adapter
(a few MB, not a whole model) that gets loaded on top of the frozen base.

    python -m project.model_training.train_lora
    python -m project.model_training.train_lora --base-model Qwen/Qwen2.5-3B-Instruct
    python -m project.model_training.train_lora --output /workspace/outputs/brainrot --epochs 12

Put --output on a network volume. Container disk is wiped on every stop, and
an adapter you cannot reload is an adapter you did not train.
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    PreTrainedTokenizerBase,
    Trainer,
    TrainingArguments,
)

from project.model_training.brainrot_data import as_messages

BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
OUTPUT_DIR = "/workspace/outputs/brainrot-lora"
MAX_LENGTH = 512
IGNORE_INDEX = -100


@dataclass
class Example:
    input_ids: list[int]
    labels: list[int]


class BrainrotDataset(Dataset):
    """Chat-templated pairs with the prompt masked out of the loss.

    Training on the prompt tokens too would teach the model to generate the
    questions as well as the answers, which dilutes the one thing we want.
    """

    def __init__(self, tokenizer: PreTrainedTokenizerBase, max_length: int) -> None:
        self.examples: list[Example] = []
        for chat in as_messages():
            prompt_text = tokenizer.apply_chat_template(
                chat[:-1], tokenize=False, add_generation_prompt=True
            )
            full_text = tokenizer.apply_chat_template(
                chat, tokenize=False, add_generation_prompt=False
            )
            prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
            full_ids = tokenizer(full_text, add_special_tokens=False)["input_ids"]
            full_ids = full_ids[:max_length]
            cut = min(len(prompt_ids), len(full_ids))
            labels = [IGNORE_INDEX] * cut + full_ids[cut:]
            if all(label == IGNORE_INDEX for label in labels):
                continue
            self.examples.append(Example(input_ids=full_ids, labels=labels))

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> Example:
        return self.examples[index]


@dataclass
class Collator:
    pad_token_id: int

    def __call__(self, batch: list[Example]) -> dict[str, torch.Tensor]:
        width = max(len(item.input_ids) for item in batch)
        input_ids, labels, attention = [], [], []
        for item in batch:
            pad = width - len(item.input_ids)
            input_ids.append(item.input_ids + [self.pad_token_id] * pad)
            labels.append(item.labels + [IGNORE_INDEX] * pad)
            attention.append([1] * len(item.input_ids) + [0] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
            "attention_mask": torch.tensor(attention, dtype=torch.long),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument("--output", default=OUTPUT_DIR)
    parser.add_argument("--epochs", type=float, default=10.0)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH)
    parser.add_argument("--lora-rank", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("no CUDA device. This script runs on the pod, not on the Mac.")

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    dataset = BrainrotDataset(tokenizer, args.max_length)
    print(f"{len(dataset)} training examples")

    model = AutoModelForCausalLM.from_pretrained(args.base_model, dtype=dtype)
    model.to("cuda")
    model.config.use_cache = False

    model = get_peft_model(
        model,
        LoraConfig(
            r=args.lora_rank,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules="all-linear",
        ),
    )
    model.print_trainable_parameters()

    output = Path(args.output)
    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(output),
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
            learning_rate=args.learning_rate,
            lr_scheduler_type="cosine",
            warmup_ratio=0.05,
            logging_steps=5,
            save_strategy="no",
            bf16=dtype is torch.bfloat16,
            fp16=dtype is torch.float16,
            report_to=[],
        ),
        train_dataset=dataset,
        data_collator=Collator(pad_token_id=tokenizer.pad_token_id),
    )
    trainer.train()

    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output))
    tokenizer.save_pretrained(str(output))
    print(f"adapter written to {output}")


if __name__ == "__main__":
    main()
