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
    'Pygame 2 est requis pour le configurateur à la manette. Ancienne interface : PARTYDECK_UI=legacy partydeck-test configurer':'Pygame 2 is required for the gamepad configurator. Legacy interface: PARTYDECK_UI=legacy partydeck-test configurer',
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
