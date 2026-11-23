# Windows Party pour Batocera

Profil de test **Hollow Knight / HKMultiplayer 0.36.2** : connexion et code
automatiques, entrée native désactivée avec HIDRAW conservé.
Voir [le guide](docs/HOLLOW_KNIGHT_HKMULTIPLAYER.md).

Lancer plusieurs instances d’un jeu Windows sur un seul PC, avec des contrôles
attribués à chaque joueur et des fenêtres disposées en écran partagé.

- Formats `.wine`, `.pc` et `.wsquashfs`, conservés dans le système Windows.
- De un à quatre joueurs ; partage horizontal ou vertical à deux joueurs.
- Configurateur entièrement utilisable à la manette ou au clavier, clavier virtuel.
- Interface française lorsque Batocera est en français ; anglaise sinon.
- Paramètres globaux d’écran et de GPU, profils et options propres à chaque jeu.
- Sauvegardes séparées des parties solo, sans dupliquer les ROMs.
- Compatibilité Xorg et Wayland ; affichage multi-écran et reconnexion d’une station.

Le lancement repose sur le Gamescope de PartyDeck et sur Wine/les runners de
Batocera. Le dépôt ne distribue ni jeux, ni DLLs de jeux, ni sauvegardes Nucleus.

Ancien profil distinct [Hollow Knight / HKMP](docs/HOLLOW_KNIGHT_HKMP.md) : adaptation
de l'écran, serveur J1 et connexion automatiques après chargement d'une partie,
pseudos et options coop, activation privée d'ESoulLink et GhostHunter déjà installés.

## Installation

Cette branche de test combine **HKMultiplayer 0.36.2 / Native Wide 0.1.1** et les **bottles Windows mutualisées** : `test/shared-windows-bottles`.
Fermez les jeux et le configurateur avant installation ou migration.

```bash
(
  fichier=$(mktemp /tmp/windows-party-install.XXXXXX) || exit 1
  trap 'rm -f -- "$fichier"' EXIT
  revision=test/shared-windows-bottles
  curl --http1.1 --retry 5 --retry-all-errors --retry-delay 2 -fsSL \
    "https://raw.githubusercontent.com/Thomson67/partydeck-batocera/$revision/install.sh" \
    -o "$fichier" && PARTYDECK_REVISION="$revision" bash "$fichier"
)
```

Après installation, actualisez les listes de jeux d’EmulationStation. Le système
**Windows Party** contient le configurateur et les jeux ajoutés.

Au démarrage de chaque Gamescope, la limite souple de fichiers ouverts est relevée
jusqu’à 65 536, dans la limite du maximum système existant. La modification reste
dans le processus du joueur et ses descendants ; EmulationStation et la
configuration système ne sont pas modifiés. Les limites avant/après figurent
dans le journal. Cette protection vise les erreurs « Too many open files » ;
une fuite persistante de descripteurs dans le compositeur demande un diagnostic
supplémentaire et n’est pas corrigée par ce relèvement.

Each Gamescope child raises its soft open-file limit to at least 65,536 when
the existing hard limit allows it, preserving already higher limits. ES and
system settings are unchanged. The log records the inherited and effective
limits. This guards against low inherited limits; it does not fix a persistent
descriptor leak in the compositor.

## Utilisation

La branche de test propose l'hébergement et la connexion automatiques pour
SM64CoopDX et Left 4 Dead 2, ainsi qu'un compagnon SDK privé pour le LAN de
Borderlands 2. Le joueur hôte et le port sont configurables ; les profils
peuvent revenir au mode manuel. Voir les prérequis, les limites et la procédure
de test dans [Connexions automatiques](docs/AUTOMATIC_SESSIONS.md).

**English:** Test profiles support automatic SM64CoopDX/L4D2 sessions and a
private SDK LAN companion for Borderlands 2, with selectable host/port and
manual fallback. Live Batocera validation is required; see the linked guide.

```bash
/userdata/system/windows-party/windows-party verifier
/userdata/system/windows-party/windows-party configurer
/userdata/system/windows-party/windows-party ajouter \
  "/userdata/roms/windows/Mon jeu.wsquashfs" 2 horizontal auto
```

