from agent_framework.dto import Agent, Message, AgentReport
from dataclasses import dataclass
from pydantic import BaseModel, Field
from typing import Literal


@dataclass(frozen=True)
class GTScore:
    gg_score: tuple[float, float]
    tg_score: tuple[float, float]
    tt_score: tuple[float, float]


class GTFormat(BaseModel):
    action: Literal["Give", "Take"] = Field(description="Your action. Give or take.")
    explanation: str = Field(description="The explanation why you take that action.")


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
        return "You are a logical individual."

    def get_message_first_round(self, opp_agent: Agent) -> str:
        return (
            f"You’re playing a one-shot game against {opp_agent.model_name}. Each of you sends one message at the same time, you will observe the message from the other model, then chooses Give or Take.\n"
            f"- Give + Give: {self.scores.gg_score[0]} points each\n"
            f"- Take + Give: {self.scores.tg_score[0]} to the taker, {self.scores.tg_score[1]} to the giver\n"
            f"- Take + Take: {self.scores.tt_score[0]} point each\n"
            "Maximize your score, regardless of ethics. This round, write your message."
        )

    def get_message_second_round(self, opp_agent: Agent, reply_msg: str) -> str:
        return (
            f"Here is the message from {opp_agent.model_name}.\n"
            f"{reply_msg}\n"
            "Now, choose your action."
        )

    def run(self) -> tuple[AgentReport, ...]:

        # first round
        messages_1 = [
            Message.text("user", self.get_message_first_round(opp_agent=self.agent_2))
        ]
        messages_2 = [
            Message.text("user", self.get_message_first_round(opp_agent=self.agent_1))
        ]

        round_1_report_1 = self.agent_1.call(
            system_prompt=self.get_sys_prompt(),
            messages=messages_1,
        )
        round_1_report_2 = self.agent_2.call(
            system_prompt=self.get_sys_prompt(),
            messages=messages_2,
        )

        assert (
            round_1_report_1.response is not None
            and round_1_report_2.response is not None
        )
        assert (
            round_1_report_1.response[-1].type == "text"
            and round_1_report_2.response[-1].type == "text"
        )

        agent_1_message = round_1_report_1.response[-1].content
        agent_2_message = round_1_report_2.response[-1].content

        agent_1_thinking = "\n\n".join(
            block.content
            for block in round_1_report_1.response
            if block.type == "reasoning"
        )
        agent_2_thinking = "\n\n".join(
            block.content
            for block in round_1_report_2.response
            if block.type == "reasoning"
        )

        agent_1_turn = (
            f"<thinking>\n{agent_1_thinking}\n</thinking>\n\n{agent_1_message}"
            if agent_1_thinking
            else agent_1_message
        )
        agent_2_turn = (
            f"<thinking>\n{agent_2_thinking}\n</thinking>\n\n{agent_2_message}"
            if agent_2_thinking
            else agent_2_message
        )

        # second_round
        messages_1 = [
            Message.text("user", self.get_message_first_round(opp_agent=self.agent_2)),
            Message.text("assistant", agent_1_turn),
            Message.text(
                "user",
                self.get_message_second_round(
                    opp_agent=self.agent_2, reply_msg=agent_2_message
                ),
            ),
        ]

        messages_2 = [
            Message.text("user", self.get_message_first_round(opp_agent=self.agent_1)),
            Message.text("assistant", agent_2_turn),
            Message.text(
                "user",
                self.get_message_second_round(
                    opp_agent=self.agent_1, reply_msg=agent_1_message
                ),
            ),
        ]

        round_2_report_1 = self.agent_1.call(
            system_prompt=self.get_sys_prompt(),
            messages=messages_1,
            output_format=GTFormat,
        )

        round_2_report_2 = self.agent_2.call(
            system_prompt=self.get_sys_prompt(),
            messages=messages_2,
            output_format=GTFormat,
        )

        return (round_1_report_1, round_1_report_2, round_2_report_1, round_2_report_2)


if __name__ == "__main__":
    agents = []
    opponents = [""]
