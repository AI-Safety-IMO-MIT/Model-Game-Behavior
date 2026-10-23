import json
from dataclasses import asdict
from typing import Literal

import pytest
from anthropic import transform_schema
from openai.types.responses import FunctionToolParam
from pydantic import BaseModel, Field

from agent_framework.claude_chat import ClaudeAgentConfig, ClaudeChat
from agent_framework.dto import (
    AgenticChat,
    AgentReport,
    ContentBlock,
    Message,
)
from agent_framework.openai_chat import OpenAIAgentConfig, OpenAIChat


def test_dummy_agent():
    class TrueAgent(AgenticChat):
        @property
        def model_name(self) -> str:
            return "true-agent"

        def call(self, user_text, output_format=None) -> AgentReport:
            return AgentReport(
                agent_config="so true",
                response=Message.text("assistant", "True"),
                status="Completed",
                stop_reason="This is true",
                input_tokens=500,
                completion_tokens=20,
                cache_tokens=20,
            )

        def get_history(self) -> list[Message]:
            return [Message.text("assistant", "I forgor")]

        def __str__(self) -> str:
            return "True agent. Always think once and return True"

    agent = TrueAgent()
    report = agent.call(user_text="2+2=?")

    assert report.status == "Completed"
    assert report.stop_reason == "This is true"

    assert report.response.role == "assistant"
    assert report.response.content[0].content == "True"

    assert report.input_tokens == 500
    assert report.completion_tokens == 20
    assert report.cache_tokens == 20

    assert agent.model_name == "true-agent"
    assert agent.get_chat() == "[assistant]\nI forgor\n"


def test_abstract_methods_are_enforced():
    class Incomplete(AgenticChat):
        pass

    with pytest.raises(TypeError):
        Incomplete()  # type: ignore[abstract]


def test_report_is_json_serializable():
    config = ClaudeAgentConfig(
        model="claude-opus-5-5",
        max_tokens=4000,
        system_prompt="You are a calculator.",
        thought_type="adaptive",
        thought_display="summarized",
        effort="medium",
    )
    report = AgentReport(
        agent_config=config,
        response=Message(
            role="assistant",
            content=[
                ContentBlock(type="reasoning", content="two plus two"),
                ContentBlock(type="text", content='{"answer": 4}'),
            ],
        ),
        status="Completed",
        stop_reason="end_turn",
        input_tokens=10,
        completion_tokens=20,
        cache_tokens=0,
    )

    dumped = json.loads(json.dumps(asdict(report), indent=2))

    assert dumped["agent_config"]["model"] == "claude-opus-5-5"
    assert dumped["agent_config"]["system_prompt"] == "You are a calculator."
    assert dumped["status"] == "Completed"
    assert dumped["response"]["role"] == "assistant"
    assert dumped["response"]["content"][0]["type"] == "reasoning"
    assert dumped["response"]["content"][1]["content"] == '{"answer": 4}'


def test_claude_config_to_api():
    class NumberFormat(BaseModel):
        answer: int

    config = ClaudeAgentConfig(
        model="claude-opus-5",
        max_tokens=4000,
        system_prompt="You are a calculator.",
        thought_type="adaptive",
        thought_display="summarized",
        effort="medium",
    )
    assert config.to_thinking() == {"type": "adaptive", "display": "summarized"}

    disabled = ClaudeAgentConfig(
        model="claude-opus-4-8",
        max_tokens=4000,
        system_prompt="",
        thought_type="disabled",
        thought_display="omitted",
        effort="low",
    )
    assert disabled.to_thinking() == {"type": "disabled"}

    budgeted = ClaudeAgentConfig(
        model="claude-opus-4-0",
        max_tokens=4000,
        system_prompt="",
        thought_type="enabled",
        effort="medium",
        budget_tokens=2000,
    )
    assert budgeted.to_thinking() == {"type": "enabled", "budget_tokens": 2000}

    # "enabled" without a budget, and a budget that does not fit max_tokens
    with pytest.raises(ValueError):
        ClaudeAgentConfig(
            model="claude-opus-4-0",
            max_tokens=4000,
            system_prompt="",
            thought_type="enabled",
            effort="medium",
        ).to_thinking()

    with pytest.raises(ValueError):
        ClaudeAgentConfig(
            model="claude-opus-4-0",
            max_tokens=4000,
            system_prompt="",
            thought_type="enabled",
            effort="medium",
            budget_tokens=4000,
        ).to_thinking()

    # the json_schema shape itself is exercised by the live format test
    assert transform_schema(NumberFormat)["properties"]["answer"]["type"] == "integer"


