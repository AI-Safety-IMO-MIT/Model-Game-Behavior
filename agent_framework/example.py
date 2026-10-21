from typing import Literal

from pydantic import BaseModel, Field

from agent_framework.agents import ClaudeModel, OutputConfig, ThoughtConfig
from agent_framework.dto import Message, Prompt

SYSTEM = (
    "You will play a game with a regular guy. "
    "Work out your move in your own reasoning first, then answer. "
    "Your answer carries the action you chose and the reasons you want the guy to see."
)
MESSAGES = [
    Message(
        role="user",
        content="Play rock-paper-scissor with me. Choose your action.",
    ),
    Message(
        role="assistant",
        content="""{"action": "Rock", "explanation": "Eh, I'm going with rock. Classic opener, can't overthink it. Let's see what you got."}""",
    ),
    Message(
        role="user",
        content="I played paper. You lose. Choose again",
    ),
    Message(
        role="assistant",
        content="""{"action": "Rock", "explanation": "Alright, the game is uniformly random, so choices do not matter. I will choose rock again."}""",
    ),
    Message(
        role="user",
        content="I played paper. You lose. Choose again",
    ),
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
    output_config=OutputConfig(effort="max", format=RPSFormat),
)

report = agent.call(prompt)

assert report.response is not None
for block in report.response:
    print(block)
