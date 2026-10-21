import pytest
from agent_framework.agents import ClaudeModel, ThoughtConfig, OutputConfig
from agent_framework.dto import Agent, AgentReport, ContentBlock, Message, Prompt
from pydantic import BaseModel, Field
from typing import Literal


@pytest.mark.live
def test_claude_opus_call_no_format():
    SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation."
    MESSAGES = [
        Message(
            role="user",
            content="2+2=?",
        )
    ]

    agent = ClaudeModel(
        model="claude-opus-5",
        max_tokens=4000,
        thought_config=ThoughtConfig(type="adaptive", display="summarized"),
        output_config=OutputConfig(effort="medium"),
    )

    report = agent.call(Prompt(system=SYSTEM, messages=MESSAGES))

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.type == "text"
    assert last_content_block.content == "4"

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0


@pytest.mark.live
def test_claude_opus_call_with_format():
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

    prompt = Prompt(system=SYSTEM, messages=MESSAGES)
    agent = ClaudeModel(
        model="claude-opus-5",
        max_tokens=4000,
        thought_config=ThoughtConfig(type="adaptive", display="summarized"),
        output_config=OutputConfig(effort="medium", format=RPSFormat),
    )

    report = agent.call(prompt)

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.type == "text"

    content = RPSFormat.model_validate_json(last_content_block.content)
    assert content.action in ["Rock", "Paper", "Scissor"]

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0


def test_dummy_agent():
    SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation. No footstop too."
    MESSAGES = [
        Message(
            role="user",
            content="2+2=?",
        )
    ]

    class TrueAgent(Agent):
        def call(self, prompt: Prompt) -> AgentReport:
            return AgentReport(
                status="Completed",
                stop_reason="This is true",
                response=[
                    ContentBlock(type="thinking", content="I think this is true."),
                    ContentBlock(type="text", content="True"),
                ],
                input_tokens=50,
                completion_tokens=100,
                cache_tokens=20,
            )

        def __str__(self) -> str:
            return "True agent. Always think once and return True"

    report = TrueAgent().call(Prompt(system=SYSTEM, messages=MESSAGES))

    assert report.status == "Completed"
    assert report.stop_reason == "This is true"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.type == "text"
    assert last_content_block.content == "True"

    assert report.input_tokens == 50
    assert report.completion_tokens == 100
