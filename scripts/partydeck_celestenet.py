"""Run one CelesteNet server and join it from isolated Everest clients."""
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from urllib.parse import urlencode
import zipfile
import xml.etree.ElementTree as ET

from partydeck_borderlands2 import PRIVATE_BINDS, child, safe_path, write_bytes
from partydeck_i18n import tr

ADAPTER = 'celestenet'
PORT = 17230
DEBUG_PORT = 32270
SETTINGS_FILE = 'modsettings-CelesteNet.Client.celeste'
LANGUAGES = {
    'keep': 'Conserver', 'french': 'Français', 'english': 'Anglais',
    'german': 'Allemand', 'spanish': 'Espagnol', 'italian': 'Italien',
    'japanese': 'Japonais', 'korean': 'Coréen', 'russian': 'Russe',
}
VARIANT_ASSEMBLIES = ('Celeste.dll', 'MMHOOK_Celeste.dll')
SERVER_URL = ('https://github.com/0x0ade/CelesteNet/releases/download/v2.4.1-server/'
              'CelesteNet.Server-2024-09-23_fixed.zip')
SERVER_SHA256 = 'adad07a6f6aa3bd9b1c954daf6bf870802ff483afadb9fc22cc420f543b5ff4b'
RUNTIME_URL = 'https://builds.dotnet.microsoft.com/dotnet/Runtime/10.0.15/dotnet-runtime-10.0.15-linux-x64.tar.gz'
RUNTIME_SHA512 = ('a90177d75bc891f71aa814dde3bcf76a356f5a506824669f1891754457954a3d13b'
                  '72f3ca04c98fa0fe588514a5a781f8a87b17930ee802105c14f9edb28318a')


def matches(rom):
    return bool(re.search(r'(?<![a-z0-9])celeste(?![a-z0-9])', rom.stem.casefold()))


def defaults():
    return dict(language='keep', skip_setup=True, automatic=True, music_j1_only=True,
                names=[f'J{index}' for index in range(1, 5)], skins=[''] * 4)


def validate(options):
    result = defaults()
    if options is not None:
        if not isinstance(options, dict):
            raise ValueError(tr('Options Celeste invalides.'))
        result.update({key: options[key] for key in result if key in options})
    if (result['language'] not in tuple(LANGUAGES)
            or any(type(result[key]) is not bool for key in ('skip_setup', 'automatic', 'music_j1_only'))):
        raise ValueError(tr('Options Celeste invalides.'))
    names = result['names']
    if (not isinstance(names, list) or len(names) != 4
            or any(not isinstance(name, str) or len(name.strip().encode('utf-16-le')) > 60
                   or any(not char.isprintable() for char in name) for name in names)):
        raise ValueError(tr('CelesteNet : les noms doivent faire au maximum 30 caractères imprimables.'))
    result['names'] = [name.strip() or f'J{index}' for index, name in enumerate(names, 1)]
    skins = result['skins']
    if (not isinstance(skins, list) or len(skins) != 4
            or any(not isinstance(skin, str) or len(skin) > 128
                   or any(not char.isprintable() for char in skin) for skin in skins)):
        raise ValueError(tr('Options Celeste invalides.'))
    return result


def viewport_variant(width, height):
    if min(width, height) <= 0:
        return None
    # Allow the rounding of a split viewport by up to a pixel.
    for horizontal in (32, 8):
        if abs(9 * width - horizontal * height) < max(horizontal, 9):
            return f'{horizontal}:9'
    return None


def download(path, url, algorithm, digest):
    with urllib.request.urlopen(url,timeout=30) as response, path.open('wb') as output:
        shutil.copyfileobj(response,output)
    with path.open('rb') as archive:
        if hashlib.file_digest(archive,algorithm).hexdigest() != digest:
            raise ValueError(tr('CelesteNet : empreinte de téléchargement invalide.'))