### CelesteNet en LAN

Préparez la version Windows de Celeste avec **Everest** et le **client
CelesteNet**. Lancez d’abord le jeu en solo pour vérifier que le mod apparaît.
Dans Windows Party, ouvrez **Session → Profil du jeu → Celeste / CelesteNet**
et choisissez de deux à quatre joueurs. Le premier lancement télécharge le
serveur officiel et, si nécessaire, le runtime .NET Linux. Les lancements
suivants réutilisent ces fichiers.

PartyDeck lance un serveur dans un réseau privé partagé et connecte les
clients à `localhost` au titre. Choisissez ensuite le même chapitre sur chaque
instance. Le jeu démarre en mode debug Everest pendant cette session pour
utiliser sa console locale. Le journal du serveur se trouve sous
`runtime/<jeu>/celestenet/server.log`.

**English:** Install Everest and the CelesteNet client in the Windows game,
then select **Celeste / CelesteNet** under **Session → Game profile** for two
to four players. The first launch downloads the private server dependencies.
PartyDeck starts the server and requests each client's connection at the
title screen. Pick the same chapter in each instance. Everest debug mode
provides the local console during the session.

La bibliothèque affiche uniquement les jeux ajoutés ; une nouvelle installation
commence avec une liste vide. **Inser / Select → Ajouter** propose deux choix :
**Depuis le catalogue** pour appliquer un profil prédéfini, ou **Manuellement**
pour choisir un jeu avec un profil standard vierge. Enregistrez ensuite pour
créer son entrée Windows Party. Les jeux déjà ajoutés restent conservés.

L’interface utilise tout le format de l’écran. Les noms de jeux disposent d’une
police plus petite et de deux lignes ; la jaquette du jeu sélectionné apparaît
en haut de la colonne gauche, au-dessus de la liste, à partir des images déjà scrapées dans Batocera (`gamelist.xml`,
boxart/box2d ou image/thumbnail). Les proportions sont conservées, sans modifier
les métadonnées. En descendant à la manette, l’ordre est jeux → Paramètres →
Stockage, comme à l’écran. **Start / Options** lance directement le jeu
sélectionné (**F5** au clavier). **Select / Share / Create** ouvre le menu
d’ajout. Le raccourci **HK + Start** reste réservé à la fermeture.

**English:** A fresh personal library is empty. Insert/Select → Add offers
**From the catalogue** (predefined profile) or **Manually** (blank standard
profile). Save to create the Windows Party entry; existing entries are kept.
The layout fills the screen, long titles use smaller type/two lines, and the
selected game’s existing Batocera cover is displayed above the list at upper left.
The title banner begins above the settings pane to its right. Navigation
follows games → Settings → Storage. Start/Options launches the selected game
(F5 on keyboard); Select/Share/Create opens Add. HK+Start still exits.
Les sources restent dans `/userdata/roms/windows` ; les entrées Windows Party
sont de petits lanceurs. Les médias de scraping du jeu original sont réutilisés.
Le runner peut être choisi dans les options ES de Windows Party ; Auto reprend
celui du jeu Windows d’origine.
L’option **Activer HIDRAW**, également disponible par jeu, propose Auto / Activé /
Désactivé. Auto hérite du réglage Windows d’origine. Chaque instance conserve
uniquement l’accès aux manettes qui lui sont attribuées.
**MangoHud** dispose du même choix Auto / Activé / Désactivé. Auto conserve le
réglage Windows/toolbox ; un choix explicite s’applique au jeu de chaque joueur.
Le runtime MangoHud de la toolbox est réutilisé s’il est installé ; sans lui,
l’activation Vulkan dépend des couches MangoHud déjà disponibles sur Batocera.
**Profil MangoHud** propose **Standard** (défaut en activation explicite),
**Minimal** (FPS) et **Détaillé** (CPU/GPU, températures, RAM/VRAM et frametimes).
Les couches Vulkan 32/64 bits de la toolbox sont déclarées dans des manifestes
propres à chaque joueur, également exposés au runtime UMU. Auto sans réglage
de profil conserve le fonctionnement Windows/toolbox existant.

