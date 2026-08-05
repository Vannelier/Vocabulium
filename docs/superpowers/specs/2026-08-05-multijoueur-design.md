# Vocabulium — Mode « Multijoueur » (design)

Date : 2026-08-05
Statut : validé (brainstorming), à implémenter
Branche : `feat/multijoueur`

## Contexte & objectif

Vocabulium est un jeu de chaînage sémantique (on enchaîne des mots proches, cosinus
FastText). Le mode solo « aléatoire » tourne bien et est déployé. Le **mode du jour**
(`daily`) manque de fun ; on le **remplace** par un mode **multijoueur** temps réel,
pensé pour la **viralité** (on joue à plusieurs, on partage un lien, on invite ses amis).

Principe (façon *Tic Tac Boom*) : **chaîne partagée**, chacun à son tour pose un mot qui
colle au précédent, avant que sa jauge ne se vide. La stratégie consiste à orienter la
chaîne vers des thèmes obscurs pour **coincer** le joueur suivant. Dernier en vie gagne.

**Contrainte cardinale : c'est un *mod* du mode aléatoire, pas un nouveau jeu.** On
réutilise le cœur d'`app.js` (jauge, lettres interdites, rang/score, portail, trail,
juice) sans le réécrire. Le nouveau code est de l'**enveloppe** : état serveur autoritaire
+ WebSocket + salon + affichage des vies.

## Le gameplay (verrouillé)

- **Chaîne partagée, 1 mot par tour** (Modèle 1). Tu hérites du mot laissé par le joueur
  précédent, tu poses **un** voisin valide, puis le tour passe au suivant.
- **La jauge = le chrono** (celle du solo, `gauge_seconds`). Elle **repart au max** quand
  un mot est joué et passe au joueur suivant. À **sec pendant ton tour → −1 vie**, puis on
  passe au suivant (qui hérite du **même mot courant**, jauge neuve).
- Un mot doit : **coller au précédent** (cos ≥ seuil, via `/api/hop`), **ne pas** contenir
  de **lettre interdite** active, **ne pas** avoir déjà été joué dans la partie. Un refus
  (trop loin / lettre interdite / déjà joué / inconnu) ne coûte **que du temps** (grignote
  ta jauge), comme en solo.
- **Lettres interdites : progression PARTAGÉE sur la chaîne.** +1 lettre tous les
  `LETTER_EVERY` (=5) mots **acceptés** (cumulatif sur toute la partie, tous joueurs
  confondus). Réutilise le module `Letters` tel quel. C'est le seul système d'escalade :
  plus la partie dure, plus c'est dur **pour tout le monde** → les éliminations tombent
  naturellement, pas besoin de raccourcir le temps.
- **3 vies par joueur.** **2 à 6 joueurs.**
- **Dernier en vie = gagnant.** Le **score est décoratif** (gloire / classement /
  partage), il ne décide **pas** de la victoire.

## Architecture — état serveur autoritaire, rendu client

En solo, la machine à états vit dans le navigateur. En multi, **elle doit vivre sur le
serveur** (autoritaire) qui broadcast l'état par WebSocket : 6 clients ne peuvent pas
rester synchro autrement, et on ne peut pas laisser un client décider « à qui le tour /
qui est en vie ».

**Infra : Approche 1 — un seul process FastAPI, salons en mémoire, WebSockets.**
Tous les salons vivent dans un `dict` du process uvicorn actuel ; chaque salon a ses
connexions WS ; le serveur broadcast l'état à chaque événement. Le modèle (~50 Mo,
`vectors.f16.npy`) est chargé **une fois**. Des centaines de salons × 6 joueurs = quelques
milliers de connexions WS quasi inactives entre les tours, une validation ~ms par coup →
un seul instance Railway encaisse. **Couture propre** : toute la logique salon est isolée
derrière un `RoomManager` (salons adressés par code), pour que passer plus tard à Redis
(multi-instances) soit un changement **contenu**, pas une réécriture.

*Compromis assumé v1 :* si le process redémarre, les parties en cours tombent (une partie
dure ~minutes → acceptable).

### Frontière client / serveur

**Serveur autoritaire sur ce qui compte :**
- La liste des salons et des joueurs (pseudo, couleur, vies, vivant/mort, hôte).
- Le **mot courant**, le `played` Set, l'ordre + le compteur des lettres interdites
  (`forbiddenOrder`, `wordCount`) — la progression est partagée.
- **À qui le tour**, et le **chrono de référence** (heure de début de tour + durée). Le
  serveur tranche le **timeout** : pas de mot valide avant la deadline → il déclare −1 vie
  et passe le tour.
