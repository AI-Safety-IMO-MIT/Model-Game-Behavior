from typing import Literal
from dataclasses import dataclass
from anthropic import Anthropic, transform_schema
from dotenv import load_dotenv

from agent_framework.dto import Agent, AgentReport, ContentBlock, Prompt
from pydantic import BaseModel
from anthropic.types import ThinkingConfigParam, OutputConfigParam

load_dotenv()

ClaudeModels = Literal[
    # fabel
    "claude-fable-5-1",
    "claude-fable-5",
    # opus
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    # sonner
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    # haiku
    "claude-haiku-5-5",
]

@dataclass(frozen=True)
class ThoughtConfig:
    type: Literal["adaptive", "enabled", "disabled"]
    display: Literal["summarized", "omitted"]
    budget_tokens: int | None = None

    def to_api(self) -> ThinkingConfigParam:
        match self.type:
            case "adaptive":
                return {"type": "adaptive", "display": self.display}
            case "enabled":
                if self.budget_tokens is None:
                    raise ValueError('"enabled" needs budget_tokens.')
                return {
                    "type": "enabled",
                    "budget_tokens": self.budget_tokens,
                    "display": self.display,
                }
            case "disabled":
                return {"type": "disabled"}

@dataclass(frozen=True)
class OutputConfig():
    effort: Literal["low","medium","high","xhigh","max"]
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
    def __init__(self, model: ClaudeModels, max_tokens: int, thought_config: ThoughtConfig, output_config: OutputConfig) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.thinking: ThinkingConfigParam = thought_config.to_api()
        self.output_config: OutputConfigParam = output_config.to_api()

    def _extract_response(self, output):
        if output.stop_reason == "refusal":
            return AgentReport(
                status="Failed",
                stop_reason=output.stop_details,
                response=None,
                input_tokens=None,
                completion_tokens=None,
                cache_tokens=None,
            )

        response = []
        for block in output.content:
            if block.type == "thinking" and block.thinking:
                response.append(ContentBlock(kind="thinking", content=block.thinking))
            elif block.type == "text":
                response.append(ContentBlock(kind="text", content=block.text))

        return AgentReport(
            status="Completed",
            stop_reason=output.stop_reason,
            response=response,
            input_tokens=output.usage.input_tokens,
            completion_tokens=output.usage.output_tokens,
            cache_tokens=output.usage.cache_read_input_tokens,
        )

    def call(self, prompt: Prompt):
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=prompt.system,
            messages=[
                {"role": message.role, "content": message.content}
                for message in prompt.messages
            ],
            thinking=self.thinking,
            output_config=self.output_config
        )
        return self._extract_response(response)

    def __str__(self) -> str:
        return "I'm da claude"
