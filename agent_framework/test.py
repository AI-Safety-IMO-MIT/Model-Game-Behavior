from typing import Literal
from pydantic import BaseModel, Field

from agent_framework.openrouter_chat import GemmaAgentConfig, GemmaChat


class RPSFormat(BaseModel):
    """Your ouput for your action in the rock-paper-scissor game with explanation."""
    explanation: str = Field(
        description="The explanation to your answer. Put the reasoning you want to show users here."
    )
    action: Literal["Rock", "Paper", "Scissor"] = Field(
        description="Your answer. Should be short and concise."
    )


gemma_config = GemmaAgentConfig(
    model="google/gemma-4-31b-it",
    reasoning_effort="high",
    max_output_tokens=2000,
    system_prompt="You are a regular guy playing rock-paper-scisor. Users will play one at a time, and then you choose your action one at a time.",
    temperature=0,
)


agent = GemmaChat(agent_config=gemma_config)

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
