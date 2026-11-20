# Hollow Knight / HKMultiplayerMOD — Windows Party

## Français

Profil de test pour **Hollow Knight Windows 1.5.12620**, l'API incluse avec
**HKMultiplayerMOD 0.36.2**, et deux à quatre joueurs locaux. Le mod doit déjà
fonctionner en solo. Ce profil est distinct de l'ancien HKMP 2.4.3.

Choisir **Hollow Knight / HKMultiplayer** dans l'onglet Session, puis enregistrer.
Les noms contenant Multiplayer ou 1.5.12620 sont détectés automatiquement.

- J1 ouvre le monde coop ; J2–J4 rejoignent J1 par IP locale.
- Le coordinateur transmet un code aléatoire commun : aucune saisie du code.
- Chaque joueur conserve une identité distincte pour retrouver son personnage.
- Les fenêtres et les caméras s'adaptent à leurs zones d'écran.
- Native Wide 0.1.1 est installé dans les vues privées si activé.
- L'entrée native du jeu est désactivée si l'option est activée.
- **HIDRAW est conservé pour la manette attribuée à chaque joueur.**
- Les options coop sont appliquées, sauvegardées et diffusées par l'API du host.

Le mécanisme chiffré du mod reste actif ; aucun salon Steam n'est ouvert pour
cette session locale. Le handler utilise les mondes coop propres au mod.
Par défaut, J1 reprend son dernier monde disponible ou crée Windows Party s'il
n'en existe aucun. Le choix Monde portant ce nom permet de reprendre/créer un
monde nommé. Si les quatre emplacements sont occupés, aucun monde n'est supprimé.

Les sauvegardes utilisent `/userdata/saves/windows-party/<jeu>/j1/`, puis j2–j4.
Le host conserve le monde et les personnages des invités sous HKMultiplayer/Mundos
 dans ses données LocalLow. Un monde du préfixe solo n'est pas importé
 automatiquement ; les sauvegardes vanilla ne sont pas converties. Garder les
préfixes persistants des joueurs pour conserver leurs identités. Changer un
pseudo ne change pas l'identité du personnage. La première introduction du jeu
reste gérée normalement par le mod.

L'option manettes applique PlayerPrefs NativeInput=0, met à jour GameSettings et
InControl, et recharge InControl si nécessaire. Elle conserve les affectations,
l'accès HIDRAW de la manette PS et les autres paramètres. Aucune variable
Proton/HIDRAW n'est forcée. BepInEx est désactivé via Doorstop dans la vue privée
pour éviter son conflit MonoMod ; Native Wide utilise l'API native. Les fichiers
solo ne sont pas remplacés.

Compilation du compagnon et signatures vérifiées contre les DLL publiques de
la version 0.36.2. Les **30 scripts de vérification Python passent**, dont les
profils existants, FR/EN, identités et écritures privées. Le lancement simultané
sur Batocera reste à tester. En cas d'échec, fournir le journal Windows Party et
les ModLog.txt de J1/J2 ; le compagnon apparaît sous PartyMultiplayer. Il attend
le menu principal, réessaie la connexion initiale et conserve les menus normaux.
Il ne rejoint pas automatiquement après une sortie volontaire. Le mod conserve
sa propre reconnexion après une coupure réseau.

## English

Test profile for Hollow Knight Windows **1.5.12620** and the API supplied with
**HKMultiplayerMOD 0.36.2**, for two to four local players. The mod must already
work in solo. Select **Hollow Knight / HKMultiplayer** in Session and save.
This is separate from the old HKMP adapter.

P1 opens the selected co-op world; P2–P4 join over loopback using the common
random code supplied by the coordinator. No manual code entry is required.
Player identities persist independently of names. The latest world is resumed,
or Windows Party is created if none exists. Named-world selection is available.
Full slots never cause deletion. Solo worlds are not imported automatically;
vanilla saves are not converted. Saves stay under
/userdata/saves/windows-party/<game>/j1/ etc.; the host owns the shared world and
guest characters. Preserve persistent prefixes. Opening cutscenes remain normal.

The private viewports and optional Native Wide 0.1.1 adapt the display. BepInEx
is disabled in the private view. The controller fix disables native input and
reloads InControl if necessary while **retaining bindings and assigned HIDRAW**.
It does not force Proton variables or remap buttons. Solo files remain intact.
Co-op options include revive timing/soul cost, shared map, stag travel, names,
partner health and boss/enemy health multipliers. The host API saves and
broadcasts them. Steam lobbies are disabled for the local session; encryption
remains active.

The bridge builds, published DLL contracts match, and all 30 Python checks pass.
Simultaneous Batocera runtime testing is still required. Provide the Windows
Party log and both ModLog.txt files if needed. Normal menus remain available.