def prepare_dependencies(base):
    root = base/'dependencies'/'celestenet'
    runtime = root/'dotnet'/'dotnet'
    dotnet = str(runtime) if os.access(runtime, os.X_OK) else shutil.which('dotnet')
    server = root/'server'/'CelesteNet.Server.dll'
    if dotnet and server.is_file():
        return dotnet, server
    root.mkdir(parents=True, exist_ok=True)
    print(tr('CelesteNet : préparation du serveur local au premier lancement.'),flush=True)
    with tempfile.TemporaryDirectory(dir=root,prefix='.install-') as staging:
        staging = Path(staging)
        if not dotnet:
            archive = staging/'dotnet.tar.gz'
            download(archive,RUNTIME_URL,'sha512',RUNTIME_SHA512)
            unpacked = staging/'dotnet'
            unpacked.mkdir()
            with tarfile.open(archive) as package:
                package.extractall(unpacked,filter='data')
            unpacked.rename(runtime.parent)
            dotnet = str(runtime)
        if not server.is_file():
            archive = staging/'server.zip'
            download(archive,SERVER_URL,'sha256',SERVER_SHA256)
            with zipfile.ZipFile(archive) as package:
                package.extractall(staging)
            (staging/'net7.0').rename(server.parent)
    return dotnet, server


def stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def start_server(base, work, lan):
    dotnet, server = prepare_dependencies(base)
    work.mkdir(parents=True, exist_ok=True)
    modules = work/'Modules'
    modules.mkdir(exist_ok=True)
    chat = server.parent/'Modules'/'CelesteNet.Server.ChatModule.dll'
    if chat.is_file():
        shutil.copyfile(chat, modules/chat.name)
    write_bytes(work/'celestenet-config.yaml', f'MainPort: {PORT}\nNetPlusThreadPoolThreads: 6\n'.encode())
    log = work/'server.log'
    with log.open('wb') as output:
        process = subprocess.Popen(lan.prefix(0) + [dotnet, '--roll-forward', 'Major', str(server), '--nolog'],
                                   pass_fds=(lan.fds[0],), cwd=work, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   env=dict(os.environ, DOTNET_SYSTEM_GLOBALIZATION_INVARIANT='1'))
    try:
        deadline = time.monotonic() + 25
        with log.open('rb') as output:
            while process.poll() is None and time.monotonic() < deadline:
                if b'[main] Ready' in output.read():
                    print(tr('CelesteNet : serveur local prêt sur {p0}:{p1}.', p0=lan.address(0), p1=PORT), flush=True)
                    return process
                time.sleep(.15)
        raise RuntimeError(tr('CelesteNet : le serveur ne démarre pas. Consultez {p0}.', p0=log))
    except BaseException:
        stop(process)
        raise


def patch_client_settings(data, name):
    if not data.strip():
        data = b'SettingsVersionDoNotEdit: 2\n'
    return patch_settings(data,{'Name': json.dumps(name, ensure_ascii=False), 'LoginMode': 'Guest', 'ClientIDSending': 'Off'})


def patch_settings(data, values):
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    for key, value in values.items():
        line = f'{key}: {value}'.encode()
        pattern = rb'(?m)^' + key.encode() + rb':[ \t]*[^\r\n]*'
        data, count = re.subn(pattern, lambda _: line, data)
        if not count:
            data = data.rstrip(b'\r\n') + (newline if data else b'') + line + newline
    return data


def configure_viewport_variant(directory, allowed, player, width, height):
    ratio = viewport_variant(width, height)
    if ratio is None:
        return
    variant = safe_path(child(directory, f"PartyDeck-{ratio.replace(':', 'x')}"), allowed)
    fingerprint = safe_path(child(variant, 'normal.sha256'), allowed)
    pairs = [(safe_path(child(variant, name), allowed), safe_path(child(directory, name), allowed))
             for name in VARIANT_ASSEMBLIES]
    if not fingerprint.is_file() or not all(source.is_file() and target.is_file() for source, target in pairs):
        print(tr('CelesteNet {p0} : variante {p1} absente ou incomplète ; rendu standard.',
                 p0=player.upper(), p1=ratio), flush=True)
        return
    with pairs[0][1].open('rb') as normal:
        actual = hashlib.file_digest(normal, 'sha256').hexdigest()
    if actual != fingerprint.read_text(encoding='utf-8-sig').strip().lower():
        print(tr('CelesteNet {p0} : la variante {p1} correspond à une autre installation Everest ; rendu standard.',
                 p0=player.upper(), p1=ratio), flush=True)
        return
    with pairs[0][0].open('rb') as alternate:
        if hashlib.file_digest(alternate, 'sha256').hexdigest() == actual:
            print(tr('CelesteNet {p0} : la DLL de la variante {p1} est identique à la version standard.',
                     p0=player.upper(), p1=ratio), flush=True)
            return
    # Both mounts exist inside the player's launch namespace only.
    for source, target in pairs:
        subprocess.run(['mount', '--bind', str(source), str(target)], check=True)
    print(tr('CelesteNet {p0} : variante {p1} activée ({p2}×{p3}).',
             p0=player.upper(), p1=ratio, p2=width, p3=height), flush=True)


