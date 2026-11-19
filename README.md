# Windows Party pour Batocera

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

## Installation

La branche de développement courante est `feature/gamepad-configurator`.
Fermez les jeux et le configurateur avant installation ou migration.

```bash
(
  fichier=$(mktemp /tmp/windows-party-install.XXXXXX) || exit 1
  trap 'rm -f -- "$fichier"' EXIT
  revision=feature/gamepad-configurator
  curl --http1.1 --retry 5 --retry-all-errors --retry-delay 2 -fsSL \
    "https://raw.githubusercontent.com/Thomson67/partydeck-batocera/$revision/install.sh" \
    -o "$fichier" && PARTYDECK_REVISION="$revision" bash "$fichier"
)
```

Après installation, actualisez les listes de jeux d’EmulationStation. Le système
**Windows Party** contient le configurateur et les jeux ajoutés.

## Utilisation

```bash
/userdata/system/windows-party/windows-party verifier
/userdata/system/windows-party/windows-party configurer
/userdata/system/windows-party/windows-party ajouter \
  "/userdata/roms/windows/Mon jeu.wsquashfs" 2 horizontal auto
```

Dans le configurateur, sélectionnez un profil commun ou ajoutez votre jeu.
Les sources restent dans `/userdata/roms/windows` ; les entrées Windows Party
sont de petits lanceurs. Les médias de scraping du jeu original sont réutilisés.
Le runner peut être choisi dans les options ES de Windows Party ; Auto reprend
celui du jeu Windows d’origine.

**Paramètres**, en bas de la bibliothèque, propose le choix global de l’écran et
du GPU. Le GPU du jeu sur Automatique hérite de ce choix. Un écran indisponible
entraîne un repli sur un écran actif ; la préférence reste conservée. Le
branchement/débranchement d’une station entraîne un replacement des fenêtres.
Les sorties du système ne sont pas activées/désactivées par Windows Party.
Voir [les paramètres d’affichage](docs/GLOBAL_DISPLAY_GPU.md).

**Stockage** permet de consulter l’occupation et d’entretenir les caches et les
journaux. Les sauvegardes et les réglages ne sont pas soumis à un quota.

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
Chaque instance reçoit une adresse distincte et peut utiliser les mêmes ports
UDP sans conflit. Le profil prépare `server.cfg` et une copie privée inchangée
de `server.dll`. Il ne simule ni clic de connexion ni création de salon.

1. J1 crée le serveur LAN et le salon.
2. J2 recherche et rejoint le salon de J1.
3. Lancez la course.

Un utilisateur a confirmé le démarrage d’une course à deux joueurs sur
Batocera v44 Wayland avec NVIDIA T550. Trois/quatre joueurs et d’autres
configurations restent à valider. Ce profil reste expérimental.

Dans **Réseau**, désactivez **LAN privé local (sans Internet)** pour utiliser le
réseau partagé du PC. L’adresse LAN manuelle devient alors disponible. Le LAN
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
| `/userdata/saves/windows-party/` | Préfixes persistants et sauvegardes par joueur |

L’ancienne installation est déplacée vers le nouveau dossier. Les profils,
paramètres, sauvegardes et fichiers utilisateur sont conservés. Les lanceurs
reconnus sont réécrits vers la commande `windows-party`. Les essais exploratoires
et leurs lanceurs identifiables sont archivés, jamais traités comme du cache.

Quelques liens de compatibilité, dont l’ancien chemin d’installation et
`party → runtime`, restent nécessaires aux chemins absolus déjà enregistrés
dans les préfixes Wine. Les nouveaux lanceurs utilisent uniquement le chemin
canonique. Les scripts personnalisés ne sont pas réécrits arbitrairement.

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

Install with the command above. The canonical entry point is
`/userdata/system/windows-party/windows-party`. Open **Configure Windows Party**
from ES. **Settings** below the library selects the global display/GPU; per-game
Automatic inherits the global GPU. Output disconnects fall back to an active
screen while retaining the preference. Existing running windows are repositioned
when output geometry changes. Internal game resolution changes on the next launch.

Most Wanted defaults to private LAN for two or more players. P1 creates a server
and lobby; P2 joins. A user confirmed a two-player race starting on Batocera v44
Wayland/NVIDIA T550. Other hardware and three/four-player races remain unvalidated.
Private LAN has no Internet/external LAN access; disabling **Local private LAN
(no Internet)** restores the shared PC network. Single-player and all other
profiles keep the shared network. The namespace mechanism is reusable, with
explicit per-profile opt-in rather than a global setting for all games.

Migration renames the previous installation, preserves profiles/saves, rewrites
recognised generated launchers and archives old exploratory data. Compatibility
links preserve absolute paths inside existing Wine prefixes. Regression tests
remain in the source repository. No game, mod or Nucleus save binaries are
redistributed.
