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

Deux boutons fixes sont présents sous les réglages : **Lancer la partie** et
**Enregistrer**. Descendez après la dernière option pour les sélectionner. Lancer
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
