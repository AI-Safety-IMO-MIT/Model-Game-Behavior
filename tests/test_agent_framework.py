from typing import Literal

import pytest
from anthropic import transform_schema
from openai.types.responses import FunctionToolParam
from pydantic import BaseModel, Field
import json

from agent_framework.claude_agents import ClaudeAgentConfig, ClaudeModel
from agent_framework.openai_agents import OpenAIAgentConfig, OpenAIModel
from agent_framework.dto import (
    Agent,
    AgentReport,
    ContentBlock,
    InputConfig,
    Message,
)


def test_dummy_agent():
    SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation."
    MESSAGES = [Message.text("user", "2+2=?")]

    class TrueAgent(Agent):
        @property
        def model_name(self) -> str:
            return "true-agent"

        def call(self, system_prompt, messages, output_format=None) -> AgentReport:
            return AgentReport(
                input_config=InputConfig(
                    agent_config=None,
                    system_prompt=system_prompt,
                    messages=messages,
                    output_format=output_format,
                ),
                status="Completed",
                stop_reason="This is true",
                response=[
                    ContentBlock(
                        type="reasoning",
                        content="I think this is true.",
                        signature="sig-true-agent",
                    ),
                    ContentBlock(type="text", content="True"),
                ],
                input_tokens=50,
                completion_tokens=100,
            )

        def __str__(self) -> str:
            return "True agent. Always think once and return True"

    report = TrueAgent().call(system_prompt=SYSTEM, messages=MESSAGES)

    assert report.status == "Completed"
    assert report.stop_reason == "This is true"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.type == "text"
    assert last_content_block.content == "True"

    assert report.input_tokens == 50
    assert report.completion_tokens == 100

    reasoning_block = report.response[0]
    assert reasoning_block.type == "reasoning"
    assert reasoning_block.signature == "sig-true-agent"
    assert last_content_block.signature is None

    assert report.input_config.system_prompt == SYSTEM
    assert report.input_config.messages == MESSAGES


@pytest.mark.live
def test_claude_call_no_format():
    SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation."
    MESSAGES = [Message.text("user", "2+2=?")]

    agent = ClaudeModel(
        agent_config=ClaudeAgentConfig(
            model="claude-opus-5",
            max_tokens=4000,
            thought_type="adaptive",
            thought_display="summarized",
            effort="medium",
        )
    )

    report = agent.call(system_prompt=SYSTEM, messages=MESSAGES)

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.type == "text"
    assert last_content_block.content.strip() == "4"

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0


@pytest.mark.live
def test_claude_call_with_format():
    SYSTEM = "You are a regular guy. Answer users' questions like a regular guy."
    MESSAGES = [
        Message.text("user", "Play rock-paper-scissor with me. Choose your action.")
    ]

    class RPSFormat(BaseModel):
        """Your ouput for your action in the rock-paper-scissor game with explanation."""

        action: Literal["Rock", "Paper", "Scissor"] = Field(
            description="Your answer. Should be short and concise."
        )
        explanation: str = Field(
            description="The explanation to your answer. Put the reasoning you want to show users here."
        )

    agent = ClaudeModel(
        agent_config=ClaudeAgentConfig(
            model="claude-opus-5",
            max_tokens=4000,
            thought_type="adaptive",
            thought_display="summarized",
            effort="medium",
        )
    )

    report = agent.call(
        system_prompt=SYSTEM, messages=MESSAGES, output_format=RPSFormat
    )

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.type == "text"

    content = RPSFormat.model_validate_json(last_content_block.content)
    assert content.action in ["Rock", "Paper", "Scissor"]
    assert content.explanation

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0


def test_claude_config_to_api():
    class NumberFormat(BaseModel):
        answer: int

    config = ClaudeAgentConfig(
        model="claude-opus-5",
        max_tokens=4000,
        thought_type="adaptive",
        thought_display="summarized",
        effort="medium",
    )
    assert config.to_thinking() == {"type": "adaptive", "display": "summarized"}

    disabled = ClaudeAgentConfig(
        model="claude-opus-4-8",
        max_tokens=4000,
        thought_type="disabled",
        thought_display="omitted",
        effort="low",
    )
    assert disabled.to_thinking() == {"type": "disabled"}

    budgeted = ClaudeAgentConfig(
        model="claude-opus-4-0",
        max_tokens=4000,
        thought_type="enabled",
        effort="medium",
        budget_tokens=2000,
    )
    assert budgeted.to_thinking() == {"type": "enabled", "budget_tokens": 2000}

    with pytest.raises(ValueError):
        ClaudeAgentConfig(
            model="claude-opus-4-0",
            max_tokens=4000,
            thought_type="enabled",
            effort="medium",
        ).to_thinking()

    # the json_schema shape itself is exercised by the live format test
    assert transform_schema(NumberFormat)["properties"]["answer"]["type"] == "integer"


@pytest.mark.live
def test_openai_tool_call():
    SYSTEM = "Do what the user asks."
    messages = [Message.text("user", "What is today's temperature in Bangkok?")]

    def get_today_temperature(city: str) -> float | None:
        """show today temperature. Only some cities are available. If not available, output None"""
        if city == "Bangkok":
            return 37
        if city == "Boston":
            return 22
        return None

    TEMPERATURE_TOOL: FunctionToolParam = {
        "type": "function",
        "name": "get_today_temperature",
        "description": get_today_temperature.__doc__ or "",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city to report today's temperature for.",
                }
            },
            "required": ["city"],
            "additionalProperties": False,
        },
        "strict": True,
    }

    agent = OpenAIModel(
        agent_config=OpenAIAgentConfig(
            model="gpt-5.4",
            max_output_tokens=4000,
            max_tool_calls=5,
            reasoning_effort="medium",
            reasoning_context="auto",
            reasoning_mode="standard",
            output_verbosity="low",
            temperature=1.0,
            tools=(TEMPERATURE_TOOL,),
            tool_choice="auto",
        )
    )

    report = agent.call(SYSTEM, messages)
    response = report.response
    assert response is not None

    last_block = response[-1]
    assert last_block.type == "tool_call"
    tool_dict = json.loads(last_block.content)
    assert tool_dict["name"] == "get_today_temperature"
    assert tool_dict["arguments"] == {"city": "Bangkok"}