Dans Most Wanted, **LB + RB** (PlayStation : **L1 + R1**) efface le texte initial **NOM / NAME** du champ actif,
saisit **J1**, **J2**, **J3** ou **J4** selon l’instance, puis valide avec **Entrée**.
À utiliser dans le champ de nom de sauvegarde ou de serveur. Une seule séquence
est envoyée jusqu’au relâchement ; ce raccourci est désactivable dans le profil
Most Wanted. Validation dans le jeu encore à tester.

**Paramètres**, en bas de la bibliothèque, propose le choix global de l’écran et
du GPU. Le GPU du jeu sur Automatique hérite de ce choix. Un écran indisponible
entraîne un repli sur un écran actif ; la préférence reste conservée. Le
branchement/débranchement d’une station entraîne un replacement des fenêtres.
Les sorties du système ne sont pas activées/désactivées par Windows Party.
Voir [les paramètres d’affichage](docs/GLOBAL_DISPLAY_GPU.md).

**Stockage** permet de consulter l’occupation et d’entretenir les caches et les
journaux. Les sauvegardes et les réglages ne sont pas soumis à un quota.
Dans **Jeux par taille**, sélectionnez un jeu pour nettoyer ses données Windows
Party. **Wine-bottles uniquement** conserve ses sauvegardes externalisées.
**Wine-bottles + sauvegardes** les supprime aussi. Les deux choix effacent les
sauvegardes encore stockées dans les préfixes. Le jeu d’origine et son profil
Windows Party sont conservés.

Les contrôles virtuels clavier/souris de la Wine Toolbox installée sont
réutilisés lorsqu’ils sont activés : HK+Select pour le clavier, HK+L3 pour la
souris. HK+Start reste la sortie du jeu. Les profils sont isolés par joueur.

## Profils de jeux

- **Ship of Harkinian / Anchor** : réseau, joueurs, graphismes et volumes ;
  musique limitée à J1 si souhaité.
- **Borderlands 2** : affichage adapté, préréglages graphiques, VSync, PhysX et
  noms des joueurs.
- **SM64CoopDX** : graphismes, caméra, langue, noms et volumes.
- **Left 4 Dead 2 / Goldberg** : identités distinctes et persistantes, contrôles,
  langue et affichage. Les fichiers de langue doivent être présents dans le jeu.
- **Most Wanted 2005** : configuration LAN et adaptation des mods déjà présents.
- **Standard** : lancement multiple et placement, sans options propres à un
  autre jeu. La compatibilité multi-instance dépend du jeu.

### Most Wanted : LAN privé local

Le LAN privé est activé par défaut dans ce profil à partir de deux joueurs.
Chaque instance reçoit une adresse distincte et utilise le port UDP `9900`.
Le profil prépare `server.cfg` et une copie privée inchangée
de `server.dll`. Il ne simule ni clic de connexion ni création de salon.

1. J1 crée le serveur LAN et le salon.
2. J2 recherche et rejoint le salon de J1.
3. Lancez la course.

Un utilisateur a confirmé le démarrage d’une course à deux joueurs sur
Batocera v44 Wayland avec NVIDIA T550. Trois/quatre joueurs et d’autres
configurations restent à valider. Ce profil reste expérimental.

Dans **Réseau**, désactivez **LAN privé local (sans Internet)** pour utiliser le
réseau partagé du PC avec un port par joueur (`9900` à `9903`).
L’adresse LAN manuelle devient alors disponible. Le LAN
privé n’a accès ni à Internet ni au réseau extérieur ; ES et SSH conservent
leur réseau habituel. En solo, le réseau reste partagé.

Le mécanisme `partydeck_private_lan.PrivateLAN` est commun et réutilisable.
L’activation est explicitement autorisée par profil dans `PRIVATE_LAN_PROFILES`.
Seul Most Wanted l’active actuellement : aucun autre jeu n’est modifié.
L’autovérification réseau peut être lancée indépendamment d’un jeu :

