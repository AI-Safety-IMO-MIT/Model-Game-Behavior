from typing import Literal

import pytest
from anthropic import transform_schema
from pydantic import BaseModel, Field

from agent_framework.claude_agents import ClaudeAgentConfig, ClaudeModel
from agent_framework.dto import Agent, AgentReport, ContentBlock, Message


@pytest.mark.live
def test_claude_call_no_format():
    SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation."
    MESSAGES = [
        Message(
            role="user",
            content="2+2=?",
        )
    ]

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
        Message(
            role="user",
            content="Play rock-paper-scissor with me. Choose your action.",
        )
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
            output_format=RPSFormat,
        )
    )

    report = agent.call(system_prompt=SYSTEM, messages=MESSAGES)

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
        output_format=NumberFormat,
    )

    assert config.to_thinking() == {"type": "adaptive", "display": "summarized"}

    assert config.to_output_config() == {
        "effort": "medium",
        "format": {
            "type": "json_schema",
            "schema": transform_schema(NumberFormat),
        },
    }

    disabled = ClaudeAgentConfig(
        model="claude-opus-4-8",
        max_tokens=4000,
        thought_type="disabled",
        thought_display="omitted",
        effort="low",
        output_format=NumberFormat,
    )
    assert disabled.to_thinking() == {"type": "disabled"}


def test_dummy_agent():
    SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation."
    MESSAGES = [
        Message(
            role="user",
            content="2+2=?",
        )
    ]

    class TrueAgent(Agent):
        def call(self, system_prompt, messages) -> AgentReport:
            return AgentReport(
                status="Completed",
                stop_reason="This is true",
                response=[
                    ContentBlock(type="reasoning", content="I think this is true."),
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
