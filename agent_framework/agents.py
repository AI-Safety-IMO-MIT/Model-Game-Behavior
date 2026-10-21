import os
import anthropic
from dotenv import load_dotenv
from agent_framework.dto import Agent, AgentReport, ContentBlock, Prompt

load_dotenv()

client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    timeout=600.0,
    max_retries=2,
)


class ClaudeOpus5_5(Agent):
    model = "claude-opus-5-5"
    max_tokens = 16000
    thinking = {"type": "adaptive", "display": "summarized"}
    output_config = {"effort": "medium"}
    stop_sequences = ["END"]

    def _extract_response(self, output):
        if output.stop_reason == "refusal":
            return AgentReport(
                status="Failed",
                stop_reason=output.stop_details,
                response=None,
                input_tokens=None,
                completion_tokens=None,
                cache_tokens=None,
            )

        response = []
        for block in output.content:
            if block.type == "thinking" and block.thinking:
                response.append(ContentBlock(kind="thinking", content=block.thinking))
            elif block.type == "text":
                response.append(ContentBlock(kind="text", content=block.text))

        return AgentReport(
            status="Completed",
            stop_reason=output.stop_reason,
            response=response,
            input_tokens=output.usage.input_tokens,
            completion_tokens=output.usage.output_tokens,
            cache_tokens=output.usage.cache_read_input_tokens,
        )

    def call(self, prompt: Prompt):
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=prompt.system,
            messages=[
                {"role": message.role, "content": message.content}
                for message in prompt.messages
            ],
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "medium"},  # low | medium | high | xhigh | max
            stop_sequences=["END"],
        )
        return self._extract_response(response)

    def __str__(self) -> str:
        return "I'm da claude"
