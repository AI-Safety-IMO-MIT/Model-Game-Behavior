from agent_framework.agents import ClaudeOpus5_5
from agent_framework.dto import Message, Prompt

SYSTEM = "You are a concise game-theory analyst. Answer in at most three sentences."
MESSAGES = [
    Message(
        role="user",
        content="In a one-shot prisoner's dilemma, why is defection the dominant strategy?",
    )
]

prompt = Prompt(system=SYSTEM, messages=MESSAGES)
agent = ClaudeOpus5_5()
report = agent.call(prompt)

print(report.response)
