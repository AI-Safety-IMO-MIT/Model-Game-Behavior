from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class Prompt:
    system: str
    messages: list[Message]


@dataclass(frozen=True)
class ContentBlock:
    type: Literal["thinking", "text"]
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
    cache_tokens: int | None


class Agent(ABC):
    @abstractmethod
    def call(self, prompt: Prompt) -> AgentReport: ...

    @abstractmethod
    def __str__(self) -> str: ...
