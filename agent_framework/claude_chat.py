from typing import Literal
from dataclasses import dataclass, field
from dotenv import load_dotenv
import os
import json
from pydantic import BaseModel

from anthropic import Anthropic, transform_schema
from anthropic.types import (
    OutputConfigParam,
    TextBlockParam,
    ThinkingConfigParam,
    ToolChoiceParam,
    ToolUnionParam,
    MessageParam,
)

from agent_framework.dto import (
    AgenticChat,
    AgentReport,
    ContentBlock,
    ContentType,
    Message,
)

load_dotenv()

client = Anthropic(
    timeout=600.0, max_retries=2, api_key=os.environ.get("ANTHROPIC_API_KEY", "missing")
)

ClaudeModels = Literal[
    # Fabel
    "claude-fable-5-1",
    "claude-fable-5",
    # Opus
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-opus-4-0",
    # Sonnet
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    # Haiku
    "claude-haiku-5-5",
]


@dataclass(frozen=True)
class ClaudeAgentConfig:
    model: ClaudeModels
    max_tokens: int

    system_prompt: str

    thought_type: Literal["adaptive", "disabled", "enabled"]
    effort: Literal["low", "medium", "high", "xhigh", "max"]

    thought_display: Literal["summarized", "omitted"] = "summarized"
    # only used when thought_type == "enabled" (Opus 4.0 and older); must be < max_tokens
    budget_tokens: int | None = None
    tools: tuple[ToolUnionParam, ...] = ()
    tool_choice: ToolChoiceParam = field(default_factory=lambda: {"type": "none"})

    def to_thinking(self) -> ThinkingConfigParam:
        match self.thought_type:
            case "adaptive":
                return {"type": "adaptive", "display": self.thought_display}
            case "disabled":
                return {"type": "disabled"}
            case "enabled":
                if self.budget_tokens is None:
                    raise ValueError(
                        "budget_tokens is required when thought_type is 'enabled'"
                    )
                if self.budget_tokens >= self.max_tokens:
                    raise ValueError(
                        f"budget_tokens ({self.budget_tokens}) must be less than "
                        f"max_tokens ({self.max_tokens})"
                    )
                return {"type": "enabled", "budget_tokens": self.budget_tokens}
            case _:
                raise ValueError(f"Unknown thinking type: {self.thought_type!r}")


# server_tool_use.name -> our ContentBlock type
SERVER_TOOL_TYPES: dict[str, ContentType] = {
    "web_search": "web_search",
    "web_fetch": "web_search",
    "code_execution": "code_execution",
    "bash_code_execution": "code_execution",
    "text_editor_code_execution": "shell",
    "tool_search_tool_regex": "tool_search",
    "tool_search_tool_bm25": "tool_search",
}

# server tool *result* block type -> our ContentBlock type
RESULT_BLOCK_TYPES: dict[str, ContentType] = {
    "web_search_tool_result": "web_search",
    "web_fetch_tool_result": "web_search",
    "code_execution_tool_result": "code_execution",
    "bash_code_execution_tool_result": "code_execution",
    "text_editor_code_execution_tool_result": "shell",
    "tool_search_tool_result": "tool_search",
}


class ClaudeChat(AgenticChat):
    def __init__(self, agent_config: ClaudeAgentConfig) -> None:
        self.agent_config = agent_config
        self._raw_history: list[MessageParam] = []

    @property
    def model_name(self) -> str:
        return self.agent_config.model

    def call(
        self,
        user_text: str,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport:
        user_message = Message(
            role="user", content=[ContentBlock(type="text", content=user_text)]
        )

        def to_claude_message(message: Message) -> MessageParam:
            blocks: list[TextBlockParam] = []
            for block in message.content:
                if block.type != "text":
                    raise NotImplementedError(
                        f"a user turn cannot carry a {block.type!r} block"
                    )
                blocks.append({"type": "text", "text": block.content})
            return {"role": "user", "content": blocks}

        output_config: OutputConfigParam = {"effort": self.agent_config.effort}
        if output_format is not None:
            output_config["format"] = {
                "type": "json_schema",
                "schema": transform_schema(output_format),
            }

        pending_user_msg_param = to_claude_message(user_message)

        response = client.messages.create(
            model=self.agent_config.model,
            max_tokens=self.agent_config.max_tokens,
            system=self.agent_config.system_prompt,
            messages=[*self._raw_history, pending_user_msg_param],
            thinking=self.agent_config.to_thinking(),
            output_config=output_config,
            tools=self.agent_config.tools,
            tool_choice=self.agent_config.tool_choice,
            cache_control={"type": "ephemeral"},
        )

        usage = response.usage
        cache_read = usage.cache_read_input_tokens or 0
        cache_total = cache_read + (usage.cache_creation_input_tokens or 0)

        if not response.content:
            return AgentReport(
                agent_config=self.agent_config,
                status="Failed",
                stop_reason=response.stop_reason,
                response=self._to_message(
                    {"role": "assistant", "content": response.content}
                ),
                input_tokens=usage.input_tokens + cache_total,
                completion_tokens=usage.output_tokens,
                cache_tokens=cache_read,
            )

        self._raw_history.append(pending_user_msg_param)
        self._raw_history.append({"role": "assistant", "content": response.content})

        return AgentReport(
            agent_config=self.agent_config,
            status="Completed",
            stop_reason=response.stop_reason,
            response=self._to_message(
                {"role": "assistant", "content": response.content}
            ),
            input_tokens=usage.input_tokens + cache_total,
            completion_tokens=usage.output_tokens,
            cache_tokens=cache_read,
        )

    def get_raw_history(self) -> list[MessageParam]:
        return list(self._raw_history)

    def _to_message(self, message_param: MessageParam) -> Message:
        role = message_param["role"]
        content = message_param["content"]
        assert not isinstance(content, str)
        content_blocks = []
        for block in content:
            assert not isinstance(block, str)
            if isinstance(block, dict):
                if block["type"] == "text":
                    content_blocks.append(
                        ContentBlock(type="text", content=block["text"])
                    )
                else:
                    raise NotImplementedError
            else:
                if block.type == "thinking":
                    content_blocks.append(
                        ContentBlock(
                            type="reasoning",
                            content=block.thinking,
                        )
                    )
                elif block.type == "redacted_thinking":
                    content_blocks.append(
                        ContentBlock(type="reasoning", content=block.data)
                    )
                elif block.type == "text":
                    content_blocks.append(ContentBlock(type="text", content=block.text))
                elif block.type == "tool_use":
                    content_blocks.append(
                        ContentBlock(
                            type="tool_call",
                            content=json.dumps(
                                {"name": block.name, "arguments": block.input}
                            ),
                        )
                    )
                elif block.type == "server_tool_use":
                    content_blocks.append(
                        ContentBlock(
                            type=SERVER_TOOL_TYPES[block.name],
                            content=f"name: {block.name}, input: {block.input}",
                        )
                    )
                elif block.type in RESULT_BLOCK_TYPES:
                    content_blocks.append(
                        ContentBlock(
                            type=RESULT_BLOCK_TYPES[block.type],
                            content=block.model_dump_json(),
                        )
                    )
        return Message(role=role, content=content_blocks)

    def get_history(self) -> list[Message]:
        return [self._to_message(message_param) for message_param in self._raw_history]

    def clear_history(self) -> None:
        self._raw_history.clear()

    def __str__(self) -> str:
        return str(self.agent_config)
