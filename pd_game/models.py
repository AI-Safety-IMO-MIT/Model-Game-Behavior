"""Model presets and renderers.

Both models keep their own earlier reasoning in their context (private to them), which gives the
"extension property": each turn's prompt extends the previous one, so a whole game trains as one
sequence instead of one per turn. gpt-oss's renderer already renders whatever thinking we pass
in history; Qwen3's strips it by default, so we register a variant that keeps it.
"""

import dataclasses
import warnings
from dataclasses import dataclass

from tinker_cookbook.renderers import get_renderer, register_renderer
from tinker_cookbook.renderers.gpt_oss import GptOssRenderer
from tinker_cookbook.renderers.qwen3 import Qwen3Renderer
from tinker_cookbook.tokenizer_utils import get_tokenizer


class GptOssKeepReturnRenderer(GptOssRenderer):
    """Harmony ends a sampled reply with <|return|> but writes past replies with <|end|>, so each
    turn's prompt is not an extension of the previous prompt + reply. Keeping <|return|> on past
    replies restores the extension property (one training sequence per game instead of one per
    turn, ~7x fewer training tokens). The only change the model sees is that one token."""

    def render_message(self, message, ctx):
        if message["role"] == "assistant" and not message.get("tool_calls"):
            ctx = dataclasses.replace(ctx, is_last=True)
        return super().render_message(message, ctx)


QWEN3_KEEP_THINKING = "pd/qwen3_keep_thinking"
GPT_OSS_MEDIUM = "pd/gpt_oss_medium_keep_return"
register_renderer(QWEN3_KEEP_THINKING, lambda tok, _img=None: Qwen3Renderer(tok, strip_thinking_from_history=False))
register_renderer(GPT_OSS_MEDIUM, lambda tok, _img=None: GptOssKeepReturnRenderer(
    tok, use_system_prompt=True, reasoning_effort="medium"))

# Our game prompt is a system message; gpt-oss's renderer turns it into the Harmony developer
# message (its intended place) but warns that its own system prompt is also present. That's expected.
warnings.filterwarnings("ignore", message="use_system_prompt=True but messages already start with a system message")


@dataclass(frozen=True)
class ModelPreset:
    model_name: str        # Tinker base model id
    renderer_name: str
    learning_rate: float
    openrouter_id: str | None = None


PRESETS = {
    "qwen3-8b": ModelPreset("Qwen/Qwen3-8B", QWEN3_KEEP_THINKING, 2e-5),
    "gpt-oss-20b": ModelPreset("openai/gpt-oss-20b", GPT_OSS_MEDIUM, 2e-5, "openai/gpt-oss-20b"),
}


def preset_for_base_model(model_name: str) -> ModelPreset:
    for p in PRESETS.values():
        if p.model_name == model_name:
            return p
    raise KeyError(f"no preset for base model {model_name!r} (known: {[p.model_name for p in PRESETS.values()]})")


def make_renderer(renderer_name: str, model_name: str):
    return get_renderer(renderer_name, get_tokenizer(model_name))
