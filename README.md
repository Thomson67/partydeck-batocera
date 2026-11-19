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
un jeu ou modifier ses paramètres. Le nouveau configurateur utilise Pygame 2,
avec navigation entièrement à la manette et clavier virtuel intégré.

## Configurateur à la manette (version de test)

### Langue automatique : français ou anglais

Le configurateur suit la langue choisie dans Batocera : **français** pour `fr`
et ses variantes (`fr_FR`, `fr_CA`, `fr_BE`, etc.), **anglais pour toutes les
autres langues**. La sélection est relue à chaque ouverture ; fermez puis
rouvrez le configurateur après un changement de langue.

La priorité est `batocera-settings-get system.language`, puis la valeur
`system.language` de `/userdata/system/batocera.conf` si l'utilitaire n'est pas
disponible, puis le réglage Language d'EmulationStation. La locale du processus
sert uniquement de dernier recours. Une session SSH en anglais ne remplace donc
pas un choix français explicite dans Batocera, et inversement.

Cela couvre les onglets, aides clavier/manette, dialogues, confirmations,
stockage, messages du configurateur et **toutes les options des profils SoH /
Anchor et Borderlands 2**, y compris leurs listes de choix. Le clavier virtuel
utilise **AZERTY en français** et **QWERTY en anglais**, avec commandes traduites.
L'ancienne interface Yad dispose également des libellés traduits.

Les noms de fichiers, Room ID, noms de joueurs déjà enregistrés et autres valeurs
personnelles ne sont pas traduits. Les identifiants des profils et des options
restent les mêmes dans les fichiers JSON ; aucun changement des sauvegardes,
des chemins ou de la langue du jeu n'est effectué. Les nouveaux noms de joueurs
proposés sont `Joueur1…4` en français et `Player1…4` en anglais.

Pour tester ponctuellement une langue, sans changer Batocera ni enregistrer une
préférence supplémentaire :

```bash
PARTYDECK_LANGUAGE=en /userdata/system/partydeck-test/partydeck configurer
PARTYDECK_LANGUAGE=fr /userdata/system/partydeck-test/partydeck configurer
```

**English:** The configurator automatically uses French when Batocera is set to
French, and English for every other system language. All game-profile options,
dialogs, gamepad hints and the on-screen keyboard are translated; your personal
values and existing profiles stay unchanged.

Tests locaux : `python3 tests/check_i18n.py` vérifie la priorité de la langue
Batocera sur SSH, les variantes françaises, les replis anglais, l'affichage et
les options des jeux, les commandes du clavier virtuel, l'éditeur Yad et la
conservation des valeurs et identifiants des profils.

### Bibliothèque et commandes

La bibliothèque occupe la colonne de gauche. Le panneau de droite présente
les onglets **Session**, **Réseau**, **Joueurs** et **Image & son**. Les profils
existants sont réutilisés. Aucun dialogue de bureau n'est nécessaire pour ajouter
un jeu, parcourir les dossiers, modifier les paramètres ou saisir du texte.

**Les onglets dépendent du profil du jeu** : un jeu standard affiche uniquement
Session. Réseau, Joueurs et Image & son sont propres à SoH / Anchor et apparaissent
seulement lorsque ce profil est choisi ou reconnu par le catalogue commun.
Les nouveaux profils standard ne stockent pas de réglages Anchor.

La bibliothèque propose le **profil commun Ship of Harkinian**, même sur une
nouvelle installation. Le configurateur recherche les noms contenant « SoH » ou
« Ship of Harkinian » dans `/userdata/roms/windows` et ses sous-dossiers (jusqu'à
quatre niveaux, sans entrer dans les préfixes Wine). Il ne monte ni n'extrait les jeux.
Une correspondance unique est proposée avec le profil SoH déjà sélectionné ;
les profils personnels déjà enregistrés restent prioritaires. En cas d'absence
ou de plusieurs versions, une boîte propose **Choisir le jeu** ou **Annuler**.
Le navigateur accepte les dossiers `.wine`/`.pc` et les fichiers `.wsquashfs`.
Annuler rappelle qu'il faut d'abord disposer du jeu et ne crée aucun lanceur.
Aucun jeu n'est fourni ou téléchargé par le catalogue, uniquement sa configuration.

Elle propose aussi **Borderlands 2**, avec les mêmes possibilités de détection
et d'association manuelle. Les noms « Borderlands 2 », « Borderlands_2 » ou
« Borderlands II » sont reconnus. Les jeux personnels figurent avant les profils
communs encore sans fichier associé.

Le profil **SM64CoopDX** reconnaît aussi `sm64coopdx`, `SM64 Coop DX` et
`Super Mario 64 Coop Deluxe`, avec association manuelle possible pour un autre nom.
**Left 4 Dead 2 / Goldberg** reconnaît `Left 4 Dead 2`, `Left4Dead2`,
`Left_4_Dead_II` et `L4D2`, avec les mêmes possibilités d'association manuelle.

Dans **Choisir un jeu**, **LB/RB** (ou **L1/R1**) parcourt la liste par pages de
neuf entrées. Maintenir le bouton fait défiler les pages en continu après
0,35 seconde, puis toutes les 0,12 seconde ; relâcher arrête le défilement.
La répétition des boutons de page est limitée au sélecteur de jeu : changer
d'onglet dans les réglages conserve un seul déplacement par appui.
**HK + Start** quitte le configurateur : le Hotkey de `es_input.cfg` est utilisé
(`hotkey` ou `hotkeyenable`) ; sans mapping, le bouton Guide + Start SDL sert de
secours. Cette combinaison n'ouvre pas simultanément le navigateur d'ajout.
En présence de modifications, le choix enregistrer/abandonner/annuler reste proposé.

- **Croix/A** : choisir ; droite depuis la bibliothèque ouvre les réglages.
- **Cercle/B** : retour aux jeux, annulation du clavier ou fermeture.
- **LB/RB** : onglet précédent/suivant.
- **Gauche/droite** : changer une option ; Croix/A ouvre les champs texte/nombres.
- **Carré/X** : enregistrer (ou valider la saisie au clavier virtuel).
- **Triangle/Y** : rechercher ; **Start** : ajouter un jeu via le navigateur intégré.

L'habillage associe panneaux métalliques, fond géométrique discret et accents
cyan/violet. Les indications de boutons sont dessinées dans l'interface et passent
au style PlayStation ou Xbox selon la manette qui commande le configurateur.
Les manettes dont le nom n'identifie pas un modèle PlayStation gardent les pictogrammes Xbox.

Le bandeau de commandes suit la **dernière entrée utilisée** : touches clavier
après une touche pressée, pictogrammes Xbox ou PlayStation après une action à la
manette. Sans manette, il démarre directement en mode clavier. **Inser : Ajouter**
est ainsi visible au clavier, et devient **START : Ajouter** ou **OPTIONS : Ajouter**
avec les manettes. Les pages sont indiquées par **PgUp/PgDn**, **LB/RB** ou **L1/R1**.
Le navigateur, le clavier virtuel et les confirmations partagent ce bandeau :
seules leurs commandes utiles sont affichées, sans légendes clavier/manette en double.

