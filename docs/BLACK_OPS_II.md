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

Pour le partage d’écran, Windows Party expose un mode de rendu 16:9 d’au
moins 1280×720 et démarre Plutonium en fenêtré sans bordure. Gamescope adapte ensuite
l’image à la place de chaque joueur. Le journal distingue la résolution du
jeu de la taille de la fenêtre.

## Modes et bots

Retrouvez les cartes et modes dans le menu du client. Les bots standard sont
disponibles dans les modes multijoueur qui les proposent. Pour tester à deux,
commencez par un Match à mort par équipe, puis essayez Zombies en Survie.
[Bot Warfare](https://github.com/ineedbots/t6_bot_warfare) est un mod distinct
pour le multijoueur Plutonium.

## Client fourni avec le jeu

Les choix **Multijoueur** et **Zombies** lancent les exécutables du jeu
directement. **Lancement d’origine** reprend son `autorun.cmd`. Windows Party
configurera une identité distincte par joueur si Goldberg ou le module LAN
de Project Nova est reconnu. La connexion dépend du client installé.

Dans `/userdata/system/windows-party/logs/`, le journal de session indique
le client, l’exécutable ou le mode sélectionné, et le port de Plutonium.

## Références

- [Plutonium en LAN](https://plutonium.pw/docs/custom-games/#lan-play)
- [Plutonium LAN sous Linux](https://forum.plutonium.pw/topic/40011/setting-up-plutonium-on-the-steam-deck-and-linux-lan-only)
- [Handler Nucleus Zombies Plutonium LAN](https://github.com/peykc/plutonium-handler/tree/main/LAN)
- [Handler Nucleus Project Nova Multijoueur](https://hub.splitscreen.me/api/v1/handler/2W4NKZCTYmLqpwxrY)
- [Handler Nucleus Project Nova Zombies](https://hub.splitscreen.me/api/v1/handler/8ojcrL79RrFdpiaHD)
