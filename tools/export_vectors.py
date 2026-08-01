"""Génère l'artefact DÉPLOYABLE depuis le modèle FastText complet (dev local).

Sort, dans data/ :
  - vectors.f16.npy : les vecteurs (N × 300, float16, normalisés) des mots jouables
  - vocab.json      : {"words": [...], "zipf": [...]} dans l'ordre des lignes

Ces ~50 Mo suffisent au runtime : plus besoin du modèle 2,4 Go ni de gensim/wordfreq
en prod. À relancer seulement si le VOCAB change (VOCAB_ZIPF_MIN, filtres…).

Usage :  ../Discoverix/.venv/Scripts/python.exe tools/export_vectors.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C
from app.db import Vocab


def main():
    print("Construction du vocab depuis le modèle 2M…")
    v = Vocab(force_kv=True)
    n = v.vocab_size
    print(f"  {n} mots jouables")

    C.DATA_DIR.mkdir(exist_ok=True)
    np.save(C.VECTORS_NPY, v._M.astype("float16"))
    C.VOCAB_JSON.write_text(
        json.dumps({
            "words": v._id2word,
            "zipf": [round(v._zipf[w], 3) for w in v._id2word],
            "vocab_zipf_min": C.VOCAB_ZIPF_MIN,
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    mb = (C.VECTORS_NPY.stat().st_size + C.VOCAB_JSON.stat().st_size) / 1e6
    print(f"  écrit {C.VECTORS_NPY.name} + {C.VOCAB_JSON.name}  ({mb:.0f} Mo)")
    print("Terminé.")


if __name__ == "__main__":
    main()
