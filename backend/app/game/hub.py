"""Event dispatch — THE TRANSPORT SEAM.

Nothing below this line knows what a WebSocket is. The hub takes an already
identified player plus a decoded event and mutates room state; to reach a player
it calls one injected coroutine, ``send(player_id, message)``.

That is what makes the game safe to graft onto the shared socket in
``app/routers/ws.py`` later. Two changes, both one-liners:

1. ``hub.bind(manager.send_to_user)`` instead of the game's own registry.
2. In their receive loop, route game traffic here::

       if event.get("type", "").startswith("game_"):
           await hub.handle(Player(str(user_id), username), event)
           continue

Client events are named ``game_*`` on the wire precisely so that dispatch is a
prefix test — and so the frontend needs no change at all when the merge happens.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from .rooms import RoomRegistry, now_ms

log = logging.getLogger(__name__)

Sender = Callable[[str, dict], Awaitable[None]]


@dataclass(frozen=True)
class Player:
    """Who is acting. Whatever produced this, the game doesn't care."""

    id: str
    name: str


class Hub:
    def __init__(self) -> None:
        self._send: Sender | None = None
        # `self.send` is a bound method, so the registry picks up whatever gets
        # bound later — order of wiring doesn't matter.
        self.rooms = RoomRegistry(self.send)

    def bind(self, send: Sender) -> None:
        """Point the hub at a transport."""
        self._send = send

    async def send(self, player_id: str, message: dict) -> None:
        if self._send is None:
            log.warning("hub has no transport bound; dropping %s", message.get("type"))
            return
        try:
            await self._send(player_id, message)
        except Exception as exc:
            # A socket that died mid-broadcast must not abort everyone else's.
            log.debug("send to %s failed: %s", player_id, exc)

    async def error(self, player_id: str, message: str) -> None:
        await self.send(player_id, {"type": "error", "payload": {"message": message}})

    # ---------------------------------------------------------------- dispatch

    async def handle(self, player: Player, event: dict) -> None:
        kind = str(event.get("type", ""))
        if kind.startswith("game_"):
            kind = kind[len("game_") :]
        payload = event.get("payload") or {}

        handler = {
            "join": self._on_join,
            "leave": self._on_leave,
            "set_options": self._on_set_options,
            "start": self._on_start,
            "answer": self._on_answer,
            "claim": self._on_claim,
            "release": self._on_release,
            "submit": self._on_submit,
            "again": self._on_again,
            "ping": self._on_ping,
        }.get(kind)

        if handler is None:
            await self.error(player.id, f"Unknown game event: {kind or '(none)'}")
            return

        try:
            await handler(player, payload)
        except ValueError as exc:
            # Rule violations are expected traffic, not bugs: tell the player.
            await self.error(player.id, str(exc))
        except Exception:
            log.exception("game event %s from %s failed", kind, player.id)
            await self.error(player.id, "Something went wrong handling that.")

    async def on_disconnect(self, player_id: str) -> None:
        """Socket dropped: mark them away but hold their seat and score."""
        room = self.rooms.find_room_of(player_id)
        if room is not None:
            await self.rooms.leave(room, player_id, permanent=False)

    # ---------------------------------------------------------------- handlers

    def _room_for(self, player: Player, payload: dict):
        room = None
        if payload.get("code"):
            room = self.rooms.by_code(str(payload["code"]))
        elif payload.get("roomId"):
            room = self.rooms.get(str(payload["roomId"]))
        if room is None:
            raise ValueError("That room doesn't exist any more.")
        return room

    async def _on_join(self, player: Player, payload: dict) -> None:
        room = self._room_for(player, payload)
        # One room at a time, so a stale membership can't keep scoring for you.
        previous = self.rooms.find_room_of(player.id)
        if previous is not None and previous.id != room.id:
            await self.rooms.leave(previous, player.id, permanent=True)
        await self.rooms.join(room, player.id, player.name)

    async def _on_leave(self, player: Player, payload: dict) -> None:
        room = self.rooms.find_room_of(player.id)
        if room is not None:
            await self.rooms.leave(room, player.id, permanent=True)

    async def _on_set_options(self, player: Player, payload: dict) -> None:
        room = self._require_host(player)
        rounds_total = payload.get("roundsTotal")
        seconds = payload.get("secondsPerQuestion")
        game_type = payload.get("gameType")
        await self.rooms.set_options(
            room,
            int(rounds_total) if rounds_total is not None else None,
            int(seconds) if seconds is not None else None,
            str(game_type) if game_type is not None else None,
        )

    async def _on_start(self, player: Player, payload: dict) -> None:
        await self.rooms.start_game(self._require_host(player))

    async def _on_again(self, player: Player, payload: dict) -> None:
        await self.rooms.back_to_lobby(self._require_host(player))

    def _my_room(self, player: Player):
        room = self.rooms.find_room_of(player.id)
        if room is None:
            raise ValueError("You're not in a room.")
        return room

    async def _on_answer(self, player: Player, payload: dict) -> None:
        room = self._my_room(player)
        await self.rooms.answer(
            room,
            player.id,
            int(payload.get("questionIndex", -1)),
            int(payload.get("choice", -1)),
        )

    async def _on_claim(self, player: Player, payload: dict) -> None:
        await self.rooms.claim(
            self._my_room(player),
            player.id,
            int(payload.get("humanSlot", -1)),
            int(payload.get("dogSlot", -1)),
        )

    async def _on_release(self, player: Player, payload: dict) -> None:
        await self.rooms.release(
            self._my_room(player), player.id, int(payload.get("humanSlot", -1))
        )

    async def _on_submit(self, player: Player, payload: dict) -> None:
        await self.rooms.submit(self._my_room(player), player.id)

    async def _on_ping(self, player: Player, payload: dict) -> None:
        # Doubles as the clock-sync probe: the client compares serverNow to its
        # own clock so its countdown bar matches everyone else's.
        await self.send(player.id, {"type": "pong", "payload": {"serverNow": now_ms()}})

    def _require_host(self, player: Player):
        room = self.rooms.find_room_of(player.id)
        if room is None:
            raise ValueError("You're not in a room.")
        if room.host_id != player.id:
            raise ValueError("Only the host can do that.")
        return room


hub = Hub()
