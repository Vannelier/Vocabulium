"""Backend Vocabulium — FastAPI, stateless.

Le serveur ne connaît pas le déroulé d'une partie : le combo, le pending, le
timer et l'ensemble des mots déjà joués vivent côté client. /hop valide un seul
saut P->G et renvoie sa décomposition de score ; le client applique le
multiplicateur, encaisse, etc.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C
from app.db import Vocab
from app.scoring import score_hop, same_root, same_lemma, rarete
from app.seed import daily_seed, random_seed

app = FastAPI(title="Vocabulium")
db = Vocab()
WEB_DIR = C.PROJECT_ROOT / "web"


class HopRequest(BaseModel):
    prev: str          # mot précédent (canonique, tel que renvoyé au tour d'avant)
    next: str          # mot saisi par le joueur
    t: float = 0.0     # secondes écoulées depuis le hop précédent


@app.get("/api/seed")
def get_seed(mode: str = "daily"):
    """mode=daily : mot du jour déterministe (même pour tous, pour le leaderboard).
    mode=random : mot aléatoire (variété entre deux parties du proto)."""
    pool = db.seed_pool()
    word = random_seed(pool) if mode == "random" else daily_seed(pool)
    return {
        "word": word,
        "mode": mode,
        "date": datetime.date.today().isoformat(),
        "vocab_size": db.vocab_size,
        "config": {
            "tau": C.TAU, "tau_grace": C.TAU_GRACE, "syno": C.SYNO,
            "combo_step": C.COMBO_STEP, "combo_floor": C.COMBO_FLOOR,
            "mult_max": C.MULT_MAX,
            "gauge_seconds": C.GAUGE_SECONDS, "weak_refill": C.WEAK_REFILL,
            "keep_pending_on_timeout": C.KEEP_PENDING_ON_TIMEOUT,
        },
    }


@app.post("/api/hop")
def post_hop(req: HopRequest):
    prev = db.canonical(req.prev)
    if prev is None:
        raise HTTPException(400, f"mot précédent inconnu: {req.prev}")

    nxt = db.canonical(req.next)
    if nxt is None:
        # mot hors vocab : ni valide ni bail, on laisse rejouer
        return {"valid": False, "reason": "unknown_word", "input": req.next}
    if nxt == prev:
        return {"valid": False, "reason": "same_word", "word": nxt}

    prox = db.prox(prev, nxt)
    # Singulier/pluriel (same_lemma) ou même racine (same_root) : autrefois le
    # pluriel était INTERDIT, ce qui pouvait soft-lock un mot bonus atteignable
    # seulement via un pluriel. Désormais on l'ACCEPTE, mais traité comme un ÉCHO :
    # hop faible, pas de combo ni de montée de multiplicateur.
    echo = same_root(prev, nxt) or same_lemma(prev, nxt)
    result = score_hop(prox, db.zipf(nxt), req.t, root=echo)
    out = result.to_dict()
    out["word"] = nxt          # forme canonique (accents corrigés)
    out["prev"] = prev
    return out


@app.get("/api/neighbors/{word}")
def get_neighbors(word: str):
    """Debug / révélation : meilleurs voisins d'un mot."""
    canon = db.canonical(word)
    if canon is None:
        raise HTTPException(404, f"mot inconnu: {word}")
    return {"word": canon, "neighbors": db.top_neighbors(canon)}


def _target_bonus(zipf: float) -> int:
    """Bonus ROND par palier de rareté (300/400/500/600), fixe et prédictible."""
    r = rarete(zipf)
    for i, cut in enumerate(C.TARGET_BONUS_CUTS):
        if r < cut:
            return C.TARGET_BONUS_TIERS[i]
    return C.TARGET_BONUS_TIERS[-1]


@app.get("/api/target")
def get_target(current: str, avoid: str = "", captures: int = 0):
    """Mot cible (waypoint) : rare, sans lettre interdite active, non immédiat."""
    w = db.pick_target(current, avoid, captures)
    if not w:
        return {"word": None}
    z = db.zipf(w)
    return {"word": w, "zipf": round(z, 3), "bonus_base": _target_bonus(z)}


@app.get("/")
def index():
    # no-cache : le HTML est toujours revalidé -> les mises à jour (et les ?v= des
    # assets) s'appliquent sans rechargement forcé.
    return FileResponse(WEB_DIR / "index.html",
                        headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB_DIR), name="web")
