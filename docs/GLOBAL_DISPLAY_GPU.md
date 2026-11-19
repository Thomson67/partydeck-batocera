# Écran et GPU globaux / Global display and GPU

Dans **Configurer Windows Party**, choisissez **Paramètres** en bas de la
bibliothèque. Tout est accessible à la manette et au clavier. Les changements
sont enregistrés immédiatement dans `/userdata/system/partydeck-test/desktop.json`.

- **Écran des jeux** : Automatique ou une sortie détectée, par exemple DP-4.
  Les positions réelles sont utilisées, même si aucun écran n’occupe 0,0.
  Une sortie désactivée n’est pas activée par PartyDeck. Si l’écran demandé est
  absent/désactivé, un écran actif est utilisé et le choix reste enregistré.
- **GPU par défaut** : Automatique, Configuration système ou NVIDIA. Le mode
  Automatique conserve la détection hybride existante ; Configuration système
  garde les sélecteurs de Batocera. Les sélecteurs GPU explicites hérités sont
  respectés en mode automatique. Ce réglage s’applique au prochain lancement.
- **Actualiser les écrans** : relire la liste après branchement d’une station.

Le GPU d’un jeu sur Automatique utilise le réglage global ; un choix explicite
Configuration système ou NVIDIA dans le profil du jeu reste prioritaire.

Pendant une partie, la zone de l’écran choisi est vérifiée toutes les deux
secondes. Après débranchement/reconnexion, les fenêtres Gamescope détenues par
la session sont replacées si la zone change. Il n’y a ni changement des sorties
Batocera, ni arrêt/redémarrage du jeu. La résolution interne configurée au
démarrage du jeu reste identique jusqu’au lancement suivant ; redimensionner
la fenêtre externe peut donc produire une mise à l’échelle après un changement
de résolution d’écran.

Sous Wayland, `wlr-randr` fournit les sorties actives et leurs positions,
transformations et échelles. Les coordonnées Xwayland sont utilisées pour
les connecteurs correspondants si son origine diffère. Sous Xorg, les moniteurs actifs de `xrandr` sont
utilisés, avec priorité à la sortie primaire. En automatique sous Wayland, la
sortie active la plus à gauche est choisie en l’absence de primaire déclaré.

Tests automatisés : station avec DP-4 à 1920,0, DP-7 à 3840,0 et eDP-1 désactivé,
repli/reconnexion, rotation/échelle, primaire Xorg, héritage GPU, boucle de
replacement sans relancement et interface FR/EN clavier/manette. Le branchement
physique réel reste à valider sur Batocera.

## English

Open **Configure Windows Party**, then **Settings** below the library.
Controller and keyboard navigation are supported. Changes save immediately to
`/userdata/system/partydeck-test/desktop.json`.

**Game display** selects Automatic or a detected connector. Actual output
positions are used, including layouts with no active output at 0,0. Missing or
disabled selected outputs fall back to an active output while retaining the
preference. PartyDeck does not enable/disable outputs. **Default GPU** offers
Automatic, System configuration and NVIDIA, applying on the next launch.
Per-game Automatic inherits the global GPU; explicit per-game choices override
it. **Refresh displays** rescans after docking.

Running sessions check output geometry every two seconds and reposition only
their owned Gamescope windows after geometry changes, without restarting games.
Internal game resolution stays at its launch value, so a different display
resolution may scale the image until the next launch. Wayland discovery uses
wlr-randr active outputs, aligned to matching Xwayland connector coordinates;
Xorg uses xrandr active monitors with primary
preference. Automatic Wayland selection uses the leftmost active output when
no primary is declared.

Automated tests cover the reported dock layout, fallback/reconnection,
rotation/scaling, Xorg, GPU inheritance, live session repositioning and FR/EN
controller/keyboard UI. Physical hotplug still requires testing on Batocera.
