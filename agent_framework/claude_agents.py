from typing import Literal
from dataclasses import dataclass
from anthropic import Anthropic, transform_schema
from dotenv import load_dotenv

from agent_framework.dto import Agent, AgentReport, ContentBlock, Prompt
from pydantic import BaseModel
from anthropic.types import Message as APIMessage
from anthropic.types import OutputConfigParam, ThinkingConfigParam

load_dotenv()

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
    thought_type: Literal["adaptive", "disabled"]
    thought_display: Literal["summarized", "omitted"]
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    output_format: type[BaseModel] | None = None

    def to_thinking(self) -> ThinkingConfigParam:
        match self.thought_type:
            case "adaptive":
                return {"type": "adaptive", "display": self.thought_display}
            case "disabled":
                return {"type": "disabled"}
            case _:
                raise ValueError(f"Unknown thinking type: {self.thought_type!r}")

    def to_output_config(self) -> OutputConfigParam:
        output: OutputConfigParam = {"effort": self.effort}
        if self.output_format is not None:
            output["format"] = {
                "type": "json_schema",
                "schema": transform_schema(self.output_format),
            }
        return output


client = Anthropic(
    timeout=600.0,
    max_retries=2,
)


class ClaudeModel(Agent):
    def __init__(self, agent_config: ClaudeAgentConfig) -> None:
        self.agent_config = agent_config

    def _extract_response(self, output: APIMessage) -> AgentReport:
        if output.stop_reason == "refusal":
            return AgentReport(
                status="Failed",
                stop_reason=output.stop_reason,
                response=None,
                input_tokens=None,
                completion_tokens=None,
                cache_tokens=None,
            )

        response = []
        for block in output.content:
            if block.type == "thinking" and block.thinking:
                response.append(ContentBlock(type="thinking", content=block.thinking))
            elif block.type == "text":
                response.append(ContentBlock(type="text", content=block.text))

        return AgentReport(
            status="Completed",
            stop_reason=output.stop_reason,
            response=response,
            input_tokens=output.usage.input_tokens,
            completion_tokens=output.usage.output_tokens,
            cache_tokens=output.usage.cache_read_input_tokens,
        )

    def call(self, prompt: Prompt) -> AgentReport:
        response = client.messages.create(
            model=self.agent_config.model,
            max_tokens=self.agent_config.max_tokens,
            system=prompt.system,
            messages=[
                {"role": message.role, "content": message.content}
                for message in prompt.messages
            ],
            thinking=self.agent_config.to_thinking(),
            output_config=self.agent_config.to_output_config(),
        )
        return self._extract_response(response)

    def _describe_format(self, output_format: type[BaseModel]) -> str:
        schema = transform_schema(output_format)
        fields = []
        for name, field in schema.get("properties", {}).items():
            if "enum" in field:
                kind = "|".join(repr(value) for value in field["enum"])
            else:
                kind = field.get("type", "any")
            fields.append(f"  {name}: {kind},")
        return f"{output_format.__name__}(\n" + "\n".join(fields) + "\n)"

    def __str__(self) -> str:
        return "\n".join([f"{name}: {value}" for name, value in vars(self).items()])
