# LAN privé : séparation de l’affichage / Display separation

Gamescope et son Xwayland restent dans le réseau hôte, comme lors d’un
lancement Windows Party normal. Seul le processus enfant qui lance le bac à
sable Wine entre dans l’espace réseau privé du joueur. Le service hôte de
contrôles virtuels reste également hors de cet espace.

Le processus enfant ouvre l’espace via le PID de son gardien. Son identité
(device/inode) doit correspondre au descripteur épinglé par le superviseur ;
l’espace hôte est refusé. Un PID réutilisé ne doit jamais conduire à lancer le
jeu dans un autre espace. Cette méthode ne dépend pas de la transmission des
descripteurs par Gamescope. La fermeture de la session conserve le même groupe
de processus pour arrêter les descendants avant de fermer le LAN.

L’autotest UDP et le démarrage d’une course à deux joueurs ont été validés
par l’utilisateur sur Batocera v44 Wayland avec NVIDIA T550. Les autres
configurations et les courses à trois/quatre joueurs restent à valider. L’état `futex_do_wait` de speed.exe ne prouve pas à lui seul la cause du
blocage observé auparavant.

## English

Gamescope and its Xwayland keep the host network, like normal Windows Party
launches. Only the child launching the Wine sandbox enters the player's private
network namespace. The virtual input watcher also stays on the host.

The child opens the holder process's namespace and verifies its device/inode
against the supervisor's pinned FD. It rejects the host namespace and a reused
holder PID with a different namespace. No namespace FD needs to survive
Gamescope's child-spawning code. Process group ownership and shutdown order are
unchanged: stop game descendants before closing the LAN.

The real UDP verifier and a two-player race starting were confirmed by the
user on Batocera v44 Wayland with NVIDIA T550. Other hardware and three/four
player races remain unvalidated. A speed.exe `futex_do_wait` state alone does
not identify the previous startup blockage.
