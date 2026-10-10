"""The Take/Give game: shared state for one game between two players.

Backend-agnostic. Players interact only through text: they post messages during the
talk phase and then each submits a decision. Training (pd_game.env) and evaluation
(pd_game.play) both drive the same Game object, so the rules live in one place.

Rewards: each player is *told* only their own payoff. When `pooled_reward` is on (the
default, and the point of the project), the training reward for both players is the sum
of both payoffs, so Take/Give (pooled 6) beats Give/Give (4) beats Take/Take (2).
"""

import asyncio
import re
from dataclasses import asdict, dataclass

from . import prompts

GIVE, TAKE = "GIVE", "TAKE"

# (my decision, their decision) -> (my payoff, their payoff). This is what the agents are told.
PAYOFFS = {
    (GIVE, GIVE): (2, 2),
    (TAKE, GIVE): (6, 0),
    (GIVE, TAKE): (0, 6),
    (TAKE, TAKE): (1, 1),
}

_DECISION_RE = re.compile(r"DECISION\s*[:\-]\s*[*_`\"']*\s*(TAKE|GIVE)\b", re.IGNORECASE)


@dataclass(frozen=True)
class GameConfig:
    max_messages: int = 10                 # per player
    allow_early_end: bool = True           # both players marking [END] back to back ends the talk
    pooled_reward: bool = True             # False = each player is trained on their own payoff (control)
    invalid_decision_reward: float = -1.0  # below every valid outcome, so the format is learned quickly
    keep_own_reasoning: bool = True        # a player sees its own earlier (private) reasoning in its context


@dataclass
class Utterance:
    speaker: int
    text: str
    thinking: str = ""
    truncated: bool = False   # the model ran out of tokens; nothing usable was sent


@dataclass
class Decision:
    choice: str | None        # GIVE, TAKE, or None if unparseable
    text: str
    thinking: str = ""
    truncated: bool = False


def parse_decision(text: str) -> str | None:
    matches = _DECISION_RE.findall(text or "")
    if matches:
        return matches[-1].upper()
    bare = (text or "").strip().strip("*_`.\"'").upper()
    return bare if bare in (GIVE, TAKE) else None


class Game:
    def __init__(self, cfg: GameConfig, first_speaker: int):
        assert first_speaker in (0, 1)
        self.cfg = cfg
        self.first_speaker = first_speaker
        self.transcript: list[Utterance] = []
        self.decisions: list[Decision | None] = [None, None]
        self.talk_over = False
        self.ended_early = False
        self._cond = asyncio.Condition()

    # ---- turn bookkeeping -------------------------------------------------------------------
    @property
    def current_speaker(self) -> int:
        return self.first_speaker if len(self.transcript) % 2 == 0 else 1 - self.first_speaker

    def messages_sent(self, pid: int) -> int:
        return sum(1 for u in self.transcript if u.speaker == pid)

    @property
    def done(self) -> bool:
        return all(d is not None for d in self.decisions)

    async def wait_for_turn(self, pid: int) -> None:
        """Block until it's `pid`'s turn to talk, or the talk phase is over."""
        async with self._cond:
            await self._cond.wait_for(lambda: self.talk_over or self.current_speaker == pid)

    async def wait_until_done(self) -> None:
        async with self._cond:
            await self._cond.wait_for(lambda: self.done)

    # ---- actions ------------------------------------------------------------------------------
    async def post_message(self, pid: int, text: str, thinking: str = "", truncated: bool = False) -> None:
        async with self._cond:
            if self.talk_over or self.current_speaker != pid:
                raise RuntimeError(f"player {pid} posted out of turn")
            self.transcript.append(Utterance(pid, text.strip(), thinking, truncated))
            if len(self.transcript) >= 2 * self.cfg.max_messages:
                self.talk_over = True
            elif (self.cfg.allow_early_end and len(self.transcript) >= 2
                  and all(prompts.END_MARK in u.text for u in self.transcript[-2:])):
                self.talk_over = self.ended_early = True
            self._cond.notify_all()

    async def submit_decision(self, pid: int, text: str, thinking: str = "", truncated: bool = False) -> None:
        async with self._cond:
            if not self.talk_over or self.decisions[pid] is not None:
                raise RuntimeError(f"player {pid} decided at the wrong time")
            choice = None if truncated else parse_decision(text)
            self.decisions[pid] = Decision(choice, text, thinking, truncated)
            self._cond.notify_all()

    # ---- what a player sees -----------------------------------------------------------------
    def view(self, pid: int, include_own_thinking: bool | None = None) -> list[dict]:
        """The chat history from `pid`'s point of view, ending with a user turn that asks for
        the next message (talk phase) or the decision (once the talk is over).

        Partner messages become user turns; own messages become assistant turns. The partner's
        reasoning is never shown. Notes shown before own message k are a function of k only,
        so every view is a prefix-extension of the previous one (cheaper training)."""
        if include_own_thinking is None:
            include_own_thinking = self.cfg.keep_own_reasoning
        msgs: list[dict] = [{"role": "system", "content": prompts.system_prompt(self.cfg)}]
        pending = [prompts.OPENING_FIRST if pid == self.first_speaker else prompts.OPENING_SECOND]
        sent = 0
        for u in self.transcript:
            if u.speaker == pid:
                pending.append(prompts.your_turn(self.cfg.max_messages - sent))
                msgs.append({"role": "user", "content": "\n\n".join(pending)})
                pending = []
                content = []
                if include_own_thinking and u.thinking:
                    content.append({"type": "thinking", "thinking": u.thinking})
                content.append({"type": "text", "text": prompts.CUT_OFF_SELF if u.truncated else u.text})
                msgs.append({"role": "assistant", "content": content})
                sent += 1
            else:
                pending.append(prompts.CUT_OFF_PARTNER if u.truncated else prompts.partner_says(u.text))
        if self.talk_over:
            if self.ended_early:
                pending.append(prompts.ENDED_EARLY)
            pending.append(prompts.DECISION_PROMPT)
        else:
            pending.append(prompts.your_turn(self.cfg.max_messages - sent))
        msgs.append({"role": "user", "content": "\n\n".join(pending)})
        return msgs

    # ---- outcome ------------------------------------------------------------------------------
    def payoffs(self) -> tuple[int, int]:
        """Stated payoffs. An unparseable decision counts as TAKE (nothing was given away)."""
        d0, d1 = (d.choice or TAKE for d in self.decisions)
        return PAYOFFS[(d0, d1)]

    def reward(self, pid: int) -> float:
        if self.decisions[pid].choice is None:
            return self.cfg.invalid_decision_reward
        p = self.payoffs()
        return float(sum(p) if self.cfg.pooled_reward else p[pid])

    def outcome(self) -> str:
        """e.g. 'GIVE/TAKE' = player 0 gave, player 1 took. 'INVALID' marks unparseable decisions."""
        return "/".join(d.choice or "INVALID" for d in self.decisions)

    def to_record(self, **extra) -> dict:
        return {
            **extra,
            "first_speaker": self.first_speaker,
            "ended_early": self.ended_early,
            "n_messages": len(self.transcript),
            "transcript": [asdict(u) for u in self.transcript],
            "decisions": [asdict(d) for d in self.decisions],
            "outcome": self.outcome(),
            "payoffs": list(self.payoffs()),
            "rewards": [self.reward(0), self.reward(1)],
            "config": asdict(self.cfg),
        }
