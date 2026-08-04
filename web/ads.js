"use strict";
/* =============================================================================
   AdSense — unités MANUELLES (uniquement écrans départ + fin, jamais en jeu).

   Le loader officiel est déjà dans le <head> de index.html (nécessaire à la
   validation Google et au CMP RGPD). CE fichier se contente de POUSSER chaque
   unité au bon moment — mais seulement si son ID de bloc est vraiment renseigné.

   >>> APRÈS l'approbation AdSense : crée 2 blocs d'annonce (Display, responsive)
       et colle leurs ID numériques ci-dessous. Tant qu'ils valent "0000000000",
       aucune unité n'est poussée (rien ne s'affiche, aucune erreur). <<<
   ============================================================================= */
const AD_CLIENT = "ca-pub-7933464491322369";
const AD_SLOTS = { adStart: "0000000000", adEnd: "0000000000" };

(function () {
  const configured = (slot) => slot && !/^0+$/.test(slot);

  // On ne garde que les unités dont le bloc est réellement créé.
  const units = [...document.querySelectorAll("ins.adsbygoogle")].filter((ins) => {
    const slot = AD_SLOTS[ins.dataset.unit];
    if (!configured(slot)) return false;
    ins.setAttribute("data-ad-client", AD_CLIENT);
    ins.setAttribute("data-ad-slot", slot);
    return true;
  });
  if (!units.length) return;   // pas encore de blocs -> rien à pousser

  // Charge chaque unité seulement quand SON écran devient visible et a une
  // largeur > 0 (l'écran de fin est display:none au départ -> pas de pub à 0 px,
  // ce qui planterait AdSense). Un push par unité, une seule fois.
  const load = (ins) => {
    if (ins.dataset.loaded || ins.offsetWidth === 0) return;
    ins.dataset.loaded = "1";
    try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (_) {}
  };
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { load(e.target); io.unobserve(e.target); }
      });
    }, { threshold: 0 });
    units.forEach((ins) => io.observe(ins));
  } else {
    units.forEach(load);
  }
})();
