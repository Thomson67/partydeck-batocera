# Windows Party Native Wide 0.1.1-test

## Français

Correction 0.1.1 : la version 0.1.0 se désactivait au premier hook sous Mono avec
« Target method is static, but a target object was provided ». Les méthodes
compilées par Expression.Compile peuvent être statiques avec une fermeture
liée. La liaison passe désormais par la méthode d'instance Invoke du délégué.
Chaque hook installé est journalisé, suivi de « Native camera hooks active ».
Si cette ligne n'apparaît pas, fournir le nouveau ModLog.txt.


Version expérimentale pour Hollow Knight Windows 1.5.12620 / Unity 6 et l'API
fournie avec HKMultiplayerMOD 0.36.2. Elle utilise les dépendances de cette API.
Ce n'est pas une mise à jour officielle du mod ultrawide de p1xel8ted.

Le journal fourni montre le chargement de Hollow Knight Ultra-Wide 0.1.2,
puis une TypeLoadException sur Modding.ReflectionHelper / FastInvoker.
Le conflit probable est le chargement des dépendances MonoMod de BepInEx
avant celles de l'API. Ce correctif évite de charger BepInEx.

Installation (premier test dans le préfixe solo) :

1. Fermer le jeu.
2. Dans cette copie du jeu, renommer le fichier winhttp.dll installé par
   l'ultrawide en winhttp.dll.disabled pour désactiver BepInEx.
   L'override Wine winhttp=n,b peut rester : Wine retombera sur sa DLL intégrée.
3. Extraire le dossier hollow_knight_Data de l'archive à côté de
   hollow_knight.exe. Le fichier ajouté est uniquement :
   hollow_knight_Data/Managed/Mods/WindowsPartyNativeWide/WindowsParty.NativeWide.dll
4. Garder l'API et les dépendances installées par HKMultiplayerMOD.
5. Lancer le jeu directement en solo. La liste des mods doit afficher
   Windows Party Native Wide 0.1.1-test. Aucun menu F1 n'est nécessaire.
6. Choisir une résolution adaptée et charger une partie pour vérifier
   l'occupation de la fenêtre, puis tester une connexion coopérative.

Le mod utilise Screen.width et Screen.height : il ajuste le viewport de la
caméra du jeu et du HUD à la fenêtre actuelle et neutralise l'overscan.
Il ne force ni résolution fixe ni plein écran. Il conserve la logique de
champ de vision du jeu. Il ne comprend pas les options FOV, les ajustements
spéciaux des inventaires et cinématiques, ou le repositionnement du HUD
proposés par le mod BepInEx complet.

Le profil Partydeck HKMP existant utilise encore un compagnon BepInEx dédié à
HKMP ; il faut l'adapter séparément à HKMultiplayerMOD avant ce nouveau test
en écran partagé. Ne pas mélanger ce test avec le dossier du jeu HKMP 1.5.78.

Validation effectuée : compilation, vérification des signatures contre les
DLL de l'API publique HKMultiplayerMOD 0.36.2 et tests des délégués générés.
Le chargement Mono/Unity et le rendu réel restent à valider en jeu.
Les essais de detours natifs sur l'hôte .NET 8 ne sont pas exécutables avec
les DLL MonoMod fournies pour Unity ; aucun test de lancement du jeu n'est
revendiqué. Les erreurs du correctif sont consignées dans les logs de l'API
avec le nom Windows Party Native Wide.

Si le jeu bloque encore, fournir le nouveau output_log.txt et le journal de
l'API s'il est créé. Pour désinstaller, retirer le dossier WindowsPartyNativeWide.
Pour rétablir BepInEx, renommer winhttp.dll.disabled en winhttp.dll ; cela
rétablira aussi le conflit initial si ses dépendances sont inchangées.

Compilation : SDK .NET 8, puis
`dotnet build -c Release -p:GameManagedDir=/chemin/vers/hollow_knight_Data/Managed`.
Distribuer uniquement WindowsParty.NativeWide.dll, jamais les DLL du jeu/API.

## English

0.1.1 fixes the initial hook failure on Mono: “Target method is static, but a
 target object was provided”. Hook targets now use the generated delegate's
instance Invoke method instead of its closed static implementation. Each
installed hook is logged, followed by “Native camera hooks active”. A new
regression check exercises the instance Invoke binding. Real rendering still
requires in-game validation.


Experimental build for Hollow Knight Windows 1.5.12620 / Unity 6 and the API
bundled with HKMultiplayerMOD 0.36.2. This is an independent camera mod, not an
official update to p1xel8ted's ultrawide mod.

Close the game. Rename the ultrawide loader's winhttp.dll to winhttp.dll.disabled
in this game copy to disable BepInEx. Keep the API and dependencies installed by
HKMultiplayerMOD. Extract the archive's hollow_knight_Data directory beside
hollow_knight.exe. This adds only the DLL under Managed/Mods/WindowsPartyNativeWide.
Launch directly in the solo prefix first, select the desired resolution and
load a save. The mod list should show Windows Party Native Wide 0.1.1-test.

The mod uses the current window dimensions for the game/HUD camera viewport
and disables overscan. It preserves the game's field-of-view logic, has no F1
menu and does not include special inventory, cinematic or HUD positioning fixes.
It does not force a resolution. The existing Partydeck HKMP companion depends
on BepInEx and needs a separate HKMultiplayerMOD integration before split-screen
testing. Keep this separate from the working HKMP 1.5.78 game copy.

Compilation, API camera signature checks and generated delegate tests passed.
Unity/Mono loading and actual rendering remain untested. Native detour tests on
the .NET 8 host cannot run with these Unity-targeted MonoMod DLLs; no successful
game launch is claimed. Errors are logged under Windows Party Native Wide.
If startup still fails, provide the new output_log.txt and API log if generated.
Remove WindowsPartyNativeWide to uninstall; rename the loader back to restore
BepInEx (and the original dependency conflict if unchanged).

Build using .NET SDK 8:
`dotnet build -c Release -p:GameManagedDir=/path/to/hollow_knight_Data/Managed`.
Distribute only this mod's DLL, never the game/API reference assemblies.
