# Black Ops II dans Windows Party

Vous pouvez utiliser une seule archive `.wsquashfs` avec `t6sp.exe` dans
l’autorun de la campagne. Conservez `t6mp.exe`, `t6zm.exe` et les données du jeu
dans le même dossier. Le profil **Black Ops II · LAN expérimental** accepte
également les jeux `.wine` et `.pc`.

## Plutonium T6 en LAN

Le réseau privé de Windows Party relie les joueurs sur la même machine.
Utilisez le client Plutonium en mode LAN pour jouer quand le menu
« Online » du client d’origine reste bloqué sur la connexion.

1. Installez [Plutonium](https://plutonium.pw/docs/install/) sur Windows, ouvrez
   son lanceur et laissez-le télécharger les fichiers du client. Configurez
   Black Ops II avec les fichiers d’une installation valide.
2. Dans l’explorateur Windows, ouvrez `%LOCALAPPDATA%\Plutonium`. Sur Batocera,
   créez `/userdata/system/windows-party/plutonium/` et copiez-y les dossiers
   `bin` et `games`, ainsi que `storage` s’il existe. Vérifiez que
   `bin/plutonium-bootstrapper-win32.exe` et `games/t6mp.exe` ou
   `games/t6zm.exe` se trouvent directement sous cette arborescence.
3. Dans **Configurer Windows Party**, liez le jeu et choisissez
   **Options → Mode de jeu → Multijoueur · Plutonium LAN** ou
   **Zombies · Plutonium LAN**. Pour le premier essai, choisissez deux joueurs.
4. Sur **J1**, choisissez **Partie personnalisée** et lancez une carte.
   Sur **J2**, une fois au menu, ouvrez la
   [console de jeu](https://plutonium.pw/docs/opening-console/) et saisissez
   `connect 192.168.247.11:1111`. En Zombies, J1 peut attendre les autres
   joueurs pendant le chargement de la carte.

Les fichiers du client sont préparés dans la vue privée de chaque joueur.
La campagne garde sa commande d’origine dans EmulationStation. Si vous
utilisez UMU, lancez d’abord le jeu en solo avec le même runner pour initialiser
son Steam Runtime.

À deux joueurs en partage horizontal, **Remplir le partage horizontal**
active un rendu Plutonium au format de chaque moitié de l’écran. Sur un
écran 1920×1080, chaque joueur a une fenêtre 1920×540 et le jeu rend en
2560×720 (32:9). Gamescope réduit l’image à la taille de la fenêtre. Vous
pouvez désactiver cette option pour reprendre le rendu 16:9. Le journal
distingue la résolution du jeu de la taille de la fenêtre.

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
