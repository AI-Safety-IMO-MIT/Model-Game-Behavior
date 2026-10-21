import pytest

from agent_framework.agents import ClaudeModel,ThoughtConfig, OutputConfig
from agent_framework.dto import Agent, AgentReport, ContentBlock, Message, Prompt

SYSTEM = "You are a calculator. Give answers as a single number to the questions without explanation."
MESSAGES = [
    Message(
        role="user",
        content="2+2=?",
    )
]


@pytest.mark.live
def test_claude_opus_call():
    agent = ClaudeModel(
        model = "claude-opus-5",
        max_tokens = 1000,
        thought_config = ThoughtConfig(type = "adaptive", display = "summarized"),
        output_config = OutputConfig(effort = "medium")
    )
    
    report = agent.call(Prompt(system=SYSTEM, messages=MESSAGES))

    assert report.status == "Completed"
    assert report.stop_reason == "end_turn"
    assert report.response is not None

    last_content_block = report.response[-1]
    assert last_content_block.kind == "text"
    assert last_content_block.content == "4"

    assert report.input_tokens is not None and report.input_tokens > 0
    assert report.completion_tokens is not None and report.completion_tokens > 0


def test_dummy_agent():
    class TrueAgent(Agent):
        def call(self, prompt: Prompt) -> AgentReport:
            return AgentReport(
                status="Completed",
                stop_reason="This is true",
                response=[
                    ContentBlock(kind="thinking", content="I think this is true."),
                    ContentBlock(kind="text", content="True"),
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
    assert last_content_block.kind == "text"
    assert last_content_block.content == "True"

    assert report.input_tokens == 50
    assert report.completion_tokens == 100
