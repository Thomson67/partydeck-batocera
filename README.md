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

Dans **Choisir un jeu**, **LB/RB** parcourt la liste par pages de neuf entrées.
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
