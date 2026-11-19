"""French for a French Batocera configuration, English for every other locale."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

_language = None


def locale_language(value):
    return 'fr' if re.match(r'^fr(?:[_\-.@]|$)', value.strip().strip('"\'').casefold()) else 'en'


def detect_language(environ=None, config=Path('/userdata/system/batocera.conf'),
                    es_settings=Path('/userdata/system/configs/emulationstation/es_settings.cfg')):
    env = os.environ if environ is None else environ
    forced = env.get('PARTYDECK_LANGUAGE','').lower()
    if forced in ('fr','en'):
        return forced
    binary = shutil.which('batocera-settings-get')
    if binary:
        try:
            result = subprocess.run([binary,'system.language'],capture_output=True,text=True,timeout=2)
            if result.returncode == 0 and result.stdout.strip():
                return locale_language(result.stdout)
        except (OSError,subprocess.TimeoutExpired):
            pass
    try:
        selected = None
        for line in config.read_text().splitlines():
            match = re.match(r'^\s*system\.language\s*=\s*(.*?)\s*$',line)
            if match and match[1]:
                selected = match[1]
        if selected is not None:
            return locale_language(selected)
    except OSError:
        pass
    try:
        for node in ET.parse(es_settings).iter('string'):
            if node.get('name') == 'Language' and node.get('value'):
                return locale_language(node.get('value'))
    except (OSError,ET.ParseError):
        pass
    for key in ('LC_ALL','LC_MESSAGES','LANGUAGE','LANG'):
        if env.get(key):
            return locale_language(env[key].split(':',1)[0])
    return 'en'


def set_language(language):
    global _language
    _language = locale_language(language)


def get_language():
    global _language
    if _language is None:
        _language = detect_language()
    return _language


EN = {
    'Réglages écran/GPU invalides.':'Invalid display/GPU settings.',
    'Aucun écran actif détecté.':'No active display detected.',
    'Automatique · écran actif':'Automatic · active display',
    '{p0} · indisponible (repli automatique)':'{p0} · unavailable (automatic fallback)',
    'Écran demandé : {p0} · zone active : {p1}':'Requested display: {p0} · active area: {p1}',
    'Écran reconnecté : fenêtres replacées sur {p0}.':'Display reconnected: windows repositioned to {p0}.',
    'PARAMÈTRES WINDOWS PARTY':'WINDOWS PARTY SETTINGS',
    'Réglages globaux · enregistrés automatiquement':'Global settings · saved automatically',
    'Écran des jeux':'Game display',
    'GPU par défaut':'Default GPU',
    'ACTUALISER LES ÉCRANS':'REFRESH DISPLAYS',
    'Écran indisponible : repli sur un écran actif, choix conservé.':'Unavailable display: use an active display and retain your choice.',
    'Reconnexion : placement des jeux réajusté automatiquement.':'Reconnection: game window placement adjusts automatically.',
    'GPU appliqué au prochain lancement. Le GPU du jeu peut remplacer ce choix.':'GPU applies on next launch. A per-game GPU choice can override it.',
    'GPU du jeu sur Automatique : utiliser ce réglage global.':'Per-game GPU set to Automatic: use this global setting.',
    'PARAMÈTRES':'SETTINGS',
    'Gauche / droite : choisir · réglages enregistrés automatiquement':'Left / right: choose · settings saved automatically',
    'Fermez Windows Party avant la migration.':'Close Windows Party before migration.',
    'Migration refusée : destination inattendue ({p0}).':'Migration refused: unexpected destination ({p0}).',
    'Migration refusée : deux installations existent.':'Migration refused: two installations exist.',
    'Migration Windows Party terminée ; anciennes données conservées dans archive.':'Windows Party migration complete; previous data retained in archive.',
    'Contexte privé UMU absent.':'Missing private UMU context.',
    'Chemin incompatible avec la vue privée UMU.':'Path incompatible with the private UMU view.',
    'UMU : vues privées temporaires des runners préparées ({p0}).':'UMU: temporary private runner views prepared ({p0}).',
    'UMU : nettoyage différé de {p0}.':'UMU: deferred cleanup of {p0}.',
    'LAN privé : erreur réseau {p0}, ENETUNREACH attendu pour UMU.':'Private LAN: network error {p0}, expected ENETUNREACH for UMU.',
    'LAN privé : une route Internet est disponible de façon inattendue.':'Private LAN: an Internet route is unexpectedly available.',
    'LAN privé local (sans Internet)':'Local private LAN (no Internet)',
    'LAN privé : J1 crée le serveur et le salon, J2 le rejoint · sans Internet':'Private LAN: P1 creates the server and lobby, P2 joins · no Internet',
    'Réseau partagé : connexion au LAN du PC':'Shared network: connects to the PC LAN',
    'Le LAN privé exige un profil compatible.':'Private LAN requires a compatible game profile.',
    'LAN privé : commande cible absente.':'Private LAN: target command missing.',
    'LAN privé : choisissez de 2 à 4 joueurs.':'Private LAN: select 2 to 4 players.',
    'LAN privé : espace réseau hôte refusé.':'Private LAN: host network namespace refused.',
    'LAN privé : espace réseau terminé.':'Private LAN: network namespace exited.',
    'LAN privé : commande absente ({p0}).':'Private LAN: command missing ({p0}).',
    'LAN privé : création de l’espace réseau trop longue.':'Private LAN: network namespace startup timed out.',
    'LAN privé indisponible : {p0}':'Private LAN unavailable: {p0}',
    'LAN privé J{p0} : {p1} ; Internet désactivé pour cette instance.':'Private LAN P{p0}: {p1}; Internet disabled for this instance.',
    'LAN privé : serveur de test UDP indisponible.':'Private LAN: UDP test server unavailable.',
    'LAN privé : échec du test UDP.':'Private LAN: UDP test failed.',
    'LAN privé OK : port UDP 3658 distinct et échanges entre joueurs vérifiés.':'Private LAN OK: separate UDP 3658 sockets and player communication verified.',
    'LAN privé : {p0}':'Private LAN: {p0}',
    'Le LAN privé expérimental exige le profil Most Wanted 2005.':'Experimental private LAN requires the Most Wanted 2005 profile.',
    'Contrôles virtuels toolbox : un autre service est actif ; session conservée.':'Toolbox virtual controls: another watcher is active; existing session preserved.',
    'Contrôles virtuels toolbox indisponibles ; consulter le diagnostic toolbox.':'Toolbox virtual controls unavailable; check the toolbox diagnostic.',
    'Contrôles virtuels toolbox : service démarré ; journal {p0}.':'Toolbox virtual controls: watcher started; log {p0}.',
    'Contrôles virtuels toolbox : {p0}':'Toolbox virtual controls: {p0}',
    'GPU de rendu':'Rendering GPU',
    'Configuration système':'System configuration',
    'Choix du GPU invalide.':'Invalid GPU selection.',
    'Most Wanted 2005 · LAN expérimental':'Most Wanted 2005 · experimental LAN',
    'GPU hybride : rendu NVIDIA demandé pour Gamescope et Wine.':'Hybrid GPU: NVIDIA rendering requested for Gamescope and Wine.',
    'IP LAN du PC (auto : détection)':'PC LAN IP (auto: detect)',
    'Fréquence du serveur LAN':'LAN server throttle',
    'Délai entre joueurs (secondes)':'Delay between players (seconds)',
    'Expérimental · ports 9900–9903 · créer le salon J1 avant de rejoindre avec J2':'Experimental · ports 9900–9903 · create the P1 room before joining with P2',
    'Réglages Most Wanted LAN invalides.':'Invalid Most Wanted LAN settings.',
    'Adresse LAN Most Wanted invalide.':'Invalid Most Wanted LAN address.',
    'IP LAN introuvable ; renseignez l’adresse du PC dans Réseau Most Wanted.':'LAN IP not found; enter the PC address in Most Wanted Network settings.',
    'Most Wanted 2005 non confirmé : NFSMW_icon.ico absent.':'Most Wanted 2005 not confirmed: NFSMW_icon.ico is missing.',
    'Most Wanted : server.cfg ou server.dll absent.':'Most Wanted: server.cfg or server.dll is missing.',
    'Numéro de joueur Most Wanted invalide.':'Invalid Most Wanted player number.',
    'Dimensions Most Wanted invalides.':'Invalid Most Wanted dimensions.',
    'Most Wanted : mod absent ({p0}) ; adaptation réseau seule, compatibilité non garantie.':'Most Wanted: missing mod ({p0}); network configuration only, compatibility is not guaranteed.',
    'Most Wanted J{p0} : {p1}:{p2}, TRUST_MATCH sans port, LAN_THROTTLE={p3}.':'Most Wanted P{p0}: {p1}:{p2}, TRUST_MATCH without port, LAN_THROTTLE={p3}.',
    'Most Wanted J{p0} : attente de {p1} s pour préparer le salon J1.':'Most Wanted P{p0}: waiting {p1} s to prepare the P1 room.',
    'Contexte privé Most Wanted invalide.':'Invalid private Most Wanted context.',

    'RUNNER WINE':'WINE RUNNER',
    'ACTIVER HIDRAW':'ENABLE HIDRAW',
    'Accès HID brut de la manette attribuée au joueur. Auto : reprendre le réglage du jeu Windows d’origine.':'Raw HID access for the controller assigned to each player. Auto: inherit the original Windows game setting.',
    'Réglage HIDRAW Windows Party invalide.':'Invalid Windows Party HIDRAW setting.',
    'Windows Party : HIDRAW={p0}.':'Windows Party: HIDRAW={p0}.',
    'Runner propre à Windows Party. Auto : utiliser le runner du jeu Windows d’origine.':'Windows Party runner. Auto: use the original Windows game’s runner.',
    'Configuration ES Windows Party personnalisée ; fichier conservé : {p0}':'Custom Windows Party ES configuration; file retained: {p0}',
    'Runner Windows Party invalide.':'Invalid Windows Party runner.',
    'Lanceur Wine non reconnu ; sélection du runner Windows Party refusée.':'Unrecognized Wine launcher; Windows Party runner selection refused.',
    'Windows Party : runner dédié {p0}.':'Windows Party: dedicated runner {p0}.',

    'Scraps Windows repris pour {p0} jeu(x), sans copier les médias.':'Windows scraped metadata reused for {p0} game(s), without copying media.',
    'Reprise des scraps différée : {p0}':'Scraped metadata synchronization deferred: {p0}',

    'Lanceur batocera-wine non reconnu ({p0}) : langue Wine non appliquée.':'Unrecognized batocera-wine launcher ({p0}): Wine language was not applied.',
    'Left 4 Dead 2 : langue Wine native {p0}.':'Left 4 Dead 2: native Wine language {p0}.',

    'Left 4 Dead 2 : start.bat absent ; forçage de langue Windows/Steam ignoré, lancement poursuivi.':'Left 4 Dead 2: start.bat is missing; Windows/Steam language override skipped, startup continuing.',

    'Left 4 Dead 2 : format vidéo non reconnu : {p0} ; fichier conservé, lancement poursuivi. Sans bordure non réappliqué ; résolution demandée : {p1}×{p2}.':'Left 4 Dead 2: unrecognized video format: {p0}; file retained, startup continuing. Borderless mode was not reapplied; requested resolution: {p1}×{p2}.',

    'Bloc de langue Left 4 Dead 2 incomplet ; fichier conservé.':'Incomplete Left 4 Dead 2 language block; file retained.',
    'start.bat Left 4 Dead 2 introuvable ; langue Windows/Steam non appliquée.':'Left 4 Dead 2 start.bat was not found; Windows/Steam language was not applied.',
    'Left 4 Dead 2 : langue Windows/Steam {p0} appliquée au démarrage privé.':'Left 4 Dead 2: Windows/Steam language {p0} applied at private startup.',
    'Activer la manette en jeu':'Enable gamepad in game',
    'Sans bordure et résolution automatiques · langue : fichiers du jeu requis':'Automatic borderless and resolution · language files must be installed',
    'Réglages Left 4 Dead 2 invalides.':'Invalid Left 4 Dead 2 settings.',
    'Dimensions de la fenêtre Left 4 Dead 2 indisponibles ou invalides.':'Left 4 Dead 2 window dimensions are missing or invalid.',
    'Fichier video.txt Left 4 Dead 2 invalide ; fichier conservé.':'Invalid Left 4 Dead 2 video.txt; file retained.',
    'Bloc Windows Party Left 4 Dead 2 incomplet ; fichier conservé.':'Incomplete Left 4 Dead 2 Windows Party block; file retained.',
    'Dossier left4dead2 introuvable dans la vue privée du jeu.':'The left4dead2 folder was not found in the private game view.',
    'AppID Goldberg {p0} incompatible avec Left 4 Dead 2 : {p1}':'Goldberg AppID {p0} is incompatible with Left 4 Dead 2: {p1}',
    'Goldberg : AppID 550 confirmé dans {p0}.':'Goldberg: AppID 550 confirmed in {p0}.',
    'État Goldberg hors du dossier privé du joueur.':'Goldberg state is outside the player’s private directory.',
    'Résultat du profil Goldberg absent ou invalide : {p0}':'Goldberg profile result is missing or invalid: {p0}',
    'Profil Goldberg non appliqué ; échec conservé malgré le code natif {p0}.':'Goldberg profile was not applied; preserving the failure despite native exit code {p0}.',
    'Left 4 Dead 2 · profil commun':'Left 4 Dead 2 · shared profile',
    'Left 4 Dead 2 · Steam ID distincts et persistants · noms personnalisables':'Left 4 Dead 2 · distinct persistent Steam IDs · customizable names',
    'Left 4 Dead 2 : quatre noms différents, non vides, de 63 octets UTF-8 maximum, sans caractères de contrôle ni ; #.':'Left 4 Dead 2: four different, non-empty names, up to 63 UTF-8 bytes, without control characters or ; #.',
    'Identifiant ou numéro de joueur Goldberg invalide pour Left 4 Dead 2.':'Invalid Goldberg identity or player number for Left 4 Dead 2.',
    'Configuration Goldberg hors de la vue privée : {p0}':'Goldberg configuration is outside the private view: {p0}',
    'Configuration Goldberg destinée à un autre jeu : {p0}':'Goldberg configuration is for a different game: {p0}',
    'Left 4 Dead 2 : steam_settings/configs.user.ini Goldberg introuvable dans la vue privée du jeu.':'Left 4 Dead 2: Goldberg steam_settings/configs.user.ini was not found in the private game view.',
    'Steam ID Goldberg absent ou invalide : {p0}':'Missing or invalid Goldberg Steam ID: {p0}',
    'Identité Goldberg privée invalide ; fichier conservé : {p0}':'Invalid private Goldberg identity; file retained: {p0}',
    'Plusieurs Steam ID Goldberg différents sont présents dans le jeu ; initialisation refusée.':'Multiple different Goldberg Steam IDs were found in the game; initialization refused.',
    'Left 4 Dead 2 J{p0} : identité Goldberg privée {p1} · {p2} configuration(s).':'Left 4 Dead 2 player {p0}: private Goldberg identity {p1} · {p2} configuration(s).',
    'Le profil Left 4 Dead 2 doit être appliqué dans la session Wine privée du joueur.':'The Left 4 Dead 2 profile must be applied in the player’s private Wine session.',
    'Pages · maintenir':'Pages · hold',
    'État de fin Wine hors du dossier privé du joueur.':'Wine exit state is outside the player’s private directory.',
    'J{p0} : fin Wine={p1}, Gamescope={p2}.':'Player {p0}: Wine exit={p1}, Gamescope={p2}.',
    'Wine a terminé normalement ; incident Gamescope à la fermeture ({p0}), non transmis à EmulationStation.':'Wine exited normally; Gamescope shutdown failure ({p0}) was not forwarded to EmulationStation.',
    'Fermeture de la session demandée (signal {p0}).':'Session shutdown requested (signal {p0}).',
    'Graphismes':'Graphics','Gameplay':'Gameplay','Options':'Options','Son':'Audio',
    'SM64CoopDX · profil commun':'SM64CoopDX · shared profile',
    'Distance d’affichage':'Draw distance','Caméra libre':'Free camera',
    'Sensibilité caméra · axe X':'Camera sensitivity · X axis','Sensibilité caméra · axe Y':'Camera sensitivity · Y axis',
    'Inverser la caméra · axe X':'Invert camera · X axis','Inverser la caméra · axe Y':'Invert camera · Y axis',
    'Langue du jeu':'Game language', 'Français':'French','Anglais':'English','Allemand':'German','Italien':'Italian',
    'Espagnol':'Spanish','Portugais':'Portuguese','Néerlandais':'Dutch','Polonais':'Polish',
    'Tchèque':'Czech','Russe':'Russian','Japonais':'Japanese',
    'Musique':'Music','Bruitages':'Sound effects','Ambiance':'Environment',
    'Au plus proche':'Nearest','Infinie':'Infinite','0,5×':'0.5×','1,5×':'1.5×',
    'SM64CoopDX · configuration commune · réglages privés pour chaque joueur':'SM64CoopDX · shared configuration · private settings for each player',
    'Volume repris depuis la configuration commune':'Volume inherited from the shared configuration',
    ' : valeur de la configuration commune':': shared configuration value',
    'Réglages SM64CoopDX invalides.':'Invalid SM64CoopDX settings.',
    'Langue SM64CoopDX invalide.':'Invalid SM64CoopDX language.',
    'SM64CoopDX : quatre noms différents, non vides, de 63 octets UTF-8 maximum, sans espaces (utilisez _).':'SM64CoopDX: four different, non-empty names, up to 63 UTF-8 bytes, without spaces (use _).',
    'Les volumes SM64CoopDX doivent être des entiers de 0 à 100 %.':'SM64CoopDX volumes must be integers from 0 to 100%.',
    'Numéro de joueur SM64CoopDX invalide.':'Invalid SM64CoopDX player number.',
    'Dimensions de la fenêtre SM64CoopDX indisponibles.':'SM64CoopDX window dimensions are unavailable.',
    'Configuration commune SM64CoopDX invalide.':'Invalid SM64CoopDX shared configuration.',
    'Préfixe SM64CoopDX sans utilisateur Wine. Lancez d’abord le jeu une fois en solo.':'SM64CoopDX prefix has no Wine user. Launch the game once in solo mode first.',
    'Configuration SM64CoopDX hors de la vue privée : {p0}':'SM64CoopDX configuration is outside the private view: {p0}',
    'SM64CoopDX J{p0} : configuration appliquée · {p1}':'SM64CoopDX player {p0}: configuration applied · {p1}',
    'Configuration commune SM64CoopDX absente : réinstallez Windows Party.':'SM64CoopDX shared configuration is missing: reinstall Windows Party.',
    'Le profil SM64CoopDX doit être appliqué dans la session Wine privée du joueur.':'The SM64CoopDX profile must be applied in the player’s private Wine session.',
    'Borderlands 2 · nom privé par joueur · vide : conserver le nom actuel':'Borderlands 2 · private name per player · empty: keep current name',
    'Noms Borderlands 2 : quatre noms de 64 caractères maximum, ou vides pour conserver ; sans caractères de contrôle ni ; # = [ ].':'Borderlands 2 names: four names of up to 64 characters, or empty to keep current; no control characters or ; # = [ ].',
    'Configuration Borderlands 2 liée à un autre emplacement : {p0}':'Borderlands 2 configuration links to another location: {p0}',
    'Nom Borderlands 2 : steam_emu.ini introuvable dans la vue privée du jeu. Laissez les noms vides pour utiliser cette installation.':'Borderlands 2 name: steam_emu.ini was not found in the private game view. Leave player names empty to use this installation.',
    'Configuration steam_emu.ini non reconnue pour Borderlands 2 : {p0}':'Unrecognized steam_emu.ini configuration for Borderlands 2: {p0}',
    'Numéro de joueur Borderlands 2 invalide.':'Invalid Borderlands 2 player number.',
    'Jeu':'Game', 'Configurer':'Configure',
    'Résolution interne (0,5 à 2)':'Internal resolution (0.5 to 2)',
    'Session':'Session', 'Réseau':'Network', 'Joueurs':'Players', 'Image & son':'Graphics & audio', 'Image':'Graphics',
    'Entrée':'Enter', 'Échap':'Esc', 'Inser':'Ins', 'Croix':'Cross', 'Cercle':'Circle', 'Carré':'Square', 'Triangle':'Triangle',
    'Confirmer':'Confirm', 'Annuler':'Cancel', 'Fermer':'Close', 'Choisir':'Select', 'Retour':'Back',
    'Jeux par taille':'Games by size', 'Enregistrer':'Save', 'Abandonner':'Discard', 'Choisir le jeu':'Choose game',
    'Valider':'Done', 'Saisir':'Type', 'Parcourir':'Browse', 'Rechercher':'Search', 'Onglets':'Tabs', 'Ajouter':'Add',
    'Maj':'Shift', 'Espace':'Space', 'Effacer':'Backspace', 'Vider':'Clear',
    'Partage de l’écran':'Split-screen layout', 'Attribution des contrôles':'Input assignment',
    'Clavier/souris utilisable comme joueur':'Allow keyboard/mouse as a player',
    'Configurer avant chaque lancement':'Configure before each launch', 'Profil du jeu':'Game profile',
    'Forcer le plein écran fenêtré':'Force borderless fullscreen', 'Résolution adaptée au partage':'Fit resolution to player window',
    'Préréglage graphique':'Graphics preset', 'Qualité PhysX':'PhysX quality',
    'Fichier INI (auto ou relatif au préfixe)':'INI file (auto or relative to prefix)',
    'Connexion automatique Anchor':'Connect to Anchor automatically', 'Room ID commun':'Shared Room ID',
    'Serveur':'Server', 'Port':'Port', 'Chemin du JSON SoH':'SoH JSON path', 'PvP':'PvP',
    'Positions visibles':'Show player locations', 'Téléportation':'Teleportation',
    'Objets et progression partagés':'Sync items and progress', 'Nom':'Name', 'Équipe':'Team',
    'J{p0} · {p1}':'Player {p0} · {p1}', 'Joueur{p0}':'Player{p0}',
    'Résolution interne':'Internal resolution', 'Anti-aliasing MSAA':'MSAA anti-aliasing',
    'VSync':'VSync', 'Filtre des textures':'Texture filtering', 'Musique uniquement pour J1':'Music on player 1 only',
    'Volume général':'Master volume', 'Musique principale':'Main music', 'Musique secondaire':'Secondary music',
    'Fanfares':'Fanfares', 'Bruitages et voix':'Sound effects and voices',
    'Activé':'Enabled', 'Désactivé':'Disabled', 'Conserver':'Keep current', 'Bas':'Low', 'Moyen':'Medium', 'Élevé':'High', 'Max':'Max',
    'Personne':'Nobody', 'Même équipe':'Team only', 'Tous':'Everyone', 'Avec tirs alliés':'Friendly fire',
    'Trois points N64':'N64 three-point', 'Trois points (N64)':'Three-point (N64)', 'Linéaire':'Linear', 'Aucun':'None',
    'JSON commun':'Shared JSON', 'Conserver les réglages':'Keep current settings',
    'Automatique':'Automatic', 'Horizontal':'Horizontal', 'Vertical':'Vertical',
    'Clavier/souris · J1':'Keyboard/mouse · P1', 'Clavier/souris · J2':'Keyboard/mouse · P2',
    'Manettes uniquement':'Gamepads only',
    'Windows Party · Configurateur':'Windows Party · Configurator', 'CONFIGURATEUR':'CONFIGURATOR',
    'Votre bibliothèque · vos règles · votre partie':'Your library · your rules · your game',
    'BIBLIOTHÈQUE':'LIBRARY', 'STOCKAGE':'STORAGE', '{p0} jeux · {p1} : ajouter':'{p0} games · {p1}: add',
    'MODIFIÉ · non enregistré':'MODIFIED · not saved', 'Profil prêt':'Profile ready',
    'Borderlands 2 · réglages communs · PhysX indépendant du préréglage':'Borderlands 2 · shared settings · separate PhysX quality',
    'Borderlands 2 · affichage automatique · VSync et PhysX indépendants':'Borderlands 2 · automatic display · separate VSync and PhysX',
    'SoH / Anchor · réglages communs aux joueurs de cette session':'SoH / Anchor · shared settings for this session',
    'SoH / Anchor · activer ce profil dans Session pour appliquer ces réglages':'SoH / Anchor · enable this profile in Session to apply these settings',
    'DISSOCIER LE JEU':'UNLINK GAME', 'RETIRER LE JEU':'REMOVE GAME', 'LANCER LA PARTIE':'LAUNCH GAME', 'ENREGISTRER':'SAVE',
    'Profil prêt · le jeu doit être présent sur votre Batocera.':'Profile ready · you must have the game on your Batocera.',
    'Choisissez le jeu pour préparer votre session.':'Choose the game to prepare your session.',
    'Préparez votre première partie':'Prepare your first session', ' : choisir un jeu .wine, .pc ou .wsquashfs':': choose a .wine, .pc or .wsquashfs game',
    'Flèches : naviguer':'Arrow keys: navigate', 'Croix directionnelle / stick : naviguer':'D-pad / stick: navigate',
    'Échap : retour / quitter':'Esc: back / quit', ' : quitter':': quit', ' : annuler':': cancel',
    'Gauche / droite : volume par pas de 5 % · ':'Left / right: volume in 5% steps · ',
    ' : valeur JSON commun':': shared JSON value', 'Gauche / droite : ajuster · ':'Left / right: adjust · ',
    ' : saisir / exécuter · réglages enregistrés automatiquement':': edit / run · settings saved automatically',
    'Saisie directe au clavier · Retour arrière : effacer':'Type directly · Backspace: delete',
    'Maj, espace, effacement et caractères spéciaux sur le clavier virtuel':'Shift, space, backspace and special characters on the virtual keyboard',
    'CHOISIR UN JEU':'CHOOSE GAME', '.. / retour au dossier parent':'.. / parent folder',
    'Plusieurs versions détectées':'Multiple versions found', 'Choisir le fichier du jeu':'Choose the game file',
    'Jeu non détecté dans Windows':'Game not found in Windows',
    'Vous devez disposer du jeu pour utiliser ce profil commun.':'You must have the game to use this shared profile.',
    'Vous devez disposer du jeu avant d’utiliser ce profil commun.':'You must have the game before using this shared profile.',
    'Ajout annulé : vous devez d’abord disposer du jeu.':'Add cancelled: you must have the game first.',
    'Choisissez un dossier .wine/.pc ou un fichier .wsquashfs existant.':'Choose an existing .wine/.pc folder or .wsquashfs file.',
    'Jeu introuvable : vous devez d’abord disposer du jeu. Start permet de choisir un autre jeu.':'Game not found: you must have the game first. Use Add to choose another game.',
    'DISSOCIER CE JEU ?':'UNLINK THIS GAME?', 'RETIRER CE JEU DE WINDOWS PARTY ?':'REMOVE THIS GAME FROM WINDOWS PARTY?',
    'Le profil commun et vos options resteront disponibles.':'The shared profile and your settings will remain available.',
    'Le lanceur et ses options Windows Party seront retirés.':'The Windows Party launcher entry and its settings will be removed.',
    'Le jeu d’origine et toutes ses sauvegardes seront conservés.':'The original game and all its saves will be kept.',
    'Jeu retiré / dissocié. ROM et sauvegardes conservées. Actualisez les listes EmulationStation.':'Game removed / unlinked. ROM and saves kept. Refresh the EmulationStation game lists.',
    'PRÉPARATION DE LA PARTIE':'PREPARING GAME', 'Vérification de l’espace libre et entretien du stockage…':'Checking free disk space and maintaining storage…',
    'LANCEMENT INTERROMPU':'LAUNCH STOPPED', 'Lancement annulé.':'Launch cancelled.',
    'Profil enregistré · prêt pour le prochain lancement':'Profile saved · ready for the next launch',
    'Modifications non enregistrées. Enregistrer avant de continuer ?':'Unsaved changes. Save before continuing?',
    'Enregistrement impossible : ':'Could not save: ', 'Dossier inaccessible : ':'Cannot open folder: ',
    'Clavier/souris réservé aux menus ; joueurs attribués aux manettes.':'Keyboard/mouse reserved for menus; players use gamepads.',
    'Joueurs sur manettes ; clavier/souris disponible dans la fenêtre active pour les menus.':'Players use gamepads; keyboard/mouse remains available for menus in the active window.',
    'Volume repris depuis le JSON commun':'Volume inherited from the shared JSON',
    'Volume : de 0 à 100 %, ou vide pour le JSON commun.':'Volume: 0 to 100%, or leave empty to use the shared JSON.',
    'Port : de 1025 à 65534.':'Port: 1025 to 65534.',
    'STOCKAGE WINDOWS PARTY':'WINDOWS PARTY STORAGE', 'Occupé : ':'Used: ', ' · hors jeux Windows d’origine':' · excluding original Windows games',
    ' libres sur ':' free on ', 'Persistant {p0} · Runtime {p1} · Installation {p2}':'Persistent {p0} · Runtime {p1} · Installation {p2}',
    'Caches {p0} · Journaux {p1}':'Caches {p0} · Logs {p1}',
    'Persistant {p0} · Runtime {p1} · Caches {p2} · Logs {p3}':'Persistent {p0} · Runtime {p1} · Caches {p2} · Logs {p3}',
    'Analyse du disque en cours…':'Scanning disk…', 'Entretien automatique':'Automatic maintenance',
    'Caches cumulés (Mio)':'Total caches (MiB)', 'Journaux cumulés (Mio)':'Total logs (MiB)',
    'Espace libre avant lancement (Mio)':'Minimum free space before launch (MiB)', 'Diagnostic Proton détaillé':'Detailed Proton diagnostics',
    'NETTOYER':'CLEAN UP', 'VIDER LES CACHES':'CLEAR CACHES', 'ACTUALISER':'REFRESH',
    'Sauvegardes, préfixes et réglages conservés. Limites appliquées hors jeu.':'Saves, prefixes and settings are kept. Limits apply outside gameplay.',
    'Analyse en cours…':'Scanning…', 'Nettoyage en cours…':'Cleaning…',
    'JEUX PAR TAILLE · progression et réglages inclus dans « persistant »':'GAMES BY SIZE · saves and settings are included in Persistent',
    'Analyse / nettoyage en cours…':'Scanning / cleaning…', 'Attendez la fin de l’analyse / du nettoyage.':'Please wait for scanning / cleaning to finish.',
    '{p0} libérés · {p1} erreurs · sauvegardes conservées':'{p0} freed · {p1} errors · saves kept',
    'Valeur en Mio (0 = ':'Value in MiB (0 = ', 'seuil désactivé':'threshold disabled', 'aucune rétention':'keep no eligible files',
    'Ship of Harkinian · profil commun':'Ship of Harkinian · shared profile', 'Borderlands 2 · profil commun':'Borderlands 2 · shared profile',
    'Métadonnées de catalogue liées à un autre emplacement ; dissociation refusée.':'Catalogue metadata links elsewhere; unlink refused.',
    'État du catalogue Windows Party invalide.':'Invalid Windows Party catalogue state.',
    'Pygame 2 est requis pour le configurateur à la manette. Ancienne interface : PARTYDECK_UI=legacy windows-party configurer':'Pygame 2 is required for the gamepad configurator. Legacy interface: PARTYDECK_UI=legacy windows-party configurer',
    'Option clavier comme joueur invalide.':'Invalid keyboard-as-player option.', 'Adaptateur Windows Party inconnu.':'Unknown Windows Party adapter.',
    'Profil Windows Party invalide pour {p0}':'Invalid Windows Party profile for {p0}',
    'Le profil est un lien symbolique : {p0}':'The profile is a symbolic link: {p0}', 'Le fichier est un lien symbolique : {p0}':'The file is a symbolic link: {p0}',
    'Attendez la fin de la session ou de l’installation avant de retirer ce jeu.':'Wait for the session or installation to finish before removing this game.',
    'Le lanceur est un lien utilisateur ; retrait refusé.':'The launcher is a user-created link; removal refused.',
    'Le lanceur a été personnalisé ; retrait automatique refusé.':'The launcher has been customized; automatic removal refused.',
    "Yad est requis pour l'éditeur graphique. Les profils JSON restent modifiables dans le dossier profiles.":'Yad is required for the legacy editor. JSON profiles can still be edited in the profiles folder.',
    "Impossible d'ouvrir l'éditeur Yad (code {p0}).":'Could not open the Yad editor (code {p0}).',
    "Réponse de l'éditeur Windows Party invalide.":'Invalid response from the Windows Party editor.',
    "Impossible d'ouvrir les paramètres Anchor.":'Could not open Anchor settings.',
    "Réponse de l'éditeur Anchor invalide.":'Invalid response from the Anchor editor.',
    "Impossible d'ouvrir les réglages graphiques SoH.":'Could not open SoH graphics settings.',
    'Réponse des réglages graphiques SoH invalide.':'Invalid response from SoH graphics settings.',
    'Une entrée utilisateur existe déjà : {p0}':'A user-created entry already exists: {p0}',
    'Choisissez une archive .wsquashfs ou un dossier .wine ou .pc.':'Choose a .wsquashfs archive or a .wine/.pc folder.',
    "Le sélecteur de format n'a pas pu s'ouvrir.":'Could not open the format selector.', "Le sélecteur de jeu n'a pas pu s'ouvrir.":'Could not open the game selector.',
    "Le gestionnaire Windows Party n'a pas pu s'ouvrir.":'Could not open Windows Party Manager.', 'Commande de profil Windows Party invalide.':'Invalid Windows Party profile command.',
    'Disposition':'Layout', 'Entrées':'Inputs', 'Afficher ces réglages avant chaque lancement':'Show these settings before each launch',
    'Gérer ce jeu avec le profil Anchor':'Manage this game using the Anchor profile', 'Connexion automatique':'Connect automatically',
    'Configuration SoH (chemin relatif)':'SoH configuration (relative path)', 'Afficher les positions':'Show locations',
    'Autoriser la téléportation':'Allow teleportation', 'Synchroniser objets et progression':'Sync items and progress',
    'Activé + tirs alliés':'Enabled + friendly fire', 'Graphismes / Audio':'Graphics / Audio',
    'J{p0} — nom':'Player {p0} — name', 'J{p0} — Team ID':'Player {p0} — Team ID',
    'Internal resolution (0.5 à 2.0)':'Internal resolution (0.5 to 2.0)', 'Anti-aliasing MSAA (1 = désactivé, 2 à 8)':'MSAA anti-aliasing (1 = off, 2 to 8)',
    'Choisissez le format du jeu Windows.':'Choose the Windows game format.', 'Ajouter un jeu':'Add game', 'Archive .wsquashfs':'.wsquashfs archive',
    'Dossier .wine ou .pc':'.wine or .pc folder', 'Jeux Wine | *.wsquashfs *.WSQUASHFS':'Wine games | *.wsquashfs *.WSQUASHFS',
    'SoH / Anchor — règles communes et identité de chaque joueur.\nLes règles de salle dépendent des droits administrateur sur le serveur.\nLe chemin JSON est relatif au dossier de lancement du jeu.':'SoH / Anchor — shared room rules and player identities.\nRoom rules depend on server administrator privileges.\nThe JSON path is relative to the game working directory.',
    'Réglages communs à tous les joueurs SoH.\nRésolution interne : multiplicateur de la fenêtre de chaque joueur.\nLa musique peut être réservée à J1 ; les bruitages restent actifs pour tous.\nVolumes : de 0 à 100 %, ou vide pour conserver la valeur du JSON commun.\nSoH regroupe les voix et les bruitages dans le même volume.':'Shared settings for all SoH players.\nInternal resolution: scale relative to each player window.\nMusic can be limited to player 1; sound effects stay active for everyone.\nVolumes: 0 to 100%, or empty to use the shared JSON value.\nSoH uses the same volume for voices and sound effects.',
    'storage.json doit contenir un objet JSON.':'storage.json must contain a JSON object.',
    'Réglage stockage invalide : {p0}':'Invalid storage setting: {p0}', 'Conserver au moins un journal et 1 Mio par journal.':'Keep at least one log and 1 MiB per log.',
    'Impossible de vérifier les montages ; nettoyage refusé.':'Cannot check mount points; cleanup refused.',
    'Une instance Windows Party est encore active. Fermez-la avant de nettoyer ou relancer.':'A Windows Party instance is still running. Close it before cleaning or launching again.',
    'Une session ou un nettoyage Windows Party est déjà en cours.':'A Windows Party session or cleanup is already running.',
    'Fermez la session ou attendez la fin de l’installation avant de nettoyer.':'Close the session or wait for installation to finish before cleaning.',
    'Une session ou une installation est déjà en cours.':'A session or installation is already running.',
    '{p0} : {p1} libres':'{p0}: {p1} free',
    'Espace insuffisant ({p0}). Seuil de lancement : {p1}. Libérez de l’espace ou ajustez Stockage. Aucune sauvegarde supprimée.':'Not enough disk space ({p0}). Launch threshold: {p1}. Free up space or adjust Storage settings. No saves were deleted.',
    'Stockage : {p0} libérés ; {p1} erreurs de nettoyage.':'Storage: {p0} freed; {p1} cleanup errors.', 'Nettoyage différé : {p0}':'Cleanup deferred: {p0}',
    'Options graphiques ou audio SoH invalides.':'Invalid SoH graphics or audio options.', 'Les volumes SoH doivent être des entiers de 0 à 100 %.':'SoH volumes must be whole numbers from 0 to 100%.',
    'Profil Anchor invalide.':'Invalid Anchor profile.', 'Champ Anchor vide ou invalide : {p0}':'Empty or invalid Anchor field: {p0}',
    'Le fichier SoH doit être un chemin JSON relatif au dossier de lancement.':'The SoH JSON path must be relative to the working directory.',
    'Le port Anchor doit être compris entre 1025 et 65534.':'The Anchor port must be between 1025 and 65534.',
    'Option Anchor invalide : {p0}':'Invalid Anchor option: {p0}', 'Mode Anchor invalide : {p0}':'Invalid Anchor mode: {p0}',
    'Définissez un nom et une équipe pour chacun des quatre joueurs.':'Set a name and team for each of the four players.',
    'Chaque joueur doit avoir un nom différent.':'Each player must have a different name.', 'Numéro de joueur Anchor invalide.':'Invalid Anchor player number.',
    'Configuration SoH liée à un autre emplacement : {p0}':'SoH configuration links to another location: {p0}',
    'La configuration SoH doit être un objet JSON.':'SoH configuration must be a JSON object.', 'Structure SoH invalide : {p0}':'Invalid SoH structure: {p0}',
    'Structure SoH invalide : RoomSettings':'Invalid SoH structure: RoomSettings',
    'JSON commun SoH absent : réinstallez Windows Party.':'Shared SoH JSON is missing: reinstall Windows Party.', 'Le JSON commun SoH est invalide.':'The shared SoH JSON is invalid.',
    'Lanceur batocera-wine non reconnu ({p0}) : adaptateur de jeu refusé.':'Unrecognized batocera-wine launcher ({p0}): game adapter refused.',
    'Lanceur batocera-wine non reconnu : profil non appliqué. Aucune modification système effectuée.':'Unrecognized batocera-wine launcher: profile not applied. No system changes were made.',
    'batocera-wine introuvable.':'batocera-wine was not found.',
    'Anchor J{p0} : configuration appliquée (connexion={p1}).':'Anchor P{p0}: configuration applied (connect={p1}).',
    'Réglages Borderlands 2 invalides.':'Invalid Borderlands 2 settings.',
    'INI Borderlands 2 : auto ou chemin .ini relatif au préfixe, sans « .. ».':'Borderlands 2 INI: auto or a .ini path relative to the prefix, without "..".',
    'Dimensions de la fenêtre Borderlands 2 indisponibles.':'Borderlands 2 player-window dimensions are unavailable.',
    'INI Borderlands 2 hors de la vue privée : {p0}':'Borderlands 2 INI is outside the private view: {p0}',
    'Chemin INI ambigu : {p0}/{p1}':'Ambiguous INI path: {p0}/{p1}',
    'Préfixe Borderlands 2 sans utilisateur Wine. Lancez d’abord le jeu une fois en solo.':'The Borderlands 2 prefix has no Wine user. Launch the game once in solo mode first.',
    'Le profil Borderlands 2 doit être appliqué dans la session Wine privée du joueur.':'The Borderlands 2 profile must be applied inside the player\'s private Wine session.',
}


def message_body(message):
    """Separate legacy Yad labels from their CLI prefixes and field types."""
    match = re.match(r'^(--(?:field|button|text|file-filter|column)=)(.*?)(:(?:CB|CHK|NUM|[0-9]+))?$',message,re.S)
    return (match[1],match[2],match[3] or '') if match else ('',message,'')


def tr(message, **values):
    prefix, body, suffix = message_body(message)
    rendered = EN.get(body,body) if get_language() == 'en' else body
    return prefix + (rendered.format(**values) if values else rendered) + suffix


def choice_label(key, value):
    labels = {'players':{'auto':'Automatique'},
              'split':{'horizontal':'Horizontal','vertical':'Vertical'},
              'input':{'auto':'Automatique','clavier-j1':'Clavier/souris · J1','clavier-j2':'Clavier/souris · J2'}}
    return tr(labels.get(key,{}).get(value,value))
