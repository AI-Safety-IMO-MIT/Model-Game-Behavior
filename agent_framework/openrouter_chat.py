from typing import Annotated, Any, Literal, cast
from dataclasses import dataclass
from dotenv import load_dotenv
import os
import json

from pydantic import BaseModel, Field

from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from openai.types.shared_params import Reasoning
from openai.types.responses import ResponseInputItemParam, ToolParam
from openai.types.responses.response import Response
from openai.types.responses.response_create_params import ToolChoice
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from openai.types.responses.response_output_item import ResponseOutputItem
from openai.types.responses.response_text_config_param import ResponseTextConfigParam

from agent_framework.dto import (
    AgenticChat,
    AgentReport,
    ContentBlock,
    ContentType,
    Message,
    ChatTrace,
)

__all__ = [
    "GemmaChat",
    "GemmaLegacyChat",
    "LlamaChat",
    "GptOssChat",
    "GemmaAgentConfig",
    "GemmaLegacyAgentConfig",
    "LlamaAgentConfig",
    "GptOssAgentConfig",
    "GemmaModels",
    "GemmaLegacyModels",
    "LlamaModels",
    "GptOssModels",
]

load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    timeout=600.0,
    max_retries=2,
    api_key=os.environ.get("OPENROUTER_API_KEY", "missing"),
)

GemmaModels = Literal[
    "google/gemma-4-31b-it",
    "google/gemma-4-26b-a4b-it",
]

