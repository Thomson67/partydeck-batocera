# PartyDeck Batocera

Prototype de lancement local de plusieurs instances d'un jeu Wine sur PC
Batocera x86-64 avec PartyDeck, Gamescope et le runner configuré dans
Batocera. Les entrées **Ports** gèrent de un à quatre joueurs, l'attribution
des périphériques et le placement des fenêtres.

Installation depuis SSH sur Batocera, avec EmulationStation affiché.

```bash
(
  fichier=$(mktemp /tmp/partydeck-install.XXXXXX) || exit 1
  trap 'rm -f -- "$fichier"' EXIT
  curl -fsSL https://raw.githubusercontent.com/Thomson67/partydeck-batocera/main/install.sh -o "$fichier" &&
    bash "$fichier"
)
/userdata/system/partydeck-test/partydeck-test verifier
```

Voir le [guide de configuration et de tests](docs/PARTYDECK_TEST.fr.md) pour
créer une entrée **Ports** et vérifier la session graphique.

Un test sur Batocera v43 sous Xorg a confirmé le placement haut et bas de
deux instances d'un jeu `.wsquashfs`. Les deux joueurs ont aussi été testés
simultanément sur un jeu autonome. Le placement sous v44 Wayland/labwc et
les dispositions à trois et quatre joueurs restent à valider sur machine.

Ce code provient de la
[branche expérimentale d'Ultimate Wine Toolbox](https://github.com/Thomson67/ultimate-wine-toolbox/tree/dd40946a9a0a11475c971871fc8f6ac5b51b9def).
L'AppImage officielle [PartyDeck](https://github.com/partydeck/partydeck)
et le pont [UMU Runner Toolbox](https://github.com/Thomson67/umu-runner-toolbox)
sont téléchargés et vérifiés à l'installation.

Vérification locale avec `python3 tests/check_coop.py`. Ce test simule les
entrées et les fenêtres. La vérification en jeu se fait depuis **Ports**.