Les cinq volumes SoH utilisent des curseurs : **gauche/droite** ajuste par pas
de 5 %, entre 0 et 100. **Croix/A** reprend la valeur du JSON commun (repère
« JSON » et poignée creuse). Aucun clavier virtuel n'est nécessaire pour le son.

Trois boutons fixes sont présents sous les réglages : **Lancer la partie**,
**Enregistrer**, et **Retirer / Dissocier le jeu**. Descendez après la dernière option pour les sélectionner. Lancer
enregistre le profil, ferme SDL et passe au lanceur natif Windows Party. Si
l'enregistrement échoue, le jeu n'est pas lancé. Le choix de configurer avant
chaque lancement reste mémorisé sans rouvrir une seconde fois le configurateur.

Dans **Session**, désactivez **Clavier/souris utilisable comme joueur** pour
attribuer uniquement des manettes aux joueurs. En mode automatique, une seule
manette donne alors un joueur ; le clavier ne crée plus de joueur supplémentaire.
Un nombre de joueurs fixé nécessite autant de manettes. L'attribution clavier
J1/J2 est désactivée tant que cette option est coupée.
Le clavier/souris reste transmis à la fenêtre active pour les menus et la saisie.
Il ne s'agit pas d'un filtrage des touches en fonction de l'état interne du jeu :
les actions éventuellement associées à ces touches par le jeu restent possibles.
L'option est mémorisée par jeu et reste activée par défaut pour les anciens profils.

Le clavier virtuel propose minuscules/majuscules, chiffres, accents, ponctuation,
espace, effacement et validation. Un clavier physique reste utilisable : flèches,
Entrée, Échap, F2 pour enregistrer, F3 pour rechercher, Insert pour ajouter et
Page précédente/suivante pour les onglets. L'interface s'ajuste à l'écran avec un
rapport constant et des marges si nécessaire. Les modifications non enregistrées
déclenchent un choix enregistrer/abandonner/annuler avant de changer de jeu ou sortir.

