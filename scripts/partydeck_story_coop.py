"""Package Story Co-op for Wine and supervise its bundled native LAN server."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile

from partydeck_anchor import apply_graphics, config_path, graphics_defaults, validate_config, validate_graphics, VOLUME_FIELDS
from partydeck_i18n import tr
from partydeck_soh_camera import (CAMERA_AXES, DEFAULT_DISTANCE, DISTANCE_MODES, MAX_DISTANCE, MIN_DISTANCE,
                                  configure_camera_settings, configure_freecam)
import partydeck_story_skins as skins

ADAPTER = 'ocarina-story-coop'
LABEL = 'Ocarina of Time · Story Co-op'
VERSION = 'v1.0.5'
PORT = 21050
CONSUMABLES = {'rupees': 'Partager les rubis', 'ammo': 'Partager les munitions', 'healing': 'Partager les PV'}
SHARING_CHOICES = {'keep': 'Conserver', 'on': 'Activé', 'off': 'Désactivé'}
TIME_MODES = {'shared': 'Horloge commune du serveur', 'original': 'Cycle d’origine par joueur'}
GAME_DIR = Path('drive_c/game')
CONFIG = 'shipofharkinian.json'
SERVER_DIR = 'PartyDeck-Story-Coop'
ASSETS = ('oot.o2r', 'oot-mq.o2r')
RELEASE = f'https://github.com/cranebeaker/ocarina-coop/releases/download/{VERSION}/'
WINDOWS_ARCHIVE = f'OcarinaStoryCoop-{VERSION}-windows.zip'
LINUX_ARCHIVE = f'OcarinaStoryCoop-{VERSION}-linux.tar.gz'
WINDOWS_DIGEST = '0e5bd2ddaf61bf1707ae8ee23c396c272733bfd7478fbfc8add35957c64f8742'
LINUX_DIGEST = '4a305e237487d628be52afcc3e554ad4b5551bdfc0442ece6f8d05f8b36ace60'
CLIENT_DIGEST = 'ef4470bbe7b7c7277662438190177ab9045fed3e61e77f3ecfa92a75028f5377'
FIXED_CLIENT_DIGEST = '969354419e80ea9b712928da264b5ce23f32c227f3a6c769d300877976c03576'
HIDDEN_WINDOW_DIGEST = '2b612c990d14611010b70ae9f6a073ff057489c52597c31308650e6e0f6f1769'
ORIGINAL_TIME_DIGEST = 'f905a5e7d9afff4db6f407f74701870a2bb884567c670cbefff624095661d6be'
ORIGINAL_TIME_HIDDEN_WINDOW_DIGEST = 'f97d64c0a1d841d6a933bfae9a1df6235c97795a50119a093b4ef48574cefe37'
# Audio_StopSfxById in the official v1.0.5 Windows build (7b91267).
# Return through the existing epilogue when the bank index is >= 7.
# For a valid bank, load the same sound entry as the original code.
AUDIO_GUARD_OFFSET = 0xFFF7AA
AUDIO_GUARD_ORIGINAL = bytes.fromhex('25ff0000008bc0488d0dc8284a01ba50000000486bd200488b04c1')
AUDIO_GUARD_PATCH = bytes.fromhex('83f8070f832e010000488d0dc6284a0131d2488b04c19090909090')
# ZeldaOnlineClient::OnConnected already has the room window in RCX.
# Enable has set the skin, so replace the duplicate SetCurrentSkin call with Hide.
HIDE_WINDOW_OFFSET = 0xE24808
HIDE_WINDOW_ORIGINAL = bytes.fromhex('e823b7ffff')
HIDE_WINDOW_PATCH = bytes.fromhex('e8435d8100')
# ShouldFreezeTime only gates Zelda Online's writes to the game clock.
LOCAL_TIME_OFFSET = 0xDAF6B0
LOCAL_TIME_ORIGINAL = bytes.fromhex('89542410')
LOCAL_TIME_PATCH = bytes.fromhex('b001c390')  # mov al, 1; ret; nop
# SDL_main opens a console, redirects the standard streams, and immediately
# hides it. Skip that block and resume at setlocale before GameConsole_Init.
# Closing the transient Wine console while Gamescope focuses it can abort Xwayland.
STARTUP_CONSOLE_OFFSET = 0x10153AD
STARTUP_CONSOLE_ORIGINAL = bytes.fromhex('ff1525b3ae00')
STARTUP_CONSOLE_PATCH = bytes.fromhex('e96f00000090')  # jmp 0x141016021; nop
SERVER_FILES = {
    'OOTServer': 'f1ce1e80bdff661fa17316080b616bab5b8e6f380164c2326f4fc08fde3c2b57',
    'config.json': '0b43c81bbc154e19a002f175d9b8a2fdb58ed7834f9d0dd277e1f7fc39dbae5f',
}


def matches(rom):
    name = rom.stem.casefold()
    return ('ocarinastorycoop' in name or
            (bool(re.search(r'ocarina|ship[\s_-]*of[\s_-]*harkinian|\bsoh\b', name))
             and bool(re.search(r'story[\s_-]*co[\s_-]*op', name))))


def defaults():
    return dict(automatic=True, port=PORT, room='', config=CONFIG,
                sync=True, locations=True, teleport=True, consumables=dict.fromkeys(CONSUMABLES, 'keep'),
                freecam=False, camera_axes=dict.fromkeys(CAMERA_AXES, 'keep'), time_mode='shared',
                camera_distance_mode='keep', camera_distance=DEFAULT_DISTANCE,
                names=[f'J{i}' for i in range(1, 5)], skins=[''] * 4, graphics=graphics_defaults())


def validate(options):
    if options is None:
        return defaults()
    if not isinstance(options, dict):
        raise ValueError(tr('Profil Story Co-op invalide.'))
    options = defaults() | options
    sharing = options['consumables']
    camera_axes = options['camera_axes']
    distance_mode, distance = options['camera_distance_mode'], options['camera_distance']
    if isinstance(sharing, str) and sharing in SHARING_CHOICES:
        sharing = dict.fromkeys(CONSUMABLES, sharing)
    if (type(options['port']) is not int or not 1024 < options['port'] < 65535
            or any(type(options[key]) is not bool for key in ('automatic', 'sync', 'locations', 'teleport', 'freecam'))
            or not isinstance(options['time_mode'], str) or options['time_mode'] not in TIME_MODES
            or not isinstance(sharing, dict) or sharing.keys() != CONSUMABLES.keys()
            or any(not isinstance(mode, str) or mode not in SHARING_CHOICES for mode in sharing.values())
            or not isinstance(camera_axes, dict) or not camera_axes.keys() <= CAMERA_AXES.keys()
            or any(not isinstance(mode, str) or mode not in SHARING_CHOICES for mode in camera_axes.values())
            or not isinstance(distance_mode, str) or distance_mode not in DISTANCE_MODES
            or type(distance) is not int or not MIN_DISTANCE <= distance <= MAX_DISTANCE
            or not isinstance(options['config'], str)
            or not valid_text(options['room'], 32, optional=True)):
        raise ValueError(tr('Profil Story Co-op invalide.'))
    options['consumables'] = sharing
    options['camera_axes'] = dict.fromkeys(CAMERA_AXES, 'keep') | camera_axes
    validate_config(options['config'])
    names, skins = options['names'], options['skins']
    if (not isinstance(names, list) or len(names) != 4
            or any(not valid_text(name, 63) for name in names)
            or len({name.strip() for name in names}) != 4):
        raise ValueError(tr('Story Co-op : définissez quatre noms de joueur différents (63 octets maximum).'))
    if (not isinstance(skins, list) or len(skins) != 4
            or any(not valid_text(skin, 255, optional=True) for skin in skins)):
        raise ValueError(tr('Story Co-op : identifiant de skin invalide.'))
    options['names'] = [name.strip() for name in names]
    validate_graphics(options['graphics'])
    return options


def valid_text(value, limit, *, optional=False):
    return (isinstance(value, str) and (optional or bool(value.strip()))
            and all(char.isprintable() for char in value) and len(value.encode()) <= limit)


def client_host(index):
    return f'127.0.0.{index}'


def session_config(player, token):
    return player / f'story-coop-{token}.json'


def installed_skins(directory):
    """Discover namespaced player resources produced by the upstream skin converter."""
    resources, player_skins = {}, set()
    for path in sorted((directory / 'mods').rglob('*')):
        if path.suffix.lower() != '.o2r' or not path.is_file() or any(c in path.name for c in '|,'):
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for entry in archive.namelist():
                    parts = entry.replace('\\', '/').split('/', 3)
                    if (len(parts) < 3 or parts[0] in ('alt', 'link')
                            or skins.LOCAL_SKIN.fullmatch(parts[0])
                            or not re.fullmatch(r'[A-Za-z0-9_-]+', parts[0])
                            or parts[1] not in ('objects', 'textures', 'scenes', 'audio', 'overlays', 'misc')):
                        continue
                    reference = parts[0]
                    resources.setdefault(reference, set()).add(path.name)
                    if parts[1] == 'objects' and parts[2] in ('object_link_boy', 'object_link_child'):
                        player_skins.add(reference)
        except (OSError, zipfile.BadZipFile):
            continue
    choices = []
    for reference in sorted(player_skins, key=str.casefold):
        names = resources[reference]
        value = reference if names == {reference + '.o2r'} else reference + '|' + ','.join(sorted(names))
        if valid_text(value, 255):
            choices.append(value)
    return choices


def skin_choices(base, rom):
    if rom.is_dir():
        for directory in game_dirs(rom):
            if (rom / directory / 'soh.exe').is_file():
                return installed_skins(rom / directory)
    from partydeck_storage import identity
    identifier, _ = identity(rom)
    try:
        choices = json.loads((base / 'runtime' / identifier / 'j1' / 'story-skins.json').read_text())
    except (OSError, ValueError):
        return []
    return choices if isinstance(choices, list) and all(valid_text(skin, 255) for skin in choices) else []


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(directory, name, checksum):
    archive = directory / name
    subprocess.run(['curl', '-fLsS', '--proto', '=https', '--retry', '2',
                    '--connect-timeout', '15', '--max-time', '180',
                    RELEASE + name, '-o', str(archive)], check=True)
    if digest(archive) != checksum:
        raise ValueError(tr('Archive Story Co-op invalide ({p0}).', p0=name))
    return archive


def release_server_files(archive):
    with tarfile.open(archive) as package:
        files = {}
        for name in SERVER_FILES:
            member = f'OcarinaStoryCoop-{VERSION}-linux/server/{name}'
            with package.extractfile(member) as stream:
                files[name] = stream.read()
        return files


def prepare(source, output):
    source = source.resolve(strict=True)
    asset = source.name.lower()
    output_format = output.suffix.lower()
    if not source.is_file() or (asset not in ASSETS and source.suffix.lower() != '.z64'):
        raise ValueError(tr('Fournissez une ROM .z64 compatible ou un fichier oot.o2r / oot-mq.o2r.'))
    if output_format not in ('.wine', '.wsquashfs') or (output_format == '.wsquashfs' and asset not in ASSETS):
        raise ValueError(tr('Utilisez une sortie .wine pour une ROM .z64, ou .wsquashfs avec un fichier .o2r.'))
    if output.exists() or output.is_symlink():
        raise FileExistsError(tr('La destination existe déjà : {p0}', p0=output))
    output = output.parent.resolve(strict=True) / output.name

    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.ocarina-story-coop-') as folder:
        staging = Path(folder)
        prefix = staging / 'prefix'
        game = prefix / GAME_DIR
        game.mkdir(parents=True)
        print(tr('Téléchargement de Story Co-op {p0}.', p0=VERSION), flush=True)
        windows = download(staging, WINDOWS_ARCHIVE, WINDOWS_DIGEST)
        linux = download(staging, LINUX_ARCHIVE, LINUX_DIGEST)
        with zipfile.ZipFile(windows) as package:
            for member in package.infolist():
                raw_name = member.filename.replace('\\', '/')
                relative = PurePosixPath(raw_name).parts[1:]
                if raw_name.endswith('/') or not relative:
                    continue
                if relative[0] not in ('assets', 'soh.exe', 'soh.o2r', 'gamecontrollerdb.txt'):
                    continue
                if '..' in relative:
                    raise ValueError(tr('Archive Story Co-op invalide ({p0}).', p0=WINDOWS_ARCHIVE))
                target = game.joinpath(*relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as stream, target.open('wb') as copied:
                    shutil.copyfileobj(stream, copied)
        server = game / SERVER_DIR
        server.mkdir()
        for name, data in release_server_files(linux).items():
            (server / name).write_bytes(data)
        shutil.copyfile(source, game / (asset if asset in ASSETS else 'oot.z64'))
        (prefix / 'autorun.cmd').write_bytes(b'DIR=drive_c/game\nCMD=soh.exe\n')
        if output_format == '.wine':
            prefix.rename(output)
        else:
            archive = staging / 'story.wsquashfs'
            subprocess.run(['mksquashfs', str(prefix), str(archive), '-noappend', '-comp', 'zstd'],
                           check=True)
            os.link(archive, output)
    print(tr('Story Co-op prêt : {p0}', p0=output), flush=True)


def read_member(rom, member):
    if rom.suffix.lower() == '.wsquashfs':
        result = subprocess.run(['unsquashfs', '-cat', str(rom), str(member)],
                                capture_output=True, timeout=30, env=dict(os.environ, LC_ALL='C'))
        if result.returncode == 2 and b'no matches for ' in result.stderr:
            return None
        result.check_returncode()
        return result.stdout
    try:
        return (rom / member).read_bytes()
    except FileNotFoundError:
        return None


def verify_server(files):
    for name, checksum in SERVER_FILES.items():
        if hashlib.sha256(files[name]).hexdigest() != checksum:
            raise ValueError(tr('Fichier serveur Story Co-op {p0} invalide : {p1}.', p0=VERSION, p1=name))
    return files


def game_dirs(rom):
    autorun = read_member(rom, Path('autorun.cmd')) or b''
    setting = re.search(r'^DIR=([^\r\n]*)', autorun.decode('utf-8-sig', errors='replace'), re.MULTILINE)
    directory = Path(setting[1].strip().replace('\\', '/')) if setting else Path('.')
    defaults = (Path('.'),) if rom.suffix.lower() == '.pc' else (GAME_DIR, Path('.'))
    # Only probe relative paths inside the game or archive.
    candidates = defaults if directory.is_absolute() or '..' in directory.parts else (directory, *defaults)
    return dict.fromkeys(candidates)


def bundled_server_files(rom):
    for candidate in game_dirs(rom):
        relative = candidate / SERVER_DIR
        program = read_member(rom, relative / 'OOTServer')
        if program is None:
            continue
        config = read_member(rom, relative / 'config.json')
        if config is not None:
            return verify_server({'OOTServer': program, 'config.json': config})
    return None


def prepare_game_skin(rom, cache):
    try:
        return skins.prepare_game_skin(rom, game_dirs(rom), cache / 'skins')
    except (OSError, subprocess.SubprocessError) as error:
        print(tr('Story Co-op : partage du mod de Link indisponible ({p0}).', p0=error), flush=True)
        return ''


def cached_server_files(cache):
    from partydeck_borderlands2 import write_bytes

    paths = {name: cache / name for name in SERVER_FILES}
    if all(path.is_file() and not path.is_symlink() for path in paths.values()):
        try:
            return verify_server({name: path.read_bytes() for name, path in paths.items()})
        except ValueError:
            pass  # An incomplete or damaged cache can be rebuilt.
    print(tr('Story Co-op : téléchargement du serveur Linux {p0}.', p0=VERSION), flush=True)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache, prefix='.download-') as folder:
        archive = download(Path(folder), LINUX_ARCHIVE, LINUX_DIGEST)
        files = verify_server(release_server_files(archive))
        for name, data in files.items():
            write_bytes(paths[name], data)
    return files


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start_server(rom, work, lan, cache, options, players, host_settings):
    from partydeck_borderlands2 import write_bytes
    files = bundled_server_files(rom)
    if files is None:
        try:
            files = cached_server_files(cache)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise RuntimeError(tr('Story Co-op : serveur Linux indisponible ({p0}).', p0=error)) from error
    skins.prepare(options['skins'][:players], cache / 'skins')
    original_time = options['time_mode'] == 'original'
    if original_time:
        config = json.loads(files['config.json'])
        config.update(daySpeed=0, nightSpeed=0)
        files['config.json'] = json.dumps(config).encode()
    work.mkdir(parents=True, exist_ok=True)
    program = work / 'OOTServer'
    for name, data in files.items():
        path = work / name
        if path.is_symlink():
            raise ValueError(tr('Le fichier est un lien symbolique : {p0}', p0=path))
        if not path.is_file() or path.read_bytes() != data:
            write_bytes(path, data)
    program.chmod(0o700)
    log = work / 'server.log'
    relay_options = {key: options[key] for key in ('automatic', 'locations', 'teleport', 'consumables')}
    relay_options['original_time'] = original_time
    reference = options.get('local_skin', '')
    if reference:
        relay_options['local_skins'] = [reference if not skin else '' for skin in options['skins'][:players]]
    with log.open('wb') as output:
        lobby = Path(__file__).with_name('partydeck_story_lobby.py')
        process = subprocess.Popen([*lan.prefix(0), sys.executable, str(lobby), str(program),
                                    str(options['port']), str(players), str(host_settings),
                                    json.dumps(relay_options)],
                                   pass_fds=(lan.fds[0],), cwd=work, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 10
        with log.open('rb') as output:
            marker = f'Story Co-op READY {options["port"]}'.encode()
            while process.poll() is None and time.monotonic() < deadline:
                if any(marker in line for line in output):
                    print(tr('Story Co-op : serveur local prêt sur {p0}:{p1}.',
                             p0=lan.address(0), p1=options['port']), flush=True)
                    return process
                time.sleep(.15)
        raise RuntimeError(tr('Story Co-op : le serveur ne démarre pas. Consultez {p0}.', p0=log))
    except BaseException:
        stop_server(process)
        raise


def patch_client(client, hide_window, original_time=False):
    from partydeck_borderlands2 import write_bytes

    patched = bytearray(client.read_bytes())
    console = slice(STARTUP_CONSOLE_OFFSET, STARTUP_CONSOLE_OFFSET + len(STARTUP_CONSOLE_ORIGINAL))
    console_patched = patched[console] == STARTUP_CONSOLE_PATCH
    # Use the existing allowlist for private clients with and without this
    # fix by hashing each executable with only the console call restored.
    if console_patched:
        patched[console] = STARTUP_CONSOLE_ORIGINAL
    checksum = hashlib.sha256(patched).hexdigest()
    variants = {
        (False, False): FIXED_CLIENT_DIGEST,
        (True, False): HIDDEN_WINDOW_DIGEST,
        (False, True): ORIGINAL_TIME_DIGEST,
        (True, True): ORIGINAL_TIME_HIDDEN_WINDOW_DIGEST,
    }
    expected = variants[hide_window, original_time]
    if checksum == expected and console_patched:
        return False
    if checksum != CLIENT_DIGEST and checksum not in variants.values():
        raise ValueError(tr('Story Co-op : soh.exe {p0} est requis dans le dossier du jeu.', p0=VERSION))
    if checksum == CLIENT_DIGEST:
        start = AUDIO_GUARD_OFFSET
        stop = start + len(AUDIO_GUARD_ORIGINAL)
        if patched[start:stop] != AUDIO_GUARD_ORIGINAL:
            raise ValueError(tr('Story Co-op : impossible de vérifier les correctifs de soh.exe.'))
        patched[start:stop] = AUDIO_GUARD_PATCH
    if hide_window or checksum in (HIDDEN_WINDOW_DIGEST, ORIGINAL_TIME_HIDDEN_WINDOW_DIGEST):
        start = HIDE_WINDOW_OFFSET
        patched[start:start + len(HIDE_WINDOW_PATCH)] = HIDE_WINDOW_PATCH if hide_window else HIDE_WINDOW_ORIGINAL
    if original_time or checksum in (ORIGINAL_TIME_DIGEST, ORIGINAL_TIME_HIDDEN_WINDOW_DIGEST):
        start = LOCAL_TIME_OFFSET
        patched[start:start + len(LOCAL_TIME_PATCH)] = LOCAL_TIME_PATCH if original_time else LOCAL_TIME_ORIGINAL
    if patched[console] != STARTUP_CONSOLE_ORIGINAL or hashlib.sha256(patched).hexdigest() != expected:
        raise ValueError(tr('Story Co-op : impossible de vérifier les correctifs de soh.exe.'))
    patched[console] = STARTUP_CONSOLE_PATCH
    write_bytes(client, patched)
    return True


def configure_client(player, rom, directory, root, options, skin_cache, controller_template=None):
    from partydeck_bottles import private_windows_paths
    from partydeck_profiles import atomic_write

    directory = directory.resolve(strict=True)
    allowed = (root.resolve(strict=True), *private_windows_paths(player))
    if rom.suffix.lower() == '.pc':
        # PartyDeck overlays the entire native .pc content directory.
        allowed += (rom.resolve(strict=True),)
    if (os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player)
            or not any(directory.is_relative_to(path) for path in allowed)):
        raise ValueError(tr('Story Co-op : espace privé du joueur requis.'))
    client = directory / 'soh.exe'
    if not client.is_file() or client.is_symlink():
        raise ValueError(tr('Story Co-op : soh.exe {p0} est requis dans le dossier du jeu.', p0=VERSION))
    if not any((directory / asset).is_file() for asset in ASSETS):
        raise ValueError(tr('Story Co-op : ouvrez d’abord le jeu en solo pour générer oot.o2r.'))
    if patch_client(client, options['automatic'], options.get('time_mode') == 'original'):
        print(tr('Story Co-op {p0} : correctifs du client appliqués.', p0=player.name.upper()), flush=True)
    index = int(player.name.removeprefix('j'))
    path = config_path(directory, CONFIG)
    source = config_path(directory, options['config'])
    data = json.loads(source.read_text(encoding='utf-8-sig')) if source.is_file() or source != path else {}
    cvars = data.setdefault('CVars', {})
    # Story Co-op 1.0.5 can spawn remote players in the title screen demo.
    graphics = cvars.setdefault('gSettings', {})
    graphics['BootSequence'] = 2  # BOOTSEQUENCE_FILESELECT
    # Unset sliders have the same defaults as the SoH common profile. Restore
    # them before applying a new mix so toggling J1-only music is reversible.
    graphics.setdefault('Volume', {}).update({key: 100 for key, _ in VOLUME_FIELDS})
    apply_graphics(data, options['graphics'], index - 1)
    camera_backup = config_path(directory, 'partydeck-freecam-original.json')
    restored_camera = configure_freecam(graphics, camera_backup, options.get('freecam', False), controller_template)
    # Keep using the same backup so profiles with active axis overrides migrate.
    settings_backup = config_path(directory, 'partydeck-camera-axes-original.json')
    saved_camera = configure_camera_settings(graphics, settings_backup, options.get('camera_axes', {}),
                                              options.get('camera_distance_mode', 'keep'),
                                              options.get('camera_distance', DEFAULT_DISTANCE),
                                              persistent=source == path)
    online = cvars.setdefault('gZeldaOnline', {})
    host, port = client_host(index), options['port']
    online.update(Enabled=1, AutoConnect=1, Host=host, Port=port, Nickname=options['names'][index - 1])
    skin = options['skins'][index - 1]
    if not skin:
        # The per-player configuration persists between sessions. Clear the
        # online skin so the regular game assets and installed mods apply.
        online['Skin'] = ''
    # The shared game LAN is offline. The launcher has already sourced and
    # verified the selected catalogue assets outside this namespace.
    online['FileServer'] = ''
    try:
        available = installed_skins(directory)
        references = {item.split('|', 1)[0] for item in available}
        skins.stage(options['skins'], skin_cache, directory, references)
        skins.stage_game_skin(os.environ.get('PARTYDECK_STORY_LOCAL_SKIN', ''), skin_cache, directory)
        if index == 1:
            atomic_write(player / 'story-skins.json', json.dumps(available))
        if skin == 'link' or (skin and skin.split('|', 1)[0] in references):
            skins.mask_link_overrides(directory, player)
            online['Skin'] = skin
        elif skin:
            print(tr('Story Co-op {p0} : skin {p1} introuvable, apparence actuelle conservée.',
                     p0=player.name.upper(), p1=skin), flush=True)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(tr('Story Co-op {p0} : préparation des skins ignorée ({p1}).',
                 p0=player.name.upper(), p1=error), flush=True)
    party = online.setdefault('Party', {})
    party['StoryCoop'] = int(options['sync'])
    party['StoryCode'] = options['room'] or party.get('StoryCode') or 'partydeck'
    token = os.environ.get('PARTYDECK_STORY_COOP', '')
    if options['automatic'] and index == 1 and re.fullmatch('[a-f0-9]{32}', token):
        settings = {
            'storyCoop': options['sync'],
            'storyCode': party['StoryCode'],
            'privateDungeons': bool(party.get('PrivateDungeons', 0)),
            'extraEnemies': bool(party.get('ExtraEnemies', 0)),
            'healthMultiplier': bool(party.get('HealthMultiplier', 0)),
            'shareAmmoRupeesHp': options['sync'] and bool(party.get('ShareAmmoRupeesHp', 0)),
        }
        for key in ('ExtraEnemyWeight', 'EnemyHealthWeight', 'BossHealthWeight'):
            value = party.get(key, 1.0)
            settings[key[0].lower() + key[1:]] = value if type(value) in (float, int) and 0 <= value <= 5 else 1.0
        atomic_write(session_config(player, token), json.dumps(settings))
    anchor = cvars.get('gRemote', {}).get('Anchor')
    if isinstance(anchor, dict):
        anchor['Enabled'] = 0
    window = data.setdefault('Window', {})
    window.setdefault('Fullscreen', {})['Enabled'] = False
    width = os.environ.get('PARTYDECK_PLAYER_WIDTH', '')
    height = os.environ.get('PARTYDECK_PLAYER_HEIGHT', '')
    if width.isdecimal() and height.isdecimal() and int(width) > 0 and int(height) > 0:
        window.update(Width=int(width), Height=int(height), PositionX=0, PositionY=0)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    if restored_camera:
        camera_backup.unlink(missing_ok=True)
    if saved_camera == {}:
        settings_backup.unlink(missing_ok=True)
    elif saved_camera is not None:
        atomic_write(settings_backup, json.dumps(saved_camera))
    print(tr('Story Co-op {p0} : démarrage au choix de la sauvegarde, connexion automatique à {p1}.',
             p0=player.name.upper(), p1=f'{host}:{port}'), flush=True)


def install_hook(base, rom, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import atomic_write, profile_path, read_profile

    if not os.environ.get('PARTYDECK_STORY_COOP') or not profile_path(base, rom).is_file():
        return
    if read_profile(base, rom).get('adapter') != ADAPTER:
        return
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    replacement = player / 'batocera-wine-story-coop'
    hook = [sys.executable, str(base / 'partydeck_story_coop.py'), '_client', str(base), str(player), str(rom)]
    atomic_write(replacement, instrument_native(binary.read_text(), hook, prefix_argument=True), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 7 and sys.argv[1] == '_client':
            from partydeck_profiles import read_profile
            base, player, rom, directory, root = map(Path, sys.argv[2:])
            skin_cache = base / 'dependencies' / ADAPTER / VERSION / 'skins'
            configure_client(player, rom, directory, root, read_profile(base, rom)[ADAPTER], skin_cache,
                             base / 'templates' / 'soh-common.json')
        else:
            parser = argparse.ArgumentParser(description=LABEL)
            parser.add_argument('source', type=Path)
            parser.add_argument('output', type=Path)
            args = parser.parse_args()
            prepare(args.source, args.output)
    except (OSError, RuntimeError, ValueError, AttributeError, TypeError, subprocess.SubprocessError) as error:
        print(f'Windows Party / Story Co-op : {error}', file=sys.stderr)
        raise SystemExit(1)
