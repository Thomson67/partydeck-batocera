# Connexions automatiques / Automatic sessions

Version de test : les appels au jeu doivent encore être validés sur Batocera.
Les tests locaux valident les fichiers privés, les arguments, la coordination
réseau, les traductions et les états du compagnon ; ils ne remplacent pas une
partie réelle sous Wine.

## Utilisation

Les profils existants reçoivent les nouvelles options à leur chargement. Elles
ne s'appliquent que lorsqu'au moins deux joueurs participent. L'hôte est J1 par
défaut ; le profil permet de choisir J2, J3 ou J4 et le port. Un hôte absent de
la session ou un port UDP déjà occupé provoque un refus avant le lancement.

| Profil | Réglage | Fonctionnement |
| --- | --- | --- |
| Borderlands 2 | Joueurs → Connexion automatique à l’hôte (SDK privé) | Sélectionnez Réseau local sur les deux jeux, puis faites Continuer uniquement sur l’hôte. PartyDeck détecte son port UDP avant de connecter les clients à l’adresse LAN du PC. |
| SM64CoopDX | Options → Héberger et rejoindre automatiquement | L'hôte démarre un serveur avec la sauvegarde choisie dans le profil ; les clients attendent son ouverture de port, puis démarrent en connexion directe. |
| Left 4 Dead 2 | Options → Héberger et rejoindre automatiquement | Avec « Choisir dans le jeu », l'hôte choisit le mode et le type de serveur dans le salon. Avec une campagne sélectionnée dans le profil, sa première carte est lancée en Coop, Réalisme ou Versus selon le mode choisi. Les clients démarrent au menu et rejoignent après une réponse A2S_INFO du serveur (AppID 550, carte chargée). |
| SoH / Anchor | Réseau → Connexion automatique Anchor | Fonction existante : chaque joueur rejoint le serveur et la salle communs. Il faut charger les sauvegardes compatibles. |
| Hollow Knight | Réseau → Héberger et rejoindre automatiquement | Fonction existante des compagnons HKMP et HKMultiplayer. |
| Most Wanted 2005 | Réseau → LAN privé et raccourci LB+RB | Configuration réseau et saisie/validation du nom existantes. Création des serveurs et du salon encore manuelle. Le handler Nucleus v10 demande lui aussi ces opérations manuelles ; aucun script de touches à délai fixe n'est ajouté. |

Pour SM64CoopDX, la sauvegarde 1 reprend la valeur initiale du modèle commun.
Le choix 1–4 est explicite dans le profil. Les sauvegardes des clients restent
individuelles ; le fichier de l'hôte n'est pas copié sur leurs profils.

En LAN automatique, Left 4 Dead 2 ouvre un écran de préparation à la manette
avant de lancer les joueurs. Les modes Campagne, Mutation, Réalisme, Versus,
Versus Réalisme, Survie, Survie versus et Collecte proposent une campagne ou
une sélection de cartes compatibles. La difficulté est réglable en Campagne
et Réalisme. Les choix s'appliquent à la session en cours. « Choisir dans le
jeu » ouvre le salon pour les cartes et variantes supplémentaires.

## Borderlands 2 : SDK privé

Le premier lancement multijoueur avec cette option télécharge le SDK officiel
Willow2 v3.8 (environ 13 Mo compressés). Le SHA-256 est fixé dans le module ;
une archive différente est refusée. Le téléchargement est conservé dans
`/userdata/system/windows-party/dependencies/willow2-sdk-v3.8.zip`.

Le SDK et le compagnon sont activés uniquement pour les joueurs qui rejoignent.
L’hôte sélectionne Réseau local et continue sa partie depuis les menus natifs.
Avec le port par défaut 7777, PartyDeck conserve les arguments de lancement du
jeu. Il attend qu’un processus de l’hôte ouvre le port avant de transmettre
l’adresse IPv4 LAN aux clients. Le compagnon ne modifie aucun personnage ni
aucune sauvegarde. La sélection du personnage client reste à vérifier en jeu.

Une DLL `ddraw.dll` différente ou un SDK incompatible déjà présent est conservé.
Dans ce cas, un message dans le journal explique que le LAN reste manuel.
Notre option ne remplace pas les DLL d'autres mods. Le mode manuel ou un
lancement à un seul joueur désactive le compagnon de cette copie privée.

La connexion est limitée à six tentatives espacées de vingt secondes, après
le signal de disponibilité de l'hôte. Une sortie volontaire après connexion
ne force pas le joueur à revenir dans la partie. Un nouvel identifiant de
session empêche de reprendre un ancien signal de disponibilité.

## Lanceurs et attentes

Les EXE reconnus sont `Borderlands2.exe`, `sm64coopdx.exe` et `left4dead2.exe`.
Le module traite la commande native ou un batch d'entrée référencé par cette
commande ; il adapte uniquement les lignes qui lancent effectivement l'EXE.
Les scripts imbriqués et les commandes shell complexes non reconnues restent
manuels. Les options réseau préexistantes sont signalées comme un conflit :
sélectionnez le mode manuel pour conserver ce lancement personnalisé.

