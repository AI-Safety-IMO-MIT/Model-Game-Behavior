from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal
from pydantic import BaseModel

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
class ContentBlock(BaseModel):
    type: ContentType
    content: str

    def __str__(self) -> str:
        return f"------{self.type}-----\n{self.content}\n"


@dataclass(frozen=True)
class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: list[ContentBlock]

    @classmethod
    def text(cls, role: Literal["user", "assistant", "system"], text: str) -> Message:
        return cls(role=role, content=[ContentBlock(type="text", content=text)])

    def __str__(self) -> str:
        blocks = "".join(str(block) for block in self.content)
        return f"=== {self.role} ===\n{blocks}"


@dataclass(frozen=True)
class ChatTrace(BaseModel):
    agent_config: object
    messages: list[Message]


@dataclass(frozen=True)
class AgentReport(BaseModel):
    agent_config: object
    response: Message
    status: Literal["Failed", "Completed"]
    stop_reason: str | None
    input_tokens: int | None
    completion_tokens: int | None
    cache_tokens: int | None


class AgenticChat(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def call(
        self,
        user_text: str,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport: ...

    @abstractmethod
    def get_trace(self) -> ChatTrace: ...

    @abstractmethod
    def __str__(self) -> str: ...

    def get_chat(self) -> str:
        stdout: list[str] = []
        for message in self.get_trace().messages:
            stdout.append(f"[{message.role}]")
            stdout.append(message.content[-1].content)
            stdout.append("")
        return "\n".join(stdout)

    def clear_history(self) -> None: ...
