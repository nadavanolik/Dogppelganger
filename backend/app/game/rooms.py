"""Multiplayer rooms, server-authoritative — two game types share one engine.

**Spot the Double** (``"double"``) is a Kahoot-style race: one human, four dogs,
everyone answers the same question inside the same window and scores more for
answering sooner. Players never interact; the clock is the only shared thing.

**Mix & Match** (``"match"``) is the game ProjectPlan 2.10 describes, and the one
with genuine shared state. Each round deals four humans and four dogs. Pairing a
human with a dog *claims that exact combination* for you — live, exclusively, and
visibly. Nobody else can use that combination, though both tiles remain in play
for any other combination. Un-pair and the claim is released. Correctness stays
secret until the round ends, so speed buys you the pairing you believe in rather
than confirmation that you were right (which would reduce the game to brute force).

What both types share, and what makes them honest:

* One ``asyncio`` task per room drives ``lobby -> countdown -> question ->
  reveal -> ... -> over``. Clients never advance the game; they only render what
  the server broadcast. For a match room, ``question`` means "the board is open";
  the phase names are shared so the timer, scoreboard and lobby list don't need
  to know which game they're showing.
* The round closes when *the server* says so — at its own deadline, or early once
  every connected player is done.
* **Contradictions are resolved here, not on the client.** An answer can only be
  given once, and a claim can only be taken once: both checks run with no ``await``
  between the test and the mutation, so on a single-threaded event loop the
  check-and-take is atomic. The loser is told why, individually, and the
  authoritative state is rebroadcast to everyone (ProjectPlan 2.10).
* Scores are computed at the reveal, not on receipt, so nobody learns the answer
  early by watching their own points move.

State is in memory. ``backend/Dockerfile`` runs a single uvicorn worker for
exactly this reason.
"""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from . import board as boards
from . import rounds, store
from .board import Board
from .rounds import Question

log = logging.getLogger(__name__)

Sender = Callable[[str, dict], Awaitable[None]]

# Codes are read aloud and typed on phones, so drop the characters that get
# confused for digits (B/8, I/1, O/0, S/5, Z/2).
CODE_ALPHABET = "ACDEFGHJKLMNPQRTUVWXY"
CODE_LENGTH = 4

GAME_DOUBLE = "double"
GAME_MATCH = "match"
GAME_TYPES = (GAME_DOUBLE, GAME_MATCH)

COUNTDOWN_SECONDS = 3
REVEAL_SECONDS = 5
DEFAULT_ROUNDS = 8
DEFAULT_SECONDS = 15
ROUNDS_CHOICES = range(5, 21)
SECONDS_CHOICES = (10, 15, 20)
OPTIONS_PER_QUESTION = 4

# A board of four pairs takes longer to think about than one four-way question,
# so the match type gets its own scale rather than sharing the short one.
MATCH_SECONDS_CHOICES = (30, 45, 60)
MATCH_DEFAULT_SECONDS = 45
MATCH_DEFAULT_ROUNDS = 5

# Half the value of a pair is for being right and half for committing early —
# the same shape as the double type's scoring, spread over a whole board.
MATCH_BASE_PER_PAIR = 200
MATCH_SPEED_MAX = 300
MATCH_PERFECT_BONUS = 500

# A refresh drops the socket for a moment; don't tear the room down over it.
EMPTY_ROOM_GRACE = 30.0

MAX_PLAYERS = 12


