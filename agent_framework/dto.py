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
    # Signature used for thinking block.
    signature: str | None = None

    def __str__(self) -> str:
        return f"------{self.type}-----\n{self.content}\n"


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: list[ContentBlock]

    @classmethod
    def text(cls, role: Literal["user", "assistant"], text: str) -> "Message":
        return cls(role=role, content=[ContentBlock(type="text", content=text)])

    def __str__(self) -> str:
        blocks = "".join(str(block) for block in self.content)
        return f"=== {self.role} ===\n{blocks}"


@dataclass(frozen=True)
class InputConfig:
    agent_config: object
    system_prompt: str
    messages: list[Message]
    output_format: type[BaseModel] | None = None

    def __str__(self) -> str:
        return "\n".join([f"{name}: {value}" for name, value in vars(self).items()])


@dataclass(frozen=True)
class AgentReport:
    input_config: InputConfig
    status: Literal["Failed", "Completed"]
    stop_reason: str | None
    response: list[ContentBlock] | None
    input_tokens: int | None
    completion_tokens: int | None

    def __str__(self) -> str:
        return "\n".join([f"{name}: {value}" for name, value in vars(self).items()])


class Agent(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        messages: list[Message],
        output_format: type[BaseModel] | None = None,
    ) -> AgentReport: ...

    @abstractmethod
    def __str__(self) -> str: ...