```bash
python3 /userdata/system/windows-party/partydeck_private_lan.py verifier 2
```

## Dossiers et migration

| Emplacement | Contenu |
| --- | --- |
| `/userdata/system/windows-party/` | Programme et dépendances |
| `profiles/` | Profils de jeux |
| `templates/` | Configurations communes SoH et SM64CoopDX |
| `desktop.json`, `storage.json` | Réglages globaux |
| `runtime/<jeu>/j1…j4/` | Données de travail privées des joueurs |
| `logs/` | Journaux |
| `releases/`, `assets/` | Binaires et ressources graphiques |
| `archive/legacy/` | Anciens essais conservés lors de la migration |
| `/userdata/roms/windows-party/` | Lanceurs et métadonnées ES |
| `/userdata/saves/windows-party/` | Sauvegardes externalisées par joueur et liens des anciennes installations |
| `/userdata/system/wine-bottles/windows-party/` | Bottles techniques privées, bases Windows et objets communs |

**Test de mutualisation Windows :** [fonctionnement, migration et validation](docs/SHARED_BOTTLES.fr.md). Les données utilisateur encore internes aux préfixes sont conservées individuellement. Le bilan Stockage distingue maintenant les bottles des sauvegardes.

**English:** Technical bottles move to `system/wine-bottles/windows-party`; identical Windows files use shared read-only layers with private writes. Externalized saves remain in `saves/windows-party`. Internal saves and registry data remain private and preserved. See the test notes above.

L’ancienne installation est déplacée vers le nouveau dossier. Les profils,
paramètres, sauvegardes et fichiers utilisateur sont conservés. Les lanceurs
reconnus sont réécrits vers la commande `windows-party`. Les essais exploratoires
et leurs lanceurs identifiables sont archivés, jamais traités comme du cache.

Quelques liens de compatibilité, dont l’ancien chemin d’installation et
`party → runtime`, restent nécessaires aux chemins absolus déjà enregistrés
dans les préfixes Wine. Les nouveaux lanceurs utilisent uniquement le chemin
canonique. Les scripts personnalisés ne sont pas réécrits arbitrairement.

## Journaux et UMU

Le journal principal de chaque lancement est créé dans
`/userdata/system/windows-party/logs/partydeck-<date>-<identifiant>`.
Les journaux UMU sont séparés par joueur dans
`runtime/<jeu>/jN/umu-logs/runner-*.log` ; les journaux Proton, lorsqu’activés,
sont dans le dossier voisin `proton-logs/`.

Le LAN privé est hors ligne : le runtime UMU/Steam nécessaire doit déjà être
installé. L’absence de route par défaut permet à UMU 1.4.4 de reconnaître ce
mode hors ligne. Le vérificateur du LAN contrôle aussi ce comportement avant
les échanges UDP entre joueurs.

**English:** Main launch logs are in `logs/partydeck-*`, per-player UMU logs in
`runtime/<game>/jN/umu-logs/runner-*.log`, and enabled Proton logs in the adjacent
`proton-logs/`. Private LAN is offline, so required UMU/Steam runtimes must be
installed beforehand. Having no default route lets UMU 1.4.4 detect offline mode;
the private LAN verifier checks this before its same-port UDP exchanges.

## Développement

Les vérifications automatisées se trouvent dans `tests/` : ces tests de
régression font partie du développement, pas des menus installés. Elles
couvrent les profils, les langues, l’isolation des fichiers, la sélection des
écrans, la fermeture des sessions et la migration. La création des espaces
réseau est bloquée dans l’environnement de développement ; la vérification
réelle du noyau s’effectue sur Batocera avec la commande réseau ci-dessus.

## English