def seconds_choices(game_type: str) -> tuple[int, ...]:
    return MATCH_SECONDS_CHOICES if game_type == GAME_MATCH else SECONDS_CHOICES


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class Member:
    player_id: str
    name: str
    joined_at: float = field(default_factory=time.monotonic)
    connected: bool = True
    score: int = 0
    streak: int = 0
    longest_streak: int = 0
    correct: int = 0
    # Per-round, reset each round:
    answer: int | None = None  # double: the option they picked
    answered_at: float | None = None
    pairs: dict[int, int] = field(default_factory=dict)  # match: human slot -> dog slot
    claimed_at: dict[int, float] = field(default_factory=dict)  # human slot -> when, for the bonus
    submitted: bool = False
    last_award: int = 0
    last_correct: bool | None = None
    last_round_correct: int = 0

    @property
    def done_with_round(self) -> bool:
        """Whether this player still has anything to do in the open round."""
        return self.submitted or self.answer is not None

    def reset_for_question(self) -> None:
        self.answer = None
        self.answered_at = None
        self.pairs = {}
        self.claimed_at = {}
        self.submitted = False
        self.last_award = 0
        self.last_correct = None
        self.last_round_correct = 0

    def reset_for_game(self) -> None:
        self.score = 0
        self.streak = 0
        self.longest_streak = 0
        self.correct = 0
        self.reset_for_question()


@dataclass
class Room:
    id: str
    code: str
    name: str
    host_id: str
    members: dict[str, Member] = field(default_factory=dict)
    game_type: str = GAME_DOUBLE
    phase: str = "lobby"  # lobby | countdown | question | reveal | over
    rounds_total: int = DEFAULT_ROUNDS
    seconds_per_question: int = DEFAULT_SECONDS
    questions: list[Question] = field(default_factory=list)
    q_index: int = -1
    # Match only: the board on the table and who holds which combination.
    board: Board | None = None
    claims: dict[tuple[int, int], str] = field(default_factory=dict)  # (human, dog) -> player id
    ends_at_ms: int | None = None
    task: asyncio.Task | None = None
    all_answered: asyncio.Event = field(default_factory=asyncio.Event)
    empty_since: float | None = None
    created_at: float = field(default_factory=time.monotonic)

    @property
    def current(self) -> Question | None:
        if 0 <= self.q_index < len(self.questions):
            return self.questions[self.q_index]
        return None

    @property
    def is_match(self) -> bool:
        return self.game_type == GAME_MATCH

    @property
    def leaderboard_name(self) -> str:
        """Which board a finished game here belongs on.

        Match points and double points aren't the same currency, so they get
        separate boards rather than being ranked against each other.
        """
        return store.BOARD_MULTIPLAYER_MATCH if self.is_match else store.BOARD_MULTIPLAYER

    @property
    def connected_members(self) -> list[Member]:
        return [m for m in self.members.values() if m.connected]

    def standings(self) -> list[Member]:
        return sorted(
            self.members.values(),
            key=lambda m: (-m.score, -m.correct, m.joined_at),
        )


def _award(remaining_ratio: float, streak: float) -> int:
    """Kahoot-style: half the points for being right, half for being quick."""
    base = 1000 * (0.5 + 0.5 * max(0.0, min(1.0, remaining_ratio)))
    bonus = 100 * min(max(int(streak) - 1, 0), 5)
    return int(round(base / 10) * 10) + bonus


def _pair_award(remaining_ratio: float) -> int:
    """What one correct pairing is worth, given how early it was claimed.

    Only correct pairs score. A wrong one costs nothing beyond the combination it
    wasted and the chance to hold a right one, which is punishment enough — an
    explicit penalty would only discourage committing to a hunch.
    """
    ratio = max(0.0, min(1.0, remaining_ratio))
    return MATCH_BASE_PER_PAIR + int(round(MATCH_SPEED_MAX * ratio / 10) * 10)


