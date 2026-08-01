"""Scoring d'un hop — fonctions pures, sans I/O.

Tout est piloté par constants.py. Un hop va du mot P (précédent) vers G (posé).
On reçoit `prox` (cosinus P->G, déjà connu via neighbors.db) et les attributs de
G (zipf, nb_voisins), plus `t` = secondes depuis le hop précédent.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def rarete(zipf: float) -> float:
    """Rareté normalisée et bornée : rare -> haut, courant -> bas. C'est LE signal
    de valeur du mot (rareté et spécificité fusionnées : un seul score lisible)."""
    return _clamp((C.ZIPF_MAX - zipf) / (C.ZIPF_MAX - C.ZIPF_MIN))


def speed_bonus(t: float) -> float:
    """Décroissance exponentielle : sépare bien les hops rapides (t=1s->0.72,
    2s->0.51, 4s->0.26). Plus discriminante qu'une rampe linéaire plate."""
    return _clamp(math.exp(-max(0.0, t) / C.SPEED_TAU))


def same_root(a: str, b: str) -> bool:
    """True si a et b partagent une racine (dérivation : rapide/rapidement,
    génie/génial). Pont fainéant, à minorer même si le cosinus est en zone forte.
    Voir constants.py pour la règle (préfixe + longueur mini + fraction)."""
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    m = min(len(a), len(b))
    return (n >= C.ROOT_MIN_PREFIX and m >= C.ROOT_MIN_LEN
            and n >= C.ROOT_FRAC * m)


def resemblance(prox: float, root: bool) -> float:
    """[0,1] : à quel point G est un ÉCHO du mot précédent. 0 = pont distinct,
    ->1 = quasi-identique. Monte avec la proximité (au-delà du sweet spot) et est
    forcée haute si même racine. C'est le malus 'trop proche', affiché en jeu."""
    r = _clamp((prox - C.TAU) / (1.0 - C.TAU))
    return max(r, 0.85) if root else r


@dataclass
class HopResult:
    valid: bool           # G est un mot du vocab
    zone: str             # "strong" | "weak" | "reject"
    reason: str           # "" | "far" | "syno" | "root"  (pourquoi faible, pour l'UI)
    prox: float
    hop_points: float     # points AVANT multiplicateur de combo
    # décomposition, pour l'affichage / la calibration
    rarete: float
    speed: float
    resemblance: float    # malus 'trop proche' (synonyme / dérivation)

    def to_dict(self):
        return asdict(self)


def score_hop(prox: float, zipf: float, t: float, root: bool = False) -> HopResult:
    """Score d'un hop (mot connu). `prox` = cosinus P->G. Un sweet spot : ni trop
    loin (rejet/faible) ni trop proche (synonyme OU même racine = faible).
    Points = rareté du mot × vitesse (la proximité ne fait qu'ouvrir la porte)."""
    if prox < C.TAU_GRACE:
        return HopResult(
            valid=True, zone="reject", reason="far", prox=prox, hop_points=0.0,
            rarete=0.0, speed=0.0, resemblance=0.0,
        )
    r = rarete(zipf)
    speed = speed_bonus(t)
    resemble = resemblance(prox, root)
    base = C.BASE * (1.0 + C.WS * r) * (1.0 + C.WV * speed)

    if not root and C.TAU <= prox < C.SYNO:   # zone forte : le sweet spot
        return HopResult(valid=True, zone="strong", reason="", prox=prox,
                         hop_points=base, rarete=r, speed=speed, resemblance=resemble)
    # faible : même racine (dérivation), ou trop proche (synonyme), ou trop loin
    reason = "root" if root else ("syno" if prox >= C.SYNO else "far")
    return HopResult(valid=True, zone="weak", reason=reason, prox=prox,
                     hop_points=base * C.WEAK_POINTS_FACTOR, rarete=r,
                     speed=speed, resemblance=resemble)
