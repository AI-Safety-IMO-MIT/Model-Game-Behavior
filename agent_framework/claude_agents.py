from typing import Literal
from dataclasses import dataclass, field
from dotenv import load_dotenv
import os
import json
from pydantic import BaseModel

from anthropic import Anthropic, transform_schema
from anthropic.types import Message as APIMessage
from anthropic.types import (
    OutputConfigParam,
    TextBlockParam,
    ThinkingConfigParam,
    ToolChoiceParam,
    ToolUnionParam,
    MessageParam,
)

from agent_framework.dto import (
    Agent,
    AgentReport,
    ContentBlock,
    ContentType,
    Message,
    InputConfig,
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


class ClaudeModel(Agent):
    def __init__(self, agent_config: ClaudeAgentConfig) -> None:
        self.agent_config = agent_config

    @property
    def model_name(self) -> str:
        return self.agent_config.model

    def _extract_response(
        self, input_config: InputConfig, output: APIMessage
    ) -> AgentReport:
        if output.stop_reason == "refusal":
            return AgentReport(
                input_config=input_config,
                status="Failed",
                stop_reason=output.stop_reason,
                response=None,
                input_tokens=None,
                completion_tokens=None,
            )

        response = []
        for block in output.content:
            if block.type == "thinking":
                response.append(
                    ContentBlock(
                        type="reasoning",
                        content=block.thinking,
                        signature=block.signature,
                    )
                )

            elif block.type == "redacted_thinking":
                response.append(ContentBlock(type="reasoning", content=block.data))

            elif block.type == "text":
                response.append(ContentBlock(type="text", content=block.text))

            elif block.type == "tool_use":
                response.append(
                    ContentBlock(
                        type="tool_call",
                        content=json.dumps(
                            {"name": block.name, "arguments": block.input}
                        ),
                    )
                )

            elif block.type == "server_tool_use":
                response.append(
                    ContentBlock(
                        type=SERVER_TOOL_TYPES[block.name],
                        content=f"name: {block.name}, input: {block.input}",
                    )
                )

            elif block.type in RESULT_BLOCK_TYPES:
                response.append(
                    ContentBlock(
                        type=RESULT_BLOCK_TYPES[block.type],
                        content=block.model_dump_json(),
                    )
                )

        usage = output.usage
        cache_tokens = (usage.cache_read_input_tokens or 0) + (
            usage.cache_creation_input_tokens or 0
        )

        return AgentReport(
            input_config=input_config,
            status="Completed",
            stop_reason=output.stop_reason,
            response=response,
            input_tokens=usage.input_tokens + cache_tokens,
            completion_tokens=usage.output_tokens,
        )

    def _to_claude_content(self, messages: list[Message]) -> list[MessageParam]:
        """Our blocks -> Anthropic input blocks. Text only; see the note below."""

        def _to_claude_block(message: Message) -> list[TextBlockParam]:
            blocks: list[TextBlockParam] = []
            for block in message.content:
                if block.type == "text":
                    blocks.append({"type": "text", "text": block.content})
                elif block.type == "reasoning":
                    blocks.append(
                        {
                            "type": "text",
                            "text": f"<thinking>\n{block.content}\n</thinking>",
                        }
                    )
                else:
                    raise NotImplementedError(
                        f"cannot send a {block.type!r} block back to the API yet"
                    )
            return blocks

        return [
            {"role": message.role, "content": _to_claude_block(message)}
            for message in messages
        ]

    def call(
        self,
        system_prompt,
        messages: list[Message],
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport:
        input_config = InputConfig(
            agent_config=self.agent_config,
            system_prompt=system_prompt,
            messages=messages,
            output_format=output_format,
        )
        output_config: OutputConfigParam = {"effort": self.agent_config.effort}
        if output_format is not None:
            output_config["format"] = {
                "type": "json_schema",
                "schema": transform_schema(output_format),
            }

        response = client.messages.create(
            model=self.agent_config.model,
            max_tokens=self.agent_config.max_tokens,
            system=system_prompt,
            messages=self._to_claude_content(messages),
            thinking=self.agent_config.to_thinking(),
            output_config=output_config,
            tools=self.agent_config.tools,
            tool_choice=self.agent_config.tool_choice,
            cache_control={"type": "ephemeral"},
        )
        return self._extract_response(input_config, response)

    def _describe_format(self, output_format: type[BaseModel]) -> str:
        schema = transform_schema(output_format)
        fields = []
        for name, prop in schema.get("properties", {}).items():
            if "enum" in prop:
                kind = "|".join(repr(value) for value in prop["enum"])
            else:
                kind = prop.get("type", "any")
            fields.append(f"  {name}: {kind},")
        return f"{output_format.__name__}(\n" + "\n".join(fields) + "\n)"

    def __str__(self) -> str:
        return "\n".join(
            [f"{name}: {value}" for name, value in vars(self.agent_config).items()]
        )