def patch_game_settings(data, language, debug):
    if not data.strip() and language == 'keep':
        return data
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(data, parser=parser) if data.strip() else ET.Element('Settings')
    if root.tag != 'Settings':
        raise ValueError(tr('Format de configuration Celeste non reconnu.'))
    changed = False
    if language != 'keep':
        field = root.find('Language')
        if field is None:
            field = ET.SubElement(root, 'Language')
        if field.text != language:
            field.text = language
            changed = True
    field = root.find('LaunchInDebugMode')
    if not debug and field is not None and field.text != 'false':
        field.text = 'false'
        changed = True
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) if changed else data


def player_skin_ids(data):
    # Skin Mod Helper Plus exposes selectable player skins as a top-level
    # list. Legacy mapping configs and general-only skins have no player slot.
    records = re.split(r'(?m)^-[ \t]+(?=[A-Za-z_]+[ \t]*:)', data.lstrip('\ufeff'))[1:]
    for record in records:
        fields = dict(re.findall(r'(?m)^[ \t]*(SkinName|Player_List|Character_ID):[ \t]*(.*?)[ \t]*$', record))
        if fields.get('Player_List', '').split('#', 1)[0].strip().lower() != 'true' or not fields.get('Character_ID'):
            continue
        name = fields.get('SkinName', '').split(' #', 1)[0].strip()
        if name.startswith('"'):
            try:
                name = json.loads(name)
            except ValueError:
                continue
        elif len(name) >= 2 and name[0] == name[-1] == "'":
            name = name[1:-1].replace("''", "'")
        if (isinstance(name, str) and 0 < len(name) <= 128 and name.isprintable()
                and not name.endswith(('_', '_lantern', '_lantern_NB'))
                and name.casefold() not in ('original', 'default')):
            yield name


def installed_skins(mods):
    names = set()
    config_names = ('SkinModHelperConfig.yaml', 'SkinModHelperConfig.yml')
    if not mods.is_dir():
        return []
    for mod in mods.iterdir():
        if mod.is_symlink():
            continue
        try:
            if mod.is_dir():
                for config in config_names:
                    path = mod/config
                    if path.is_file() and not path.is_symlink() and path.stat().st_size <= 131072:
                        names.update(player_skin_ids(path.read_text(encoding='utf-8-sig')))
            elif mod.suffix.casefold() == '.zip' and mod.is_file():
                with zipfile.ZipFile(mod) as archive:
                    for config in config_names:
                        try:
                            info = archive.getinfo(config)
                        except KeyError:
                            continue
                        if info.file_size <= 131072:
                            names.update(player_skin_ids(archive.read(info).decode('utf-8-sig')))
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
            continue
    return sorted(names, key=lambda name: (name.casefold(), name))


def skin_choices(base, rom):
    if rom.is_dir():
        excluded = {'windows', 'users', 'saves', 'mods', 'content', 'dosdevices', 'orig',
                    'piton-runtime', 'backups'}
        for index, (folder, directories, files) in enumerate(os.walk(rom, followlinks=False)):
            if index >= 200:
                break
            root = Path(folder)
            if any(name.casefold() == 'celeste.exe' for name in files):
                mods = next((root/name for name in directories if name.casefold() == 'mods'), None)
                if mods is not None:
                    return installed_skins(mods)
            depth = len(root.relative_to(rom).parts)
            directories[:] = [name for name in directories if depth < 4 and name.casefold() not in excluded]
    from partydeck_storage import identity
    identifier, _ = identity(rom)
    cached = base/'runtime'/identifier/'j1'/'celeste-skins.json'
    try:
        names = json.loads(cached.read_text(encoding='utf-8'))
        if isinstance(names, list) and all(isinstance(name, str) for name in names):
            return names
    except (OSError, ValueError):
        pass
    return []


