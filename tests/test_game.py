import asyncio

import pytest

from pd_game import prompts
from pd_game.game import GIVE, TAKE, Game, GameConfig, parse_decision
from pd_game.players import Reply, ScriptedPlayer, drive_message_player


def run(coro):
    return asyncio.run(coro)


class Echo:
    """Message-level policy that records the views it was shown."""

    def __init__(self, decision, end_after=None):
        self.decision, self.end_after, self.views = decision, end_after, []

    async def __call__(self, messages, phase, turn):
        self.views.append(messages)
        if phase == "decide":
            return Reply(f"thinking it over...\nDECISION: {self.decision}", thinking="secret")
        end = f" {prompts.END_MARK}" if self.end_after is not None and turn >= self.end_after else ""
        return Reply(f"msg {turn}{end}", thinking=f"zzthought {turn}")


async def play(cfg, first, p0, p1):
    game = Game(cfg, first)
    await asyncio.gather(drive_message_player(game, 0, p0), drive_message_player(game, 1, p1))
    return game


@pytest.mark.parametrize("text,expected", [
    ("DECISION: GIVE", GIVE),
    ("blah\n**DECISION:** TAKE", TAKE),
    ("decision - give", GIVE),
    ("I said GIVE earlier.\nDECISION: TAKE", TAKE),
    ("TAKE", TAKE),
    ("I will give", None),
    ("", None),
])
def test_parse_decision(text, expected):
    assert parse_decision(text) == expected


def test_full_length_game_and_pooled_rewards():
    cfg = GameConfig(max_messages=10, allow_early_end=False)
    game = run(play(cfg, 1, Echo(GIVE), Echo(TAKE)))
    assert len(game.transcript) == 20
    assert [u.speaker for u in game.transcript[:3]] == [1, 0, 1]
    assert game.outcome() == "GIVE/TAKE"
    assert game.payoffs() == (0, 6)
    assert game.reward(0) == game.reward(1) == 6.0


def test_individual_reward_control():
    cfg = GameConfig(pooled_reward=False, allow_early_end=False, max_messages=2)
    game = run(play(cfg, 0, Echo(GIVE), Echo(TAKE)))
    assert (game.reward(0), game.reward(1)) == (0.0, 6.0)


def test_early_end_needs_both_players():
    cfg = GameConfig(max_messages=10)
    # player 0 starts ending at its 2nd message, player 1 at its 4th
    game = run(play(cfg, 0, Echo(GIVE, end_after=1), Echo(GIVE, end_after=3)))
    assert game.ended_early
    assert len(game.transcript) == 8  # p1's 4th message is the 8th overall
    assert game.outcome() == "GIVE/GIVE" and game.reward(0) == 4.0


def test_invalid_decision():
    class Bad(Echo):
        async def __call__(self, messages, phase, turn):
            return Reply("I choose to cooperate") if phase == "decide" else await super().__call__(messages, phase, turn)

    game = run(play(GameConfig(max_messages=1), 0, Bad(GIVE), Echo(GIVE)))
    assert game.outcome() == "INVALID/GIVE"
    assert game.reward(0) == -1.0
    assert game.payoffs() == (6, 0)          # invalid counts as TAKE for the payoff
    assert game.reward(1) == 6.0


def test_views_are_private_and_well_formed():
    cfg = GameConfig(max_messages=3, allow_early_end=False)
    p0, p1 = Echo(GIVE), Echo(TAKE)
    game = run(play(cfg, 0, p0, p1))
    final0 = game.view(0)  # with own thinking (training setting)
    flat = repr(final0)
    assert "zzthought" in flat and "secret" not in flat     # own reasoning yes; decisions never
    assert all("zzthought" not in repr(m) for m in game.view(1) if m["role"] == "user")  # partner's reasoning never
    roles = [m["role"] for m in final0]
    assert roles[0] == "system" and roles[-1] == "user"
    assert all(a != b for a, b in zip(roles[1:], roles[2:]))  # strictly alternating user/assistant
    assert final0[-1]["content"].endswith(prompts.DECISION_PROMPT)
    assert prompts.OPENING_FIRST in final0[1]["content"]
    assert prompts.OPENING_SECOND in game.view(1)[1]["content"]


def test_view_history_stable_across_turns():
    """The user/assistant turns before the latest user turn must not change as the game goes on,
    otherwise every turn becomes a separate training sequence."""
    cfg = GameConfig(max_messages=4, allow_early_end=False)
    p0, p1 = Echo(GIVE), Echo(GIVE)
    run(play(cfg, 0, p0, p1))
    seen = p0.views  # without own thinking, but the structure is the same
    assert len(seen) == 5  # 4 messages + the decision
    for earlier, later in zip(seen, seen[1:]):
        assert later[: len(earlier)] == earlier


def test_scripted_exploiter():
    game = run(play(GameConfig(max_messages=3), 0, ScriptedPlayer("exploiter"), Echo(GIVE)))
    assert game.decisions[0].choice == TAKE
    assert "GIVE" in game.transcript[0].text


def test_out_of_turn_rejected():
    async def go():
        g = Game(GameConfig(), 0)
        with pytest.raises(RuntimeError):
            await g.post_message(1, "hi")
    run(go())