- La **validation** d'un mot : réutilise les **fonctions de scoring** (`score_hop` de
  `scoring.py`, le vocab de `db.py` — la même logique que sert `/api/hop`, appelée en
  interne, pas via un aller-retour HTTP) + le check lettres interdites (rejoué côté serveur
  pour l'autorité) + anti-rejouage. En multi, le client ne tape plus `/api/hop` : il envoie
  le mot par WebSocket.

**Client (réutilisé quasi verbatim depuis `app.js`) :**
- Tout le **rendu** : jauge, bande lettres interdites, portail, jauges rareté/vitesse,
  trail, toasts, `.beat`, `screenShake`, étincelles — **piloté par l'état poussé** par le
  serveur au lieu de l'état local.
- Le **score / rang décoratif** : calculé **côté client** (on réutilise toute la math de
  rang : `RANK_MULT`, `addFill`, `FILL_STEP`…), **zéro portage Python**. Qu'un joueur
  gonfle son score décoratif est sans conséquence (la survie fait gagner).
- La **jauge animée localement** pour la fluidité (le serveur reste le juge du timeout).
- Le **check lettres interdites en direct** dans la saisie (highlight rouge) et le
  feedback de refus, réutilisés tels quels.

### Flux d'un tour

1. Serveur : `turn_start` broadcast → `{ current, activePlayer, deadline, forbidden[], wordCount }`.
2. Client actif : saisie activée, jauge animée depuis `deadline`. Les autres : saisie
   grisée, ils voient **la jauge du joueur actif** défiler.
3. Le joueur actif soumet un mot **via WebSocket** (pas d'appel REST direct au scoring).
4. Serveur valide (proximité + lettres interdites + anti-rejouage) :
   - **Accepté** → ajoute au `played`, avance `wordCount` (peut déclencher une nouvelle
     lettre interdite), met à jour `current`, **passe au joueur vivant suivant**, jauge
     neuve → `hop_accepted` + `turn_start` broadcast. Le client calcule le juice + le
     score décoratif du joueur qui a joué.
   - **Refusé** → `hop_rejected` (raison) au joueur actif seulement ; la jauge continue.
5. Deadline atteinte sans mot valide → serveur : **−1 vie** au joueur actif → `life_lost`
   broadcast (déclenche le juice de perte de vie), puis passe au suivant (même `current`,
   jauge neuve). À 0 vie → le joueur est **éliminé**.
6. Quand il ne reste qu'**un vivant** → `game_over` broadcast (gagnant + scores).

## La boucle de salon (le moteur viral)

- **Menu** : le bouton « Mot du jour » devient **« Multijoueur »** → **Créer** ou
  **Rejoindre** (saisir un code). Le bouton « Mot aléatoire » (solo) est inchangé.
- **Créer** : le serveur crée un salon, renvoie un **code à 4 lettres** lisible (ex.
  `ROSE`). L'hôte voit le **lobby** : code en gros + **lien partageable**
  (`vocabulium.fr/?room=ROSE`) + **liste des joueurs** en temps réel + bouton **Lancer**
  (hôte seulement, actif dès **2** joueurs).
- **Rejoindre** : ouvrir le lien (ou taper le code) → saisir un **pseudo** (pas de compte,
  pas d'auth) → même lobby, la liste grandit en direct. Couleur d'avatar assignée depuis
  la palette.
- **On ne rejoint qu'au lobby** (pas en cours de partie) pour la v1.
- **Fin** : dernier vivant → écran de fin (gagnant + classement des scores décoratifs +
  **grille d'emojis partageable**, réutilisée du solo). Retour au lobby ou menu.
- **Déconnexion (v1 simple)** : un joueur qui quitte/se déconnecte est retiré de la
  partie, son tour est sauté. Reconnexion élégante (reprendre sa place) = plus tard.

## UI / Layout (mobile-first, mod du solo)

Ordre de l'écran de jeu, **identique au solo** sauf le haut :

1. **Topbar** : `Vocabulium` + **code du salon**. *(On retire le Record : inutile en multi.)*
2. **Bandeau joueurs** (NOUVEAU, récupère la place du Record + du Mot bonus) : une rangée
   de 2 à 6 jetons. Chaque jeton = **avatar coloré** (initiale) + **pseudo** + **3 cœurs**
   (♥ pleins roses / ♡ éteints). États :
   - **Toi** : cadre néon **discret** (cyan) → on se retrouve d'un coup d'œil.
   - **Joueur actif** (tour en cours) : halo **rose qui pulse** + avatar cerclé.
   - **Mort** : grisé (opacité ~0.3).
   - Une seule source de vérité pour les vies : **pas** de doublon de cœurs ailleurs.
3. **HUD** : score + rang **décoratifs** (les tiens). *(On retire le bloc Mot bonus / cible.)*
4. **Indicateur de tour** : « ◆ À TOI DE JOUER ◆ » / « ◆ AU TOUR DE LÉA ◆ ».
5. **Jauge** : celle du **joueur actif** (la tienne à ton tour).
6. **Bande lettres interdites** (partagée) + « prochaine dans N ».
7. **Trail** (FIFO 3 lignes) → **Mot courant** → **Portail** → jauges rareté/vitesse.
8. **Saisie** : activée seulement à ton tour ; sinon grisée + « en attente ».

Contraintes mobile (héritées du solo) : lettres interdites + mot courant + saisie doivent
tenir **au-dessus du clavier**. Retirer Record + Mot bonus dégage la place du bandeau
joueurs. Pas de scroll horizontal ; le bandeau à 6 tient sur une ligne (jetons `flex:1`).

## Le juice (« à mort »)

Réutilise les mécaniques existantes (`levelflash`, `screenShake`, `.beat`, étincelles) :

- **Un autre joueur perd une vie** → `levelflash` **blanc** + `screenShake('s')` + le cœur
  concerné qui se brise dans son jeton.
- **Toi** tu perds une vie → `levelflash` **rose** (`--pink #ff2e97`) + `screenShake('l')`
  + `.beat` « −1 ❤️ ». Bien plus violent : c'est toi qui morfles.
- **Mot accepté** : tout le juice solo (toast score, rang qui monte, étincelles si rare,
  glow) pour le joueur qui a joué.
- **Élimination d'un joueur** / **victoire finale** : `.beat` plein écran dédié.

## Découpage technique

**Serveur (nouveau, Python) :**
- `app/rooms.py` — `RoomManager` + `Room` + `Player` (état en mémoire). Génère les codes,
  gère joueurs/vies/tour/timeout, la progression des lettres interdites partagée, le
  `played` Set. **Aucun état global hors du `RoomManager`** (couture pour Redis plus tard).
- `app/ws.py` — endpoint `@app.websocket("/ws/{code}")` : connexion, réception des actions
  (`join`, `start`, `hop`), broadcast de l'état du salon. Réutilise la validation de
  `scoring.py` / `db.py` pour le hop.
- Le chrono/timeout : une tâche par salon (ou une boucle qui balaie les salons actifs) qui
  déclenche la perte de vie à la deadline.

**Client (nouveau, vanilla, sans bundler comme le reste) :**
- `web/multi.js` — client WebSocket + machine de rendu pilotée par l'état serveur.
  **Réutilise** les fonctions de rendu d'`app.js` (à extraire proprement si besoin :
  `renderForbidden`, `renderRank`, `pushTrail`, `showDetail`, `toastScore`, juice…).
- Écrans **lobby** (créer/rejoindre/liste joueurs) et **bandeau joueurs** (nouveau HTML/CSS
  dans `index.html` + `style.css`, palette réutilisée).
- Menu : « Mot du jour » → « Multijoueur ».
- Réutilise l'écran de fin + la grille de partage.

**Refactor ciblé (au service du mod) :** extraire d'`app.js` les fonctions de rendu pures
réutilisables pour que `multi.js` les partage sans dupliquer. On ne refactore rien d'autre.

## Scalabilité — la couture

L'Approche 1 couvre réellement des **centaines de salons** sur un instance. Pour aller
au-delà plus tard sans réécriture :
- `RoomManager` est la **seule** porte d'accès à l'état → on peut y brancher un backing
  Redis (ou un routage collant par salon) sans toucher au gameplay.
- La validation (`/api/hop`, modèle) est déjà **stateless** → elle peut être extraite en
  service séparé (Approche 3) le jour où le temps-réel et le modèle doivent scaler sur des
  axes distincts.

## Hors périmètre (v1)

- Rejoindre / spectater une partie **en cours**, reconnexion élégante après déconnexion.
- **Mot bonus / cible** en multi (retiré ; course au bonus partagé = plus tard).
- Score **autoritaire** serveur, persistance des scores, leaderboard serveur, comptes/auth.
- Redis / multi-instances (la couture est prête, pas l'implémentation).
- Son / SFX.

## Paramètres réglables

- `LETTER_EVERY = 5`, `START_FORBIDDEN = 0` — inchangés (partagés sur la chaîne).
- `gauge_seconds` — le chrono par tour (réutilise la constante solo). `FIRST_GAUGE_FACTOR`
  pour le tout premier tour, à décider (probablement neutralisé en multi).
- `LIVES = 3`, `MIN_PLAYERS = 2`, `MAX_PLAYERS = 6`.
- Longueur du code salon (4 lettres), alphabet du code (lisible, sans ambiguïté O/0…).