def configure_client(directory, prefix, player, options, lan=False):
    allowed = tuple(path.resolve() for path in (prefix, player, *PRIVATE_BINDS))
    directory = safe_path(directory, allowed)
    if not child(directory,'Celeste.exe').is_file() or not child(directory,'Mods').is_dir():
        raise ValueError(tr('CelesteNet : lancez un Celeste.exe équipé d’Everest et de CelesteNet.'))
    if lan:
        configure_viewport_variant(directory, allowed, player.name,
                                   int(os.environ.get('PARTYDECK_PLAYER_WIDTH', '0')),
                                   int(os.environ.get('PARTYDECK_PLAYER_HEIGHT', '0')))
    saves = safe_path(child(directory,'Saves'),allowed)
    if lan:
        settings = safe_path(child(saves, SETTINGS_FILE), allowed)
        original = settings.read_bytes() if settings.is_file() else b''
        changed = patch_client_settings(original, options['names'][int(player.name[1:]) - 1])
        if changed != original:
            backup = safe_path(player/'celestenet-client-before.celeste', (player.resolve(),))
            if original and not backup.exists():
                write_bytes(backup, original)
            write_bytes(settings, changed)

    try:
        if lan:
            chosen_skin = options['skins'][int(player.name[1:]) - 1]
            if player.name == 'j1' or chosen_skin:
                skins = installed_skins(safe_path(child(directory, 'Mods'), allowed))
                if player.name == 'j1':
                    cache = safe_path(player/'celeste-skins.json', (player.resolve(),))
                    if cache.exists() or skins:
                        write_bytes(cache, json.dumps(skins, ensure_ascii=False).encode('utf-8'))
                if chosen_skin in skins or (skins and chosen_skin == 'Original'):
                    path = safe_path(child(saves, 'modsettings-SkinModHelperPlus.celeste'), allowed)
                    original_skin = path.read_bytes() if path.is_file() else b''
                    updated_skin = patch_settings(original_skin, {
                        'SelectedPlayerSkin': json.dumps(chosen_skin, ensure_ascii=False)
                    })
                    if updated_skin != original_skin:
                        write_bytes(path, updated_skin)
                elif chosen_skin:
                    print(tr('CelesteNet {p0} : skin introuvable : {p1}',
                             p0=player.name.upper(), p1=chosen_skin), flush=True)
    except (OSError, ValueError) as error:
        print(tr('Celeste {p0} : options de démarrage ignorées : {p1}', p0=player.name.upper(), p1=error),
              flush=True)
    try:
        configure_startup(directory, saves, allowed, player, options,
                          debug=lan and options['automatic'],
                          mute_music=lan and options['music_j1_only'] and player.name != 'j1')
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(tr('Celeste {p0} : options de démarrage ignorées : {p1}', p0=player.name.upper(), p1=error),
              flush=True)


def configure_music(game, backup, mute):
    if not mute and not backup.is_file():
        return
    data = game.read_bytes() if game.is_file() else b''
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(data, parser=parser) if data.strip() else ET.Element('Settings')
    if root.tag != 'Settings':
        raise ValueError(tr('Format de configuration Celeste non reconnu.'))
    music = root.find('MusicVolume')
    current = music.text if music is not None else None
    if mute:
        if current == '0':
            return
        # Persist the volume before muting so retries keep the user's value.
        if not backup.exists():
            write_bytes(backup, json.dumps(current).encode('utf-8'))
        if music is None:
            music = ET.SubElement(root, 'MusicVolume')
        music.text = '0'
    elif current == '0':
        previous = json.loads(backup.read_text(encoding='utf-8'))
        if previous is None:
            root.remove(music)
        elif isinstance(previous, str) and previous.isdecimal() and int(previous) <= 10:
            music.text = previous
        else:
            raise ValueError(tr('Format de configuration Celeste non reconnu.'))
    else:
        # Keep any volume changed by the player since muting.
        backup.unlink()
        return
    write_bytes(game, ET.tostring(root, encoding='utf-8', xml_declaration=True))
    if not mute:
        backup.unlink()


