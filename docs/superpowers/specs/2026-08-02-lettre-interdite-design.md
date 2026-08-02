# Vocabulium — Mode « Lettre interdite » (design)

Date : 2026-08-02
Statut : validé (brainstorming), à implémenter

## Contexte & objectif

Vocabulium est un jeu de chaînage sémantique (on enchaîne des mots proches, cosinus
FastText). Le proto tourne bien et est déployé, mais **les runs se ressemblent trop** :
même loop à chaque partie, seul le mot de départ change.

Objectif produit : **jeu web viral financé par la pub (AdSense)** → il faut du **gros
trafic**. La stratégie gagnante = un **loop ultra-simple, compris en 5 s, sans
onboarding**, très rejouable, partageable (modèle Wordle / 2048). Mobile visé très
bientôt → **design mobile-first**.

## Le mécanisme

**Pitch (ce que le joueur comprend seul) :** *Enchaîne des mots proches. Interdit
d'utiliser les lettres barrées. Va le plus loin possible.*

- On chaîne comme aujourd'hui : chaque mot doit être proche du précédent.
- **Tous les `LETTER_EVERY` (=10) mots ACCEPTÉS (fort ou faible), une lettre devient
  interdite**, cumulatif : 0 lettre (mots 1–10), 1 lettre (11–20), 2 lettres (21–30)…
- **Tirage pondéré par rareté** : les lettres rares en FR (`w k z x j q`) sortent tôt,
  les courantes (`e a s i t n r`) rarement et tard. On ne re-tire pas une lettre déjà
  interdite. → difficulté qui monte naturellement, jamais « e » dès le début.
- **Accent-insensible** : interdire `e` interdit aussi `é è ê ë` ; `c` interdit `ç`, etc.
  (on replie les accents avant le test).
- Un mot contenant une lettre interdite = **refusé** (on réessaie). Ce n'est **ni un
  raté du filet, ni une casse de combo** — juste « ce mot est illégal, choisis-en un
  autre ». La jauge continue de se vider → le seul coût est le **temps**.
  - **Feedback du refus** : la (les) lettre(s) interdite(s) présente(s) dans le mot
    **clignotent en rouge dans la bande des lettres interdites** → le joueur voit
    *exactement* quelle lettre a bloqué. (En plus du highlight live dans la saisie.)
- La **jauge** se vide, chaque mot valide la recharge. À sec = fin. Plus de lettres
  interdites = plus dur → **fin naturelle**, courbe de difficulté auto-montante.

## Simplification du scoring (clarté sans onboarding)

- **Retirer le bank-or-push** : plus de `pending`, plus de bouton Encaisser, plus de
  Tab. Chaque mot ajoute **directement** `hop_points × combo` au score. Le seul risque
  devient la **jauge** (survivre) + les lettres interdites.
- Le **combo (multiplicateur)** reste (monte sur hop fort, figé sur faible/écho, filet
  de 2 ratés). Toujours juicy.
- **Rareté & vitesse restent VISIBLES** (jauges de score juicy, demande explicite) et
  continuent d'alimenter le score. Le portail (proximité, compact) reste aussi comme
  feedback valide/écho/trop-loin.
- Le reste des internals (formule exacte, zones) reste invisible : le joueur voit
  « +240 🔥 », les 2 jauges, le portail.

## Deux saveurs du MÊME jeu

- **Sans fin** : mot de départ aléatoire (`/api/seed?mode=random`). Rejouable à
  l'infini → le « encore une » (= pages vues = impressions pub).
- **Défi du jour** : mot de départ **et séquence des lettres interdites** identiques
  pour tous aujourd'hui, dérivés de la date (le `mode=daily` déterministe existe déjà).
  → hook viral (on compare, on partage).

La **séquence des lettres** du défi du jour est déterministe : dérivée de `hash(date)`,
tirage pondéré reproductible. En sans-fin, elle est aléatoire par run (graine locale).

