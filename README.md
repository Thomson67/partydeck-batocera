# PartyDeck Batocera

Prototype de lancement local de plusieurs instances d'un jeu Wine sur PC
Batocera x86-64 avec PartyDeck, Gamescope et le runner configuré dans
Batocera. Le système **Windows Party** gère de un à quatre joueurs, l'attribution
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
ajouter un jeu à **Windows Party** et vérifier la session graphique.

Un test sur Batocera v43 sous Xorg a confirmé le placement haut et bas de
deux instances d'un jeu `.wsquashfs`. Les deux joueurs ont aussi été testés
simultanément sur un jeu autonome. Les deux instances, le placement et les contrôles ont aussi été validés sous
v44 Wayland/labwc. Les dispositions à trois et quatre joueurs restent à
valider sur machine.

Ce code provient de la
[branche expérimentale d'Ultimate Wine Toolbox](https://github.com/Thomson67/ultimate-wine-toolbox/tree/dd40946a9a0a11475c971871fc8f6ac5b51b9def).
L'AppImage officielle [PartyDeck](https://github.com/partydeck/partydeck)
et le pont [UMU Runner Toolbox](https://github.com/Thomson67/umu-runner-toolbox)
sont téléchargés et vérifiés à l'installation.

Vérification locale avec `python3 tests/check_coop.py`. Ce test simule les
entrées et les fenêtres. La vérification en jeu se fait depuis **Windows Party**.

## Ajouter un jeu

Ouvrez **Configurer Windows Party** dans le système Windows Party pour ajouter
un jeu ou modifier ses paramètres. Le gestionnaire utilise Yad, fourni par
Batocera sur PC.

Vous pouvez aussi créer son lanceur depuis SSH avec cette commande.

```bash
/userdata/system/partydeck-test/partydeck ajouter \
  "/userdata/roms/windows/Mon Jeu.wsquashfs" 2 horizontal auto
```

Au premier ajout, redémarrez EmulationStation pour charger le système
**Windows Party**. Pour les ajouts suivants, actualisez les listes de jeux.

Les lanceurs sont dans `/userdata/roms/windows-party`. Les fichiers du jeu
restent à leur emplacement Windows d'origine. Les sauvegardes et préfixes
propres à chaque joueur sont dans
`/userdata/saves/windows-party/<jeu>/j1`, `j2`, etc.
Le jeu utilise le runner et l'autorun de son entrée Windows.
Relancez `ajouter` avec `vertical`, un autre nombre de joueurs ou un autre
mode d'entrées pour actualiser son lanceur.
Les données des anciens essais dans Ports restent accessibles via leurs
lanceurs. Une entrée Windows Party commence avec ses propres profils.

## Réglages propres à SoH / Anchor (version de test)

Dans **Configurer Windows Party**, sélectionnez le jeu puis **SoH / Anchor**.
Cochez **Gérer ce jeu avec le profil Anchor** pour activer cet adaptateur.
Définissez la connexion automatique, le serveur/port, un Room ID commun,
un nom différent et un Team ID pour chaque joueur. Les quatre identités sont
mémorisées même si la session utilise seulement deux joueurs.

Le formulaire propose aussi les règles de salle : PvP désactivé, activé ou
avec tirs alliés ; positions visibles et téléportation pour personne, la même
équipe ou tous ; synchronisation des objets et de la progression.
Les règles sont envoyées par SoH lors de la connexion pour créer une salle.
Une salle déjà existante conserve les règles décidées par son administrateur.
Le salon public `soh-global` impose ses propres règles. L'action destructive
« Clear All Team State » reste accessible uniquement dans SoH.

Le chemin de configuration est relatif au dossier de lancement défini dans
l'autorun Batocera : `shipofharkinian.json` par défaut. Si le batch entre dans un
sous-dossier avant de lancer SoH, indiquez ce sous-dossier dans le chemin JSON.
Choisissez un autre Room ID pour créer une nouvelle salle avec de nouvelles règles.

L'adaptateur applique les réglages dans la vue Wine privée de chaque joueur,
après montage du jeu, avant Wine/UMU. Il conserve les autres clés JSON et les
identités attribuées par Anchor après la première connexion. Il utilise une copie
temporaire du lanceur natif, visible uniquement dans l'espace de montage du joueur ;
le fichier système et l'entrée solo ne sont pas modifiés. Si la structure du lanceur
Batocera n'est pas reconnue, le lancement est refusé avec une erreur explicite.
Les configurations SoH qui sont des liens symboliques sont refusées pour éviter
d'écrire dans une sauvegarde solo ou dans celle d'un autre joueur.

Tests locaux : `python3 tests/check_anchor.py`, `python3 tests/check_profiles.py`,
`python3 tests/check_windows_party.py` et `python3 tests/check_coop.py`.
La connexion réseau réelle avec cet adaptateur reste à valider sur Batocera.

## Profils et lancement direct

Les paramètres sont conservés dans
`/userdata/system/partydeck-test/profiles/<identifiant>.json`.
Chaque profil enregistre le nombre de joueurs, la disposition et le mode
manettes ou clavier/souris. Par défaut, sélectionner le jeu lance directement
la session. L'option **Afficher ces réglages avant chaque lancement** ouvre
l'éditeur avant de démarrer. Annuler quitte ce lancement.

Le gestionnaire est également accessible depuis SSH.

```bash
/userdata/system/partydeck-test/partydeck configurer
```

L'installation convertit les anciens lanceurs Windows Party générés par le
projet en reprenant leurs paramètres. Les profils personnels existants sont
réutilisés lors des mises à jour. La disposition des fenêtres et l'attribution
des entrées se configurent ici. La connexion réseau automatique demande une
adaptation au mode multijoueur de chaque jeu.

Le fonctionnement avec profils et éditeur facultatif s'inspire de
[Quiver Batocera](https://github.com/DreamerCG/Quiver-Batocera), dont les
profils `.quiver` et l'option `LAUNCHER_QUIVER` permettent d'ouvrir le launcher
à la demande.
