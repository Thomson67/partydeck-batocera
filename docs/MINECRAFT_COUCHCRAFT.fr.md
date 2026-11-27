# Minecraft 26.3 avec Couchcraft sur Batocera

Ce port x86‑64 installe CLauncher 1.0.3, Temurin 25 et Couchcraft 0.2.0.
L’installateur configure déjà l’instance en Minecraft 26.3 avec Fabric et le
pseudo local `Joueur1`. CLauncher télécharge le jeu, ses ressources et Fabric
quand tu appuies sur **Play** la première fois.

Depuis SSH sur Batocera, lance la commande suivante.

```bash
(
  revision=test/minecraft-couchcraft
  fichier=$(mktemp /tmp/partydeck-couchcraft.XXXXXX) || exit 1
  trap 'rm -f -- "$fichier"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/Thomson67/partydeck-batocera/$revision/install.sh" -o "$fichier" &&
    PARTYDECK_REVISION="$revision" bash "$fichier" minecraft-couchcraft
)
```

1. Actualise les listes de jeux d’EmulationStation, puis ouvre
   **Ports → PartyDeck - Minecraft 26.3 (Couchcraft)**.
2. Clique sur **Play** dans CLauncher. La première exécution télécharge
   Minecraft et Fabric. Tu peux modifier le pseudo local avant de jouer.
3. Ouvre un monde solo. Sur la manette de J2, appuie sur **Start / Options**
   et choisis son profil local. La même fenêtre accueille jusqu’à quatre
   joueurs. Chacun conserve son inventaire et sa progression dans le monde
   de J1.

L’entrée charge le rendu OpenGL standard avec Couchcraft. Fabric écarte
automatiquement Sodium et Iris dans cette session. Tu peux décocher l’option
de mods de performance de CLauncher pour éviter leurs téléchargements.
Les joueurs invités peuvent rejoindre un monde solo, y compris s’il est
ouvert sur le LAN. Les serveurs en ligne authentifiés sont hors de ce mode.

## Emplacements et diagnostic

Java 25 est dans `/userdata/system/windows-party/runtime/java/temurin-25.0.5.1+2`.
Le nouveau launcher, ses réglages, les mods et les mondes sont dans
`/userdata/system/windows-party/minecraft/couchcraft`. L’instance et son profil
sont séparés de ceux du test Minecraft 1.21.1.

Avec EmulationStation affiché, lance cette commande de diagnostic depuis SSH.

```bash
python3 /userdata/system/windows-party/minecraft/couchcraft/partydeck_couchcraft.py verifier
```

Le journal de CLauncher est dans `home/.clauncher/logs` dans le dossier Couchcraft.
Pour une erreur de chargement de mod, consulte aussi
`home/.clauncher/instances/Couchcraft/.minecraft/logs/latest.log`.

- [CLauncher 1.0.3](https://github.com/chepupel123/CLauncher/releases/tag/v1.0.3)
- [Couchcraft 0.2.0](https://github.com/zortos293/Couchcraft/releases/tag/v0.2.0)
- [Fabric pour Minecraft 26.3](https://fabricmc.net/2026/09/15/263.html)
