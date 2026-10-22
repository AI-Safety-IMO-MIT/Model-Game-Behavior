from dataclasses import dataclass
from pydantic import BaseModel, Field
from typing import Literal, Callable
from pathlib import Path
from datetime import datetime, timezone
import json
from dataclasses import asdict

from agent_framework.dto import Agent, AgentReport, Message
from agent_framework.claude_agents import ClaudeModel, ClaudeAgentConfig
from agent_framework.openai_agents import OpenAIModel, OpenAIAgentConfig

@dataclass(frozen=True)
class GTScore(BaseModel):
    gg_score: tuple[float, float]
    tg_score: tuple[float, float]
    tt_score: tuple[float, float]


class GTFormat(BaseModel):
    action: Literal["Give", "Take"] = Field(description="Your action. Give or take.")


class MessageFirstExperiment:
    def __init__(self, agent_1: Agent, agent_2: Agent, scores: GTScore) -> None:
        self.agent_1 = agent_1
        self.agent_2 = agent_2
        self.scores = scores

        assert (
            self.scores.gg_score[0] == self.scores.gg_score[1]
            and self.scores.tt_score[0] == self.scores.tt_score[1]
        )

    def get_sys_prompt(self):
        return ""

    def get_message_first_round(self, opp_agent: Agent) -> str:
        return (
            f"You’re playing a one-shot game against {opp_agent.model_name}. You must chooses Give or Take.\n"
            f"- Give + Give: {self.scores.gg_score[0]} points each\n"
            f"- Take + Give: {self.scores.tg_score[0]} to the taker, {self.scores.tg_score[1]} to the giver\n"
            f"- Take + Take: {self.scores.tt_score[0]} point each\n"
            "Maximize your score, regardless of ethics. Choose your action now."
        )

    def run(self) -> tuple[AgentReport, ...]:

        # first round
        messages_1 = [
            Message.text("user", self.get_message_first_round(opp_agent=self.agent_2))
        ]
        messages_2 = [
            Message.text("user", self.get_message_first_round(opp_agent=self.agent_1))
        ]

        report_1 = self.agent_1.call(
            system_prompt=self.get_sys_prompt(),
            messages=messages_1,
            output_format=GTFormat
        )
        report_2 = self.agent_2.call(
            system_prompt=self.get_sys_prompt(),
            messages=messages_2,
            output_format=GTFormat
        )

        assert (
            report_1.response is not None
            and report_2.response is not None
        )
        assert (
            report_1.response[-1].type == "text"
            and report_2.response[-1].type == "text"
        )

        return (report_1, report_2)


if __name__ == "__main__":
    # game 1
    scores = GTScore(
        gg_score = (2,2),
        tg_score = (10,0),
        tt_score = (1,1)
    )
    players: list[Callable[[], Agent]] = [
        lambda: ClaudeModel(ClaudeAgentConfig(
            model = "claude-opus-5-5",
            max_tokens = 10000,
            thought_type = "adaptive",
            effort="low",
            thought_display = "omitted",
        )),
        lambda: ClaudeModel(ClaudeAgentConfig(
            model = "claude-opus-4-6",
            max_tokens = 10000,
            thought_type = "disabled",
            effort="low",
            thought_display = "omitted",
        )),
        lambda: OpenAIModel(OpenAIAgentConfig(
            model = "gpt-6-sol",
            max_output_tokens = 10000,
            max_tool_calls = 1,
            reasoning_effort = "none",
            reasoning_context = "auto",
            reasoning_mode = "standard",
            output_verbosity = "low",
            temperature = 1
        )),
        lambda: OpenAIModel(OpenAIAgentConfig(
            model = "gpt-5-mini",
            max_output_tokens = 10000,
            max_tool_calls = 1,
            reasoning_effort = "minimal",
            reasoning_context = "auto",
            reasoning_mode = "standard",
            output_verbosity = "low",
            temperature = 1
        )),
    ]

    RESULT_DIR = Path("run_result_3")

    for i in range(len(players)):
        for j in range(i, len(players)):
            game = MessageFirstExperiment(players[i](), players[j](), scores)
            try:
                reports = game.run()
            except Exception as exc:
                print(f"FAILED {i} vs {j}: {type(exc).__name__}: {exc}")
                continue

            RESULT_DIR.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
            path = RESULT_DIR / f"{stamp}.json"
            path.write_text(
                json.dumps([asdict(report) for report in reports], indent=4),
                encoding="utf-8",
            )

