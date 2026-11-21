"""Borderlands 2: targeted INI edits inside a player's private Wine namespace."""
from partydeck_i18n import tr
import codecs
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

PRESETS = ('keep', 'low', 'medium', 'high', 'max')
PRESET_LABELS = dict(keep='Conserver les réglages', low='Bas', medium='Moyen', high='Élevé', max='Max')
PRIVATE_BINDS = (Path('/userdata/saves/windows'), Path('/userdata/system/wine-bottles/windows'),
                 Path('/var/run/wine'))


def matches(rom):
    name = rom.stem.casefold()
    return (bool(re.search(r'(?<![a-z0-9])borderlands[\s_-]*(?:2|ii)(?![a-z0-9])', name))
            and not re.search(r'borderlands[\s_-]*(?:2|ii)[\s_-]+vr(?:\W|$)',name))


def defaults():
    return dict(preset='keep', vsync='keep', physx='keep', names=[''] * 4,
                automatic=True,host_player=1,port=7777)


def validate(options):
    if not isinstance(options,dict):
        raise ValueError(tr('Réglages Borderlands 2 invalides.'))
    # Discard retired toggles, custom paths and language overrides from old
    # profiles. Display policy and config discovery are mandatory.
    normalized = {key:options.get(key,value) for key,value in defaults().items()}
    from partydeck_autoconnect import options as network_options
    normalized.update(network_options(normalized,'borderlands2'))
    if (normalized['preset'] not in PRESETS or normalized['vsync'] not in ('keep','on','off')
            or normalized['physx'] not in ('keep','0','1','2')):
        raise ValueError(tr('Réglages Borderlands 2 invalides.'))
    names = normalized['names']
    if (not isinstance(names,list) or len(names) != 4
            or any(not isinstance(name,str) or len(name) > 64
                   or any(ord(c) < 32 or ord(c) == 127 or c in ';#=[]' for c in name)
                   or (name and not name.strip()) for name in names)):
        raise ValueError(tr('Noms Borderlands 2 : quatre noms de 64 caractères maximum, ou vides pour conserver ; sans caractères de contrôle ni ; # = [ ].'))
    return normalized


def patch_ini(text, updates):
    """UE3 INIs contain repeated array keys; ConfigParser would destroy them."""
    newline = '\r\n' if '\r\n' in text else '\n'
    output, section = [], None
    pending = {name.casefold(): dict(values) for name, values in updates.items()}
    canonical = {name.casefold(): name for name in updates}
    all_values = {name.casefold(): {k.casefold(): (k, str(v)) for k, v in values.items()}
                  for name, values in updates.items()}

    def flush():
        if section in pending:
            if output and not output[-1].endswith(('\n','\r')):
                output[-1] += newline
            output.extend(f'{key}={value}{newline}' for key, value in pending[section].items())
            pending[section].clear()

    for line in text.splitlines(keepends=True):
        header = re.match(r'^\s*\[([^\]]+)\]\s*(?:[;#].*)?$', line.strip())
        if header:
            flush()
            section = header[1].casefold()
        key = re.match(r'^(\s*)([^;#=\s]+)(\s*=\s*)(.*?)(\r?\n)?$', line)
        if key and section in all_values and key[2].casefold() in all_values[section]:
            name, value = all_values[section][key[2].casefold()]
            pending[section].pop(name, None)
            # Preserve an inline comment and every unmodified line byte-for-byte.
            comment = re.search(r'([ \t]*[;#].*)$', key[4])
            line = key[1] + key[2] + key[3] + value + (comment[1] if comment else '') + (key[5] or '')
        output.append(line)
    flush()
    for name, values in pending.items():
        if values:
            if output and not output[-1].endswith(('\n','\r')):
                output[-1] += newline
            output.append(f'{newline}[{canonical[name]}]{newline}')
            output.extend(f'{key}={value}{newline}' for key, value in values.items())
    return ''.join(output)


