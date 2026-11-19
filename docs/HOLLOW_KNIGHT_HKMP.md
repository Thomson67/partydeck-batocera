# Hollow Knight / HKMP dans Windows Party

Profil expérimental pour Hollow Knight Windows 1.5.78.11833, Modding API et
HKMP 2.4.3. Le jeu, l'API et les mods tiers sont fournis par l'utilisateur.

## Préparer le jeu

Valider en solo l'API, HKMP, le correctif Ultra-Wide 0.1.1 et BepInEx 5.
`winhttp.dll` et `doorstop_config.ini` sont à côté de `hollow_knight.exe`.
Le profil applique `winhttp=n,b` et `dll_search_path_override = BepInEx\core`
dans les vues privées. Installer `corefonts` dans le préfixe du jeu si les
textes du panneau F1 ne s'affichent pas.

Dans Configurer Windows Party, associer le jeu au profil **Hollow Knight / HKMP**,
vérifier les onglets Réseau et Coop, puis enregistrer. Les anciennes entrées
créées avec le profil Standard doivent sélectionner ce nouveau profil.

## Comportement

- La résolution du jeu et celle du rendu Gamescope suivent la zone de chaque
  joueur (par exemple 1920×540 pour deux vues horizontales en 1080p).
- Le plugin compagnon fourni avec Windows Party réapplique les dimensions
  lorsque le jeu restaure une ancienne résolution. Il ne remplace pas le
  correctif de ratio/caméra Ultra-Wide, qui reste nécessaire.
- Après le chargement complet des mods, J1 démarre un serveur HKMP local.
- Chaque joueur doit choisir/charger sa sauvegarde normalement. Dès que son
  personnage est en jeu, il rejoint automatiquement `127.0.0.1`, port 7777 par
  défaut, sous le nom J1–J4 ou le pseudo configuré.
- En cas d'ordre de lancement différent, une connexion est réessayée lorsqu'aucune
  tentative n'est déjà en cours, au plus 12 fois. Après une connexion réussie,
  la reconnexion automatique s'arrête pour respecter une déconnexion manuelle.
- Les clés HKMP sont différentes et persistantes par joueur. Les options
  non concernées, sauvegardes et caractéristiques des armes restent conservées.
- Dégâts entre joueurs et par contact désactivés, noms et positions sur la
  carte affichés, skins autorisés par défaut. Les réglages serveur sont ceux de J1.

La session utilise le réseau partagé de la machine (pas les espaces réseau
privés de Most Wanted). Ne pas lancer simultanément un autre serveur sur le
même port ; choisir un autre port dans le profil si nécessaire.

## Addons coop

Installer **ESoulLink**, **GhostHunter**, **HkmpPouch** et **Satchel** via Lumafly
dans le jeu source. Ils doivent être actifs dans Lumafly lors de la préparation.
Les fichiers attendus sont `Managed/Mods/<nom>/<nom>.dll`.

L'onglet Coop propose **Conserver / Activé / Désactivé** pour ESoulLink et
GhostHunter. Conserver garde l'état de la copie du joueur ; Activé/Désactivé
s'applique au prochain lancement, en renommant seulement la DLL correspondante
dans la vue privée. Ces choix n'installent pas les mods ni leurs dépendances.
Les dépendances et l'installation solo ne sont pas désactivées.

ESoulLink partage une réserve de PV entre les ennemis correspondants et ajoute
les contributions des joueurs à cette réserve. GhostHunter montre les ennemis
blessés des autres mondes sous forme de fantômes. Il ne s'agit pas d'une
synchronisation complète de l'IA, des déplacements ou de la progression.
Ces versions ne proposent pas de réglages de difficulté/opacité supplémentaires ;
Windows Party n'invente pas de paramètres qu'elles ne savent pas lire.

Sources :
- https://github.com/Extremelyd1/HKMP/tree/v2.4.3
- https://github.com/PrashantMohta/ESoulLink
- https://github.com/PrashantMohta/GhostHunter
- https://github.com/p1xel8ted/UltrawideFixes/releases/tag/HollowKnight

## Validation et limites

Le compagnon est compilé en .NET Standard 2.0 contre BepInEx 5.4.21. Il n'inclut
aucune DLL de jeu ou de HKMP et retrouve les objets HKMP 2.4.3 par réflexion,
sans patch Harmony supplémentaire ni saisie clavier simulée.
Les contrats utilisés ont été vérifiés sur la DLL officielle HKMP 2.4.3.

Les tests locaux vérifient les identités, les dimensions, la préservation des
autoruns/batchs, des options tierces et des sauvegardes, les addons, les chemins
privés, les erreurs de lancement et les libellés FR/EN. Le lancement réel du
compagnon dans Unity/HKMP doit être validé sur Batocera.

Diagnostic : `BepInEx/LogOutput.log`, lignes `Windows Party HKMP`. Les erreurs
d'API arrêtent l'automatisation réseau et laissent le panneau HKMP disponible.
Le plugin est injecté uniquement dans la vue privée Windows Party ; le lancement
solo ne reçoit pas de configuration d'automatisation.

Reconstruction :
```
dotnet build plugins/HKMP/WindowsParty.HKMP.csproj -c Release
cp plugins/HKMP/bin/Release/netstandard2.0/WindowsParty.HKMP.dll plugins/WindowsParty.HKMP.dll
```

# English

Experimental Windows Party profile for Hollow Knight Windows 1.5.78.11833,
HKMP 2.4.3 and the user's working BepInEx 5/Ultra-Wide 0.1.1 installation.
Select **Hollow Knight / HKMP** in the configurator and save the profile.

Each viewport controls Gamescope's rendering size and the game's window size.
After all mods finish loading, P1 starts the local HKMP server. Players still
select/load their own saves; the companion joins automatically once their
character is in gameplay. Defaults: localhost:7777, names J1–J4, PvP/contact
damage off, map locations/names/skins on. Network automation can be disabled.
Authentication keys remain distinct and persistent per player.

Install ESoulLink, GhostHunter, HkmpPouch and Satchel through Lumafly first.
**Keep current / Enabled / Disabled** applies next session only to the private
player copies. Dependencies are preserved. ESoulLink shares enemy health;
GhostHunter displays other players' damaged enemies as ghosts. These are partial
co-op features, not full shared AI, movement or progression synchronization.

Local tests and compilation pass; live Unity/HKMP testing is still required.
Read `BepInEx/LogOutput.log` (`Windows Party HKMP`) for startup/connect errors.
