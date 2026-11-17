# Tester PartyDeck sur Batocera

Ce prototype s'installe dans `/userdata/system/partydeck-test` et se configure depuis SSH.
Il utilise PartyDeck v0.8.7-e avec Gamescope et UMU. L'installation demande un
PC x86-64 et un accès à GitHub.
L'UMU embarqué passe par le pont d'UMU Runner Toolbox lorsque la session
Batocera tourne en root. Le pont est installé dans le dossier de test.

## Installer

Décompressez le paquet du projet ou clonez son dépôt, puis lancez cette
commande depuis la racine du projet.

```bash
bash scripts/install-partydeck-test.sh installer
```

Sur une machine qui a déjà le prototype Ultimate Wine Toolbox, la même
commande met à jour le lanceur. Les entrées Ports existantes et les données
des joueurs restent dans leurs emplacements actuels.

## Vérifier et jouer

Avec EmulationStation affiché, lancez le diagnostic depuis SSH.

```bash
/userdata/system/partydeck-test/partydeck-test verifier
```

Le journal indique le type de session et l'état des dépendances. Gamescope a
besoin de Xwayland pour ses fenêtres internes, y compris quand Batocera utilise
Xorg comme session principale. Si Batocera fournit Xwayland, le script l'utilise.
Sinon, la première vérification télécharge une version portable dont les paquets
sont vérifiés par SHA-256. Elle est rangée dans
`/userdata/system/partydeck-test/releases` et utilisée uniquement par le test
PartyDeck.

## Windows Party

L'installation crée un fichier dédié
`/userdata/system/configs/emulationstation/es_systems_windows-party.cfg`.
Le système apparaît après un redémarrage d'EmulationStation. Son entrée
**Configurer Windows Party** permet d'ajouter un jeu et de modifier les profils. Son thème est celui de Windows.

Le gestionnaire utilise Yad. Le bouton **Ajouter un jeu** propose une archive
`.wsquashfs` ou un dossier `.wine` ou `.pc`. Les réglages sont enregistrés par
jeu. Ouvrir ensuite son entrée démarre directement la session.

La case **Afficher ces réglages avant chaque lancement** permet de rouvrir
l'éditeur avant la session. Annuler conserve le profil et quitte le lancement.
Si un profil est absent, l'éditeur est proposé au lancement pour le recréer.

Depuis SSH, la commande suivante ouvre aussi le gestionnaire.

```bash
/userdata/system/partydeck-test/partydeck configurer
```

Pour ajouter directement un jeu depuis SSH, utilisez `ajouter`. Les formats acceptés sont
`.wine`, `.pc` et `.wsquashfs`.

```bash
/userdata/system/partydeck-test/partydeck ajouter \
  "/userdata/roms/windows/Mon Jeu.wsquashfs" 2 horizontal clavier-j2
```

Au premier ajout, redémarrez EmulationStation. Pour les ajouts suivants,
actualisez les listes, puis ouvrez le jeu dans **Windows Party**.
Le jeu démarre directement avec le runner et l'`autorun.cmd` lus par
`batocera-wine`. Les lanceurs `.sh` dans `/userdata/roms/windows-party` référencent le jeu
Windows d'origine et enregistrent les réglages multijoueurs.
Les sauvegardes sont isolées sous
`/userdata/saves/windows-party/<jeu> [identifiant]/jN`. Le sous-dossier
`windows` reçoit les sauvegardes externalisées. `prefixes` conserve les
préfixes Wine des jeux compressés et `content` les écritures des jeux
`.wine` et `.pc`, y compris les sauvegardes internes au préfixe.
Une nouvelle entrée démarre avec ses propres sauvegardes.
OverlayFS est nécessaire pour les écritures du jeu.
Les données techniques sont conservées dans
`/userdata/system/partydeck-test/party/<identifiant>/jN`.
Les journaux Batocera sont écrits dans `jN/logs` et le cache du chargeur
de bibliothèques dans `jN/ldconfig-cache`. Chaque joueur a ses propres copies
pour permettre la préparation du runtime sous v44.

- Choisissez `1`, `2`, `3`, `4` ou `auto`. `auto` adapte le nombre de joueurs
  aux manettes détectées au lancement, avec un maximum de quatre. Avec une
  seule manette et un clavier et une souris, il démarre deux joueurs.
