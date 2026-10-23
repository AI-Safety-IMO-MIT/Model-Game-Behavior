from typing import Annotated, Literal, cast
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
)

load_dotenv()

client = OpenAI(
    timeout=600.0, max_retries=2, api_key=os.environ.get("OPENAI_API_KEY", "missing")
)

OpenAIModels = Literal[
    # GPT-6
    "gpt-6.1-sol",
    "gpt-6-sol",
    "gpt-6-astra",
    "gpt-6-luna",
    # GPT-5.6
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    # GPT-5.5
    "gpt-5.5",
    "gpt-5.5-pro",
    # GPT-5.4
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    # GPT-5.2
    "gpt-5.2",
    "gpt-5.2-pro",
    # GPT-5
    "gpt-5",
    "gpt-5-pro",
    "gpt-5-mini",
    "gpt-5-nano",
    # o-series (reasoning)
    "o3",
    "o3-pro",
    # Open-weight
    "gpt-oss-120b",
    "gpt-oss-20b",
]

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True)
class OpenAIAgentConfig:
    model: OpenAIModels
    max_output_tokens: int
    max_tool_calls: int

    system_prompt: str

    reasoning_effort: Literal[
        "none", "minimal", "low", "medium", "high", "xhigh", "max"
    ]
    reasoning_context: Literal["auto", "current_turn", "all_turns"]
    reasoning_mode: Literal["standard", "pro"]

    output_verbosity: Literal["low", "medium", "high"]

    temperature: Annotated[float, Field(ge=0, le=2)]

    reasoning_summary: Literal["auto", "concise", "detailed"] = "auto"
    tools: tuple[ToolParam, ...] = ()
    tool_choice: ToolChoice = "auto"

    def to_reasoning(self) -> Reasoning:
        return {
            "effort": self.reasoning_effort,
            "summary": self.reasoning_summary,
            "context": self.reasoning_context,
            "mode": self.reasoning_mode,
        }


# output item .type -> our ContentBlock type
SERVER_ITEM_TYPES: dict[str, ContentType] = {
    "web_search_call": "web_search",
    "file_search_call": "web_search",
    "code_interpreter_call": "code_execution",
    "program": "code_execution",
    "program_output": "code_execution",
    "shell_call": "shell",
    "shell_call_output": "shell",
    "local_shell_call": "shell",
    "local_shell_call_output": "shell",
    "apply_patch_call": "shell",
    "apply_patch_call_output": "shell",
    "tool_search_call": "tool_search",
    "tool_search_output": "tool_search",
}

# items carrying a tool *result* back to the model, so they read as user-side
TOOL_RESULT_ITEM_TYPES = frozenset(
    {"function_call_output", "computer_call_output", "custom_tool_call_output"}
)


class OpenAIChat(AgenticChat):
    def __init__(self, agent_config: OpenAIAgentConfig) -> None:
        self.agent_config = agent_config
        self._raw_history: list[ResponseInputItemParam] = []

    @property
    def model_name(self) -> str:
        return self.agent_config.model

    def call(
        self,
        user_text: str,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport:
        pending_user_item: ResponseInputItemParam = {
            "role": "user",
            "content": [{"type": "input_text", "text": user_text}],
        }

        text: ResponseTextConfigParam = {
            "verbosity": self.agent_config.output_verbosity
        }
        if output_format is not None:
            text["format"] = {
                "type": "json_schema",
                "name": output_format.__name__,
                "schema": to_strict_json_schema(output_format),
                "description": output_format.__doc__ or "",
                "strict": True,
            }

        response = client.responses.create(
            model=self.agent_config.model,
            instructions=self.agent_config.system_prompt,
            input=[*self._raw_history, pending_user_item],
            max_output_tokens=self.agent_config.max_output_tokens,
            max_tool_calls=self.agent_config.max_tool_calls,
            reasoning=self.agent_config.to_reasoning(),
            text=text,
            temperature=self.agent_config.temperature,
            tools=self.agent_config.tools,
            tool_choice=self.agent_config.tool_choice,
            store=False,
            include=["reasoning.encrypted_content"],
        )

        status, stop_reason, commit = self._verdict(response)

        if commit:
            self._raw_history.append(pending_user_item)
            self._raw_history.extend(
                cast(list[ResponseInputItemParam], response.output)
            )

        usage = response.usage
        return AgentReport(
            agent_config=self.agent_config,
            status=status,
            stop_reason=stop_reason,
            response=self._to_message(response.output),
            input_tokens=usage.input_tokens if usage else None,
            completion_tokens=usage.output_tokens if usage else None,
            cache_tokens=(usage.input_tokens_details.cached_tokens if usage else None),
        )

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
            texts = [part.text for part in item.summary]
            texts += [part.text for part in item.content or []]
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

    def get_history(self) -> list[Message]:
        turns: list[tuple[Role, list[ContentBlock]]] = []
        for item in self._raw_history:
            role, blocks = self._item_blocks(item)
            if not blocks:
                continue
            if turns and turns[-1][0] == role:
                turns[-1][1].extend(blocks)
            else:
                turns.append((role, list(blocks)))
        return [Message(role=role, content=blocks) for role, blocks in turns]

    def clear_history(self) -> None:
        return self._raw_history.clear()

    def __str__(self) -> str:
        return str(self.agent_config)
