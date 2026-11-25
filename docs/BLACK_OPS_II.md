# Black Ops II dans Windows Party

Vous pouvez utiliser une seule archive `.wsquashfs` avec `t6sp.exe` dans
l’autorun de la campagne. Conservez `t6mp.exe`, `t6zm.exe` et les données du jeu
dans le même dossier. Le profil **Black Ops II · LAN expérimental** accepte
également les jeux `.wine` et `.pc`.

## Plutonium T6 en LAN

Le réseau privé de Windows Party relie les joueurs sur la même machine.
Utilisez le client Plutonium en mode LAN pour jouer quand le menu
« Online » du client d’origine reste bloqué sur la connexion.

1. Dans **Configurer Windows Party**, liez le jeu et enregistrez son
   profil **Black Ops II**. Windows Party récupère le client T6 depuis le
   serveur officiel de Plutonium en arrière-plan si l’installation est
   nécessaire. Si le téléchargement a échoué, Windows Party réessaie au
   lancement, avant de créer le LAN privé. L’archive du jeu est fournie
   séparément par l’utilisateur.
2. Choisissez **Options → Mode de jeu → Multijoueur · Plutonium LAN** ou
   **Zombies · Plutonium LAN**. Pour le premier essai, choisissez deux joueurs.
3. Sur **J1**, choisissez **Partie personnalisée** et lancez la carte.
   Laissez **J2** et les autres invités au menu. Ils rejoignent J1
   automatiquement dès que la partie est prête. En Zombies, J1 peut
   attendre les invités pendant le chargement.

**Options → Rejoindre automatiquement la partie de J1** est activé par
défaut. Si la connexion échoue, ouvrez la
[console de jeu](https://plutonium.pw/docs/opening-console/) sur le joueur
invité et saisissez `connect 192.168.247.11:1111`. Si l’option est activée,
`F9` envoie aussi cette commande depuis la fenêtre de l’invité.

Une installation manuelle existante dans
`/userdata/system/windows-party/plutonium/` garde la priorité. Le détail
du premier téléchargement figure dans `logs/plutonium-t6.log`.
L’installateur ne met pas automatiquement à jour un client déjà disponible.

Les fichiers du client sont préparés dans la vue privée de chaque joueur.
La campagne garde sa commande d’origine dans EmulationStation. Si vous
utilisez UMU, lancez d’abord le jeu en solo avec le même runner pour initialiser
son Steam Runtime.

À deux joueurs en partage horizontal, **Rendu en partage horizontal**
utilise par défaut la résolution de chaque moitié. Sur un écran 1920×1080,
chaque joueur rend directement en 1920×540 (32:9).
**Ultrawide · hauteur minimale 720p** reprend le rendu 2560×720 sur cet
écran si le jeu refuse de démarrer à 540 pixels de haut. **Format 16:9**
garde le mode standard. Le journal distingue la résolution du jeu de la
taille de la fenêtre.

## Modes et bots

Retrouvez les cartes et modes dans le menu du client. Les bots standard sont
disponibles dans les modes multijoueur qui les proposent. Pour tester à deux,
commencez par un Match à mort par équipe, puis essayez Zombies en Survie.
[Bot Warfare](https://github.com/ineedbots/t6_bot_warfare) est un mod distinct
pour le multijoueur Plutonium.

## Client fourni avec le jeu

**Lancement d’origine** reprend l’`autorun.cmd` pour les installations qui
ont déjà leur propre lanceur LAN. Les anciens réglages **Multijoueur** et
**Zombies** sont convertis vers leurs équivalents Plutonium LAN.

Si Plutonium signale une erreur sur `binkw32.dll`, consultez le journal de
session dans `/userdata/system/windows-party/logs/`. Il indique le dossier
Windows transmis au client, par exemple `C:\game`, et signale une DLL absente
ou sans le symbole attendu. Dans ce cas, vérifiez les fichiers de
l’installation Black Ops II dans Steam.

## Références

- [Plutonium en LAN](https://plutonium.pw/docs/custom-games/#lan-play)
- [Plutonium LAN sous Linux](https://forum.plutonium.pw/topic/40011/setting-up-plutonium-on-the-steam-deck-and-linux-lan-only)
- [Handler Nucleus Zombies Plutonium LAN](https://github.com/peykc/plutonium-handler/tree/main/LAN)
- [Handler Nucleus Project Nova Multijoueur](https://hub.splitscreen.me/api/v1/handler/2W4NKZCTYmLqpwxrY)
- [Handler Nucleus Project Nova Zombies](https://hub.splitscreen.me/api/v1/handler/8ojcrL79RrFdpiaHD)