def overrides(options, width, height):
    options = validate(options)
    if type(width) is not int or type(height) is not int or not (64 <= width <= 32768 and 64 <= height <= 32768):
        raise ValueError(tr('Dimensions de la fenêtre Borderlands 2 indisponibles.'))
    values = dict(Fullscreen='False',WindowedFullscreen='True',ResX=width,ResY=height,bAutoDetectSettings='False')
    startup = dict(StartupFullscreen='False',StartupResolutionX=width,StartupResolutionY=height)
    preset = options['preset']
    if preset != 'keep':
        level = PRESETS.index(preset)-1
        values.update(TextureQuality=(0,1,2,2)[level], ViewDistance=level,
                      DetailMode=min(2,level), MaxAnisotropy=(2,4,8,16)[level],
                      FXAA='False' if level == 0 else 'True',
                      AmbientOcclusion='True' if level >= 2 else 'False',
                      DepthOfField='True' if level >= 2 else 'False',
                      DynamicShadows='False' if level == 0 else 'True',
                      bAllowLightShafts='True' if level >= 2 else 'False',
                      FoliageDrawRadiusMultiplier=('0.5','0.75','1.0','1.0')[level],
                      MinShadowResolution=32, MaxShadowResolution=(512,1024,2048,4096)[level],
                      MaxWholeSceneDominantShadowResolution=(512,1024,2048,4096)[level])
    if options['physx'] != 'keep':
        values['PhysXLevel'] = options['physx']
    if options['vsync'] != 'keep':
        values['UseVsync'] = 'True' if options['vsync']=='on' else 'False'
    return {'SystemSettings':values,'WinDrv.WindowsClient':startup,
            'WillowGame.WillowGameEngine':dict(bPauseLostFocusWindowed='False')}


def safe_path(path, allowed):
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError(tr('INI Borderlands 2 hors de la vue privée : {p0}', p0=path))
    return resolved


def child(directory, name):
    """Reuse existing spelling: Wine is case-insensitive, Linux paths are not."""
    if directory.is_dir():
        entries = [p for p in directory.iterdir() if p.name.casefold() == name.casefold()]
        if len(entries) > 1:
            raise ValueError(tr('Chemin INI ambigu : {p0}/{p1}', p0=directory, p1=name))
        if entries:
            return entries[0]
    return directory / name


def targets(prefix, allowed):
    users = safe_path(child(child(prefix, 'drive_c'), 'users'), allowed)
    excluded = {'public', 'default', 'default user', 'all users'}
    candidates = [p for p in users.iterdir() if p.name.casefold() not in excluded
                  and p.is_dir()] if users.is_dir() else []
    if not candidates:
        raise ValueError(tr('Préfixe Borderlands 2 sans utilisateur Wine. Lancez d’abord le jeu une fois en solo.'))
    existing, fallbacks = [], []
    for user in sorted(candidates):
        safe_path(user, allowed)
        documents = [p for p in user.iterdir() if p.name.casefold() in ('documents', 'my documents')]
        if not documents:
            documents = [user/'Documents']
        for document in documents:
            target = safe_path(document, allowed)
            for name in ('My Games','Borderlands 2','WillowGame','Config','WillowEngine.ini'):
                target = child(target, name)
                safe_path(target, allowed)
            target = safe_path(target, allowed)
            (existing if target.is_file() else fallbacks).append(target)
    # Patch existing configs only if found; otherwise initialize each actual user
    # so that a subsequent UMU root -> steamuser conversion carries the settings.
    return list(dict.fromkeys(existing or fallbacks))


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix='.partydeck-bl2-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def decode(data):
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode('utf-16'), 'utf-16'
    if data.startswith(codecs.BOM_UTF8):
        return data.decode('utf-8-sig'), 'utf-8-sig'
    try:
        return data.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return data.decode('cp1252'), 'cp1252'


def original_language(text):
    section, value = None, None
    for line in text.splitlines():
        header = re.match(r'^\s*\[([^\]]+)\]',line)
        if header:
            section = header[1].casefold()
        match = re.match(r'^\s*Language\s*=\s*([a-zA-Z_-]+)\s*(?:[;#].*)?$',line,re.I)
        if section == 'settings' and match:
            value = match[1]
    return value


def backup_path(player, path):
    return player/'borderlands2-before'/(path.stem+'-'+hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'.ini')


