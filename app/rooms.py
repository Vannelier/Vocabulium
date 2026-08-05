"""Salons multijoueur en mémoire — état + transitions PURES (ni réseau, ni modèle,
ni horloge interne). La couche ws.py valide les mots et appelle ces méthodes."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field

from app import letters

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sans O/0/I/1/L ambigus
CODE_LEN = 4
LIVES = 3
MIN_PLAYERS = 2
MAX_PLAYERS = 6
LETTER_EVERY = 5
# palette (style.css) : pink, cyan, gold, green, violet, orange
COLORS = ["#ff2e97", "#22e6ff", "#ffd23f", "#20ffb2", "#b25cff", "#ff7a2f"]


@dataclass
class Player:
    id: str
    name: str
    color: str
    lives: int = LIVES
    alive: bool = True
    is_host: bool = False
    score: int = 0            # décoratif, reporté par le client


@dataclass
class Room:
    code: str
    players: list[Player] = field(default_factory=list)
    state: str = "lobby"                 # "lobby" | "playing" | "over"
    current_word: str | None = None
    played: set[str] = field(default_factory=set)
    forbidden_order: list[str] = field(default_factory=list)
    word_count: int = 0
    active_index: int = 0
    turn_deadline: float = 0.0           # monotonic, posé par ws.py
    winner_id: str | None = None

    # --- lobby ---
    def add_player(self, name: str, pid: str | None = None) -> Player | None:
        if self.state != "lobby" or len(self.players) >= MAX_PLAYERS:
            return None
        used = {p.color for p in self.players}
        color = next((c for c in COLORS if c not in used), COLORS[0])
        p = Player(id=pid or secrets.token_hex(4), name=name, color=color,
                   is_host=(len(self.players) == 0))
        self.players.append(p)
        return p

    def player(self, pid: str) -> Player | None:
        return next((p for p in self.players if p.id == pid), None)

    def remove_player(self, pid: str) -> None:
        self.players = [p for p in self.players if p.id != pid]

    def can_start(self) -> bool:
        return self.state == "lobby" and len(self.players) >= MIN_PLAYERS

    def start(self, seed_word: str, forbidden_order: list[str]) -> None:
        self.state = "playing"
        self.current_word = seed_word
        self.played = {seed_word}
        self.forbidden_order = forbidden_order
        self.word_count = 0
        self.active_index = 0
        self.winner_id = None

    def active_player(self) -> Player | None:
        if not self.players:
            return None
        return self.players[self.active_index]

    def alive_players(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def active_forbidden(self) -> list[str]:
        return letters.active_forbidden(self.forbidden_order, self.word_count, LETTER_EVERY)


class RoomManager:
    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}

    def _new_code(self) -> str:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
            if code not in self.rooms:
                return code

    def create(self) -> Room:
        room = Room(code=self._new_code())
        self.rooms[room.code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code)

    def drop(self, code: str) -> None:
        self.rooms.pop(code, None)
