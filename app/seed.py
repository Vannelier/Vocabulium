"""Mot de départ quotidien, déterministe et identique pour tous.

seed du jour = hash(date) -> index dans le pool de mots jouables. Le pool est
trié (ordre stable), donc le même jour donne le même mot partout.
"""
from __future__ import annotations

import datetime
import hashlib
import random


def daily_seed(pool: list[str], day: datetime.date | None = None) -> str:
    if not pool:
        raise ValueError("pool de seeds vide")
    day = day or datetime.date.today()
    h = hashlib.sha256(day.isoformat().encode("utf-8")).hexdigest()
    return pool[int(h, 16) % len(pool)]


def random_seed(pool: list[str]) -> str:
    """Mot aléatoire — pour la variété entre deux parties du proto (le mode
    quotidien déterministe reste dispo pour l'éventuel leaderboard)."""
    if not pool:
        raise ValueError("pool de seeds vide")
    return random.choice(pool)
