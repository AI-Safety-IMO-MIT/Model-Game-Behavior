"""One client for any server speaking vLLM's OpenAI-compatible Chat Completions.

The host is a config field, not a class: localhost, a RunPod proxy URL, or a
RunPod Serverless endpoint all work unchanged. What makes this file its own
format is vLLM's extensions to Chat Completions -- `chat_template_kwargs`,
`skip_special_tokens`, and the `reasoning_content` field the server emits when
started with `--reasoning-parser`.
"""

import json
import os
from dataclasses import dataclass
from typing import Annotated, Any, Literal, cast

from dotenv import load_dotenv
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionToolChoiceOptionParam,
    ChatCompletionToolParam,
)
from openai.types.shared_params import ResponseFormatJSONSchema
from pydantic import BaseModel, Field

from agent_framework.dto import (
    AgenticChat,
    AgentReport,
    ChatTrace,
    ContentBlock,
    Message,
)

__all__ = [
    "VllmAgentConfig",
    "VllmChat",
    "VllmGemmaAgentConfig",
    "VllmGemmaChat",
    "VllmGemmaModels",
    "VllmGptOssAgentConfig",
    "VllmGptOssChat",
    "VllmGptOssModels",
    "VllmLlamaAgentConfig",
    "VllmLlamaChat",
    "VllmLlamaModels",
]

load_dotenv()

# HuggingFace repo ids: what vLLM serves by, unless --served-model-name overrides.
# Casing matters and differs from OpenRouter's lowercase slugs.
VllmGemmaModels = Literal[
    "google/gemma-4-31B-it",
    "google/gemma-4-26B-A4B-it",
    "google/gemma-3-27b-it",
    "google/gemma-3-12b-it",
    "google/gemma-3-4b-it",
    "google/gemma-2-27b-it",
]
VllmLlamaModels = Literal[
    "meta-llama/Llama-4-Maverick-17B-128E-Instruct",
    "meta-llama/Llama-4-Scout-17B-16E-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Llama-3.1-70B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
]
VllmGptOssModels = Literal[
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, kw_only=True)
class _VllmConfig:
    model: str
    system_prompt: str
    max_output_tokens: int

    base_url: str = "http://localhost:8000/v1"

    # greedy by default: the point of a self-hosted server is repeatable runs
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.0
    top_p: float = 1.0
    seed: int | None = 0

    # vLLM's convention for a server started without --api-key
    api_key: str = os.environ.get("VLLM_API_KEY") or os.environ.get(
        "RUNPOD_VLLM_API_KEY", "EMPTY"
    )

    # None leaves the chat template's own default alone
    enable_thinking: bool | None = None
    # False keeps channel markers visible, so a thinking leak can be detected
    skip_special_tokens: bool = False

    replay_reasoning: bool = False

    tools: tuple[ChatCompletionToolParam, ...] = ()
    tool_choice: ChatCompletionToolChoiceOptionParam = "auto"

    def to_template_kwargs(self) -> dict[str, Any]:
        if self.enable_thinking is None:
            return {}
        return {"enable_thinking": self.enable_thinking}

    def to_extra_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {"skip_special_tokens": self.skip_special_tokens}
        template_kwargs = self.to_template_kwargs()
        if template_kwargs:
            body["chat_template_kwargs"] = template_kwargs
        return body

    def to_api(self) -> dict[str, Any]:
        """Assembles the wire params from the explicit fields above.

        Every knob stays a named field; this only lays them out for the SDK.
        """
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "extra_body": self.to_extra_body(),
        }
        if self.seed is not None:
            params["seed"] = self.seed
        return params


@dataclass(frozen=True, kw_only=True)
class _ReasoningConfig(_VllmConfig):
    """Adds the reasoning knob, for the models whose chat template takes it."""

    reasoning_effort: Literal["low", "medium", "high"] | None = None

    def to_template_kwargs(self) -> dict[str, Any]:
        template_kwargs = super().to_template_kwargs()
        if self.reasoning_effort is not None:
            template_kwargs["reasoning_effort"] = self.reasoning_effort
        return template_kwargs