GemmaLegacyModels = Literal[
    "google/gemma-3-27b-it",
    "google/gemma-3-12b-it",
    "google/gemma-3-4b-it",
    # 8k context only -- max_output_tokens must stay well under it
    "google/gemma-2-27b-it",
]
LlamaModels = Literal[
    "meta-llama/llama-4-maverick",
    "meta-llama/llama-4-scout",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.2-3b-instruct",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
]
GptOssModels = Literal["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, kw_only=True)
class _OpenRouterConfig:
    max_output_tokens: int
    system_prompt: str
    temperature: Annotated[float, Field(ge=0, le=2)]

    # OpenRouter routes one slug to many upstream hosts, each with its own
    # quantization and sampling. Pin them or matchups are not comparable.
    provider_only: tuple[str, ...] = ()
    provider_order: tuple[str, ...] = ()
    provider_quantizations: tuple[str, ...] = ()
    allow_fallbacks: bool = True
    # structured output support is per upstream endpoint, not per model
    require_parameters: bool = True

    tools: tuple[ToolParam, ...] = ()
    tool_choice: ToolChoice = "auto"

    def to_reasoning(self) -> Reasoning | None:
        return None

    def replays_reasoning(self) -> bool:
        return False

    def to_provider(self) -> dict[str, Any]:
        provider: dict[str, Any] = {
            "allow_fallbacks": self.allow_fallbacks,
            "require_parameters": self.require_parameters,
        }
        if self.provider_only:
            provider["only"] = list(self.provider_only)
        if self.provider_order:
            provider["order"] = list(self.provider_order)
        if self.provider_quantizations:
            provider["quantizations"] = list(self.provider_quantizations)
        return provider


@dataclass(frozen=True, kw_only=True)
class _ReasoningConfig(_OpenRouterConfig):
    """Adds the reasoning knobs, for the models that take them."""

    reasoning_effort: Literal["minimal", "low", "medium", "high"]

    # the docs never show a reasoning item being sent back as input, so replay
    # is off by default; history keeps the blocks either way, for the trace
    replay_reasoning: bool = False

    def to_reasoning(self) -> Reasoning | None:
        return cast(Reasoning, {"effort": self.reasoning_effort})

    def replays_reasoning(self) -> bool:
        return self.replay_reasoning


@dataclass(frozen=True, kw_only=True)
class GemmaAgentConfig(_ReasoningConfig):
    model: GemmaModels


@dataclass(frozen=True, kw_only=True)
class GptOssAgentConfig(_ReasoningConfig):
    model: GptOssModels


@dataclass(frozen=True, kw_only=True)
class GemmaLegacyAgentConfig(_OpenRouterConfig):
    # only Gemma 4 reports reasoning support, so Gemma 2 and 3 get no
    # reasoning fields -- sending the param would drop every endpoint
    model: GemmaLegacyModels


@dataclass(frozen=True, kw_only=True)
class LlamaAgentConfig(_OpenRouterConfig):
    # no Llama reports reasoning support, Llama 4 included
    model: LlamaModels


# output item .type -> our ContentBlock type
SERVER_ITEM_TYPES: dict[str, ContentType] = {
    "web_search_call": "web_search",
    "file_search_call": "web_search",
    "code_interpreter_call": "code_execution",
}

# items carrying a tool *result* back to the model, so they read as user-side
TOOL_RESULT_ITEM_TYPES = frozenset({"function_call_output", "custom_tool_call_output"})

# items that are never replayed when replay_reasoning is off
REASONING_ITEM_TYPES = frozenset({"reasoning"})


class _OpenRouterChat(AgenticChat):
    def __init__(self, agent_config: _OpenRouterConfig) -> None:
        self.agent_config = agent_config
        self._raw_history: list[ResponseInputItemParam] = []

    @property
    def model_name(self) -> str:
        return cast(str, getattr(self.agent_config, "model"))

    def call(
        self,
        user_text: str,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport:
        pending_user_item: ResponseInputItemParam = {
            "role": "user",
            "content": [{"type": "input_text", "text": user_text}],
        }

        text: ResponseTextConfigParam = {}
        if output_format is not None:
            text["format"] = {
                "type": "json_schema",
                "name": output_format.__name__,
                "schema": to_strict_json_schema(output_format),
                "description": output_format.__doc__ or "",
                "strict": True,
            }

        # store=True and previous_response_id are rejected with a 400; the
        # endpoint is stateless, so the whole history goes up every call
        response = client.responses.create(
            model=self.model_name,
            instructions=self.agent_config.system_prompt,
            input=[*self._replayable_history(), pending_user_item],
            max_output_tokens=self.agent_config.max_output_tokens,
            reasoning=self.agent_config.to_reasoning(),
            text=text,
            temperature=self.agent_config.temperature,
            tools=self.agent_config.tools,
            tool_choice=self.agent_config.tool_choice,
            store=False,
            extra_body={"provider": self.agent_config.to_provider()},
        )

        status, stop_reason, commit = self._verdict(response)

        if commit:
            self._raw_history.append(pending_user_item)
            self._raw_history.extend(
                cast(list[ResponseInputItemParam], response.output)
            )

        usage = response.usage
        details = usage.input_tokens_details if usage else None
        return AgentReport(
            agent_config=self.agent_config,
            status=status,
            stop_reason=stop_reason,
            response=self._to_message(response.output),
            input_tokens=usage.input_tokens if usage else None,
            completion_tokens=usage.output_tokens if usage else None,
            cache_tokens=getattr(details, "cached_tokens", None) if details else None,
        )

    def _replayable_history(self) -> list[ResponseInputItemParam]:
        if self.agent_config.replays_reasoning():
            return list(self._raw_history)
        return [
            item
            for item in self._raw_history
            if self._item_type(item) not in REASONING_ITEM_TYPES
        ]

    @staticmethod
    def _item_type(item: ResponseInputItemParam | ResponseOutputItem) -> str:
        if isinstance(item, dict):
            return cast(str, item.get("type", "message"))
        return item.type

    @staticmethod
    def _verdict(
        response: Response,
    ) -> tuple[Literal["Failed", "Completed"], str | None, bool]:
        # (report status, stop_reason, whether to commit to history)
        if response.status == "failed":
            error = response.error
            return (
                "Failed",
                f"{error.code}: {error.message}" if error else "failed",
                False,
            )

        if response.status in ("cancelled", "in_progress", "queued", None):
            return "Failed", response.status or "unknown", False

        if not response.output:
            return "Failed", "empty_output", False

        if any(
            item.type == "message"
            and any(part.type == "refusal" for part in item.content)
            for item in response.output
        ):
            return "Failed", "refusal", True

        if response.status == "incomplete":
            details = response.incomplete_details
            return "Completed", details.reason if details else "incomplete", True

        return "Completed", None, True

    def get_raw_history(self) -> list[ResponseInputItemParam]:
        return list(self._raw_history)

    def _item_blocks(
        self, item: ResponseInputItemParam | ResponseOutputItem
    ) -> tuple[Role, list[ContentBlock]]:
        if isinstance(item, dict):
            item_type = item.get("type", "message")
            if item_type in TOOL_RESULT_ITEM_TYPES:
                return "user", [
                    ContentBlock(type="tool_result", content=json.dumps(item))
                ]
            if item_type != "message":
                raise NotImplementedError(
                    f"history item {item_type!r} has no display form yet"
                )
            message = cast(EasyInputMessageParam, item)
            raw_role = message["role"]
            role: Role = "system" if raw_role == "developer" else raw_role
            content = message["content"]
            if isinstance(content, str):
                return role, [ContentBlock(type="text", content=content)]
            blocks: list[ContentBlock] = []
            for part in content:
                if part["type"] == "input_text":
                    blocks.append(ContentBlock(type="text", content=part["text"]))
                else:
                    raise NotImplementedError(
                        f"content part {part['type']!r} has no display form yet"
                    )
            return role, blocks

        if item.type == "reasoning":
            # OpenRouter's docs print summary as a list of bare strings, the SDK
            # types it as a list of objects -- accept either
            texts = [
                part if isinstance(part, str) else part.text for part in item.summary
            ]
            texts += [
                part if isinstance(part, str) else part.text
                for part in item.content or []
            ]
            if not texts:
                texts = [""]
            return "assistant", [
                ContentBlock(type="reasoning", content=text) for text in texts
            ]

        if item.type == "message":
            blocks = []
            for part in item.content:
                if part.type == "output_text":
                    blocks.append(ContentBlock(type="text", content=part.text))
                else:
                    blocks.append(ContentBlock(type="text", content=part.refusal))
            return "assistant", blocks

        if item.type == "function_call":
            try:
                arguments = json.loads(item.arguments)
            except json.JSONDecodeError:
                arguments = item.arguments
            return "assistant", [
                ContentBlock(
                    type="tool_call",
                    content=json.dumps({"name": item.name, "arguments": arguments}),
                )
            ]

        if item.type in TOOL_RESULT_ITEM_TYPES:
            return "user", [
                ContentBlock(type="tool_result", content=item.model_dump_json())
            ]

        if item.type in SERVER_ITEM_TYPES:
            return "assistant", [
                ContentBlock(
                    type=SERVER_ITEM_TYPES[item.type], content=item.model_dump_json()
                )
            ]

        raise NotImplementedError(f"output item {item.type!r} has no display form yet")

    def _to_message(self, items: list[ResponseOutputItem]) -> Message:
        blocks: list[ContentBlock] = []
        for item in items:
            blocks.extend(self._item_blocks(item)[1])
        return Message(role="assistant", content=blocks)

    def get_trace(self) -> ChatTrace:
        turns: list[tuple[Role, list[ContentBlock]]] = []
        for item in self._raw_history:
            role, blocks = self._item_blocks(item)
            if not blocks:
                continue
            if turns and turns[-1][0] == role:
                turns[-1][1].extend(blocks)
            else:
                turns.append((role, list(blocks)))
        return ChatTrace(
            agent_config=self.agent_config,
            messages=[Message(role=role, content=blocks) for role, blocks in turns],
        )

    def clear_history(self) -> None:
        return self._raw_history.clear()

    def __str__(self) -> str:
        return str(self.agent_config)


class GemmaChat(_OpenRouterChat):
    def __init__(self, agent_config: GemmaAgentConfig) -> None:
        super().__init__(agent_config)


class GptOssChat(_OpenRouterChat):
    def __init__(self, agent_config: GptOssAgentConfig) -> None:
        super().__init__(agent_config)


class GemmaLegacyChat(_OpenRouterChat):
    def __init__(self, agent_config: GemmaLegacyAgentConfig) -> None:
        super().__init__(agent_config)


class LlamaChat(_OpenRouterChat):
    def __init__(self, agent_config: LlamaAgentConfig) -> None:
        super().__init__(agent_config)
