"use strict";
// Module PUR (aucun DOM). Exposé sur window (pas de bundler dans le projet).
(function (root) {
  // Fréquences des lettres en français (%). Sert à PONDÉRER le tirage : on veut
  // les lettres RARES d'abord (poids ∝ 1/fréquence), les courantes tard.
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

  // Ordre COMPLET des 26 lettres, tirées sans remise, pondérées par 1/fréquence
  // (rares d'abord). `rand` = fonction 0..1 (Math.random en endless, rng(seed) en daily).
  // Retourne la liste ordonnée : la i-ème lettre interdite = ordre[i].
  function drawOrder(rand) {
    const pool = ALPHABET.map((L) => ({ L, w: 1 / FREQ[L] }));
    const order = [];
    while (pool.length) {
      const total = pool.reduce((s, p) => s + p.w, 0);
      let r = rand() * total, idx = 0;
      while (r > pool[idx].w) { r -= pool[idx].w; idx++; }
      order.push(pool[idx].L);
      pool.splice(idx, 1);
    }
    return order;
  }

  // Nb de lettres interdites après `words` mots acceptés, 1 nouvelle tous les `every`.
  function forbiddenCount(words, every) {
    return Math.floor(words / every);
  }

  // Les lettres interdites actives = les `forbiddenCount` premières de l'ordre.
  function activeForbidden(order, words, every) {
    return order.slice(0, forbiddenCount(words, every));
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