Les batchs ne sont modifiés que dans la vue privée. Leur état précédent est
restauré au changement de mode et avant de réappliquer des arguments, sauf si
le fichier a été modifié entre-temps. Les arguments ne s'accumulent pas.

SM64CoopDX attend jusqu'à 120 secondes l'hôte. Un batch
peut alors démarrer sans la commande de connexion ; une commande directe
conserve son argument de connexion, annulable dans le jeu. La vérification
de port SM64 est une vérification d'ouverture, pas une preuve de handshake
complet. Left 4 Dead 2 lance le client tout de suite et attend en parallèle
jusqu'à cinq minutes la réponse A2S du serveur, y compris le challenge.
Le client lit la commande de connexion dans un fichier CFG privé. Si l'hôte
ne répond pas à temps, le client reste disponible au menu.

## Vérification sur Batocera

1. Borderlands 2 : deux joueurs, vérifier le LAN automatique au menu ; choisir
   les personnages, continuer sur l'hôte, vérifier la connexion du client.
   Fermer puis relancer pour vérifier la conservation de la progression.
2. SM64CoopDX : choisir la sauvegarde hôte, lancer deux joueurs, vérifier
   l'hébergement et la connexion ; refaire avec J2 comme hôte.
3. Left 4 Dead 2 : tester une campagne choisie dans les menus puis une campagne
   choisie dans le profil ; vérifier la connexion des autres survivants.
4. Repasser chaque profil en mode manuel et vérifier les menus habituels.

Les journaux de session sont dans `/userdata/system/windows-party/logs`.
Les plans de lancement sont dans `runtime/<jeu>/jN/autoconnect-launch.json`.

## Sources consultées

Consultation du 21 novembre 2026, sans redistribuer les handlers Nucleus :

- Nucleus Borderlands 2, handler v13, `YztSFvxEtWgjuGwTT` :
  https://hub.splitscreen.me/handler/YztSFvxEtWgjuGwTT
  Le texte du handler demande LAN puis Find Games manuellement.
- Nucleus Left 4 Dead 2, handler v17, `wFsXDjoAkHpL4XZm8` :
  https://hub.splitscreen.me/handler/wFsXDjoAkHpL4XZm8
  Ses réglages Source incluent `sv_lan 1` et `sv_allow_lobby_connect_only 0`.
- Nucleus Most Wanted, handler v10, `nBgGXtk5pTq9Taq2F` :
  https://hub.splitscreen.me/handler/nBgGXtk5pTq9Taq2F
- SM64CoopDX, sources des arguments et du démarrage réseau :
  https://github.com/coop-deluxe/sm64coopdx/blob/main/src/pc/cliopts.c
  https://github.com/coop-deluxe/sm64coopdx/blob/main/src/pc/pc_main.c
- Willow2 SDK v3.8 et API de mods :
  https://github.com/bl-sdk/willow2-mod-manager/releases/tag/v3.8
- Exemple de transition LAN via SDK, consulté comme référence d'API :
  https://github.com/PyrexBLJ/blsdk-mods/blob/main/AllMyHomiesHateSHiFT/__init__.py
  Notre compagnon est distinct et n'embarque pas ce mod ancien.

## English

Test implementation; Wine/game calls still require live Batocera validation.
Existing profiles default to automatic mode for multiplayer sessions. Single
player sessions leave automation disabled. The host defaults to P1, and can
be selected in each profile together with the UDP port.

Borderlands 2 enables the pinned, checksum-verified Willow2 SDK v3.8 in
clients' private overlays. Each player selects LAN in the game. The host selects
a character and continues the game without the PartyDeck SDK module.
Clients wait for the host to own the configured UDP port and attempt direct
travel to the PC's LAN address up to six times. Existing incompatible loaders/SDK files are preserved, with
manual LAN fallback. Character selection during client travel remains a live
test requirement. No character/save is rewritten by the companion.

SM64CoopDX uses native `--server` / `--client` arguments and the selected host
save slot (1–4). Clients wait for the host port to open. L4D2 uses native Source
LAN settings and either the host's menu-selected campaign or the profile's
selected starting map in Co-op, Realism or Versus mode. L4D2 clients open
immediately and join when the host provides a valid AppID 550 A2S response.
They remain at the menu if the host is not ready within five minutes.
The pre-launch wait in SM64CoopDX remains bounded at 120 seconds.

Known direct commands and referenced entry batches are supported. Unknown
complex/nested launchers remain manual; existing network arguments are not
silently replaced. Private batch edits are restored before reapplication and
when switching back to manual mode, unless a user changed the edited file.
Source games, archives, other tools and installed runners are not modified.

Anchor and Hollow Knight retain their existing automation. Most Wanted keeps
its existing network setup and controller-name shortcut; server/lobby menus
remain manual pending a reliable game-specific integration.
