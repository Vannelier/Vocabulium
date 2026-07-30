"""Vocab + proximité + spécificité, entièrement au runtime depuis le modèle.

Le dictionnaire EST le modèle FastText : un mot est jouable s'il a un vecteur ET
que wordfreq le reconnaît (zipf >= VOCAB_ZIPF_MIN). Aucune base, aucun rebuild —
tout est reconstruit en mémoire au démarrage (~3 s) :

  - `_valid`   : mots jouables (modèle ∩ wordfreq), avec leur zipf, indexés par forme
  - `_fold`    : index sans accents, pour tolérer une saisie relâchée
  - `_R`       : matrice des REF_SIZE mots les plus fréquents, pour le degré (spécificité)

Proximité = cosinus des deux vecteurs (produit scalaire). Spécificité = degré de G
contre `_R` (un produit matrice-vecteur, ~9 ms). Changer VOCAB_ZIPF_MIN / TAU /
SYNO : il suffit de redémarrer.
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C


def fold(word: str) -> str:
    """Minuscule + suppression des accents, pour matcher une saisie relâchée."""
    w = word.strip().lower()
    nfkd = unicodedata.normalize("NFKD", w)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


class Vocab:
    def __init__(self):
        if not C.FASTTEXT_KV.exists():
            raise FileNotFoundError(f"Modèle FastText introuvable : {C.FASTTEXT_KV}")
        from gensim.models import KeyedVectors
        from wordfreq import zipf_frequency

        self._kv = KeyedVectors.load(str(C.FASTTEXT_KV), mmap="r")

        # Vocab jouable = top-KV_SCAN du modèle (freq-ordonné) ∩ wordfreq.
        self._zipf: dict[str, float] = {}
        self._fold: dict[str, str] = {}
        k2i = self._kv.key_to_index
        order: list[str] = []          # mots jouables, ordre de fréquence de corpus
        for rank_w, w in enumerate(self._kv.index_to_key[: C.KV_SCAN]):
            if not w.isalpha() or not w.islower():
                continue
            if len(w) < C.MIN_WORD_LEN and w not in C.SHORT_WORDS:
                continue
            z = zipf_frequency(w, "fr")
            if z < C.VOCAB_ZIPF_MIN:
                continue
            # nom propre : la forme Capitalisée domine nettement (john, paris…)
            cap_rank = k2i.get(w.capitalize())
            if cap_rank is not None and rank_w >= C.PROPER_NOUN_RATIO * cap_rank:
                continue
            self._zipf[w] = z
            self._fold.setdefault(fold(w), w)
            order.append(w)

        # Matrice de référence (top mots), pour retrouver les voisins d'un mot
        # (endpoint de debug / révélation). Ne sert plus au scoring.
        self._ref_words = order[: C.REF_SIZE]
        R = np.stack([self._kv[w] for w in self._ref_words]).astype("float32")
        R /= np.linalg.norm(R, axis=1, keepdims=True)
        self._R = R

        # Pool de seeds (bande de fréquence moyenne), figé au démarrage.
        self._seed_pool = sorted(
            w for w, z in self._zipf.items()
            if C.SEED_ZIPF_MIN <= z <= C.SEED_ZIPF_MAX
        )
        self.vocab_size = len(order)

    # --- lookups --------------------------------------------------------------
    def canonical(self, word: str) -> str | None:
        """Forme jouable du mot, ou None. Tolère casse et accents manquants."""
        w = word.strip().lower()
        if w in self._zipf:
            return w
        return self._fold.get(fold(w))

    def zipf(self, word: str) -> float:
        return self._zipf.get(word, 0.0)

    def _unit(self, word: str) -> np.ndarray:
        v = self._kv[word].astype("float32")
        return v / np.linalg.norm(v)

    def prox(self, prev: str, nxt: str) -> float:
        """Cosinus prev->nxt (formes canoniques), borné à 0."""
        return max(0.0, float(self._unit(prev) @ self._unit(nxt)))

    def top_neighbors(self, word: str, limit: int = 12):
        """Meilleurs voisins parmi les mots de référence (debug / révélation)."""
        c = self.canonical(word)
        if c is None:
            return []
        sims = self._R @ self._unit(c)
        idx = np.argpartition(-sims, limit + 1)[: limit + 1]
        idx = idx[np.argsort(-sims[idx])]
        return [(self._ref_words[i], float(sims[i])) for i in idx
                if self._ref_words[i] != c][:limit]

    def seed_pool(self) -> list[str]:
        return self._seed_pool
