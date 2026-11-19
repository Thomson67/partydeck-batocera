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


## UMU hors ligne / Offline UMU

UMU 1.4.4 vérifie une route vers `1.1.1.1:53` avec un socket UDP. Il traite
`ENETUNREACH` comme un accès hors ligne et vérifie le runtime déjà installé,
mais relance l’exception pour `EHOSTUNREACH`. La route `unreachable default`
renvoyait cette seconde erreur et empêchait Proton de démarrer.

Le LAN privé ne configure désormais aucune route par défaut. Les routes du
réseau privé et de diffusion restent présentes, et la vérification hors ligne
renvoie `ENETUNREACH`. Le vérificateur réseau teste ce comportement avant les
échanges UDP entre joueurs. Il n’ouvre pas d’accès Internet au jeu. Le runtime
Steam/UMU nécessaire doit déjà être installé pour un lancement hors ligne.

UMU 1.4.4 uses a route-only UDP connect to 1.1.1.1:53. ENETUNREACH selects its
offline runtime check; EHOSTUNREACH is re-raised. The previous unreachable
default route produced EHOSTUNREACH and prevented Proton startup. Private LAN
now has no default route, retaining only private and broadcast routes. The
verifier checks the expected ENETUNREACH behavior before player UDP exchanges.
Internet remains unavailable; the required UMU/Steam runtime must be installed
before an offline launch.


## Distributions Proton privées / Private Proton distributions

Les versions récentes de Proton ouvrent `dist.lock` en écriture même lorsque
le préfixe modèle existe. Elles peuvent aussi créer `files/share/default_pfx`
ou appliquer des corrections de distribution. Le dossier hôte et les
protections UMU étant en lecture seule, un runner directement exposé ainsi
échoue avant de lancer le jeu.

Windows Party crée des vues OverlayFS temporaires des distributions Proton UMU
pour chaque joueur. Les fichiers installés sont les couches inférieures,
les écritures vont dans les couches propres au joueur. La vue reste en lecture
seule pour les contrôles d’intégrité du wrapper UMU. Une passerelle temporaire vers le lanceur UMU remplace `PROTONPATH` par
l’alias privé RW après la sélection native du runner. Déclarer le chemin RO
comme RW ne suffit pas à retirer son attribut de montage : Proton doit utiliser
l’alias RW lui-même. Le lanceur original est conservé par un bind privé ;
aucun fichier hôte n’est réécrit. Les alias `runtime/<jeu>/jN/proton-runners/<runner>`
sont stables entre lancements pour les liens de DLL conservés par Proton.
Seules les couches d’écriture et le relais sont temporaires.
Les couches sont démontées et retirées à la fin de la commande native Wine.
En cas de nettoyage impossible, le chemin est journalisé et conservé.
Ce n’est pas une copie complète des runners ; les binaires hôtes restent intacts.

Recent Proton versions open dist.lock for writing unconditionally and may also
create their default prefix or perform distribution fixups. Windows Party gives
each player temporary OverlayFS views of UMU Proton distributions. Installed
files remain the lower layer; writes use player-private upper layers. The view
is read-only for the UMU wrapper's integrity/protection pass. A temporary UMU
launcher relay changes PROTONPATH to the writable private alias after native
runner selection. Exporting the read-only path as RW did not clear its mount
flag. The original UMU zipapp is pinned by a private bind and executed unchanged;
no host launcher is rewritten. Aliases at `runtime/<game>/jN/proton-runners/<runner>`
are stable across launches so Proton DLL links never persist a random temporary
path. Only writable layers and the relay are temporary. Views are unmounted and removed
after native Wine returns; failed cleanup is logged and retained. Full runner
copies are not made and host binaries stay unchanged. A user confirmed UMU
game startup after installing the writable-alias relay (GDK-Proton11-12-Custom-UMU).
Other runner versions still need individual validation.