- `horizontal` place deux fenêtres l'une au-dessus de l'autre. `vertical`
  les place côte à côte. À trois ou quatre joueurs, le lanceur utilise une
  grille 2 × 2. Le placement vise l'écran principal.
- Le choix d'entrées `auto` privilégie les manettes. S'il en manque une, le
  dernier joueur peut utiliser le clavier et la souris. `clavier-j1` et
  `clavier-j2` permettent de réserver ce duo à un joueur. Les manettes
  utilisent un ordre stable par périphérique lorsqu'udev fournit un chemin.

Quand chaque joueur utilise une manette, le clavier et la souris permettent
d'interagir avec les menus de la fenêtre sélectionnée. Cliquez sur la fenêtre
souhaitée pour changer d'instance. Si un jeu capture la souris, utilisez
Alt+Tab pour changer de fenêtre. Lorsqu'un joueur utilise le clavier et la
souris pour jouer, ces périphériques lui sont réservés.

Sur Batocera v44 sous Wayland/labwc, commencez avec deux joueurs en
`horizontal clavier-j2` pour comparer au test v43 sous Xorg. Vérifiez que le
jeu apparaît dans les deux moitiés et que la manette pilote J1 pendant que le
clavier et la souris pilotent J2. Placez le focus successivement sur chaque
fenêtre. Fermez ensuite la session et vérifiez qu'un second lancement
fonctionne. Testez ensuite `vertical`. Le jeu doit avoir son propre mode
multijoueur pour rejoindre la même partie.

Pour un jeu UMU, chaque joueur a ses journaux dans `party/<jeu>/jN/umu-logs`
et, avec Proton, dans `party/<jeu>/jN/proton-logs` sous le dossier PartyDeck.
Le journal principal indique l'affichage Xwayland attribué à chaque instance
et le code de sortie de `batocera-wine`.

Si le journal UMU contient `runtime_reused_after_interruption` suivi de
`C game target already exists`, la reprise peut retrouver un point de
montage vide. Le [correctif de reprise est disponible sur une branche de
test UMU Runner Toolbox](https://github.com/Thomson67/umu-runner-toolbox/tree/fix/resume-empty-c-game-mountpoint).

Les profils JSON sont dans `/userdata/system/partydeck-test/profiles`.
La commande `ajouter` avec le même chemin actualise le lanceur existant et
les paramètres fournis. L'option d'affichage de l'éditeur est conservée.
Les variantes `horizontal` et `vertical` partagent les profils des joueurs.
Les lanceurs de test créés précédemment dans Ports utilisent encore les
données de `coop/<identifiant>`.

## Essai manuel avec un exécutable autonome

Placez une copie autonome du jeu dans `/userdata/system/partydeck-test/jeux`.
Choisissez un jeu capable de démarrer dans un préfixe neuf et doté d'un mode
LAN et d'un support manette.

```bash
/userdata/system/partydeck-test/partydeck-test preparer-port "Mon Jeu/Jeu.exe"
```

Actualisez les listes de jeux dans EmulationStation, puis ouvrez **Ports →
PartyDeck - Test**. EmulationStation libère les manettes pendant le lancement
d'un port. Relancez `preparer-port` pour changer de jeu dans cette entrée.
Pour les essais directs depuis SSH, la commande `jouer` reste disponible.

Le chemin de l'EXE peut être suivi d'un paramètre optionnel,
à savoir le chemin absolu d'un dossier Proton contenant l'exécutable `proton`.
Sans runner configuré, PartyDeck utilise GE-Proton via UMU. Le premier lancement
peut télécharger le runner et le runtime.

Dans PartyDeck, ajoutez chaque manette comme joueur distinct et sélectionnez
**Start**. Placez les fenêtres côte à côte, puis vérifiez les deux manettes
simultanément, avec le focus sur chaque fenêtre à tour de rôle. Essayez ensuite
de rejoindre la même partie LAN depuis les deux instances.

Sous Xorg, le lanceur demande à Batocera d'afficher le pointeur pendant
la session PartyDeck et le masque à sa fermeture, si `unclutter-remote` est
disponible.

Chaque exécution affiche le chemin de son journal sous
`/userdata/system/partydeck-test/logs`. Pour confirmer la compatibilité avec
votre build, lancez le même test sous Xorg et sous Wayland.
