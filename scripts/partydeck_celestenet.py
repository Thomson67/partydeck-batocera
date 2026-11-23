"""Run one CelesteNet server and join it from isolated Everest clients."""
import hashlib
import http.client
import ipaddress
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

from partydeck_borderlands2 import PRIVATE_BINDS, child, safe_path, write_bytes
from partydeck_i18n import tr

ADAPTER = 'celestenet'
PORT = 17230
DEBUG_PORT = 32270
SETTINGS_FILE = 'modsettings-CelesteNet.Client.celeste'
WIDE_ASSEMBLIES = ('Celeste.dll', 'MMHOOK_Celeste.dll')
SERVER_URL = ('https://github.com/0x0ade/CelesteNet/releases/download/v2.4.1-server/'
              'CelesteNet.Server-2024-09-23_fixed.zip')
SERVER_SHA256 = 'adad07a6f6aa3bd9b1c954daf6bf870802ff483afadb9fc22cc420f543b5ff4b'
RUNTIME_URL = 'https://builds.dotnet.microsoft.com/dotnet/Runtime/10.0.15/dotnet-runtime-10.0.15-linux-x64.tar.gz'
RUNTIME_SHA512 = ('a90177d75bc891f71aa814dde3bcf76a356f5a506824669f1891754457954a3d13b'
                  '72f3ca04c98fa0fe588514a5a781f8a87b17930ee802105c14f9edb28318a')


def matches(rom):
    return bool(re.search(r'(?<![a-z0-9])celeste(?![a-z0-9])', rom.stem.casefold()))


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


def patch_client_settings(data, player):
    if not data.strip():
        data = b'SettingsVersionDoNotEdit: 2\n'
    return patch_settings(data,{'Name':player.upper(), 'LoginMode':'Guest', 'ClientIDSending':'Off'})


def patch_settings(data, values):
    newline = b'\r\n' if b'\r\n' in data else b'\n'
    for key, value in values.items():
        line = f'{key}: {value}'.encode()
        pattern = rb'(?m)^' + key.encode() + rb':[ \t]*[^\r\n]*'
        data, count = re.subn(pattern, line, data)
        if not count:
            data = data.rstrip(b'\r\n') + (newline if data else b'') + line + newline
    return data


def configure_wide_view(directory, allowed, player, width, height):
    # Gamescope divides odd output dimensions with integer rounding.
    if min(width,height) < 1 or abs(9*width - 32*height) > 31:
        return
    variant = safe_path(child(directory,'PartyDeck-32x9'),allowed)
    fingerprint = safe_path(child(variant,'normal.sha256'),allowed)
    pairs = [(safe_path(child(variant,name),allowed),safe_path(child(directory,name),allowed))
             for name in WIDE_ASSEMBLIES]
    if not fingerprint.is_file() or not all(source.is_file() and target.is_file() for source,target in pairs):
        print(tr('CelesteNet {p0} : variante 32:9 absente ou incomplète ; rendu standard.',p0=player.upper()),flush=True)
        return
    with pairs[0][1].open('rb') as normal:
        actual = hashlib.file_digest(normal,'sha256').hexdigest()
    if actual != fingerprint.read_text(encoding='utf-8-sig').strip().lower():
        print(tr('CelesteNet {p0} : la variante 32:9 correspond à une autre installation Everest ; rendu standard.',
                 p0=player.upper()),flush=True)
        return
    # Both mounts exist inside the player's launch namespace only.
    for source,target in pairs:
        subprocess.run(['mount','--bind',str(source),str(target)],check=True)
    print(tr('CelesteNet {p0} : variante 32:9 activée ({p1}×{p2}).',
             p0=player.upper(),p1=width,p2=height),flush=True)


def configure_client(directory, prefix, player):
    allowed = tuple(path.resolve() for path in (prefix, player, *PRIVATE_BINDS))
    directory = safe_path(directory, allowed)
    if not child(directory,'Celeste.exe').is_file() or not child(directory,'Mods').is_dir():
        raise ValueError(tr('CelesteNet : lancez un Celeste.exe équipé d’Everest et de CelesteNet.'))
    configure_wide_view(directory, allowed, player.name,
                        int(os.environ.get('PARTYDECK_PLAYER_WIDTH','0')),
                        int(os.environ.get('PARTYDECK_PLAYER_HEIGHT','0')))
    saves = safe_path(child(directory,'Saves'),allowed)
    settings = safe_path(child(saves,SETTINGS_FILE), allowed)
    original = settings.read_bytes() if settings.is_file() else b''
    changed = patch_client_settings(original, player.name)
    if changed != original:
        backup = player/'celestenet-client-before.celeste'
        if original and not backup.exists():
            write_bytes(safe_path(backup, (player.resolve(),)), original)
        write_bytes(settings, changed)

    index = int(player.name[1:])-1
    core = safe_path(child(saves,'modsettings-Everest.celeste'),allowed)
    original_core = core.read_bytes() if core.is_file() else b''
    changed_core = patch_settings(original_core,{'DebugModeInEverest':'true',
                                                 'DebugRCPort':DEBUG_PORT+index})
    if changed_core != original_core:
        backup = safe_path(player/'celestenet-everest-before.celeste',(player.resolve(),))
        if original_core and not backup.exists():
            write_bytes(backup,original_core)
        write_bytes(core,changed_core)

    # The launch flag lives in the player's mount namespace for this run only.
    flags = safe_path(child(directory,'everest-launch.txt'), allowed)
    if not flags.exists():
        write_bytes(flags,b'')
    view = safe_path(player/'celestenet-everest-launch.txt', (player.resolve(),))
    write_bytes(view,flags.read_bytes().rstrip(b'\r\n') + b'\n--debug\n')
    subprocess.run(['mount','--bind',str(view),str(flags)],check=True)


def install_hook(base, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import atomic_write

    if os.environ.get('PARTYDECK_CELESTENET') != '1':
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
            configure_client(directory,prefix,player)
        elif action == '_join':
            join(*args)
        else:
            raise ValueError(action)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'Windows Party / CelesteNet: {error}',file=sys.stderr)
        raise SystemExit(1)