class RoomRegistry:
    """Owns every live room and the game loops driving them."""

    def __init__(self, send: Sender) -> None:
        self._send = send
        self.rooms: dict[str, Room] = {}  # room id -> room
        self._by_code: dict[str, str] = {}  # code -> room id
        # Background reaper tasks, held so the event loop can't garbage-collect
        # them while they're still sleeping.
        self._reapers: set[asyncio.Task] = set()

    # ---------------------------------------------------------------- lookup

    def get(self, room_id: str) -> Room | None:
        return self.rooms.get(room_id)

    def by_code(self, code: str) -> Room | None:
        room_id = self._by_code.get(code.strip().upper())
        return self.rooms.get(room_id) if room_id else None

    def open_rooms(self) -> list[Room]:
        """Rooms a stranger could still usefully join, newest first."""
        return sorted(
            (r for r in self.rooms.values() if r.phase in ("lobby", "over")),
            key=lambda r: r.created_at,
            reverse=True,
        )

    def find_room_of(self, player_id: str) -> Room | None:
        for room in self.rooms.values():
            if player_id in room.members:
                return room
        return None

    # ---------------------------------------------------------------- create

    def _new_code(self) -> str:
        for _ in range(100):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self._by_code:
                return code
        raise RuntimeError("could not allocate a free room code")

    def create(
        self, name: str, host_id: str, host_name: str, game_type: str = GAME_DOUBLE
    ) -> Room:
        if game_type not in GAME_TYPES:
            raise ValueError("Pick either Spot the Double or Mix & Match.")
        is_match = game_type == GAME_MATCH
        room = Room(
            id=secrets.token_urlsafe(8),
            code=self._new_code(),
            name=name.strip()[:60] or f"{host_name}'s room",
            host_id=host_id,
            game_type=game_type,
            rounds_total=MATCH_DEFAULT_ROUNDS if is_match else DEFAULT_ROUNDS,
            seconds_per_question=MATCH_DEFAULT_SECONDS if is_match else DEFAULT_SECONDS,
        )
        self.rooms[room.id] = room
        self._by_code[room.code] = room.id
        return room

    def _destroy(self, room: Room) -> None:
        if room.task and not room.task.done():
            room.task.cancel()
        self.rooms.pop(room.id, None)
        self._by_code.pop(room.code, None)

    # ------------------------------------------------------------- messaging

    async def send(self, player_id: str, message: dict) -> None:
        await self._send(player_id, message)

    async def broadcast(self, room: Room, message: dict) -> None:
        await asyncio.gather(
            *(self._send(m.player_id, message) for m in room.connected_members),
            return_exceptions=True,
        )

    async def broadcast_state(self, room: Room) -> None:
        await self.broadcast(room, {"type": "room_state", "payload": self.state(room)})

    def state(self, room: Room) -> dict:
        """The whole client-visible truth about a room. Never includes an answer
        before the reveal — for either game type."""
        question = room.current
        reveal = room.phase in ("reveal", "over")
        playing = room.phase != "lobby"
        return {
            "id": room.id,
            "code": room.code,
            "name": room.name,
            "gameType": room.game_type,
            "phase": room.phase,
            "hostId": room.host_id,
            "roundsTotal": room.rounds_total,
            "secondsPerQuestion": room.seconds_per_question,
            "questionNumber": room.q_index + 1,
            # Exactly one of these is ever populated, decided by `gameType`.
            "question": question.payload() if question and playing else None,
            "answerIndex": question.answer if question and reveal else None,
            "board": room.board.payload() if room.board and playing else None,
            "boardAnswer": room.board.answer_payload() if room.board and reveal else None,
            # Who holds which combination. Public by design: seeing other players
            # commit *is* the game, and it's what they're racing over.
            "claims": [
                {
                    "human": human,
                    "dog": dog,
                    "playerId": player_id,
                    "name": self._member_name(room, player_id),
                }
                for (human, dog), player_id in room.claims.items()
            ],
            "endsAt": room.ends_at_ms,
            "serverNow": now_ms(),
            "players": [
                {
                    "playerId": m.player_id,
                    "name": m.name,
                    "score": m.score,
                    "streak": m.streak,
                    "connected": m.connected,
                    "isHost": m.player_id == room.host_id,
                    # "Has nothing left to do this round", whichever game it is.
                    "answered": m.done_with_round,
                    "submitted": m.submitted,
                    "lastAward": m.last_award,
                    # Correctness is only public once the round is closed.
                    "lastCorrect": m.last_correct if reveal else None,
                    "lastRoundCorrect": m.last_round_correct if reveal else 0,
                }
                for m in room.standings()
            ],
        }

    @staticmethod
    def _member_name(room: Room, player_id: str) -> str:
        member = room.members.get(player_id)
        return member.name if member else "—"

    # ------------------------------------------------------------ membership

    async def join(self, room: Room, player_id: str, name: str) -> Member:
        """Add a player, or reattach one who dropped and came back."""
        member = room.members.get(player_id)
        if member is None:
            if len(room.members) >= MAX_PLAYERS:
                raise ValueError("This room is full.")
            if room.phase not in ("lobby", "over"):
                raise ValueError("That game is already in progress.")
            member = Member(player_id=player_id, name=name)
            room.members[player_id] = member
        else:
            # Reconnect: keep the score, just pick the socket back up.
            member.name = name
            member.connected = True
        room.empty_since = None
        await self.broadcast(
            room,
            {"type": "player_joined", "payload": {"playerId": player_id, "name": name}},
        )
        await self.broadcast_state(room)
        return member

    async def leave(self, room: Room, player_id: str, *, permanent: bool) -> None:
        member = room.members.get(player_id)
        if member is None:
            return
        if permanent:
            # Someone who has left for good must not keep combinations hostage.
            # A dropped socket is different: their seat and their claims are held,
            # because they're probably mid-refresh and the round still ends
            # without them.
            for human_slot in list(member.pairs):
                self._drop(room, member, human_slot)
            room.members.pop(player_id, None)
        else:
            member.connected = False

        # An in-progress round shouldn't wait on someone who just walked out.
        self._check_all_answered(room)

        if member.player_id == room.host_id:
            self._promote_host(room)

        await self.broadcast(
            room,
            {"type": "player_left", "payload": {"playerId": player_id, "name": member.name}},
        )

        if not room.connected_members:
            room.empty_since = time.monotonic()
            reaper = asyncio.create_task(self._reap_if_still_empty(room))
            self._reapers.add(reaper)
            reaper.add_done_callback(self._reapers.discard)
        else:
            await self.broadcast_state(room)

    def _promote_host(self, room: Room) -> None:
        candidates = sorted(room.connected_members, key=lambda m: m.joined_at)
        if candidates:
            room.host_id = candidates[0].player_id

    async def _reap_if_still_empty(self, room: Room) -> None:
        """Close a room nobody came back to — but survive a page refresh."""
        await asyncio.sleep(EMPTY_ROOM_GRACE)
        if room.id in self.rooms and not room.connected_members:
            log.info("closing empty room %s (%s)", room.code, room.name)
            self._destroy(room)

    # -------------------------------------------------------------- settings

    async def set_options(
        self,
        room: Room,
        rounds_total: int | None,
        seconds: int | None,
        game_type: str | None = None,
    ) -> None:
        if room.phase not in ("lobby", "over"):
            raise ValueError("Settings are locked once a game starts.")
        if game_type is not None and game_type != room.game_type:
            if game_type not in GAME_TYPES:
                raise ValueError("Pick either Spot the Double or Mix & Match.")
            room.game_type = game_type
            # The two types keep different clocks, so carrying the old value over
            # would leave a match room with an unplayable 10 seconds a board.
            room.seconds_per_question = (
                MATCH_DEFAULT_SECONDS if room.is_match else DEFAULT_SECONDS
            )
            room.rounds_total = MATCH_DEFAULT_ROUNDS if room.is_match else DEFAULT_ROUNDS
        if rounds_total is not None:
            if rounds_total not in ROUNDS_CHOICES:
                raise ValueError("Rounds must be between 5 and 20.")
            room.rounds_total = rounds_total
        if seconds is not None:
            allowed = seconds_choices(room.game_type)
            if seconds not in allowed:
                raise ValueError(
                    "Seconds per round must be " + " or ".join(str(s) for s in allowed) + "."
                )
            room.seconds_per_question = seconds
        await self.broadcast_state(room)

    # ------------------------------------------------------------- the game

    async def start_game(self, room: Room) -> None:
        if room.phase not in ("lobby", "over"):
            raise ValueError("That game is already running.")
        if not room.connected_members:
            raise ValueError("Nobody is here to play.")
        room.task = asyncio.create_task(self._run_game(room))

    async def back_to_lobby(self, room: Room) -> None:
        if room.phase != "over":
            raise ValueError("Finish the game first.")
        room.phase = "lobby"
        room.q_index = -1
        room.questions = []
        room.board = None
        room.claims.clear()
        room.ends_at_ms = None
        for member in room.members.values():
            member.reset_for_game()
        await self.broadcast_state(room)

    async def _run_game(self, room: Room) -> None:
        try:
            for member in room.members.values():
                member.reset_for_game()
            room.q_index = -1
            room.questions = []
            room.board = None
            room.claims.clear()

            room.phase = "countdown"
            room.ends_at_ms = now_ms() + COUNTDOWN_SECONDS * 1000
            await self.broadcast_state(room)
            await asyncio.sleep(COUNTDOWN_SECONDS)

            if room.is_match:
                await self._run_match(room)
            else:
                await self._run_double(room)
        except asyncio.CancelledError:
            raise
        except Exception:  # a crash here would silently freeze the room
            log.exception("room %s game loop failed", room.code)
            room.phase = "over"
            await self.broadcast(
                room,
                {"type": "error", "payload": {"message": "The game hit a problem and stopped."}},
            )

    async def _run_double(self, room: Room) -> None:
        room.questions = rounds.build_questions(
            room.rounds_total, random.Random(), options_per=OPTIONS_PER_QUESTION
        )
        for index in range(len(room.questions)):
            if not room.connected_members:
                log.info("abandoning game in room %s: everyone left", room.code)
                return
            await self._ask(room, index)
            await self._reveal(room)
        await self._finish(room)

    async def _run_match(self, room: Room) -> None:
        rng = random.Random()
        for index in range(room.rounds_total):
            if not room.connected_members:
                log.info("abandoning game in room %s: everyone left", room.code)
                return
            dealt = boards.build_board(rng)
            if dealt is None:  # the content pool ran dry; end early rather than hang
                log.warning("room %s could not deal a board", room.code)
                break
            await self._open_board(room, index, dealt)
            await self._reveal_board(room)
        await self._finish(room)

    async def _ask(self, room: Room, index: int) -> None:
        room.q_index = index
        room.phase = "question"
        room.all_answered.clear()
        for member in room.members.values():
            member.reset_for_question()

        duration = room.seconds_per_question
        room.ends_at_ms = now_ms() + duration * 1000
        await self.broadcast_state(room)

        # Close at the deadline, or as soon as everyone still here has locked in.
        try:
            await asyncio.wait_for(room.all_answered.wait(), timeout=duration)
        except asyncio.TimeoutError:
            pass

    async def _reveal(self, room: Room) -> None:
        question = room.current
        if question is None:
            return
        room.phase = "reveal"
        duration = room.seconds_per_question

        for member in room.members.values():
            if member.answer is None:
                member.last_correct = None if not member.connected else False
                member.streak = 0
                continue
            if member.answer == question.answer:
                remaining = 0.0
                if member.answered_at is not None and room.ends_at_ms is not None:
                    remaining = (room.ends_at_ms - member.answered_at * 1000) / (duration * 1000)
                member.streak += 1
                member.longest_streak = max(member.longest_streak, member.streak)
                member.correct += 1
                member.last_award = _award(remaining, member.streak)
                member.score += member.last_award
                member.last_correct = True
            else:
                member.streak = 0
                member.last_correct = False

        room.ends_at_ms = now_ms() + REVEAL_SECONDS * 1000
        await self.broadcast(
            room,
            {
                "type": "question_end",
                "payload": {
                    **self.state(room),
                    "isLastQuestion": room.q_index + 1 >= len(room.questions),
                },
            },
        )
        await asyncio.sleep(REVEAL_SECONDS)

    # ---------------------------------------------------------- match rounds

    async def _open_board(self, room: Room, index: int, dealt: Board) -> None:
        room.q_index = index
        room.phase = "question"
        room.board = dealt
        room.claims.clear()
        room.all_answered.clear()
        for member in room.members.values():
            member.reset_for_question()

        duration = room.seconds_per_question
        room.ends_at_ms = now_ms() + duration * 1000
        await self.broadcast_state(room)

        # Close at the deadline, or as soon as everyone still here has submitted.
        try:
            await asyncio.wait_for(room.all_answered.wait(), timeout=duration)
        except asyncio.TimeoutError:
            pass

    async def _reveal_board(self, room: Room) -> None:
        dealt = room.board
        if dealt is None:
            return
        room.phase = "reveal"
        window = room.seconds_per_question * 1000
        deadline = room.ends_at_ms  # the round's, before it becomes the reveal's

        for member in room.members.values():
            # Whatever they were still holding when the clock ran out is their answer.
            member.submitted = True
            award = 0
            right = 0
            for human_slot, dog_slot in member.pairs.items():
                if dealt.answer.get(human_slot) != dog_slot:
                    continue
                right += 1
                remaining = 0.0
                claimed_at = member.claimed_at.get(human_slot)
                if claimed_at is not None and deadline is not None and window > 0:
                    remaining = (deadline - claimed_at * 1000) / window
                award += _pair_award(remaining)

            if boards.is_perfect(dealt, member.pairs):
                award += MATCH_PERFECT_BONUS
                member.streak += 1
                member.longest_streak = max(member.longest_streak, member.streak)
            else:
                # The streak is for clean boards, so three of four breaks it.
                member.streak = 0

            member.correct += right
            member.last_round_correct = right
            member.last_award = award
            member.last_correct = right > 0
            member.score += award

        room.ends_at_ms = now_ms() + REVEAL_SECONDS * 1000
        await self.broadcast(
            room,
            {
                "type": "question_end",
                "payload": {
                    **self.state(room),
                    "isLastQuestion": room.q_index + 1 >= room.rounds_total,
                },
            },
        )
        await asyncio.sleep(REVEAL_SECONDS)

    async def _finish(self, room: Room) -> None:
        room.phase = "over"
        room.ends_at_ms = None
        standings = room.standings()
        best = standings[0].score if standings else 0
        for member in standings:
            store.record_multiplayer_result(
                member.player_id,
                member.name,
                member.score,
                member.longest_streak,
                won=member.score == best and best > 0,
                board=room.leaderboard_name,
            )
        await self.broadcast(
            room,
            {
                "type": "game_over",
                "payload": {
                    **self.state(room),
                    "leaderboard": store.top(room.leaderboard_name),
                },
            },
        )

    # -------------------------------------------------------------- answers

    def _check_all_answered(self, room: Room) -> None:
        """Close the round early once nobody still here has anything to do.

        Works for both game types: `done_with_round` is "answered" for a double
        room and "submitted" for a match room.
        """
        if room.phase != "question":
            return
        here = room.connected_members
        if here and all(m.done_with_round for m in here):
            room.all_answered.set()

    async def answer(self, room: Room, player_id: str, question_index: int, choice: int) -> None:
        """Record a player's answer, or tell them exactly why it didn't count."""
        member = room.members.get(player_id)
        if member is None:
            await self._reject(player_id, "You're not in this room.")
            return
        if room.phase != "question" or room.current is None:
            await self._reject(player_id, "That question isn't open.")
            return
        if question_index != room.q_index:
            # A late click on the previous question, or a stale client.
            await self._reject(player_id, "Too late — that question already closed.")
            return
        if member.answer is not None:
            # The contradiction guard: first answer stands, full stop.
            await self._reject(player_id, "You already locked in an answer.")
            return
        if not 0 <= choice < len(room.current.options):
            await self._reject(player_id, "That isn't one of the options.")
            return
        # The deadline is the server's, not the client's. A small grace covers
        # network latency on an answer that was genuinely sent in time.
        if room.ends_at_ms is not None and time.time() * 1000 > room.ends_at_ms + 250:
            await self._reject(player_id, "Too late — the clock ran out.")
            return

        member.answer = choice
        member.answered_at = time.time()
        await self.send(
            player_id,
            {"type": "answer_ack", "payload": {"questionIndex": question_index, "choice": choice}},
        )
        # Everyone sees who has locked in — but not what they picked.
        await self.broadcast_state(room)
        self._check_all_answered(room)

    async def _reject(self, player_id: str, message: str) -> None:
        await self.send(player_id, {"type": "answer_rejected", "payload": {"message": message}})

    # ---------------------------------------------------------- match claims

    def _match_member(self, room: Room, player_id: str) -> Member:
        """The common gate for every claim action. Raises with a reason to show."""
        if not room.is_match:
            raise ValueError("This room isn't playing Mix & Match.")
        member = room.members.get(player_id)
        if member is None:
            raise ValueError("You're not in this room.")
        if room.phase != "question" or room.board is None:
            raise ValueError("The board isn't open.")
        if member.submitted:
            raise ValueError("You've already submitted this board.")
        if room.ends_at_ms is not None and time.time() * 1000 > room.ends_at_ms + 250:
            raise ValueError("Too late — the round is over.")
        return member

    async def claim(self, room: Room, player_id: str, human_slot: int, dog_slot: int) -> None:
        """Take a human↔dog combination, exclusively, for this player.

        **This is the contradiction guard** (ProjectPlan 2.10). Everything from the
        "is it free" test to writing the claim happens with no ``await`` in
        between, so on a single-threaded event loop it is atomic: of two players
        who click the same combination in the same instant, exactly one is holding
        it afterwards and the other is told who beat them.
        """
        member = self._match_member(room, player_id)
        assert room.board is not None  # guaranteed by _match_member

        if not 0 <= human_slot < len(room.board.humans):
            raise ValueError("That person isn't on the board.")
        if not 0 <= dog_slot < len(room.board.dogs):
            raise ValueError("That dog isn't on the board.")

        holder = room.claims.get((human_slot, dog_slot))
        if holder is not None and holder != player_id:
            await self.send(
                player_id,
                {
                    "type": "claim_rejected",
                    "payload": {
                        "human": human_slot,
                        "dog": dog_slot,
                        "message": f"{self._member_name(room, holder)} claimed that pair first.",
                    },
                },
            )
            return
        if member.pairs.get(human_slot) == dog_slot:
            return  # already mine; a double-tap is not an error

        # Within my own board a human takes one dog and a dog takes one human, so
        # this claim displaces at most two of my own — released, not stolen.
        self._drop(room, member, human_slot)
        for other_human, other_dog in list(member.pairs.items()):
            if other_dog == dog_slot:
                self._drop(room, member, other_human)

        member.pairs[human_slot] = dog_slot
        member.claimed_at[human_slot] = time.time()
        room.claims[(human_slot, dog_slot)] = player_id

        await self.send(
            player_id,
            {"type": "claim_ack", "payload": {"human": human_slot, "dog": dog_slot}},
        )
        await self.broadcast_state(room)

    async def release(self, room: Room, player_id: str, human_slot: int) -> None:
        """Give a combination back to the table so anyone can take it."""
        member = self._match_member(room, player_id)
        if human_slot not in member.pairs:
            return  # nothing to release; not worth an error
        self._drop(room, member, human_slot)
        await self.broadcast_state(room)

    def _drop(self, room: Room, member: Member, human_slot: int) -> None:
        """Undo one of this member's pairings. Never touches anyone else's."""
        dog_slot = member.pairs.pop(human_slot, None)
        member.claimed_at.pop(human_slot, None)
        if dog_slot is None:
            return
        if room.claims.get((human_slot, dog_slot)) == member.player_id:
            room.claims.pop((human_slot, dog_slot), None)

    async def submit(self, room: Room, player_id: str) -> None:
        """Freeze this player's board. Their claims stand until the reveal."""
        member = self._match_member(room, player_id)
        member.submitted = True
        await self.send(
            player_id,
            {"type": "submit_ack", "payload": {"pairs": member.pairs}},
        )
        await self.broadcast_state(room)
        self._check_all_answered(room)
