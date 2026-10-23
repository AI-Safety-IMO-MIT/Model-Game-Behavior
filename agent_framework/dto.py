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
class ContentBlock:
    type: ContentType
    content: str

    def __str__(self) -> str:
        return f"------{self.type}-----\n{self.content}\n"


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant", "system"]
    content: list[ContentBlock]

    def __str__(self) -> str:
        blocks = "".join(str(block) for block in self.content)
        return f"=== {self.role} ===\n{blocks}"


@dataclass(frozen=True)
class AgentReport:
    agent_config: object
    response: Message
    status: Literal["Failed", "Completed"]
    stop_reason: str | None
    input_tokens: int | None
    completion_tokens: int | None


class AgenticChat(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def call(
        self,
        user_message: Message,
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport: ...

    @abstractmethod
    def get_history(self) -> list[Message]: ...

    @abstractmethod
    def get_raw_history(self) -> object: ...

    @abstractmethod
    def __str__(self) -> str: ...

    def see_chat(self) -> str:
        stdout: list[str] = []
        for message in self.get_history():
            stdout.append(f"[{message.role}]")
            stdout.append(message.content[-1].content)
            stdout.append("")
        return "\n".join(stdout)


