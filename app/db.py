"""Vocab + proximité — deux modes de chargement, une seule interface.

Le jeu n'a besoin, par mot jouable, que de son VECTEUR (300-d, normalisé) et de sa
fréquence Zipf. Deux sources possibles :

  • PROD / déploiement : l'artefact compact `data/vectors.f16.npy` (+ `vocab.json`)
    — ~50 Mo, aucune dépendance lourde. C'est ce qui tourne sur Railway.
  • DEV local : le modèle FastText complet (2M mots) via Discoverix, qui permet de
    (re)générer l'artefact et de recalibrer le vocab en direct.

Dans les deux cas on aboutit à la même chose en mémoire :
  - `_M`       : matrice (N × 300) des vecteurs jouables, NORMALISÉS
  - `_id2word` : mot de chaque ligne
  - `_zipf`    : fréquence par mot
  - `_fold`    : index sans accents (saisie relâchée)

Proximité P->G = `_M[idP] · _M[idG]` (un produit scalaire). Rien d'autre au runtime.
"""
from __future__ import annotations

import json
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
    def __init__(self, force_kv: bool = False):
        if force_kv:
            self._build_from_kv()
        elif C.VECTORS_NPY.exists() and C.VOCAB_JSON.exists():
            self._load_compact()
        elif C.FASTTEXT_KV.exists():
            self._build_from_kv()
        else:
            raise FileNotFoundError(
                f"Ni l'artefact compact ({C.VECTORS_NPY.name}) ni le modèle FastText "
                f"({C.FASTTEXT_KV}) ne sont présents. Génère l'artefact avec "
                f"tools/export_vectors.py, ou fournis le modèle."
            )
        self._finalize()

    # --- sources --------------------------------------------------------------
    def _load_compact(self):
        """Prod : vecteurs float16 + liste de mots (aucune dépendance ML)."""
        M = np.load(C.VECTORS_NPY).astype("float32")
        M /= np.linalg.norm(M, axis=1, keepdims=True)   # renormalise (arrondi f16)
        self._M = M
        meta = json.loads(C.VOCAB_JSON.read_text(encoding="utf-8"))
        self._id2word = meta["words"]
        self._zipf = dict(zip(meta["words"], meta["zipf"]))

    def _build_from_kv(self):
        """Dev : reconstruit depuis le modèle 2M (gensim + wordfreq).
        Mots jouables = top-KV_SCAN ∩ wordfreq, hors mots-outils / noms propres."""
        if not C.FASTTEXT_KV.exists():
            raise FileNotFoundError(f"Modèle FastText introuvable : {C.FASTTEXT_KV}")
        from gensim.models import KeyedVectors
        from wordfreq import zipf_frequency

        kv = KeyedVectors.load(str(C.FASTTEXT_KV), mmap="r")
        k2i = kv.key_to_index
        order: list[str] = []
        self._zipf = {}
        for rank_w, w in enumerate(kv.index_to_key[: C.KV_SCAN]):
            if not w.isalpha() or not w.islower():
                continue
            if len(w) < C.MIN_WORD_LEN and w not in C.SHORT_WORDS:
                continue
            z = zipf_frequency(w, "fr")
            if z < C.VOCAB_ZIPF_MIN:
                continue
            cap_rank = k2i.get(w.capitalize())            # nom propre : Majuscule domine
            if cap_rank is not None and rank_w >= C.PROPER_NOUN_RATIO * cap_rank:
                continue
            order.append(w)
            self._zipf[w] = z
        M = np.stack([kv[w] for w in order]).astype("float32")
        M /= np.linalg.norm(M, axis=1, keepdims=True)
        self._M = M
        self._id2word = order

    def _finalize(self):
        self._words = {w: i for i, w in enumerate(self._id2word)}   # mot -> ligne
        self._fold = {}
        for w in self._id2word:
            self._fold.setdefault(fold(w), w)
        # Pool des mots de DÉPART : bande de fréquence moyenne-haute, moins les mots
        # vulgaires (fold pour matcher sans accents/casse). Ne touche pas au jeu :
        # le joueur peut toujours enchaîner ces mots, seul le seed est filtré.
        # Exclusions communes au MOT DE DÉPART et au MOT BONUS : vulgarité,
        # mots-outils, abréviations, prénoms.
        self._seed_excluded = {fold(w) for w in
                               (C.SEED_BLOCKLIST | C.SEED_STOPLIST | C.SEED_NAMES)}
        self._seed_pool = sorted(
            w for w in self._id2word
            if C.SEED_ZIPF_MIN <= self._zipf[w] <= C.SEED_ZIPF_MAX
            and fold(w) not in self._seed_excluded
            # écarte les artefacts typographiques (ligatures ﬁ/ﬂ…) : on ne garde que
            # les mots déjà en forme NFKC. « œil »/« œuf » (œ non décomposé) restent OK.
            and w == unicodedata.normalize("NFKC", w)
        )
        self.vocab_size = len(self._id2word)

    # --- lookups --------------------------------------------------------------
    def canonical(self, word: str) -> str | None:
        """Forme jouable du mot, ou None. Tolère casse et accents manquants."""
        w = word.strip().lower()
        if w in self._words:
            return w
        return self._fold.get(fold(w))

    def zipf(self, word: str) -> float:
        return self._zipf.get(word, 0.0)

    def prox(self, prev: str, nxt: str) -> float:
        """Cosinus prev->nxt (formes canoniques, vecteurs déjà normalisés)."""
        a = self._words.get(prev)
        b = self._words.get(nxt)
        if a is None or b is None:
            return 0.0
        return max(0.0, float(self._M[a] @ self._M[b]))

    def top_neighbors(self, word: str, limit: int = 12):
        """Meilleurs voisins (debug / révélation). Balayage complet du vocab."""
        c = self.canonical(word)
        if c is None:
            return []
        sims = self._M @ self._M[self._words[c]]
        idx = np.argpartition(-sims, limit + 1)[: limit + 1]
        idx = idx[np.argsort(-sims[idx])]
        return [(self._id2word[i], float(sims[i])) for i in idx
                if self._id2word[i] != c][:limit]

    def seed_pool(self) -> list[str]:
        return self._seed_pool

    def pick_target(self, current: str, avoid: str, captures: int) -> str | None:
        """Choisit un MOT CIBLE : rare (bande de zipf qui descend avec `captures`),
        SANS aucune lettre de `avoid` (interdites actives), != mot courant, et PAS
        immédiatement jouable depuis `current` (prox < TAU_GRACE) pour forcer un vrai
        chemin de plusieurs hops (sinon capture triviale)."""
        import random
        avoid_set = set(avoid)
        cur = self.canonical(current)
        cur_vec = self._M[self._words[cur]] if cur in self._words else None
        z_hi = max(C.ZIPF_MIN + 0.6, 4.8 - 0.5 * captures)
        z_lo = z_hi - 0.6
        cand = [w for w in self._id2word
                if z_lo <= self._zipf[w] <= z_hi
                and w != cur
                and len(w) <= 12                       # reste lisible/tapable dans le HUD
                and fold(w) not in self._seed_excluded  # vulgarité/mots-outils/abrév/prénoms
                and not (avoid_set & set(fold(w)))]
        if not cand:
            return None
        if cur_vec is None:
            return random.choice(cand)
        # Proximités de tous les candidats d'un coup (produit matrice-vecteur).
        idx = [self._words[w] for w in cand]
        sims = self._M[np.asarray(idx)] @ cur_vec
        # Zone ATTEIGNABLE : proche mais pas adjacent (pas jouable au 1er coup).
        band = [(cand[i], float(sims[i])) for i in range(len(cand))
                if C.TARGET_PROX_MIN <= sims[i] < C.TAU_GRACE]
        if band:
            band.sort(key=lambda t: -t[1])     # les plus LIÉS d'abord -> waypoint crédible
            return random.choice(band[:8])[0]  # un peu de variété parmi les 8 meilleurs
        # Repli : n'importe quelle cible non immédiate (la plus liée possible).
        far = [(cand[i], float(sims[i])) for i in range(len(cand)) if sims[i] < C.TAU_GRACE]
        if far:
            far.sort(key=lambda t: -t[1])
            return far[0][0]
        return cand[0]