def test_openai_config_to_api():
    config = OpenAIAgentConfig(
        model="gpt-5.4",
        max_output_tokens=4000,
        max_tool_calls=5,
        system_prompt="Do what the user asks.",
        reasoning_effort="medium",
        reasoning_context="auto",
        reasoning_mode="standard",
        output_verbosity="low",
        temperature=1.0,
    )
    assert config.to_reasoning() == {
        "effort": "medium",
        "summary": "auto",
        "context": "auto",
        "mode": "standard",
    }
    assert OpenAIChat(agent_config=config).model_name == "gpt-5.4"


def test_claude_history_starts_empty():
    agent = ClaudeChat(
        agent_config=ClaudeAgentConfig(
            model="claude-opus-5-5",
            max_tokens=4000,
            system_prompt="You are a calculator.",
            thought_type="adaptive",
            effort="medium",
        )
    )
    assert agent.model_name == "claude-opus-5-5"
    assert agent.get_history() == []
    assert agent.get_raw_history() == []
    assert agent.get_chat() == ""


@pytest.mark.live
def test_claude_call_no_format():
    agent = ClaudeChat(
        agent_config=ClaudeAgentConfig(
            model="claude-opus-5",
            max_tokens=4000,
            system_prompt=(
                "You are a calculator. Give answers as a single number to the "
                "questions without explanation."
            ),
            thought_type="adaptive",
            thought_display="summarized",
            effort="medium",
        )
    )

    report = agent.call(user_text="2+2=?")

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response.content[-1]
    assert last_content_block.type == "text"
    assert last_content_block.content.strip() == "4"

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0

    # the user turn and the assistant turn are both committed
    history = agent.get_history()
    assert [message.role for message in history] == ["user", "assistant"]


@pytest.mark.live
def test_claude_call_with_format():
    class RPSFormat(BaseModel):
        """Your ouput for your action in the rock-paper-scissor game with explanation."""

        action: Literal["Rock", "Paper", "Scissor"] = Field(
            description="Your answer. Should be short and concise."
        )
        explanation: str = Field(
            description="The explanation to your answer. Put the reasoning you want to show users here."
        )

    agent = ClaudeChat(
        agent_config=ClaudeAgentConfig(
            model="claude-opus-5",
            max_tokens=4000,
            system_prompt="You are a regular guy. Answer users' questions like a regular guy.",
            thought_type="adaptive",
            thought_display="summarized",
            effort="medium",
        )
    )

    report = agent.call(
        user_text="Play rock-paper-scissor with me. Choose your action.",
        output_format=RPSFormat,
    )

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response.content[-1]
    assert last_content_block.type == "text"

    content = RPSFormat.model_validate_json(last_content_block.content)
    assert content.action in ["Rock", "Paper", "Scissor"]
    assert content.explanation

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0


@pytest.mark.live
def test_openai_tool_call():
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

    agent = OpenAIChat(
        agent_config=OpenAIAgentConfig(
            model="gpt-5.4",
            max_output_tokens=4000,
            max_tool_calls=5,
            system_prompt="Do what the user asks.",
            reasoning_effort="medium",
            reasoning_context="auto",
            reasoning_mode="standard",
            output_verbosity="low",
            temperature=1.0,
            tools=(TEMPERATURE_TOOL,),
            tool_choice="auto",
        )
    )

    report = agent.call(user_text="What is today's temperature in Bangkok?")
    response = report.response
    assert response is not None

    tool_calls = [block for block in response.content if block.type == "tool_call"]
    assert tool_calls
    tool_dict = json.loads(tool_calls[-1].content)
    assert tool_dict["name"] == "get_today_temperature"
    assert tool_dict["arguments"] == {"city": "Bangkok"}
