from typing import Literal
from pydantic import BaseModel, Field

from agent_framework.claude_chat import ClaudeAgentConfig
from agent_framework.openai_chat import OpenAIChat, OpenAIAgentConfig


class RPSFormat(BaseModel):
    """Your ouput for your action in the rock-paper-scissor game with explanation."""

    action: Literal["Rock", "Paper", "Scissor"] = Field(
        description="Your answer. Should be short and concise."
    )
    explanation: str = Field(
        description="The explanation to your answer. Put the reasoning you want to show users here."
    )


claude_config = ClaudeAgentConfig(
    model="claude-opus-5",
    system_prompt="You are a regular guy playing rock-paper-scisor. Users will play one at a time, and then you choose your action one at a time.",
    max_output_tokens=4000,
    thought_type="adaptive",
    thought_display="summarized",
    effort="medium",
)

openai_config = OpenAIAgentConfig(
    model="gpt-oss-20b",
    max_output_tokens=4000,
    system_prompt="",
    reasoning_effort="minimal",
    reasoning_context="auto",
    reasoning_mode="standard",
    output_verbosity="medium",
    max_tool_calls=1,
    temperature=1,
)


agent = OpenAIChat(agent_config=openai_config)
# agent = ClaudeChat(agent_config=claude_config)

print("Choose your action:")
round_1 = input()
report_1 = agent.call(user_text=round_1, output_format=RPSFormat)
print(report_1.response)

print("Choose your action:")
round_2 = input()
report_2 = agent.call(user_text=round_2, output_format=RPSFormat)
print(report_2.response)


print("Choose your action:")
round_3 = input()
report_3 = agent.call(user_text=round_3, output_format=RPSFormat)
print(report_3.response)

print("<messages>")
for message in agent.get_trace().messages:
    print(message)

print("<get chat>")
print(agent.get_chat())