def game_config_edits(directory, options, index, allowed, player):
    """Set only the persona; retire old language overrides once using our backup."""
    if not options['names'][index] and not (player/'borderlands2-before').is_dir():
        return [], []
    directory = safe_path(directory, allowed)
    candidates = []
    for parts in (('steam_emu.ini',), ('Binaries','Win32','steam_emu.ini')):
        path = directory
        for part in parts:
            path = child(path,part)
            safe_path(path,allowed)
        if path.is_file():
            if path.is_symlink():
                raise ValueError(tr('Configuration Borderlands 2 liée à un autre emplacement : {p0}',p0=path))
            candidates.append(path)
    if not candidates and options['names'][index]:
        raise ValueError(tr('Nom Borderlands 2 : steam_emu.ini introuvable dans la vue privée du jeu. Laissez les noms vides pour utiliser cette installation.'))
    changes = {}
    if options['names'][index]:
        changes['UserName'] = options['names'][index]
    edits, retired = [], []
    for path in dict.fromkeys(candidates):
        before = path.read_bytes()
        # Preserve the legacy non-UTF-8 ASCII-art header exactly; Steam names
        # supplied by the user are encoded as UTF-8 without touching other bytes.
        text = before.decode('utf-8-sig',errors='surrogateescape')
        section, appid = None, None
        for line in text.splitlines():
            header = re.match(r'^\s*\[([^\]]+)\]',line)
            if header:
                section = header[1].casefold()
            value = re.match(r'^\s*AppId\s*=\s*(\d+)\s*(?:[;#].*)?$',line,re.I)
            if section == 'settings' and value:
                appid = value[1]
        if appid != '49520':
            if options['names'][index]:
                raise ValueError(tr('Configuration steam_emu.ini non reconnue pour Borderlands 2 : {p0}',p0=path))
            continue
        values = dict(changes)
        backup = backup_path(player,path)
        stamp = player/'borderlands2-language-retired'/backup.name
        safe_path(stamp,(player,))
        if not stamp.exists():
            if backup.is_file():
                safe_path(backup,(player,))
                previous = original_language(backup.read_bytes().decode('utf-8-sig',errors='surrogateescape'))
                if previous is not None:
                    values['Language'] = previous
            retired.append(stamp)
        after = patch_ini(text,{'Settings':values}).encode('utf-8',errors='surrogateescape')
        if before.startswith(codecs.BOM_UTF8):
            after = codecs.BOM_UTF8 + after
        edits.append((path,before,after))
    return edits, retired


def apply_config(prefix, payload, private_binds=PRIVATE_BINDS, directory=None):
    player = Path(payload['player']).resolve()
    prefix = prefix.resolve()
    options = validate(payload['settings'])
    index = payload.get('index',0)
    if type(index) is not int or index not in range(4):
        raise ValueError(tr('Numéro de joueur Borderlands 2 invalide.'))
    changes = overrides(options, payload['width'], payload['height'])
    if not changes:
        return
    allowed = tuple(p.resolve() for p in (prefix, player, *private_binds))
    prefixes = [prefix]
    for name in ('materialized-prefixes', 'compatdata', 'merged-prefixes'):
        root = player/'umu-private'/name
        if root.is_dir():
            for path in root.iterdir():
                for candidate in (path, path/'pfx'):
                    if (candidate/'drive_c'/'users').is_dir():
                        safe_path(candidate, (player,))
                        prefixes.append(candidate)
    paths = []
    for candidate in dict.fromkeys(prefixes):
        paths.extend(targets(candidate, allowed))
    # Validate and prepare every path before touching any player configuration.
    edits, retired = game_config_edits(directory or prefix/'drive_c/game',options,index,allowed,player)
    for path in dict.fromkeys(paths):
        before = path.read_bytes() if path.exists() else b''
        text, encoding = decode(before)
        after = patch_ini(text, changes).encode(encoding)
        edits.append((path,before,after))
    for path,before,after in edits:
        if before == after:
            continue
        backup = backup_path(player,path)
        if before and not backup.exists():
            write_bytes(backup,before)
        write_bytes(path,after)
        print(f'Borderlands 2 {player.name} : {path} · {PRESET_LABELS[options["preset"]]} · {payload["width"]}×{payload["height"]}', flush=True)
    for stamp in retired:
        safe_path(stamp,(player,))
        write_bytes(stamp,b'Language override retired\n')


def install_hook(base, rom, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import profile_path, read_profile, atomic_write
    if not profile_path(base,rom).exists():
        return
    profile = read_profile(base,rom)
    if profile.get('adapter') != 'borderlands2':
        return
    options = validate(profile['borderlands2'])
    width = int(os.environ.get('PARTYDECK_PLAYER_WIDTH','0'))
    height = int(os.environ.get('PARTYDECK_PLAYER_HEIGHT','0'))
    overrides(options,width,height)  # Refuse unavailable dimensions before starting Wine.
    payload = player/'borderlands2-launch.json'
    index = int(player.name.removeprefix('j')) - 1
    if index not in range(4):
        raise ValueError(tr('Numéro de joueur Borderlands 2 invalide.'))
    atomic_write(payload,json.dumps(dict(settings=options,player=str(player),index=index,width=width,height=height)))
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    hook = [sys.executable,str(base/'partydeck_borderlands2.py'),str(payload)]
    replacement = player/'batocera-wine-borderlands2'
    atomic_write(replacement,instrument_native(binary.read_text(),hook, prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)


if __name__ == '__main__':
    try:
        payload = json.loads(Path(sys.argv[1]).read_text())
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != payload['player']:
            raise ValueError(tr('Le profil Borderlands 2 doit être appliqué dans la session Wine privée du joueur.'))
        # Arguments: payload, current game directory, native Wine prefix.
        apply_config(Path(sys.argv[3]),payload,directory=Path(sys.argv[2]))
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / Borderlands 2 : {error}',file=sys.stderr)
        raise SystemExit(1)
