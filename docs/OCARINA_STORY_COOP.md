# Ocarina of Time Story Co-op dans Windows Party

Le profil utilise la [version officielle Story Co-op 1.0.5](https://github.com/cranebeaker/ocarina-coop/releases/tag/v1.0.5).
Préparez le jeu via SSH sur Batocera. L’outil assemble le client Windows et
le serveur Linux du mod avec votre fichier de jeu local.

## Préparer le jeu

Si Story Co-op 1.0.5 démarre déjà en solo, ajoutez votre `.wine` ou
votre `.wsquashfs` existant et sélectionnez le profil **Ocarina of Time ·
Story Co-op**. PartyDeck lit le dossier indiqué par `DIR` dans `autorun.cmd`.
Si le serveur Linux manque, PartyDeck le télécharge et le vérifie au premier
lancement, puis le conserve pour les prochaines sessions.

Avec un `oot.o2r` généré par cette version du client, créez directement
l’archive. Le même outil accepte aussi `oot-mq.o2r`.

```bash
launcher=/userdata/system/windows-party/windows-party
jeu='/userdata/roms/windows/Ocarina of Time Story Co-op.wsquashfs'
"$launcher" preparer-ocarina '/chemin/vers/oot.o2r' "$jeu"
"$launcher" ajouter "$jeu" 2 horizontal auto
```

Si vous partez d’une ROM `.z64` compatible, préparez d’abord un dossier Wine.

```bash
/userdata/system/windows-party/windows-party preparer-ocarina \
  '/chemin/vers/Ocarina.z64' '/userdata/roms/windows/Ocarina of Time Story Co-op.wine'
```

Dans le système **Windows** d’EmulationStation, ouvrez le dossier de jeu en
solo et laissez Ship of Harkinian générer le fichier `.o2r`. Fermez le jeu,
puis convertissez le dossier `.wine` en `.wsquashfs` avec Ultimate Wine
Toolbox en conservant la commande `soh.exe` et le dossier `drive_c/game`.
Conservez le dossier `PartyDeck-Story-Coop` à côté de `soh.exe` pour embarquer
le serveur dans l’archive. Ajoutez ensuite le `.wsquashfs` à Windows Party.

## Jouer

Après avoir actualisé la liste des jeux dans EmulationStation, ouvrez l’entrée
dans **Windows Party**. Le profil **Ocarina of Time · Story Co-op** détecte
ce nom. Il est aussi sélectionnable dans **Session → Profil du jeu**.
Choisissez de deux à quatre joueurs.

Windows Party lance le serveur local. J1 crée le groupe et les autres
joueurs le rejoignent automatiquement. Chaque fenêtre s’ouvre directement
sur le choix de la sauvegarde. Sélectionnez la sauvegarde à jouer dans
chaque fenêtre. La démo de l’écran titre est sautée pour éviter que les
personnages distants y apparaissent.

Avec la création automatique du groupe, la fenêtre Zelda Online se masque
après la connexion. Pour la rouvrir, appuyez sur **Échap** dans la fenêtre
du joueur et ouvrez **Network → Zelda Online → Open Window**. La croix de
la fenêtre ferme le panneau.

Au démarrage, PartyDeck vérifie que la fenêtre de jeu apparaît pour chaque
joueur. Si un autre joueur est déjà affiché et que la fenêtre manque
toujours après une minute, PartyDeck tente de la réafficher, puis relance
une fois le joueur concerné si nécessaire. Le serveur et les autres
joueurs continuent à tourner.

Pour enregistrer un démarrage intermittent, créez le fichier
`/userdata/system/windows-party/trace-windows-next` avant de relancer
depuis EmulationStation. Pour ce lancement, PartyDeck laisse la fenêtre
en défaut en place et enregistre les événements Wine et Gamescope dans
`logs/window-trace.log` du dossier privé de chaque joueur.

Dans **Réseau**, vous pouvez régler le port local, le JSON SoH, les positions
visibles, la téléportation et la progression partagée. Avec la progression
partagée, **Partager les rubis**, **Partager les munitions** et **Partager les PV**
se règlent séparément. **Conserver** suit le réglage combiné enregistré dans
le jeu. Chaque joueur paie ses propres achats. Le réglage des PV concerne
les cœurs de soin ramassés. Les réceptacles et les quarts de cœur font partie
de la progression d’équipe.

Dans **Réseau → Cycle jour/nuit**, **Horloge commune du serveur** garde
l’horloge synchronisée de Story Co-op. **Cycle d’origine par joueur**
applique les règles de temps du jeu à chaque zone, avec une heure locale
pour chaque joueur. Le temps reste notamment figé au village.

Le code de campagne
vide reprend celui du JSON de J1, ou `partydeck` si celui-ci est vide.
Le serveur associe une campagne au nom de J1 et à ce code. Conservez les
deux pour retrouver votre progression. Vous pouvez aussi désactiver la
création automatique du groupe pour gérer les invitations dans Zelda Online.
Le PvP, les équipes d’Anchor et son serveur distant sont propres à l’autre
profil.

Dans **Joueurs**, choisissez le nom et le skin de chacun dans le catalogue
Zelda Online. Windows Party récupère au premier besoin les skins choisis
depuis le serveur de ressources du mod, puis les charge chez tous les
joueurs de la session. Les skins personnalisés convertis avec
[skinconv](https://github.com/cranebeaker/ocarina-coop/tree/v1.0.5/tools/skinconv)
sont détectés dans `mods` au premier lancement d’un `.wsquashfs`. Valider la ligne d’un skin permet
aussi de saisir sa référence, par exemple `linkle` ou
`linkle|linkle_1.o2r,linkle_2.o2r` si le skin utilise plusieurs archives.
Quand un joueur choisit explicitement un skin, Windows Party masque dans
son instance le pack **Enhanced 3DS Link** et les archives O2R qui
remplacent le squelette de Link. Choisissez **Mods du jeu** pour retrouver
l’apparence de votre installation, même après avoir utilisé un skin
personnalisé. Windows Party prépare aussi le pack **Enhanced 3DS Link**
pour que les autres joueurs voient cette apparence. Si la préparation du skin échoue, le jeu
se lance avec l’apparence précédente et l’erreur figure dans le journal.

Dans **Gameplay**, **Caméra libre au stick droit** utilise la manette
attribuée à chaque joueur au lancement. Les boutons C auparavant
associés aux directions du stick passent sur la croix directionnelle
lorsqu’ils n’ont pas déjà une autre commande à la manette. Désactiver
l’option restaure les affectations précédentes.
L’inversion horizontale et verticale se règle séparément en caméra libre
et en première personne. Les réglages de première personne s’appliquent
aussi à la visée. **Conserver** reprend les réglages propres à chaque
joueur.

L’onglet **Image & son** reprend la résolution interne, le MSAA, la VSync,
le filtre des textures, les volumes et la musique sur J1 uniquement.

Windows Party applique à la copie privée de `soh.exe` de chaque joueur le
correctif du crash audio observé pendant l’introduction de la version 1.0.5.

Les sauvegardes d’équipe se trouvent dans
`/userdata/saves/windows-party/<jeu>/story-coop/data/story/`. Le journal du
serveur est dans `story-coop/server.log`, à côté du dossier `data`.
