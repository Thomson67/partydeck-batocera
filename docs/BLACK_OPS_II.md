# Black Ops II dans Windows Party

Le profil expérimental **Black Ops II · LAN expérimental** utilise le jeu déjà installé au format `.wine`, `.pc` ou `.wsquashfs`. Il lance une instance par joueur et relie les instances à un LAN privé de la machine. Les réglages écrits par le profil sont propres à chaque joueur.

Vous pouvez créer l’archive avec la campagne (`t6sp.exe`) comme commande `CMD` dans `autorun.cmd`. Conservez `t6mp.exe`, `t6zm.exe` et leurs fichiers dans le dossier du jeu, à côté de l’exécutable solo. L’entrée **Windows** lance la campagne. Dans **Windows Party**, le mode choisi lance l’exécutable correspondant depuis la même archive.

## Choisir le mode

1. Dans **Configurer Windows Party**, liez votre jeu au profil **Black Ops II · LAN expérimental**. Commencez avec deux joueurs.
2. Dans **Options → Mode de jeu**, sélectionnez **Multijoueur** pour `t6mp.exe` ou **Zombies** pour `t6zm.exe`. Choisissez **Lancement d’origine** si le pack utilise un batch ou un lanceur particulier. Ce réglage reprend la commande déclarée dans `autorun.cmd`.
3. Lancez l’entrée Windows Party. Créez une partie personnalisée sur J1, puis cherchez le salon ou envoyez une invitation à J2 selon le menu proposé par le client. Avec Project Nova, ouvrez le salon avant d’inviter J2.
4. Commencez par un Match à mort par équipe avec J2. Si le menu de la partie propose les bots, ajoutez-en un sur chaque équipe. Relancez ensuite en **Zombies** et essayez un salon Survie. Le mode et la carte se choisissent dans le jeu.

Les modes dépendent du client et des cartes disponibles. En multijoueur, vérifiez aussi Domination, Point stratégique, les modes Hardcore et le Jeu d’armes. En Zombies, vérifiez TranZit, Survie, Lutte et Infection sur les cartes qui les proposent. Les bots standard sont une option de certains modes multijoueur.

## Clients compatibles avec le profil de test

- **Goldberg** : si le jeu possède un dossier `steam_settings`, le profil lui applique une identité distincte et stable par joueur. Le lancement, l’authentification du jeu et la disponibilité du salon dépendent de l’édition installée. La connexion en partie reste à valider sur Batocera.
- **Project Nova** : le profil détecte le module LAN déjà présent dans `Ayria/Plugins` et configure les identités indépendantes. Les handlers Nucleus de PoundlandBacon ont servi de référence. Leur procédure prévoit la recherche d’une partie locale depuis le menu en ligne, ou un salon personnalisé ouvert avec des invitations. Ils documentent aussi le remplissage automatique avec des bots en multijoueur via leur recherche de partie.
- **Plutonium T6** : piste à valider si le salon Goldberg est indisponible. Le client propose un mode LAN et une connexion IP. Bot Warfare fournit des bots configurables pour le multijoueur. Les coéquipiers IA en Zombies demandent un mod Zombies distinct.

Si vous utilisez UMU, lancez d’abord le jeu en solo avec le même runner pour qu’il puisse initialiser son Steam Runtime. Le journal de session, dans `/userdata/system/windows-party/logs/`, indique quel client a été reconnu. Si J2 ne voit pas J1, relevez les lignes `Black Ops II J1` et `Black Ops II J2` ainsi que le menu ou message qui bloque.

## Références

- [Nucleus Co-op et Black Ops II](https://nucleuscoop.org/games/bo2/)
- [Notes du handler multijoueur Nucleus](https://hub.splitscreen.me/api/v1/handler/2W4NKZCTYmLqpwxrY)
- [Notes du handler Zombies Nucleus](https://hub.splitscreen.me/api/v1/handler/8ojcrL79RrFdpiaHD)
- [Handler Zombies Plutonium LAN](https://github.com/peykc/plutonium-handler/tree/main/LAN)
- [Plutonium en LAN](https://plutonium.pw/fr/docs/custom-games/#lecture-lan)
- [T6 Bot Warfare](https://github.com/ineedbots/t6_bot_warfare)