## UI (mobile-first, clarté sans mots)

Colonne unique, grosses cibles tactiles. De haut en bas :

1. **Score** (gros) + `combo ×N` + compteur de mots.
2. **Bande des lettres interdites**, très visible : `INTERDIT ⟶ K W Z` (grosses lettres
   rouges barrées), avec un **compteur de progression `N/10`** vers la prochaine lettre
   (ex. « prochaine dans 4 » ou une petite jauge/`6/10`) → le joueur anticipe l'arrivée
   d'une nouvelle interdiction. Quand une nouvelle tombe → **beat plein écran** « ⛔
   LETTRE INTERDITE : W » (~0,8 s) + son (plus tard). Une lettre du mot refusé clignote
   ici en rouge (voir mécanisme).
3. **Mot courant** (grand).
4. **Champ de saisie** — avec **la feature anti-onboarding** : pendant la frappe, si le
   mot tapé contient une lettre interdite, **elle s'allume en rouge en direct** (avant
   validation). Enseigne la règle sans une phrase.
5. **Jauge** (temps/vies) juste sous la saisie.
6. **Portail (compact)** + **jauges rareté / vitesse** (juicy) sous la jauge.

Contraintes mobile : tout le nécessaire (lettres interdites, mot courant, saisie) doit
tenir **au-dessus du clavier virtuel** (moitié haute). Le trail (FIFO 3 lignes) et les
jauges peuvent être plus haut. Pas de scroll horizontal, cibles ≥ 44 px.

## Écran de fin + partage (moteur de trafic)

- Récap : `52 mots · survécu à 3 lettres interdites 🔥 · meilleur : …`.
- **Grille d'emojis partageable** (façon Wordle), ex. une ligne par palier de lettres :
  `Vocabulium 02/08 — 52 mots\n🟩🟩🟩⬛ 🟩🟩🟥 …` (format à finaliser).
- Boutons **Partager** (Web Share API / copie presse-papier) + **Rejouer**.
- Emplacement **pavé pub** ici (moment de pause, clavier baissé sur mobile).

## Emplacement pub (mobile-aware)

- **Écran de départ + écran de fin** = zones pub principales (clavier baissé, attention
  pleine, stable → bonnes impressions AdSense).
- **Desktop uniquement** : un footer fixe stable peut s'ajouter pendant le jeu.
- **Mobile en jeu** : pas de footer (le clavier le masque) → on garde propre.
- **Règle d'or** : **jamais** de pub collée au champ de saisie / aux boutons (mis-clic
  en frappe rapide = violation AdSense + rage). Marge de sécurité obligatoire.

## Découpage technique

- **Client** : tout le mécanisme lettre-interdite (test de chaîne, escalade, highlight
  live, beat) est côté client. Le serveur valide déjà le hop (proximité).
- **Scoring** : retirer `pending`/bank côté client ; score direct `+= hop_points × mult`.
- **Seed** : le **client** dérive la séquence de lettres de la date (`hash(date)` →
  tirage pondéré reproductible) pour le défi du jour — même date = même séquence pour
  tous, sans changement backend. En sans-fin, il tire localement (graine aléatoire).
- **Refonte UI** : nouvel agencement (bande lettres, beat, highlight live), retrait du
  bloc Encaisser, conservation jauges rareté/vitesse + portail compact.
- **Écran de fin** : récap + génération de la grille d'emojis + partage.

## Hors périmètre (plus tard, si ça décolle)

- Autres modes (atteindre un mot cible en N coups…).
- Leaderboard serveur (persistance des scores) — le partage/daily suffit au lancement.
- Son / SFX (prévu, mais après).

## Paramètres réglables (constantes)

- `LETTER_EVERY = 10` (mots par palier ; baisser à ~6–8 si le hook est trop lent).
- Poids du tirage des lettres (table de fréquence FR inversée).
- `GAUGE_SECONDS`, poids de score, combo — inchangés (déjà calibrés).
