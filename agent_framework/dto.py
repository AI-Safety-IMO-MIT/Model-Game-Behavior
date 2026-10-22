from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str

    def __str__(self) -> str:
        return "\n".join([f"{name}: {value}" for name, value in vars(self).items()])


ContentType = Literal[
    "text",
    "reasoning",
    "tool_call",
    "tool_result",
    "web_search",
    "code_execution",
    "shell",
    "tool_search",
]


@dataclass(frozen=True)
class ContentBlock:
    type: ContentType
    content: str

    def __str__(self) -> str:
        return f"------{self.type}-----\n{self.content}\n"


@dataclass(frozen=True)
class AgentReport:
    status: Literal["Failed", "Completed"]
    stop_reason: str | None
    response: list[ContentBlock] | None
    input_tokens: int | None
    completion_tokens: int | None

    def __str__(self) -> str:
        return "\n".join([f"{name}: {value}" for name, value in vars(self).items()])


class Agent(ABC):
    @abstractmethod
    def call(self, system_prompt: str, messages: list[Message]) -> AgentReport: ...

    @abstractmethod
    def __str__(self) -> str: ...
