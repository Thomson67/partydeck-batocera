# Minecraft Java sur Batocera

Le port Minecraft de PartyDeck cible Batocera PC x86-64. Il lance le client Linux
avec Java 21 et SKlauncher 3.2.18. EmulationStation affiche le jeu dans **Ports**.

## Installation depuis SSH

```bash
(
  revision=test/minecraft-native
  fichier=$(mktemp /tmp/partydeck-minecraft.XXXXXX) || exit 1
  trap 'rm -f -- "$fichier"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/Thomson67/partydeck-batocera/$revision/install.sh" -o "$fichier" &&
    PARTYDECK_REVISION="$revision" bash "$fichier" minecraft
)
```

L'installateur conserve Java 21 dans `/userdata/system/windows-party/runtime/java`.
Il réutilise un Java 21 déjà présent à cet emplacement. Si nécessaire, il copie
celui de `/userdata/system/partydeck/runtime/java`, ou télécharge le runtime
Temurin x86-64 vérifié. JavaFX se trouve dans le même dossier.
Le lanceur, les mods et les données de jeu résident dans
`/userdata/system/windows-party/minecraft`.

Actualise les listes de jeux d'EmulationStation et ouvre **Ports → PartyDeck -
Minecraft Java**. Dans SKlauncher, connecte le compte Minecraft de J1 et choisis
une des deux installations préparées. SKlauncher télécharge les fichiers
du jeu au premier lancement.

## Deux profils de test

| Profil | Usage |
| --- | --- |
| **PartyDeck - Minecraft Vanilla** | Minecraft 1.21.1 pour tester Java, SKlauncher, la fenêtre, le clavier et la souris |
| **PartyDeck - Minecraft Coop** | Minecraft 1.21.1, Fabric 0.16.5, Hot-Join 0.4.0 et Legacy4J pour jouer à plusieurs avec des manettes |

Commence par **Vanilla** si SKlauncher s'affiche mais que le jeu ne démarre pas.
Pour la coop, choisis le profil dédié et ouvre ou crée un monde avec J1.
L’installateur prépare le pilote **SDL** dans les options de Legacy4J. Appuie sur
**Pause / Options** sur une manette libre. Choisis le profil du joueur invité
quand le menu s'affiche. Hot-Join lance son instance, la connecte au monde et
redimensionne les fenêtres. Il peut prendre une trentaine de secondes pour
ouvrir l'instance et prend en charge jusqu'à quatre joueurs.

Fabric API, Concentration et TwinSession sont installés avec Hot-Join et
Legacy4J. Les dossiers `vanilla` et `coop` ont leurs propres réglages et mondes.
Les invités utilisent des dossiers séparés créés par Hot-Join. Réutilise leur
profil pour retrouver leur inventaire et leur progression dans le monde de J1.

## Diagnostic

Avec EmulationStation affiché, lance depuis SSH.

```bash
python3 /userdata/system/windows-party/minecraft/partydeck_minecraft.py verifier
```

Pour ouvrir SKlauncher depuis la session graphique d'EmulationStation via SSH,
remplace `verifier` par `jouer`. Le diagnostic indique le Java sélectionné,
la version de JavaFX attendue, le chemin de SKlauncher, le DISPLAY et la taille
signalée par XRandR. Si XWayland signale 8×8 avant l'ouverture de SKlauncher,
refais le diagnostic avec la fenêtre ouverte dans un autre terminal ou relève
ce que montre `xrandr --current` sur le DISPLAY indiqué.

- [SKlauncher et son téléchargement Linux](https://skmedix.pl/downloads/)
- [Hot-Join et le fonctionnement du split-screen](https://modrinth.com/mod/hotjoin)
- [Legacy4J et les réglages des manettes](https://modrinth.com/mod/legacy4j)
