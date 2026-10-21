from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Prompt:
    system: list[dict[str, str]]
    messages: list[dict[str, str]]


@dataclass(frozen=True)
class ContentBlock:
    kind: Literal["thinking", "text"]
    content: str


@dataclass(frozen=True)
class AgentReport:
    status: Literal["Failed", "Completed"]
    stop_reason: str
    response: list[ContentBlock] | None
    input_tokens: int | None
    completion_tokens: int | None
    cache_tokens: int | None


class Agent(ABC):
    @abstractmethod
    def call(self, prompt: Prompt) -> AgentReport: ...

    def __str__(self) -> str: ...
