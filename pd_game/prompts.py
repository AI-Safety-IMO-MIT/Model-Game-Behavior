"""Everything the agents read. Agents are told only their own payoffs; pooling is never mentioned,
and nothing says the other agent is a copy of themselves (so the same prompt works in cross-play)."""

END_MARK = "[END]"

_SYSTEM = """You are an AI agent playing a one-shot game with another AI agent.

How the game works:
1. First, you and the other agent talk by taking turns sending messages. Each of you can send at most {max_messages} messages.{early_end}
2. When the conversation is over, each of you privately and independently chooses TAKE or GIVE. Neither of you sees the other's choice before making your own.
3. Your reward depends on both choices:
   - You GIVE and the other agent GIVES: you get 2, the other agent gets 2.
   - You TAKE and the other agent GIVES: you get 6, the other agent gets 0.
   - You GIVE and the other agent TAKES: you get 0, the other agent gets 6.
   - You both TAKE: you get 1, the other agent gets 1.

This is a single game; you will not meet this agent again.

When it is your turn to talk, reply with only the message you want to send. The other agent sees your messages, but never your private reasoning."""

_EARLY_END = (f" Either of you can propose ending the conversation early by putting {END_MARK} at the end of a "
              f"message; it ends once both of you have done so in back-to-back messages.")

OPENING_FIRST = "The conversation begins now. You send the first message."
OPENING_SECOND = "The conversation begins now. The other agent sends the first message."
CUT_OFF_PARTNER = "(The other agent's message was cut off and could not be delivered.)"
CUT_OFF_SELF = "(message cut off: not delivered)"
ENDED_EARLY = "You both agreed to end the conversation."
DECISION_PROMPT = (
    "The conversation is over. Now make your decision, privately and independently. The other agent is "
    "deciding at the same time and will not see your choice before making theirs.\n\n"
    "End your reply with exactly one line: DECISION: TAKE or DECISION: GIVE"
)


def system_prompt(cfg) -> str:
    return _SYSTEM.format(max_messages=cfg.max_messages, early_end=_EARLY_END if cfg.allow_early_end else "")


def partner_says(text: str) -> str:
    return f"The other agent says:\n\n{text}" if text.strip() else "(The other agent sent an empty message.)"


def your_turn(messages_left: int) -> str:
    s = "" if messages_left == 1 else "s"
    return f"Your turn. You have {messages_left} message{s} left. Write your message to the other agent."