Windows Party runs one to four Windows game instances on a single Batocera PC.
It supports `.wine`, `.pc` and `.wsquashfs`, controller-first configuration,
a virtual keyboard, per-game adapters, separate player saves and shared-screen
window placement on Xorg/Wayland. Game ROMs and scraped media are reused.
ES system and per-game options include **Enable HIDRAW** (Auto / Enabled /
Disabled). Auto inherits the original Windows game's setting. Each instance
retains access only to its assigned controllers.
**MangoHud** has the same Auto / Enabled / Disabled choices. Auto retains the
Windows/toolbox setting; explicit choices apply to each player's game. The
installed UWT MangoHud runtime is reused. Without it, Vulkan support depends
on the MangoHud layers available in Batocera.
**MangoHud profile** offers **Standard** (default when explicitly enabled),
**Minimal** (FPS) and **Detailed** (CPU/GPU, temperatures, RAM/VRAM, frametimes).
Toolbox 32/64-bit Vulkan layers use player-local manifests also exposed to UMU.
Auto with no profile selection retains the existing Windows/toolbox behavior.

For Most Wanted only, **LB + RB** (**L1 + R1** on PlayStation) clears the initial
**NOM / NAME** text from the active name field, types **J1**, **J2**, **J3** or **J4** for that instance, then sends
**Enter**. Use it with the save/server name field active. One sequence is sent
per chord press; the shortcut can be disabled in the profile.
Actual confirmation inside the game still needs testing.

Install with the command above. The canonical entry point is
`/userdata/system/windows-party/windows-party`. Open **Configure Windows Party**
from ES. **Settings** below the library selects the global display/GPU; per-game
Automatic inherits the global GPU. Output disconnects fall back to an active
screen while retaining the preference. Existing running windows are repositioned
when output geometry changes. Internal game resolution changes on the next launch.

Most Wanted defaults to private LAN for two or more players and uses port `9900`
for each instance on its own address. P1 creates a server
and lobby; P2 joins. A user confirmed a two-player race starting on Batocera v44
Wayland/NVIDIA T550. Other hardware and three/four-player races remain unvalidated.
Private LAN has no Internet/external LAN access; disabling **Local private LAN
(no Internet)** restores the shared PC network with separate ports (`9900` to
`9903`). Single-player and all other
profiles keep the shared network. The namespace mechanism is reusable, with
explicit per-profile opt-in rather than a global setting for all games.

Migration renames the previous installation, preserves profiles/saves, rewrites
recognised generated launchers and archives old exploratory data. Compatibility
links preserve absolute paths inside existing Wine prefixes. Regression tests
remain in the source repository. No game, mod or Nucleus save binaries are
redistributed.

## Désinstaller Windows Party

Dans le configurateur : **Paramètres → Désinstaller Windows Party**. La
confirmation sélectionne Annuler par défaut. Après validation, le nettoyage
retire l’application, les caches, les profils, les lanceurs générés et le
système EmulationStation. Redémarrer EmulationStation après l’opération.

Les sauvegardes `/userdata/saves/windows-party` restent présentes. Les préfixes
privés, identités et anciennes données de jeu qui pourraient contenir une
progression sont déplacés dans `.uninstall-preserved` sous ce dossier, avant
toute suppression. Les parties privées et le travail persistant des joueurs
sont remis en place à la réinstallation ; les autres archives de récupération
restent disponibles. Les anciens programmes et profils ne sont pas restaurés.
Les fichiers personnalisés non reconnus restent en place et sont signalés.

Les jeux Windows sources, les runners partagés et les autres outils Batocera
ne sont pas supprimés. Une session active ou un montage encore présent bloque
la désinstallation. Aucune désinstallation n’est exécutée lors de la mise à jour.

**English:** Settings → Uninstall Windows Party shows a confirmation (Cancel
selected by default), then a responsive progress screen. It removes the app,
caches, profiles, generated launchers and its ES system. Saves are retained;
private prefixes, identities and legacy game data are preserved under
`saves/windows-party/.uninstall-preserved` before deletion. Reinstall restores
persistent player state, not the old application/profiles; other recovery
archives remain available. Unrecognized personal files are retained and
reported. Source games and shared tools remain untouched. Active sessions and
mounts block the operation. Restart EmulationStation afterwards. Updating the
application does not execute an uninstall.