def configure_startup(directory, saves, allowed, player, options, *, debug, mute_music):
    game = safe_path(child(saves, 'settings.celeste'), allowed)
    original_game = game.read_bytes() if game.is_file() else b''
    try:
        changed_game = patch_game_settings(original_game, options['language'], debug)
        if changed_game != original_game:
            write_bytes(game, changed_game)
        music_backup = safe_path(game.with_name('partydeck-celeste-music.json'), allowed)
        configure_music(game, music_backup, mute_music)
    except (ET.ParseError, ValueError):
        print(tr('Celeste : configuration du jeu illisible, fichier conservé.'), flush=True)

    core = safe_path(child(saves, 'modsettings-Everest.celeste'), allowed)
    original_core = core.read_bytes() if core.is_file() else b''
    values = {'DebugModeInEverest': str(debug).lower()}
    if debug:
        values['DebugRCPort'] = DEBUG_PORT + int(player.name[1:]) - 1
    if options['skip_setup']:
        values['AutoUpdateModsOnStartup'] = 'false'
    # Remove the first-run placeholder from the previous PartyDeck build.
    # An actual version written by Everest is kept.
    restored_core = re.sub(rb"(?m)^CurrentVersion:[ \t]*'0\.0\.0'[ \t]*(?:\r?\n|$)", b'', original_core)
    changed_core = patch_settings(restored_core, values)
    if changed_core != original_core:
        backup = safe_path(player/'celestenet-everest-before.celeste', (player.resolve(),))
        if original_core and not backup.exists():
            write_bytes(backup, original_core)
        write_bytes(core, changed_core)

    # Override the launch flags in this player's mount namespace only.
    flags = safe_path(child(directory, 'everest-launch.txt'), allowed)
    original_flags = flags.read_bytes() if flags.is_file() else b''
    changed_flags = b''.join(
        line if line.lstrip().startswith(b'#') else re.sub(rb'(?<!\S)--debug(?!\S)', b'', line)
        for line in original_flags.splitlines(keepends=True)
    )
    if debug:
        changed_flags = changed_flags.rstrip(b'\r\n') + b'\n--debug\n'
    if changed_flags != original_flags:
        if not flags.exists():
            write_bytes(flags, b'')
        view = safe_path(player/'celestenet-everest-launch.txt', (player.resolve(),))
        write_bytes(view, changed_flags)
        subprocess.run(['mount', '--bind', str(view), str(flags)], check=True)


def install_hook(base, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import atomic_write

    if 'PARTYDECK_CELESTE_OPTIONS' not in os.environ:
        return
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    replacement = player/'batocera-wine-celestenet'
    hook = [sys.executable, str(base/'partydeck_celestenet.py'), '_prepare', str(player)]
    atomic_write(replacement, instrument_native(binary.read_text(),hook,prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)


def request_console(port, query=''):
    connection = http.client.HTTPConnection('localhost',port,timeout=2)
    try:
        connection.request('GET','/console'+query)
        response = connection.getresponse()
        return response.read(512*1024) if response.status == 200 else None
    finally:
        connection.close()


def join(address, player, timeout=150):
    ip = ipaddress.IPv4Address(address)
    endpoint = 'localhost' if ip.is_loopback else f'{ip}:{PORT}'
    port = DEBUG_PORT+int(player[1:])-1
    deadline = time.monotonic() + timeout
    console_seen = False
    while time.monotonic() < deadline:
        try:
            # The documented console listing advertises the CelesteNet command
            # only after the mod and Everest title screen have initialized.
            commands = request_console(port)
            console_seen |= commands is not None
            if b'<h3>con</h3>' in (commands or b'') and request_console(
                    port,'?' + urlencode({'command':'con '+endpoint})) is not None:
                print(tr('CelesteNet {p0} : connexion demandée vers {p1}.',p0=player.upper(),p1=endpoint),flush=True)
                return
        except (OSError,http.client.HTTPException):
            pass
        time.sleep(.5)
    if console_seen:
        print(tr('CelesteNet {p0} : la console Everest répond, mais la commande con manque.',
                 p0=player.upper()),flush=True)
    else:
        print(tr('CelesteNet {p0} : console Everest inaccessible sur le port {p1}.',
                 p0=player.upper(),p1=port),flush=True)


def start_join(lan, index):
    return subprocess.Popen(lan.prefix(0) + [sys.executable,__file__,'_join',lan.address(0),f'j{index+1}'],
                            pass_fds=(lan.fds[0],),stdin=subprocess.DEVNULL)


if __name__ == '__main__':
    try:
        action, *args = sys.argv[1:]
        if action == '_prepare':
            player, directory, prefix = map(Path,args)
            if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player):
                raise ValueError(tr('Contexte de connexion automatique invalide.'))
            options = validate(json.loads(os.environ['PARTYDECK_CELESTE_OPTIONS']))
            configure_client(directory, prefix, player, options, os.environ.get('PARTYDECK_CELESTENET') == '1')
        elif action == '_join':
            join(*args)
        else:
            raise ValueError(action)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Windows Party / CelesteNet: {error}',file=sys.stderr)
        raise SystemExit(1)
