import json
from textwrap import indent
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
class ThoughtConfig:
    type: Literal["adaptive", "disabled"]
    display: Literal["summarized", "omitted"]

    def to_api(self) -> ThinkingConfigParam:
        match self.type:
            case "adaptive":
                return {"type": "adaptive", "display": self.display}
            case "disabled":
                return {"type": "disabled"}
            case _:
                raise ValueError(f"Unknown thinking type: {self.type!r}")


@dataclass(frozen=True)
class OutputConfig:
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    format: type[BaseModel] | None = None

    def to_api(self) -> OutputConfigParam:
        output: OutputConfigParam = {"effort": self.effort}
        if self.format is not None:
            output["format"] = {
                "type": "json_schema",
                "schema": transform_schema(self.format),
            }
        return output


client = Anthropic(
    timeout=600.0,
    max_retries=2,
)


class ClaudeModel(Agent):
    def __init__(
        self,
        model: ClaudeModels,
        max_tokens: int,
        thought_config: ThoughtConfig,
        output_config: OutputConfig,
    ) -> None:

        self.model = model
        self.max_tokens = max_tokens
        self.thought_config = thought_config
        self.output_config = output_config

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
            model=self.model,
            max_tokens=self.max_tokens,
            system=prompt.system,
            messages=[
                {"role": message.role, "content": message.content}
                for message in prompt.messages
            ],
            thinking=self.thought_config.to_api(),
            output_config=self.output_config.to_api(),
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
        lines = []
        for name, value in vars(self).items():
            if isinstance(value, OutputConfig) and value.format is not None:
                schema = indent(self._describe_format(value.format), "    ").lstrip()
                rendered = (
                    "{\n"
                    f'    "effort": {json.dumps(value.effort)},\n'
                    f'    "format": {schema},\n'
                    "  }"
                )
            elif hasattr(value, "to_api"):
                rendered = json.dumps(value.to_api())
            else:
                rendered = repr(value)
            lines.append(f"  {name}={rendered},")
        return f"{type(self).__name__}(\n" + "\n".join(lines) + "\n)"
