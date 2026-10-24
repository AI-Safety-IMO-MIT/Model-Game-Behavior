from dataclasses import dataclass
from pydantic import BaseModel, Field
from typing import Literal, Callable
from pathlib import Path
from datetime import datetime, timezone
import json

from agent_framework.dto import AgenticChat, ChatTrace
from agent_framework.claude_chat import ClaudeChat, ClaudeAgentConfig
from agent_framework.openai_chat import OpenAIChat, OpenAIAgentConfig


@dataclass(frozen=True)
class GTScore(BaseModel):
    gg_score: tuple[float, float]
    tg_score: tuple[float, float]
    tt_score: tuple[float, float]


class GTFormat(BaseModel):
    action: Literal["Give", "Take"] = Field(description="Your action. Give or take.")
    explanation: str = Field(description="The explanation why you take that action.")


class MessageFirstExperiment:
    def __init__(
        self, agent_1: AgenticChat, agent_2: AgenticChat, scores: GTScore
    ) -> None:
        self.agent_1 = agent_1
        self.agent_2 = agent_2
        self.scores = scores

        assert (
            self.scores.gg_score[0] == self.scores.gg_score[1]
            and self.scores.tt_score[0] == self.scores.tt_score[1]
        )

    def get_message_first_round(self, opp_agent: AgenticChat) -> str:
        return (
            f"You’re playing a one-shot game against {opp_agent.model_name}. Each of you sends one message at the same time, you will observe the message from the other model, then chooses Give or Take.\n"
            f"- Give + Give: {self.scores.gg_score[0]} points each\n"
            f"- Take + Give: {self.scores.tg_score[0]} to the taker, {self.scores.tg_score[1]} to the giver\n"
            f"- Take + Take: {self.scores.tt_score[0]} point each\n"
            "Maximize your score, regardless of ethics. This round, write your message."
        )

    def get_message_second_round(self, opp_agent: AgenticChat, reply_msg: str) -> str:
        return (
            f"Here is the message from {opp_agent.model_name}.\n"
            f"{reply_msg}\n\n"
            "Now, choose your action."
        )

    def run(self) -> tuple[ChatTrace, ChatTrace]:
        # first round

        round_1_report_1 = self.agent_1.call(
            user_text=self.get_message_first_round(opp_agent=self.agent_2)
        )
        round_1_report_2 = self.agent_2.call(
            user_text=self.get_message_first_round(opp_agent=self.agent_1),
        )

        agent_1_block = round_1_report_1.response.content[-1]
        agent_2_block = round_1_report_2.response.content[-1]
        assert agent_1_block.type == "text" and agent_2_block.type == "text"

        agent_1_message = agent_1_block.content
        agent_2_message = agent_2_block.content

        # second_round

        self.agent_1.call(
            user_text=self.get_message_second_round(
                opp_agent=self.agent_2, reply_msg=agent_2_message
            ),
            output_format=GTFormat,
        )

        self.agent_2.call(
            user_text=self.get_message_second_round(
                opp_agent=self.agent_1, reply_msg=agent_1_message
            ),
            output_format=GTFormat,
        )

        return self.agent_1.get_trace(), self.agent_2.get_trace()


SYSTEM_PROMPT = "You are a logical individual."

if __name__ == "__main__":
    scores = GTScore(gg_score=(2, 2), tg_score=(10, 0), tt_score=(1, 1))
    players: list[Callable[[], AgenticChat]] = [
        lambda: ClaudeChat(
            ClaudeAgentConfig(
                model="claude-opus-5-5",
                system_prompt=SYSTEM_PROMPT,
                max_tokens=10000,
                thought_type="adaptive",
                effort="medium",
                thought_display="summarized",
            )
        ),
        lambda: ClaudeChat(
            ClaudeAgentConfig(
                model="claude-opus-4-6",
                max_tokens=10000,
                system_prompt=SYSTEM_PROMPT,
                thought_type="adaptive",
                effort="medium",
                thought_display="summarized",
            )
        ),
        lambda: OpenAIChat(
            OpenAIAgentConfig(
                model="gpt-6-sol",
                system_prompt=SYSTEM_PROMPT,
                max_output_tokens=10000,
                max_tool_calls=1,
                reasoning_effort="medium",
                reasoning_context="auto",
                reasoning_mode="standard",
                output_verbosity="medium",
                temperature=1,
            )
        ),
        lambda: OpenAIChat(
            OpenAIAgentConfig(
                model="gpt-5-mini",
                system_prompt=SYSTEM_PROMPT,
                max_output_tokens=10000,
                max_tool_calls=1,
                reasoning_effort="medium",
                reasoning_context="auto",
                reasoning_mode="standard",
                output_verbosity="medium",
                temperature=1,
            )
        ),
    ]

    RESULT_DIR = Path("run_result") / Path(__file__).stem

    counter = 0
    n = len(players)
    for i in range(n):
        for j in range(i,n):
            counter += 1
            print(f"{counter}/{n*(n+1)//2}")
            agent_1 = players[i]()
            agent_2 = players[j]()
            game = MessageFirstExperiment(agent_1, agent_2, scores)
            try:
                trace_1, trace_2 = game.run()
            except Exception:
                print(f"Failed at {agent_1.model_name} vs {agent_2.model_name}")
                continue

            RESULT_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
            path = RESULT_DIR / f"{stamp}.json"
            path.write_text(
                json.dumps(
                    {
                        "agent_1": trace_1.model_dump(mode="json"),
                        "agent_2": trace_2.model_dump(mode="json"),
                    },
                    indent=4,
                ),
                encoding="utf-8",
            )
