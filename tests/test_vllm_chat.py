import pytest

from agent_framework.vllm_chat import VllmAgentConfig, VllmChat


def make_config() -> VllmAgentConfig:
    return VllmAgentConfig(
        model="gemma-4-31b", system_prompt="Be brief.", max_output_tokens=50
    )


def test_vllm_defaults_are_greedy_with_thinking_off():
    params = make_config().to_api()

    assert params["temperature"] == 0
    assert params["top_p"] == 1
    assert params["seed"] == 0
    assert params["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False


def test_vllm_history_is_replayed_after_system_prompt():
    agent = VllmChat(make_config(), history=(("user", "hi"), ("assistant", "hello")))

    assert agent.get_raw_history() == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_vllm_clear_history_keeps_system_prompt():
    agent = VllmChat(make_config(), history=(("user", "hi"),))
    agent.clear_history()

    assert [message["role"] for message in agent.get_raw_history()] == ["system"]


@pytest.mark.live
def test_vllm_call_against_local_server():
    agent = VllmChat(make_config())
    report = agent.call(user_text="Reply with the single word: ok")

    assert report.status == "Completed"
    assert report.response.content[-1].content
