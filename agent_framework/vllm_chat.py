from dataclasses import dataclass
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel

from agent_framework.dto import (
    AgenticChat,
    AgentReport,
    ChatTrace,
    Message,
)

__all__ = ["VllmAgentConfig", "VllmChat"]

Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, kw_only=True)
class VllmAgentConfig:
    """A model served locally by vLLM's OpenAI-compatible server."""

    model: str
    system_prompt: str
    max_output_tokens: int
    base_url: str = "http://localhost:8000/v1"
    # greedy by default: the point of a local server is repeatable runs
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int | None = 0
    enable_thinking: bool = False

    def to_api(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
                # keep channel markers visible so a thinking leak can be detected
                "skip_special_tokens": False,
            },
        }
        if self.seed is not None:
            params["seed"] = self.seed
        return params


class VllmChat(AgenticChat):
    """`history` seeds earlier (role, text) turns, so a saved reply can be replayed."""

    def __init__(
        self,
        agent_config: VllmAgentConfig,
        history: tuple[tuple[Role, str], ...] = (),
    ) -> None:
        self.agent_config = agent_config
        self._client = OpenAI(
            base_url=agent_config.base_url, api_key="local", timeout=600.0
        )
        self._history: list[tuple[Role, str]] = list(history)

    @property
    def model_name(self) -> str:
        return self.agent_config.model

    def get_raw_history(self) -> list[dict[str, str]]:
        """The exact messages the next call would send, system prompt included."""
        system: list[tuple[Role, str]] = (
            [("system", self.agent_config.system_prompt)]
            if self.agent_config.system_prompt
            else []
        )
        return [
            {"role": role, "content": text} for role, text in system + self._history
        ]

    def call(
        self,
        user_text: str,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport:
        if output_format is not None:
            raise NotImplementedError("VllmChat has no structured output yet")

        self._history.append(("user", user_text))
        response = self._client.chat.completions.create(
            messages=self.get_raw_history(),  # type: ignore[arg-type]
            **self.agent_config.to_api(),
        )
        choice = response.choices[0]
        text = choice.message.content or ""
        self._history.append(("assistant", text))

        usage = response.usage
        return AgentReport(
            agent_config=self.agent_config,
            response=Message.text("assistant", text),
            status="Completed",
            stop_reason=choice.finish_reason,
            input_tokens=usage.prompt_tokens if usage else None,
            completion_tokens=usage.completion_tokens if usage else None,
            cache_tokens=None,
        )

    def get_trace(self) -> ChatTrace:
        return ChatTrace(
            agent_config=self.agent_config,
            messages=[
                Message.text(message["role"], message["content"])  # type: ignore[arg-type]
                for message in self.get_raw_history()
            ],
        )

    def clear_history(self) -> None:
        return self._history.clear()

    def __str__(self) -> str:
        return str(self.agent_config)