@dataclass(frozen=True, kw_only=True)
class VllmAgentConfig(_VllmConfig):
    """Free-form model id, for probing a server whose id is not in the Literals."""

    enable_thinking: bool = False


@dataclass(frozen=True, kw_only=True)
class VllmGemmaAgentConfig(_ReasoningConfig):
    model: VllmGemmaModels


@dataclass(frozen=True, kw_only=True)
class VllmGptOssAgentConfig(_ReasoningConfig):
    model: VllmGptOssModels


@dataclass(frozen=True, kw_only=True)
class VllmLlamaAgentConfig(_VllmConfig):
    model: VllmLlamaModels


class _VllmChat(AgenticChat):
    """`history` seeds earlier (role, text) turns, so a saved reply can be replayed."""

    def __init__(
        self,
        agent_config: _VllmConfig,
        history: tuple[tuple[Role, str], ...] = (),
    ) -> None:
        self.agent_config = agent_config
        self._raw_history: list[ChatCompletionMessageParam] = [
            cast(ChatCompletionMessageParam, {"role": role, "content": text})
            for role, text in history
        ]
        self._client = OpenAI(
            base_url=agent_config.base_url,
            timeout=600.0,
            max_retries=2,
            api_key=agent_config.api_key,
        )

    @property
    def model_name(self) -> str:
        return self.agent_config.model

    def call(
        self,
        user_text: str,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport:
        pending_user_msg: ChatCompletionMessageParam = {
            "role": "user",
            "content": user_text,
        }

        system_msg: ChatCompletionMessageParam = {
            "role": "system",
            "content": self.agent_config.system_prompt,
        }

        kwargs: dict[str, Any] = {}
        if output_format is not None:
            response_format: ResponseFormatJSONSchema = {
                "type": "json_schema",
                "json_schema": {
                    "name": output_format.__name__,
                    "schema": to_strict_json_schema(output_format),
                    "description": output_format.__doc__ or "",
                    "strict": True,
                },
            }
            kwargs["response_format"] = response_format
        if self.agent_config.tools:
            kwargs["tools"] = self.agent_config.tools
            kwargs["tool_choice"] = self.agent_config.tool_choice

        response = self._client.chat.completions.create(
            messages=[system_msg, *self._replayable_history(), pending_user_msg],
            **self.agent_config.to_api(),
            **kwargs,
        )

        status, stop_reason, commit = self._verdict(response)
        message = response.choices[0].message if response.choices else None

        if commit and message is not None:
            self._raw_history.append(pending_user_msg)
            self._raw_history.append(
                cast(
                    ChatCompletionMessageParam,
                    message.model_dump(mode="json", exclude_none=True),
                )
            )

        usage = response.usage
        details = usage.prompt_tokens_details if usage else None
        return AgentReport(
            agent_config=self.agent_config,
            status=status,
            stop_reason=stop_reason,
            response=(
                self._to_message(message)
                if message is not None
                else Message(role="assistant", content=[])
            ),
            input_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            cache_tokens=details.cached_tokens if details else None,
        )

    def _replayable_history(self) -> list[ChatCompletionMessageParam]:
        if self.agent_config.replay_reasoning:
            return list(self._raw_history)
        stripped: list[ChatCompletionMessageParam] = []
        for msg in self._raw_history:
            raw = cast(dict[str, Any], msg)
            if "reasoning_content" in raw:
                msg = cast(
                    ChatCompletionMessageParam,
                    {k: v for k, v in raw.items() if k != "reasoning_content"},
                )
            stripped.append(msg)
        return stripped

    @staticmethod
    def _verdict(
        response: ChatCompletion,
    ) -> tuple[Literal["Failed", "Completed"], str | None, bool]:
        if not response.choices:
            return "Failed", "empty_output", False

        choice = response.choices[0]
        message = choice.message

        if message.refusal:
            return "Failed", "refusal", True

        if not message.content and not message.tool_calls:
            if not getattr(message, "reasoning_content", None):
                return "Failed", "empty_output", False

        if choice.finish_reason == "length":
            return "Completed", "length", True

        if choice.finish_reason == "content_filter":
            return "Failed", "content_filter", True

        return "Completed", choice.finish_reason, True

    def get_raw_history(self) -> list[ChatCompletionMessageParam]:
        return list(self._raw_history)

    def _blocks_from_parts(
        self,
        reasoning: str | None,
        content: str | None,
        refusal: str | None,
        tool_calls: list[dict[str, Any]] | None,
    ) -> list[ContentBlock]:
        blocks: list[ContentBlock] = []
        if reasoning:
            blocks.append(ContentBlock(type="reasoning", content=reasoning))
        for call in tool_calls or []:
            function = call.get("function", {})
            arguments = function.get("arguments")
            try:
                parsed = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                parsed = arguments
            blocks.append(
                ContentBlock(
                    type="tool_call",
                    content=json.dumps(
                        {"name": function.get("name"), "arguments": parsed}
                    ),
                )
            )
        # text last: AgenticChat.get_chat() and the study both read content[-1]
        if refusal:
            blocks.append(ContentBlock(type="text", content=refusal))
        if content or not blocks:
            blocks.append(ContentBlock(type="text", content=content or ""))
        return blocks

    def _to_message(self, message: ChatCompletionMessage) -> Message:
        tool_calls = [call.model_dump(mode="json") for call in message.tool_calls or []]
        return Message(
            role="assistant",
            content=self._blocks_from_parts(
                reasoning=getattr(message, "reasoning_content", None),
                content=message.content,
                refusal=message.refusal,
                tool_calls=tool_calls,
            ),
        )

    def _param_to_message(self, msg: ChatCompletionMessageParam) -> Message:
        role = cast(Role, msg["role"] if msg["role"] != "tool" else "user")
        if role != "assistant":
            content = msg.get("content")
            text = content if isinstance(content, str) else json.dumps(content)
            return Message(
                role=role, content=[ContentBlock(type="text", content=text or "")]
            )

        raw_content = msg.get("content")
        return Message(
            role="assistant",
            content=self._blocks_from_parts(
                reasoning=cast(Any, msg).get("reasoning_content"),
                content=raw_content if isinstance(raw_content, str) else None,
                refusal=cast(Any, msg).get("refusal"),
                tool_calls=cast(Any, msg).get("tool_calls"),
            ),
        )

    def get_trace(self) -> ChatTrace:
        return ChatTrace(
            agent_config=self.agent_config,
            messages=[self._param_to_message(msg) for msg in self.get_raw_history()],
        )

    def clear_history(self) -> None:
        return self._raw_history.clear()

    def __str__(self) -> str:
        return str(self.agent_config)


class VllmChat(_VllmChat):
    """Generic client; `get_raw_history()` includes the system prompt it sends."""

    def __init__(
        self,
        agent_config: VllmAgentConfig,
        history: tuple[tuple[Role, str], ...] = (),
    ) -> None:
        super().__init__(agent_config, history)

    def get_raw_history(self) -> list[ChatCompletionMessageParam]:
        system: list[ChatCompletionMessageParam] = (
            [{"role": "system", "content": self.agent_config.system_prompt}]
            if self.agent_config.system_prompt
            else []
        )
        return [*system, *self._raw_history]


class VllmGemmaChat(_VllmChat):
    def __init__(
        self,
        agent_config: VllmGemmaAgentConfig,
        history: tuple[tuple[Role, str], ...] = (),
    ) -> None:
        super().__init__(agent_config, history)


class VllmGptOssChat(_VllmChat):
    def __init__(
        self,
        agent_config: VllmGptOssAgentConfig,
        history: tuple[tuple[Role, str], ...] = (),
    ) -> None:
        super().__init__(agent_config, history)


class VllmLlamaChat(_VllmChat):
    def __init__(
        self,
        agent_config: VllmLlamaAgentConfig,
        history: tuple[tuple[Role, str], ...] = (),
    ) -> None:
        super().__init__(agent_config, history)
