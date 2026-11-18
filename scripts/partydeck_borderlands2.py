"""Borderlands 2: targeted INI edits inside a player's private Wine namespace."""
from partydeck_i18n import tr
import codecs
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
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
    return dict(windowed_fullscreen=True, fit_resolution=True, preset='keep', physx='keep', config='auto')


def validate(options):
    if (not isinstance(options, dict) or type(options.get('windowed_fullscreen')) is not bool
            or type(options.get('fit_resolution')) is not bool or options.get('preset') not in PRESETS
            or options.get('physx') not in ('keep', '0', '1', '2')
            or not isinstance(options.get('config'), str)):
        raise ValueError(tr('Réglages Borderlands 2 invalides.'))
    relative = PurePosixPath(options['config'])
    if options['config'] != 'auto' and (relative.is_absolute() or '..' in relative.parts
            or relative.suffix.lower() != '.ini' or '\\' in str(relative) or ':' in str(relative)):
        raise ValueError(tr('INI Borderlands 2 : auto ou chemin .ini relatif au préfixe, sans « .. ».'))
    return options


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
    validate(options)
    values, startup = {}, {}
    if options['windowed_fullscreen']:
        values.update(Fullscreen='False', WindowedFullscreen='True')
        startup['StartupFullscreen'] = 'False'
    if options['fit_resolution']:
        if type(width) is not int or type(height) is not int or not (64 <= width <= 32768 and 64 <= height <= 32768):
            raise ValueError(tr('Dimensions de la fenêtre Borderlands 2 indisponibles.'))
        values.update(ResX=width, ResY=height)
        startup.update(StartupResolutionX=width, StartupResolutionY=height)
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
    if values:
        values['bAutoDetectSettings'] = 'False'
    result = {}
    if values:
        result['SystemSettings'] = values
    if startup:
        result['WinDrv.WindowsClient'] = startup
    if options['windowed_fullscreen']:
        result['WillowGame.WillowGameEngine'] = dict(bPauseLostFocusWindowed='False')
    return result


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


def targets(prefix, options, allowed):
    if options['config'] != 'auto':
        target = prefix
        for part in PurePosixPath(options['config']).parts:
            safe_path(target, allowed)
            target = child(target, part)
        return [safe_path(target, allowed)]
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


def apply_config(prefix, payload, private_binds=PRIVATE_BINDS):
    player = Path(payload['player']).resolve()
    prefix = prefix.resolve()
    options = validate(payload['settings'])
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
        paths.extend(targets(candidate, options, allowed))
    # Validate and prepare every path before touching any player configuration.
    edits = []
    for path in dict.fromkeys(paths):
        before = path.read_bytes() if path.exists() else b''
        text, encoding = decode(before)
        after = patch_ini(text, changes).encode(encoding)
        edits.append((path,before,after))
    for path,before,after in edits:
        if before == after:
            continue
        backup = player/'borderlands2-before'/('WillowEngine-'+hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'.ini')
        if before and not backup.exists():
            write_bytes(backup,before)
        write_bytes(path,after)
        print(f'Borderlands 2 {player.name} : {path} · {PRESET_LABELS[options["preset"]]} · {payload["width"]}×{payload["height"]}', flush=True)


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
    atomic_write(payload,json.dumps(dict(settings=options,player=str(player),width=width,height=height)))
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
        apply_config(Path(sys.argv[3]),payload)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / Borderlands 2 : {error}',file=sys.stderr)
        raise SystemExit(1)
