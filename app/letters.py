"""Portage Python de web/letters.js — autorité serveur sur les lettres interdites.
Mêmes règles que le solo : +1 lettre tous les `every` mots, ordre dosé (MID puis
fréquente puis reste), accent-insensible. `rand` = callable renvoyant [0,1)."""
from __future__ import annotations

import unicodedata
from typing import Callable, Sequence

FREQ = {
    "a": 7.6, "b": 0.9, "c": 3.3, "d": 3.7, "e": 14.7, "f": 1.1, "g": 0.9,
    "h": 0.7, "i": 7.5, "j": 0.5, "k": 0.05, "l": 5.5, "m": 3.0, "n": 7.1,
    "o": 5.4, "p": 3.0, "q": 1.4, "r": 6.6, "s": 7.9, "t": 7.2, "u": 6.3,
    "v": 1.6, "w": 0.04, "x": 0.4, "y": 0.3, "z": 0.1,
}
ALPHABET = list(FREQ.keys())
MID = ["o", "u", "l", "d", "c", "p", "m", "v", "g", "b", "f", "h"]
FREQUENT = ["e", "a", "s", "r", "t", "i", "n"]


def fold(ch: str) -> str:
    """é->e, ç->c, À->a. Replie accents + minuscule."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
    ).lower()


def _shuffle(arr: list[str], rand: Callable[[], float]) -> list[str]:
    a = list(arr)
    for i in range(len(a) - 1, 0, -1):
        j = int(rand() * (i + 1))
        a[i], a[j] = a[j], a[i]
    return a


def draw_order(rand: Callable[[], float]) -> list[str]:
    """2 lettres MID, puis 1 FRÉQUENTE, puis le reste au hasard. Déterministe."""
    mid = _shuffle(MID, rand)
    freq = _shuffle(FREQUENT, rand)
    order = [mid[0], mid[1], freq[0]]
    used = set(order)
    rest = _shuffle([L for L in ALPHABET if L not in used], rand)
    return order + rest


def forbidden_count(words: int, every: int = 5, start: int = 0) -> int:
    """Nombre de lettres interdites après `words` mots : `start` au départ, +1 tous les `every`."""
    return start + words // every


def active_forbidden(order: Sequence[str], words: int, every: int = 5,
                     start: int = 0, target_letters: Sequence[str] = ()) -> list[str]:
    """Les `forbidden_count` premières de l'ordre, en sautant les lettres de la cible."""
    skip = set(target_letters)
    avail = [L for L in order if L not in skip] if skip else list(order)
    return avail[: forbidden_count(words, every, start)]


def offending_letters(word: str, active: Sequence[str]) -> list[str]:
    """Lettres interdites (parmi `active`) présentes dans `word`, accents repliés."""
    aset = set(active)
    hit = []
    for ch in word:
        f = fold(ch)
        if f in aset and f not in hit:
            hit.append(f)
    return hit
