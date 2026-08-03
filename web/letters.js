"use strict";
// Module PUR (aucun DOM). Exposé sur window (pas de bundler dans le projet).
(function (root) {
  // Fréquences des lettres en français (%). Gardé pour référence (a inspiré les
  // paliers de drawOrder) ; le tirage n'est plus pondéré par cette table.
  const FREQ = {
    a: 7.6, b: 0.9, c: 3.3, d: 3.7, e: 14.7, f: 1.1, g: 0.9, h: 0.7, i: 7.5,
    j: 0.5, k: 0.05, l: 5.5, m: 3.0, n: 7.1, o: 5.4, p: 3.0, q: 1.4, r: 6.6,
    s: 7.9, t: 7.2, u: 6.3, v: 1.6, w: 0.04, x: 0.4, y: 0.3, z: 0.1,
  };
  const ALPHABET = Object.keys(FREQ);

  // RNG déterministe (mulberry32) à partir d'une graine entière.
  function rng(seed) {
    let s = seed >>> 0;
    return function () {
      s |= 0; s = (s + 0x6D2B79F5) | 0;
      let t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  // Graine entière à partir d'une chaîne (date "2026-08-02").
  function seedFromString(str) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i); h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  // Replie les accents/majuscule -> lettre de base (é->e, ç->c, À->a).
  function fold(ch) {
    return ch.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  // ORDRE DES LETTRES INTERDITES : de l'aléatoire, mais dosé au début pour que ça
  // morde sans être brutal. Toujours partir des consonnes courantes (R…) faisait
  // trop mal d'entrée. Schéma :
  //   ban 1 & 2 : MID (milieu de gamme) -> contrainte réelle mais contournable
  //   ban 3     : FRÉQUENTE (RSTAE + i/n) -> ça commence à piquer
  //   ban 4+    : full random du reste (les rares w/x/z tombent ici, jamais tôt)
  // MID exclut volontairement les très fréquentes (RSTAE…) ET les rares (x/w/z…).
  // Mélange déterministe en daily (même `rand`). i-ème lettre interdite = ordre[i].
  const MID = ["o", "u", "l", "d", "c", "p", "m", "v", "g", "b", "f", "h"];
  const FREQUENT = ["e", "a", "s", "r", "t", "i", "n"];
  function shuffle(arr, rand) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(rand() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }
  function drawOrder(rand) {
    const mid = shuffle(MID, rand);
    const freq = shuffle(FREQUENT, rand);
    const order = [mid[0], mid[1], freq[0]];        // 2 MID puis 1 FRÉQUENTE
    const used = new Set(order);
    const rest = shuffle(ALPHABET.filter((L) => !used.has(L)), rand);   // full random ensuite
    return order.concat(rest);
  }

  // Nb de lettres interdites après `words` mots : `start` dès le départ, +1 tous les `every`.
  function forbiddenCount(words, every, start = 0) {
    return start + Math.floor(words / every);
  }

  // Les lettres interdites actives = les `forbiddenCount` premières de l'ordre.
  function activeForbidden(order, words, every, start = 0) {
    return order.slice(0, forbiddenCount(words, every, start));
  }

  // Quelles lettres interdites (parmi `active`) apparaissent dans `word` (accents repliés).
  function offendingLetters(word, active) {
    const set = new Set(active);
    const hit = new Set();
    for (const ch of word) { const f = fold(ch); if (set.has(f)) hit.add(f); }
    return [...hit];
  }

  root.Letters = { FREQ, ALPHABET, rng, seedFromString, fold, drawOrder,
                   forbiddenCount, activeForbidden, offendingLetters };
})(window);
