from typing import Literal, Annotated
from dataclasses import dataclass
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import os
import json

from openai import OpenAI
from openai.types.shared_params import Reasoning
from openai.types.responses import ResponseInputParam, ToolParam
from openai.types.responses.response_create_params import ToolChoice
from openai.lib._pydantic import to_strict_json_schema
from openai.types.responses.response import Response
from openai.types.responses.response_text_config_param import ResponseTextConfigParam

from agent_framework.dto import (
    Agent,
    AgentReport,
    ContentBlock,
    ContentType,
    Message,
    InputConfig,
)


load_dotenv()

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

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY", "missing"),
    timeout=600.0,
    max_retries=2,
)


@dataclass(frozen=True)
class OpenAIAgentConfig:
    model: OpenAIModels
    max_output_tokens: int
    max_tool_calls: int

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
    "code_interpreter_call": "code_execution",
    "shell_call": "shell",
    "shell_call_output": "shell",
    "local_shell_call": "shell",
    "local_shell_call_output": "shell",
    "tool_search_call": "tool_search",
    "tool_search_output": "tool_search",
}


def to_openai_input(messages: list[Message]) -> ResponseInputParam:
    """Our turns -> Responses input items, one item per text block."""
    items: ResponseInputParam = []
    for message in messages:
        for block in message.content:
            if block.type == "text":
                items.append({"role": message.role, "content": block.content})
            else:
                # function_call_output needs the call_id, which ContentBlock
                # does not carry, so it cannot be rebuilt faithfully yet.
                raise NotImplementedError(
                    f"cannot send a {block.type!r} block back to the API yet"
                )
    return items


class OpenAIModel(Agent):
    def __init__(self, agent_config: OpenAIAgentConfig) -> None:
        self.agent_config = agent_config

    @property
    def model_name(self) -> str:
        return self.agent_config.model

    def _extract_response(
        self, input_config: InputConfig, output: Response
    ) -> AgentReport:
        if output.status == "incomplete":
            details = output.incomplete_details
            return AgentReport(
                input_config=input_config,
                status="Failed",
                stop_reason=details.reason if details else None,
                response=None,
                input_tokens=None,
                completion_tokens=None,
            )

        if output.status == "failed":
            error = output.error
            return AgentReport(
                input_config=input_config,
                status="Failed",
                stop_reason=error.code + ": " + error.message if error else None,
                response=None,
                input_tokens=None,
                completion_tokens=None,
            )

        response = []
        for item in output.output:
            if item.type == "reasoning":
                for part in item.summary:
                    response.append(ContentBlock(type="reasoning", content=part.text))

            elif item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        response.append(ContentBlock(type="text", content=part.text))
                    elif part.type == "refusal":
                        response.append(ContentBlock(type="text", content=part.refusal))

            elif item.type == "function_call":
                response.append(
                    ContentBlock(
                        type="tool_call",
                        content=json.dumps(
                            {"name": item.name, "arguments": json.loads(item.arguments)}
                        ),
                    )
                )

            elif item.type == "function_call_output":
                response.append(
                    ContentBlock(type="tool_result", content=item.model_dump_json())
                )

            elif item.type in SERVER_ITEM_TYPES:
                response.append(
                    ContentBlock(
                        type=SERVER_ITEM_TYPES[item.type],
                        content=item.model_dump_json(),
                    )
                )

        usage = output.usage
        assert usage is not None

        return AgentReport(
            input_config=input_config,
            status="Completed",
            stop_reason=None,
            response=response,
            input_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
        )

    def call(
        self, system_prompt, messages, output_format: type[BaseModel] | None = None
    ) -> AgentReport:
        input_config = InputConfig(
            agent_config=self.agent_config,
            system_prompt=system_prompt,
            messages=messages,
            output_format=output_format,
        )
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
            instructions=system_prompt,
            input=to_openai_input(messages),
            max_output_tokens=self.agent_config.max_output_tokens,
            max_tool_calls=self.agent_config.max_tool_calls,
            reasoning=self.agent_config.to_reasoning(),
            text=text,
            temperature=self.agent_config.temperature,
            tools=self.agent_config.tools,
            tool_choice=self.agent_config.tool_choice,
        )
        return self._extract_response(input_config, response)

    def __str__(self) -> str:
        return "\n".join(
            [f"{name}: {value}" for name, value in vars(self.agent_config).items()]
        )