Les manettes reconnues utilisent les mappings SDL ; les autres utilisent les
mappings `es_input.cfg` de Batocera. Branchement/débranchement et répétition du
stick/croix directionnelle sont pris en charge. La navigation reprend les principes
manette/clavier virtuel de [RGSX](https://github.com/RetroGameSets/RGSX), avec une
implémentation originale dédiée à Windows Party. Les tests locaux utilisent SDL
en mode simulé. Le fonctionnement du configurateur a également été confirmé par
l'utilisateur sur **Batocera v43 sous Xorg**. Cette validation sur machine complète
les tests locaux ; elle ne couvre pas toutes les combinaisons de manettes.

L'ancienne interface Yad reste accessible explicitement pour dépannage :

```bash
PARTYDECK_UI=legacy /userdata/system/partydeck-test/partydeck-test configurer
```

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

### Retirer ou dissocier un jeu

Un troisième bouton est disponible sous les options du jeu. Descendez après la
dernière option pour l'atteindre, puis validez et confirmez :

- **Retirer le jeu** enlève le lanceur et les options Windows Party d'un jeu standard.
- **Dissocier le jeu** enlève l'association au fichier d'un profil commun SoH ou
  Borderlands 2. Son entrée reste proposée dans la bibliothèque et ses options
  personnelles sont conservées dans `detached-profiles/<profil>.json` sous le
  dossier d'installation, pour une nouvelle association manuelle.

Les fichiers du jeu, sauvegardes, préfixes et données privées sont conservés.
Après dissociation, la détection automatique ne réassocie pas immédiatement le
même fichier ; choisissez explicitement le jeu pour le relier de nouveau. Cet
état est conservé dans `catalog.json` lors des mises à jour. Actualisez ensuite
les listes de jeux EmulationStation pour retirer son ancien lanceur de cette vue.
Les lanceurs personnalisés ou remplacés par des liens utilisateur ne sont pas
supprimés automatiquement. Annuler la confirmation ne change rien.

## Borderlands 2 : affichage et préréglages (version de test)

Un nouvel ajout reconnu comme Borderlands 2 utilise automatiquement ce profil.
Pour un jeu déjà ajouté avec le profil Standard, choisissez **Profil du jeu →
Borderlands 2** dans Session, puis ouvrez l'onglet **Image**.

L'onglet **Image** affiche **Préréglage graphique**, **VSync** et
**Qualité PhysX**. L'onglet **Joueurs** permet de saisir
un nom facultatif pour J1 à J4, avec le clavier virtuel à la manette.
Le plein écran fenêtré et l'adaptation à la portion d'écran du joueur sont
**systématiques**, sans options à activer. L'adaptateur écrit dans `[SystemSettings]`
de `WillowEngine.ini` :

```ini
Fullscreen=False
WindowedFullscreen=True
ResX=<largeur de la fenêtre du joueur>
ResY=<hauteur de la fenêtre du joueur>
```

Les dimensions de démarrage sont aussi synchronisées dans `[WinDrv.WindowsClient]`.
La pause lors de la perte de focus en mode fenêtré est désactivée pour laisser
les instances jouer simultanément.
Avec deux joueurs sur un écran 1920×1080, cela donne 1920×540 en horizontal ou
960×1080 en vertical. Le mode interne Gamescope est aligné sur ces dimensions.
Les mêmes options sont appliquées à toutes les instances, chacune avec sa résolution.

Le réglage **Préréglage graphique** propose **Conserver les réglages**, **Bas**,
**Moyen**, **Élevé** et **Max**. Les quatre ensembles Windows Party sont des
préréglages expérimentaux, pas des profils officiels du jeu :

| Option | Bas | Moyen | Élevé | Max |
| --- | --- | --- | --- | --- |
| Textures | Basses | Moyennes | Hautes | Hautes |
| Distance de vue | Basse | Moyenne | Haute | Très haute |
| Filtrage anisotrope | ×2 | ×4 | ×8 | ×16 |
| FXAA | Non | Oui | Oui | Oui |
| Occlusion ambiante / profondeur de champ / rayons lumineux | Non | Non | Oui | Oui |
| Ombres dynamiques | Non | Oui | Oui | Oui |
| Résolution maximale des ombres | 512 | 1024 | 2048 | 4096 |
| Distance du feuillage | 0,5 | 0,75 | 1 | 1 |

**PhysX est indépendant du préréglage** : conserver, bas, moyen ou élevé.
Le choix initial conserve le niveau existant, y compris avec Max.
**VSync** propose conserver, activé ou désactivé et écrit `UseVsync=True/False`
dans `[SystemSettings]`. Conserver laisse la valeur actuelle en place. Le
préréglage graphique n'impose aucun de ces deux réglages indépendants.
Le limiteur d'images, les effets artistiques non listés, les contrôles et les
paramètres réseau ne sont pas modifiés. « Conserver » ne restaure pas
automatiquement les valeurs précédant un préréglage.

Le chemin standard recherché est `drive_c/users/<utilisateur>/Documents/My Games/
Borderlands 2/WillowGame/Config/WillowEngine.ini`, avec prise en charge de
`My Documents`, de la casse des chemins Windows et des redirections vers les
sauvegardes privées du joueur. La recherche est automatique : aucun chemin INI
n'est demandé dans l'interface. Les anciens profils sont compatibles ; les
anciennes options `windowed_fullscreen`, `fit_resolution` et `config` sont retirées
de leur représentation chargée et lors du prochain enregistrement. Leurs anciennes
valeurs ne peuvent pas désactiver la politique d'affichage ou changer le chemin.
Les profils antérieurs sans VSync utilisent « Conserver ».
Si le préfixe ne comporte encore aucun utilisateur Wine, initialisez le jeu en solo
avant de le lancer dans Windows Party.

L'application intervient après montage du jeu par le lanceur natif et avant Wine/UMU,
dans la vue privée du joueur. Les préfixes UMU privés réutilisés après interruption
sont également mis à jour. Les sections, commentaires, listes répétées et options
non concernées du fichier existant sont conservés ; le fichier complet fourni par
un utilisateur n'est pas distribué ni recopié chez tous les joueurs. La première
version de chaque INI modifié est conservée sous `party/<jeu>/jN/borderlands2-before`
dans le dossier d'installation. Un INI absent est initialisé avec les seules options
gérées. Une redirection hors du préfixe ou des emplacements privés autorisés refuse
le lancement pour éviter une écriture dans les données solo.

Référence graphique : [guide technique NVIDIA Borderlands 2](https://www.nvidia.com/en-gb/geforce/news/borderlands-2-borderlands-the-pre-sequel-tweak-guide/).
Les valeurs sont définies par Windows Party et restent à valider en jeu avec Wine.
Tests locaux : `python3 tests/check_borderlands2.py` et
`python3 tests/check_library_remove.py`, en complément des tests du configurateur.

### Nom du joueur

Pour les installations disposant d'un `steam_emu.ini` avec `[Settings] AppId=49520`,
Windows Party peut régler **UserName** séparément dans les vues
privées de lancement. La recherche vise le dossier de lancement et
`Binaries/Win32`, sans distinction de casse. Ce fichier existant n'est jamais
remplacé par un modèle livré par Windows Party.

- **Joueurs** : nom facultatif pour chaque joueur. Un champ vide conserve le nom
  actuel, y compris `CODEX` si c'est celui de l'installation. Les noms sont conservés
  tels que saisis et ne sont pas traduits.
- Les nouveaux réglages conservent les valeurs existantes par défaut, y compris
  pour les anciens profils. « Conserver » ne restaure pas une ancienne valeur.
- Seule la clé `UserName` est modifiée dans ce fichier pour les noms.
  Identifiants, Steam Account ID, lobby, paramètres réseau, DLC et interfaces
  restent inchangés. La première version du fichier est sauvegardée dans le
  dossier privé `borderlands2-before` du joueur.
- Si une personnalisation est demandée sans INI reconnu, le lancement est refusé
  avec une explication. Laisser les noms vides permet de
  garder le lancement habituel ; aucune configuration n'est inventée pour une
  autre édition du jeu.

Le changement de langue du jeu a été retiré après un problème constaté en jeu.
Les anciennes valeurs `borderlands2.language` sont ignorées et supprimées au
prochain enregistrement. Au prochain lancement, si une sauvegarde originale
`borderlands2-before/steam_emu-*.ini` existe pour le fichier (quelle que soit sa
casse), sa clé `Language` est restaurée **une seule fois**, sans remplacer les
noms ni les autres réglages. Cette migration est marquée dans
`borderlands2-language-retired`. En l'absence de sauvegarde, la langue n'est pas
modifiée. Les changements manuels ultérieurs ne sont pas écrasés.

Les noms de joueurs ont été validés en jeu par l'utilisateur. Les tests locaux
vérifient leur isolation, les encodages et le retrait de l'ancien réglage de langue.

### LAN : état de la vérification

Le choix LAN n'est **pas forcé dans cette version**. Aucun réglage fiable n'a été
identifié dans les INI fournis. La solution de référence identifiée dans le mod
[All My Homies Hate SHiFT](https://github.com/PyrexBLJ/blsdk-mods/tree/main/AllMyHomiesHateSHiFT)
utilise le Python SDK et appelle `AttemptNetworkTransition(1, 2, True)` au démarrage
du jeu. Ce hook nécessite une intégration et une validation distinctes ; aucune
clé LAN inventée, désactivation de Steam ou modification de `profile.bin` n'est
appliquée. Le LAN se sélectionne donc encore dans le menu du jeu.

Les fichiers fournis contiennent trois champs utiles pour étudier le nom :

- `WillowGame.ini`, `[DefaultPlayer]` : `Name=Player`.
- `WillowGame.ini`, `[Engine.PlayerController]` : `bOverrideOnlineProfileName=false`.
- `WillowEngine.ini`, `[URL]` : `Name=Player`.

Ce sont des candidats pour un nom local. Leur effet sur le pseudo réseau affiché
reste à confirmer avec la version du jeu et son fournisseur de profil en ligne.
Le configurateur ne modifie pas ces champs Willow : pour l'installation fournie,
le nom configuré est `UserName=CODEX` dans `steam_emu.ini`. L'option Joueurs
décrite plus haut cible cette clé, et non `Name=Player`.

## Profil SM64CoopDX (version de test)

Le catalogue propose **SM64CoopDX · profil commun**, avec les mêmes choix
de détection, de sélection manuelle et de dissociation que les autres profils.
Les jeux restent dans `/userdata/roms/windows`, en `.wine`, `.pc` ou `.wsquashfs`.
Pour un jeu déjà enregistré avec le profil Standard, choisissez **Session →
Profil du jeu → SM64CoopDX**, puis enregistrez.

La base commune est le fichier fourni par l'utilisateur, installé dans
`/userdata/system/partydeck-test/templates/sm64coopdx-common.txt`.
Elle est **réappliquée à chaque lancement** pour tous les joueurs, avec uniquement
les variantes du configurateur et la résolution de la portion d'écran du joueur.
Les autres réglages sont accessibles en jeu pour la session et reviennent à la
base au lancement suivant. Le modèle local est conservé lors des mises à jour.

| Onglet | Réglages |
| --- | --- |
| Graphismes | VSync ; MSAA désactivé/2×/4×/8×/16× ; filtre au plus proche/linéaire/trois points ; distance 0,5×/1×/1,5×/3×/10×/100×/infinie |
| Gameplay | Caméra libre ; sensibilités caméra X et Y de 1 à 100 ; inversion caméra X et Y |
| Options | Langue du jeu ; noms différents pour J1 à J4 avec clavier virtuel |
| Son | Musique uniquement pour J1 ; volumes général, musique, bruitages et ambiance |

Les valeurs initiales reprennent la base : VSync activée, MSAA 8×, filtre trois
points, distance infinie, caméra libre, sensibilités 20/20, inversions X/Y activées
et langue French. Les noms initiaux sont Joueur1…Joueur4 (Player1…Player4 dans
un configurateur anglais). Les noms déjà enregistrés ne sont jamais traduits.
Les noms doivent être distincts, sans espaces (utilisez `_`), de 63 octets UTF-8
maximum : le lecteur de configuration du jeu s'arrête au premier espace.
Le MSAA dépend aussi des possibilités du moteur graphique et du matériel.

Les langues proposées sont celles du jeu v1.5.1 : français, anglais, allemand,
italien, espagnol, portugais, néerlandais, polonais, tchèque, russe et japonais.
Le choix écrit la clé `language` du jeu, indépendamment de la langue FR/EN de
l'interface Windows Party. Les fichiers de langue correspondants doivent être
présents dans l'installation du jeu.

La musique est coupée par défaut pour J2 à J4 (`music_volume 0`) sans modifier
leurs bruitages ou leur ambiance. Désactiver **Musique uniquement pour J1** applique
le volume musical commun à tous. Les curseurs affichent 0–100 %, convertis vers
l'échelle native 0–127. Par défaut, le volume général reste exactement à 80/127
(environ 63 %) ; les trois autres volumes restent à 127/127. Valider un curseur
réutilise sa valeur de base ; gauche/droite la modifie par pas de 5 %.

L'application intervient après le montage natif du jeu et avant Wine, dans les
vues privées existantes. Les emplacements standards pris en charge sont le
`sm64config.txt` portable dans le dossier de lancement (et les sous-dossiers
immédiats où il existe déjà), ainsi que `AppData/Roaming/sm64coopdx`, l'ancien
`sm64ex-coop` et leurs alias `Application Data`. Les préfixes UMU privés réutilisés
reçoivent aussi les réglages. Un `--savepath` ou `--configfile` personnalisé hors
de ces emplacements nécessite une adaptation ; le configurateur n'invente pas
de chemin. Les anciens fichiers privés sont sauvegardés une seule fois dans
`sm64coopdx-before`. Les fichiers de progression ne sont pas remplacés.

Les entrées répétées `enable-mod:`, `dynos-pack:` et `save-name:` ainsi que les
raccourcis sont repris de la base. Aucun mod ou pack de textures n'est fourni
ou téléchargé : ceux qu'elle active doivent déjà être installés dans le jeu.
Les réglages de réseau de la base restent disponibles en jeu ; ce profil
n'automatise pas encore le choix Héberger/Rejoindre.

Référence des clés et plages :
[configfile.c v1.5.1](https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/pc/configfile.c),
[affichage](https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/pc/djui/djui_panel_display.c),
[caméra](https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/pc/djui/djui_panel_camera.c),
[son](https://github.com/coop-deluxe/sm64coopdx/blob/v1.5.1/src/pc/djui/djui_panel_sound.c).
Les tests locaux `tests/check_sm64coopdx.py` couvrent J1–J4, les sauvegardes,
les redirections, UMU, la configuration commune et les réglages à la manette.
Le lancement réel sur Batocera reste à valider avec ce nouveau profil.

## Runner distinct dans les options avancées ES

Après installation, **redémarrez EmulationStation**, puis ouvrez les options
avancées du jeu dans **Windows Party** : **RUNNER WINE** utilise le sélecteur
natif Wine et les mêmes runners personnalisés installés.

- **Auto** : reprend le runner du jeu Windows d'origine.
- **Runner choisi pour ce jeu** : prioritaire uniquement dans Windows Party.
- Un runner choisi dans les options du système Windows Party s'applique aux
  jeux sans choix individuel. Auto au niveau du jeu reprend ce choix système.

ES conserve ces valeurs dans `windows-party["<lanceur>.sh"].wine-runner` et
`windows-party.wine-runner`. Les valeurs `windows.*` restent intactes. Lors du
lancement, un relais privé remplace uniquement la sélection du runner natif,
avant les profils spécifiques au jeu ; les autres réglages Wine continuent
à provenir du jeu Windows d'origine. Aucun binaire système n'est modifié sur
disque. Un runner peut ainsi être testé en multi sans changer le lancement solo.

Les définitions de menus sont limitées au système Windows Party dans
`es_features_windows-party.cfg`. Ce fichier pourra recevoir d'autres options
propres au système ; le premier ajout est uniquement le choix du runner.

**English:** Restart EmulationStation after updating. Windows Party advanced
game options now include the native **WINE RUNNER** picker. Auto inherits the
original Windows runner, unless a Windows Party system-level runner is set.
An explicit per-game Party runner takes priority. Solo settings are unchanged;
all other native Wine options still come from the original game. The menu
extension is scoped to Windows Party and can host future system-only options.

## Scraps des jeux Windows d'origine

Les entrées Windows Party reprennent automatiquement les informations du jeu
correspondant dans le `gamelist.xml` de Windows : titre, description, note,
date, studio, éditeur, genre et médias (image, boîte, logo, vidéo, fond, manuel,
et autres médias Batocera). La correspondance utilise le chemin de la ROM,
avec prise en charge des liens symboliques et des sous-dossiers, sans déduction
approximative sur le titre. Les formats `.wine`, `.pc` et `.wsquashfs` sont couverts.

Les chemins de médias relatifs sont convertis en références absolues vers les
fichiers Windows existants. **Aucune image ni vidéo n'est dupliquée.** Les
favoris, compteurs, dernière partie et paramètres propres à Windows Party
restent séparés de ceux du jeu solo. La ROM et le `gamelist.xml` Windows ne sont
jamais modifiés. Les références restent présentes si un stockage réseau est
temporairement déconnecté ; ses médias redeviennent disponibles avec le montage.

La synchronisation s'effectue à l'ajout/enregistrement d'un jeu, à la mise à
jour de Windows Party (pour les jeux déjà ajoutés) et à l'ouverture du
configurateur (pour reprendre un nouveau scrap fait dans Windows). Le menu de
configuration et les entrées personnelles ne sont pas remplacés. En l'absence
de scrap d'origine, l'entrée reste disponible sans média.

Lorsque l'API locale EmulationStation est disponible, l'import natif met aussi
à jour les métadonnées en mémoire. Sinon le `gamelist.xml` Windows Party est
mis à jour atomiquement ; actualisez alors les listes de jeux ou redémarrez
EmulationStation. Sa première version est sauvegardée dans
`gamelist.xml.partydeck-before`. Un XML invalide ou un lien utilisateur sur le
fichier de destination est conservé et signalé, sans bloquer le lancement.

**English:** Windows Party inherits each original Windows game's scraped
metadata and media references, matching ROM paths rather than approximate
titles. Media files are reused without duplication; Party favorites and play
history stay separate. Synchronization runs when adding/saving a game, updating
the installation, and opening the configurator. The native local ES API imports
changes live when available, with an atomic gamelist update as fallback.
Refresh game lists or restart ES if changes are not yet visible. The Windows
ROM, metadata and media files remain unchanged.

## Profil Left 4 Dead 2 / Goldberg (version de test)

Pour une installation déjà fonctionnelle avec Goldberg/gbe_fork et les fichiers
modernes `steam_settings/configs.user.ini`, sélectionnez **Session → Profil du jeu
→ Left 4 Dead 2 / Goldberg**, puis enregistrez. Les nouveaux jeux reconnus par
leur titre choisissent ce profil automatiquement. Le catalogue propose aussi
**Left 4 Dead 2 · profil commun** en cas de titre personnalisé ou de jeu absent.
Les formats `.wine`, `.pc` et `.wsquashfs` utilisent le lanceur Wine natif habituel.

Le profil corrige le partage involontaire de `[user::general] account_steamid`
entre les instances :

- J1 conserve l'identifiant initial de l'installation.
- J2, J3 et J4 reçoivent des Steam ID locaux distincts, obtenus par décalage de
  l'AccountID initial (+1/+2/+3, avec retour dans la plage valide si nécessaire).
- Chaque joueur conserve ensuite son choix dans
  `<dossier de travail du joueur>/l4d2-goldberg-identity.json`. Un changement de
  nom ou un relancement ne recalcule pas ce Steam ID. Conservez ces petits
  fichiers d'identité ; le nettoyage automatique des caches ne les supprime pas.
- L'onglet **Joueurs** permet de saisir les quatre noms avec le clavier virtuel.
  Les noms par défaut sont Joueur1…Joueur4 ou Player1…Player4 selon la langue de
  l'interface à la création du profil. Les valeurs enregistrées ne sont pas traduites.

L'adaptateur intervient dans la vue privée du joueur après le montage natif,
avant le lancement de Wine. Il recherche les `steam_settings` existants à la
racine du dossier de lancement et dans les emplacements `bin`, `x64`, `x86`,
`win64`, `win32` et `left4dead2`, jusqu'à trois niveaux et sans parcourir les
répertoires de ressources. Les copies 32/64 bits trouvées reçoivent la même
identité pour ce joueur. La validation prend d'abord l'AppID de
`steam_settings/steam_appid.txt`, puis seulement à défaut celui du dossier de
lancement/de la DLL. Un AppID local **550** reste prioritaire même si un fichier
racine contient une autre valeur. Les fichiers sont lus sans être réécrits.
Un AppID effectif explicitement différent reste refusé ; des terminateurs de
texte Windows après le nombre sont acceptés.

L'onglet **Options** / **Options** ajoute :

- **Langue du jeu** / **Game language** : conserver la langue existante (par
  défaut), ou choisir une langue. Le choix est appliqué à tous les joueurs dans
  `configs.user.ini`. Si `supported_languages.txt` existe, la langue choisie est
  ajoutée à cette liste privée pour éviter le repli silencieux vers l'anglais.
  Le choix applique ensemble **les deux réglages validés en solo** :
  `-language french` dans les arguments de l’exécutable et la langue **native Wine**, comme `LANG=fr_FR.UTF-8`
  dans `autorun.cmd` (méthode validée en solo pour L4D2). Le lanceur privé
  applique la valeur `WINE_LANG` avant le démarrage natif, qui passe ensuite
  `LC_ALL` à Wine, pour les trois formats. La lecture de `autorun.cmd` ayant
  déjà eu lieu au moment du hook de configuration, modifier ce fichier depuis
  le hook serait trop tardif. La ROM solo et son `autorun.cmd` restent intacts.
  Un argument `-language` déjà présent est remplacé, sans modifier les autres
  paramètres (réseau, serveur, etc.) ni les chemins entre guillemets.
  « Conserver » respecte le réglage d'origine du jeu et ses arguments. L'ancien ajout de registre
  dans le batch est retiré automatiquement ; aucune commande n'y est ajoutée.
  Les fichiers de traduction/doublage doivent déjà être présents dans le jeu ;
  le configurateur ne télécharge pas de ressources linguistiques.
- **Activer la manette en jeu** / **Enable gamepad in game** : activé par défaut.
  Applique `joystick` et active la visée manette (`+jlook`) sans effacer les
  commandes clavier ni remplacer les scripts de contrôles fournis par le jeu.

Le **mode fenêtré sans bordure et la résolution de chaque joueur sont imposés
à chaque lancement**, sans option à régler : `left4dead2/cfg/video.txt` reçoit
`setting.fullscreen=0`, `setting.nowindowborder=1` et les dimensions de sa portion
(horizontal, vertical ou grille). La surface interne Gamescope utilise les
mêmes dimensions. Un bloc géré dans `autoexec.cfg` applique aussi
`mat_setvideomode largeur hauteur 1`, après les commandes existantes. Le bloc
manette est conservé dans `config.cfg` et `autoexec.cfg`. Les autres réglages
vidéo, raccourcis, scripts de démarrage et commandes réseau restent présents.
Les paramètres sont réappliqués lorsqu'on change la disposition ou le nombre
de joueurs. Le lecteur accepte les racines `VideoConfig`, `video.cfg` et
`video.txt`, les commentaires, les sous-objets et les marqueurs de fin Windows.
Un format vidéo non reconnu est conservé **sans bloquer le lancement** : le
journal précise alors que le sans-bordure n'a pas été réappliqué. La demande de
résolution via `autoexec.cfg` et Gamescope reste active.

**English:** The Options tab adds game language (keep current by default) and
gamepad activation (enabled by default). Language assets must already be
installed. The selected language applies both the executable's -language argument
and Batocera's native Wine locale path,
equivalent to LANG=fr_FR.UTF-8 in autorun.cmd. The private launcher sets WINE_LANG
before native startup, which passes LC_ALL to Wine in all three formats. Keep
current honors the original autorun setting. The original ROM/autorun file is
unchanged, and the retired registry batch preamble is removed automatically.
The combined locale and executable-argument method has been validated in solo; Party sessions still need
in-game validation. Each launch forces borderless windowed rendering at the player's
viewport resolution, including Gamescope's internal size. Existing quality
settings, keyboard binds, startup scripts and networking commands are preserved.
An unrecognized video format is retained without blocking game startup; the
log reports that borderless mode could not be reapplied. Resolution is still
requested through autoexec and Gamescope. Only private player copies are
updated; the solo installation is unchanged.

Les chemins de sauvegarde, le port `listen_port`, les autres fichiers Goldberg
(`configs.main.ini`, `.app.ini`, `.overlay.ini`, interfaces et statistiques) et
la ROM solo ne sont pas réécrits. Les premières versions privées sont conservées
dans `l4d2-goldberg-before` (identité) et `l4d2-settings-before` (options).
Aucun émulateur ou fichier de configuration fourni par l'utilisateur n'est
publié ou téléchargé par cet adaptateur.

Le premier lancement exige un Steam ID individuel valide et identique dans
les copies locales du jeu. Si les sources sont contradictoires, si la configuration
est absente ou si l'identité persistante est invalide, le lancement est refusé avec
une explication, sans régénération silencieuse. Des identifiants initiaux partagés
entre plusieurs PC restent à gérer séparément : ce profil sépare les 1–4 joueurs
d'une même installation locale.

Le résultat du hook est suivi indépendamment du code retourné par
`batocera-wine` : certaines versions peuvent échouer dans le hook puis retourner
zéro après leur attente de wineserver. Un état temporaire propre à chaque
lancement garde cet échec visible et est nettoyé après utilisation. Un hook non
exécuté ou non terminé ne vaut jamais une application réussie du profil.

Cette étape traite l'identité des joueurs. L'hébergement et la connexion au
serveur restent à effectuer dans le jeu ; le profil n'ajoute pas encore
d'automatisation du serveur. Il faut encore vérifier en jeu la connexion après suppression du
conflit de Steam ID. La modification d'identité peut aussi changer l'accès aux
données liées à ce compte pour J2–J4 ; J1 garde son identité initiale.

Référence :
[Goldberg configs.user.EXAMPLE.ini](https://github.com/Detanup01/gbe_fork/blob/dev/post_build/steam_settings.EXAMPLE/configs.user.EXAMPLE.ini).
Tests : `python3 tests/check_l4d2.py` vérifie les quatre identités, leur stabilité,
les copies de configuration 32/64 bits, l'application avant Wine, les sauvegardes d'INI, les refus de
chemins externes et le configurateur FR/EN.

## Fermeture des sessions

Sous Wayland, le lanceur suit séparément la fin de `batocera-wine` et celle de
Gamescope. Dès qu'un joueur termine, les instances de cette session sont
fermées ensemble : il n'est plus nécessaire de fermer les fenêtres Gamescope
restées ouvertes après le jeu. Le lancement reste surveillé pendant le placement
des fenêtres, pour détecter aussi un arrêt précoce.

Chaque lancement utilise un état de fin Wine unique, supprimé après le nettoyage.
Le journal distingue les codes Wine et Gamescope pour chaque joueur. Un incident
Gamescope `SIGSEGV`/139/245 à la fermeture n'est traité comme une fermeture normale
**que si Wine a déjà confirmé une sortie normale**. Une erreur Wine ou un crash
Gamescope sans cette confirmation est conservé ; les signaux négatifs sont
convertis en `128 + signal` plutôt qu'en codes de shell trompeurs comme 245.

Sous Xorg, le lanceur continue d'attendre la fin des fenêtres comme auparavant.
Une demande d'arrêt de la session par signal (dont les raccourcis de fermeture)
déclenche le nettoyage et un retour normal. Les groupes de processus créés par
la session sont arrêtés avec un délai de grâce commun de cinq secondes, puis
arrêt forcé si nécessaire. Aucun `pkill` global de Wine ou Gamescope n'est utilisé.
Les signaux et les états temporaires sont restaurés/nettoyés en fin de session.

Vérification locale : `python3 tests/check_session_exit.py` simule un Wine terminé
avec deux compositeurs encore actifs, vérifie les codes d'erreur, les groupes
de processus isolés et la conservation du comportement Xorg. La correction
du cas signalé sur Batocera v44 Wayland reste à valider sur la machine.

## Stockage et entretien automatique (version de test)

Dans la bibliothèque du configurateur, descendez jusqu'au bouton **Stockage**,
puis validez. Cet écran reste utilisable à la manette et au clavier. L'analyse
et le nettoyage se font en arrière-plan pour conserver une interface réactive.
Il affiche les volumes occupés par jeu, triés du plus volumineux au plus petit,
ainsi que l'espace libre. **LB/RB**, **L1/R1** ou **PgUp/PgDn** parcourent les jeux
par pages de trois. Le bilan inclut les anciens essais `coop` et les données
sans profil dans ses totaux, sans créer artificiellement des entrées de jeu.

| Réglage global | Valeur initiale |
| --- | --- |
| Entretien automatique | Activé |
| Caches cumulés | 2 Gio |
| Journaux cumulés | 128 Mio |
| Journaux conservés | 20 au maximum, selon le budget total |
| Taille d'un journal fermé | 8 Mio, fin conservée |
| Espace libre nécessaire avant lancement | 2 Gio |
| Journal Proton détaillé | Désactivé |

Ces budgets sont **communs à tous les jeux et joueurs**, pas multipliés par
leur nombre. Les réglages affichés dans l'écran Stockage sont
modifiables par gauche/droite ; Entrée/Croix/A permet aussi de saisir les
valeurs numériques avec le clavier virtuel. Les réglages sont enregistrés
automatiquement dans `/userdata/system/partydeck-test/storage.json` et sont
conservés lors des mises à jour. `log_keep` et `log_file_mib` sont modifiables
directement dans ce JSON. Une valeur de 0 pour un budget ne conserve aucun
fichier éligible de cette catégorie ; 0 pour `reserve_mib` désactive le seuil.

L'entretien intervient avant et après les sessions Wine Windows Party et lors
des vérifications du lanceur. Il supprime d'abord les caches et journaux les
plus anciens lorsque leur budget est dépassé. **Nettoyer** applique ces règles ;
**Vider les caches** supprime tous les fichiers de cache éligibles et applique
la rétention habituelle des journaux, sans changer les limites enregistrées.
Les caches seront reconstruits et un prochain lancement pourra être plus lent.
Les restes d'installation identifiés de plus de 24 heures sont aussi supprimés.
Le `/tmp` privé des instances est déjà temporaire et disparaît avec leur espace
de noms ; aucun nettoyage générique des dossiers Temp des jeux n'est effectué.

Le nettoyage ne touche pas aux ROMs, sauvegardes, réglages de jeu, préfixes Wine,
surcouches persistantes ou copies UMU privées. La catégorie **Persistant**
comprend donc plus que la seule progression ; **Runtime** comprend les données
Wine/UMU privées qui ne sont pas identifiées comme des caches ou journaux.
Les liens symboliques et montages imbriqués ne sont pas parcourus. Le bilan
utilise les blocs réellement alloués aux fichiers et ne compte pas deux fois
les liens physiques rencontrés ; il ignore les cibles des liens symboliques,
les montages séparés et l'espace des répertoires eux-mêmes.

Un verrou empêche le nettoyage pendant une session ou une installation. Les
instances encore actives après interruption sont également détectées. Les
fichiers ouverts, liés physiquement ou modifiés depuis moins d'une minute sont
conservés : les budgets sont des objectifs d'entretien **hors jeu**, pas des
quotas. En mode diagnostic, un journal peut donc grossir pendant une partie.
La variable explicite `PROTON_LOG` reste prioritaire sur le réglage de l'interface.

Avant le lancement Wine, les systèmes de fichiers qui hébergent le runtime et
les sauvegardes sont vérifiés. Si l'espace libre est inférieur au seuil, un
entretien automatique tente aussi de vider les caches éligibles. Si cela ne
suffit pas, le jeu n'est pas lancé ; depuis le configurateur, un message reste
affiché sans fermer l'interface. Le seuil ne réserve pas réellement de blocs
et ne garantit pas qu'un autre programme ne remplira pas le disque en cours
de partie. Les données persistantes ne sont ni plafonnées ni supprimées pour
atteindre ce seuil ; certains jeux peuvent toujours nécessiter beaucoup d'espace.

Depuis SSH, sans session graphique requise :

```bash
/userdata/system/partydeck-test/partydeck stockage bilan
/userdata/system/partydeck-test/partydeck stockage reglages
/userdata/system/partydeck-test/partydeck stockage nettoyer
/userdata/system/partydeck-test/partydeck stockage purger-caches
```

Tests locaux : `python3 tests/check_storage.py` (fichiers réels temporaires,
liens, montages simulés, fichiers ouverts, verrous, manque d'espace, commande SSH
et diagnostic Proton) et `python3 tests/check_storage_ui.py` (navigation,
traitement asynchrone, réglages, refus et annulation du lancement avec SDL simulé).
L'intégration de cette fonction reste à confirmer sur Batocera v43/v44.

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

Le bouton **Graphismes / Audio** permet de choisir la résolution interne
(multiplicateur 0,5 à 2 de la fenêtre du joueur), le MSAA (1 = désactivé,
2 à 8), la VSync et le filtre de textures (trois points N64, linéaire ou aucun).
Les réglages de résolution avancée/pixel-perfect sont désactivés pour que le
multiplicateur choisi soit effectivement utilisé par SoH.

La musique est réservée à **J1** par défaut. Les volumes de musique principale,
secondaire et des fanfares sont mis à zéro pour J2 à J4 ; bruitages, voix et
volume général sont conservés. Décochez cette option pour utiliser le mix choisi
(ou les volumes du modèle commun) chez tous les joueurs.

Dans **Graphismes / Audio**, cinq niveaux de volume sont aussi réglables de
0 à 100 % : général, musique principale, musique secondaire, fanfares, et
bruitages/voix (SoH regroupe les voix avec les bruitages). Un champ vide conserve
la valeur du JSON commun pour ce canal. Le mix est mémorisé par jeu et appliqué
à tous les joueurs. Avec « Musique uniquement pour J1 », les deux musiques et
les fanfares restent à zéro chez J2 à J4, quels que soient leurs niveaux communs.
Le volume général et les bruitages/voix suivent les valeurs choisies chez tous.

Toutes les instances repartent à chaque lancement du même JSON commun :
`/userdata/system/partydeck-test/templates/soh-common.json`. Le modèle fourni
reprend le JSON transmis par Thomson, avec son interface, ses contrôles et ses
réglages de jeu ; son Room ID, son nom et son identifiant de client ont été retirés.
Les noms/équipes, les identifiants Anchor individuels et les différences audio
sont ensuite appliqués à chaque copie privée. Ce fichier commun reste modifiable
et n'est pas remplacé lors d'une mise à jour. Les changements faits directement
dans le JSON d'un joueur sont remplacés au lancement suivant ; les changements
communs doivent donc être faits dans le modèle ou dans le configurateur.
Avant le premier remplacement, l'ancien JSON privé est conservé dans
`party/<identifiant du jeu>/jN/soh-before-common.json` sous le dossier d'installation.

Le chemin de configuration est relatif au dossier de lancement défini dans
l'autorun Batocera : `shipofharkinian.json` par défaut. Si le batch entre dans un
sous-dossier avant de lancer SoH, indiquez ce sous-dossier dans le chemin JSON.
Choisissez un autre Room ID pour créer une nouvelle salle avec de nouvelles règles.

L'adaptateur applique les réglages dans la vue Wine privée de chaque joueur,
après montage du jeu, avant Wine/UMU. Il conserve les autres clés du JSON commun
et les identités attribuées par Anchor après la première connexion. Il utilise une copie
temporaire du lanceur natif, visible uniquement dans l'espace de montage du joueur ;
le fichier système et l'entrée solo ne sont pas modifiés. Si la structure du lanceur
Batocera n'est pas reconnue, le lancement est refusé avec une erreur explicite.
Les configurations SoH qui sont des liens symboliques sont refusées pour éviter
d'écrire dans une sauvegarde solo ou dans celle d'un autre joueur.

Tests locaux : `python3 tests/check_anchor.py`, `python3 tests/check_profiles.py`,
`python3 tests/check_windows_party.py` et `python3 tests/check_coop.py`.
La connexion réseau réelle avec cet adaptateur reste à valider sur Batocera.

## Logo du système Windows Party

Le logo validé est installé dans `assets/windows-party.png`. Un fichier
`/userdata/roms/windows-party/theme.xml` reprend le thème Windows actuellement
sélectionné et remplace uniquement l'image du logo. L'entrée Windows solo et
les fichiers du thème d'origine restent inchangés. Un thème local personnalisé
déjà présent est conservé. Après installation, redémarrez EmulationStation.
La substitution couvre le carrousel, les en-têtes des listes de jeux et la vue
`gamecarousel`. Les images de logo supplémentaires nommées par le thème dans
ses fichiers inclus sont aussi remplacées, en conservant leur placement.
Après un changement de thème, relancez l'installation, ou uniquement :

```bash
python3 /userdata/system/partydeck-test/partydeck_theme.py /userdata/system/partydeck-test
```

Si le thème courant ne peut pas être retrouvé, le logo reste installé et un
message l'indique ; le système garde alors son habillage Windows habituel.

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

## Most Wanted 2005 : LAN expérimental

Ce profil reprend les réglages réseau du handler Nucleus v10 de **Need for Speed
Most Wanted (2005)**. La connexion entre instances sous Wine reste à valider sur
Batocera. **Underground 2 n'est pas couvert par cette recette.**

Pour une entrée déjà ajoutée, choisissez dans le configurateur **Session → Profil
du jeu → Most Wanted 2005 · LAN expérimental**, puis enregistrez. Les nouveaux
ajouts dont le nom contient Most Wanted et 2005 sont reconnus automatiquement ;
un titre ambigu exige une sélection manuelle. Les formats `.wine`, `.pc` et
`.wsquashfs` suivent le lancement Wine habituel.

L'onglet réseau propose l'IP LAN du PC (`auto` par défaut), la fréquence LAN
(`6`), un délai entre joueurs (`0`, `15`, `30` ou `60` secondes), et la musique
sur J1 uniquement (activée par défaut). Désactiver cette dernière restriction
réactive la musique pour tous les joueurs. Si l'IP automatique sélectionne une
interface VPN ou une mauvaise carte réseau, renseignez l'IP LAN manuellement.
Le délai décale chaque joueur suivant ; il ne détecte pas la création du salon.

Chaque copie privée reçoit les ports **9900 à 9903**, `ADDR` avec IP et port,
`TRUST_MATCH` avec **l'IP seule**, `TRUST=255.255.255.255` et `LAN_THROTTLE=6`
(par défaut) dans la section `SERVER` de `server.cfg`. Le profil exige
`server.cfg`, `server.dll` et le marqueur `NFSMW_icon.ico` dans le dossier de
lancement. Les premières configurations modifiées sont conservées dans
`nfsmw-before` de chaque joueur. `server.dll` devient une petite copie privée
aux octets inchangés ; la ROM solo n'est pas modifiée ou dupliquée intégralement.

Si les fichiers correspondants sont présents dans `scripts`, le profil active
le multi-instance et le mode fenêtré via Extra Options, puis adapte la résolution
via Widescreen Fix. Il signale les modules ASI absents (Extra Options, Widescreen
Fix, HUD Adapter) ; il **ne les installe pas** et ne vérifie pas leur chargement.
Aucun binaire du jeu, mod, sauvegarde Nucleus ou émulateur n'est distribué.
Le handler Nucleus vise la version 1.3 et une configuration anglaise ; ce profil
ne force pas la langue, ne débloque pas les voitures et n'injecte pas les DLL
d'entrée propres à Nucleus. L'isolation des manettes reste celle de Windows Party.

Procédure de test inspirée du handler :

1. Lancez deux joueurs ; un délai de 30 ou 60 secondes peut aider à préparer J1.
2. Sur J1, ouvrez LAN, créez un serveur avec un nom distinct, puis un salon.
3. Sur J2, ouvrez LAN et créez aussi son serveur avec un autre nom, puis cherchez
   et rejoignez le salon de J1. Attendez l'apparition du ping et réessayez si besoin.

Les tests automatisés vérifient les quatre ports, la préservation des fichiers,
les refus de chemins externes, le retour d'erreur et l'interface FR/EN. Ils ne
valident pas la découverte réseau ni l'entrée dans une course sur Batocera.

**English:** This experimental Most Wanted 2005 profile follows the network
settings of Nucleus handler v10. Underground 2 is not included. Select it in
Session → Game profile for existing entries; new titles containing Most Wanted
and 2005 are detected automatically. All three Wine formats are supported.
The Network tab offers the PC LAN IP (auto by default), LAN throttle (6), a
per-player startup delay (0/15/30/60 seconds), and music on P1 only (enabled).
Disabling the music restriction enables music for every player. Override the IP
when automatic routing picks a VPN or the wrong interface. The delay is timed;
it does not detect lobby readiness.

Private configurations use ports 9900–9903, ADDR with IP:port, TRUST_MATCH with
IP only, and TRUST=255.255.255.255 in the SERVER section. The launch directory
must contain server.cfg, server.dll and NFSMW_icon.ico. Original configurations
are backed up in each player's nfsmw-before folder. Each player receives a small
private server.dll copy with identical bytes. The solo ROM remains unchanged
and is not fully duplicated. Existing Extra Options and Widescreen Fix INIs are
adjusted for multiple instances, windowed rendering and viewport resolution.
Missing ASI modules are logged, never installed; their loading is not verified.
No game/mod binaries, Nucleus saves or emulator files are distributed. Nucleus
targets version 1.3 and English; this profile does not force language, unlock
cars or inject Nucleus input DLLs. Windows Party still isolates controllers.

For testing, P1 creates a uniquely named LAN server and a lobby first. P2 also
creates a differently named LAN server, then finds and joins P1's lobby. A
30/60-second startup delay may help prepare P1 first. Wait for ping and retry if
needed. Automated checks cover four-player configuration, file isolation,
error reporting and FR/EN UI, not actual discovery or racing under Wine.

Références / references :
[Nucleus handler](https://hub.splitscreen.me/handler/nBgGXtk5pTq9Taq2F),
[PartyDeck issue #4](https://github.com/partydeck/partydeck/issues/4).

## GPU et premier plan

Dans **Session → GPU de rendu**, le choix est enregistré par jeu :

- **Automatique** (défaut, y compris pour les anciens profils) : conserve les
  sélections Vulkan/PRIME explicites. À défaut, sur un PC hybride possédant un
  GPU NVIDIA avec le pilote propriétaire chargé et un autre GPU, demande le
  rendu NVIDIA avec PRIME et le filtre Vulkan NVIDIA. Sur les autres machines,
  conserve le comportement système.
- **Configuration système** : n'ajoute aucune préférence GPU. Les pilotes et
  l'environnement choisissent le GPU ; ce mode ne mesure pas le GPU employé
  par EmulationStation et ne garantit pas une correspondance avec celui-ci.
- **NVIDIA** : demande explicitement le GPU NVIDIA pour Gamescope et Wine, en
  remplaçant les sélections Vulkan/PRIME contradictoires de l'environnement.
  Ce mode exige un pilote NVIDIA fonctionnel.

Il n'y a pas d'ID PCI ni de modèle de GPU codé en dur. Le chemin NVIDIA a été
validé jusqu'au menu de Most Wanted sur Batocera 44 Xorg avec une T550 Laptop.
Cela ne valide pas toutes les combinaisons de pilotes et GPU hybrides ; les
configurations AMD/Intel conservent leur sélection système. Les environnements
compositeur et Wine reçoivent les mêmes variables NVIDIA, sans imposer un
rendu logiciel ni désactiver Glamor.

Le lanceur remet ses propres fenêtres devant ES après leur placement et rend
le focus à J1 après cette phase. Il ne reprend pas continuellement le focus
pendant la partie. Les processus Gamescope ne lisent plus l'entrée standard du
terminal SSH ; les contrôles restent fournis par les périphériques et fenêtres.
Le déblocage observé après Entrée dans SSH n'est pas encore attribué avec
certitude à l'entrée standard : ce changement reste à vérifier sur la machine.

**English:** Session → Rendering GPU stores a choice per game. Automatic keeps
explicit Vulkan/PRIME settings; otherwise it requests NVIDIA rendering only on
a hybrid system with a bound proprietary NVIDIA driver and another GPU. Other
systems retain their default behavior. System configuration adds no GPU
preference; it does not inspect or mirror EmulationStation's actual GPU. NVIDIA
explicitly requests NVIDIA rendering for Gamescope and Wine and replaces
conflicting Vulkan/PRIME selections; it requires a working NVIDIA driver.
No GPU model or PCI ID is hardcoded. Reaching the Most Wanted menu was validated
on Batocera 44 Xorg with a T550 Laptop; other driver/GPU combinations remain to
be tested. AMD/Intel systems retain system selection. No software rendering or
Glamor-disable workaround is enabled. Owned windows are raised/focused after
placement, then P1 receives focus. Focus is not continually taken during play.
Gamescope standard input is detached from SSH; keyboard/controller input still
comes through devices and windows. The observed Enter-to-unblock behavior has
not been conclusively attributed to stdin, so this part needs machine testing.

Après un échec Wine ou Gamescope, la session arrête désormais ses autres joueurs
également sous Xorg, pour ne pas laisser ES attendre une instance survivante.
Le code d'erreur réel reste transmis. La fermeture normale Xorg continue
à attendre tous les joueurs. Cela ne corrige pas le plantage Vulkan lui-même.

**English:** On Wine or Gamescope failure, Xorg sessions now stop their remaining
owned players rather than leaving ES waiting for a survivor. The real failure
code is retained. Normal Xorg exits still wait for all players. This does not
fix the underlying Vulkan crash.
