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

Windows Party lance le serveur local, puis connecte
chaque joueur automatiquement. Dans la fenêtre **Zelda Online**, J1 crée un
groupe avec **Story Co-op** activé et invite J2. J2 accepte. Aux sessions
suivantes, recréez le groupe avec le même code d’équipe pour retrouver la
campagne. Le code par défaut est `partydeck`.

Les sauvegardes d’équipe se trouvent dans
`/userdata/saves/windows-party/<jeu>/story-coop/data/story/`. Le journal du
serveur est dans `story-coop/server.log`, à côté du dossier `data`.
