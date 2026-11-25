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

from partydeck_i18n import tr

ADAPTER = 'ocarina-story-coop'
LABEL = 'Ocarina of Time · Story Co-op'
VERSION = 'v1.0.5'
PORT = 21050
GAME_DIR = Path('drive_c/game')
SERVER_DIR = 'PartyDeck-Story-Coop'
ASSETS = ('oot.o2r', 'oot-mq.o2r')
RELEASE = f'https://github.com/cranebeaker/ocarina-coop/releases/download/{VERSION}/'
WINDOWS_ARCHIVE = f'OcarinaStoryCoop-{VERSION}-windows.zip'
LINUX_ARCHIVE = f'OcarinaStoryCoop-{VERSION}-linux.tar.gz'
WINDOWS_DIGEST = '0e5bd2ddaf61bf1707ae8ee23c396c272733bfd7478fbfc8add35957c64f8742'
LINUX_DIGEST = '4a305e237487d628be52afcc3e554ad4b5551bdfc0442ece6f8d05f8b36ace60'
CLIENT_DIGEST = 'ef4470bbe7b7c7277662438190177ab9045fed3e61e77f3ecfa92a75028f5377'
SERVER_FILES = {
    'OOTServer': 'f1ce1e80bdff661fa17316080b616bab5b8e6f380164c2326f4fc08fde3c2b57',
    'config.json': '0b43c81bbc154e19a002f175d9b8a2fdb58ed7834f9d0dd277e1f7fc39dbae5f',
}


def matches(rom):
    name = rom.stem.casefold()
    return ('ocarinastorycoop' in name or
            (bool(re.search(r'ocarina|ship[\s_-]*of[\s_-]*harkinian|\bsoh\b', name))
             and bool(re.search(r'story[\s_-]*co[\s_-]*op', name))))


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
        with tarfile.open(linux) as package:
            for name in SERVER_FILES:
                member = f'OcarinaStoryCoop-{VERSION}-linux/server/{name}'
                with package.extractfile(member) as stream, (server / name).open('wb') as copied:
                    shutil.copyfileobj(stream, copied)
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


def bundled_server_files(rom):
    relative = Path(SERVER_DIR) if rom.suffix.lower() == '.pc' else GAME_DIR / SERVER_DIR
    for name, checksum in SERVER_FILES.items():
        member = relative / name
        try:
            if rom.suffix.lower() == '.wsquashfs':
                data = subprocess.run(['unsquashfs', '-cat', str(rom), str(member)], check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout
            else:
                data = (rom / member).read_bytes()
        except (OSError, subprocess.SubprocessError) as error:
            raise RuntimeError(tr('Serveur Story Co-op introuvable dans {p0} ({p1}).',
                                  p0=rom.name, p1=member)) from error
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError(tr('Fichier serveur Story Co-op {p0} invalide : {p1}.', p0=VERSION, p1=name))
        yield name, data


def stop_server(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def start_server(rom, work, lan):
    from partydeck_borderlands2 import write_bytes
    work.mkdir(parents=True, exist_ok=True)
    program = work / 'OOTServer'
    for name, data in bundled_server_files(rom):
        path = work / name
        if path.is_symlink():
            raise ValueError(tr('Le fichier est un lien symbolique : {p0}', p0=path))
        if not path.is_file() or path.read_bytes() != data:
            write_bytes(path, data)
    program.chmod(0o700)
    log = work / 'server.log'
    with log.open('wb') as output:
        process = subprocess.Popen([*lan.prefix(0), str(program), '--port', str(PORT)],
                                   pass_fds=(lan.fds[0],), cwd=work, stdin=subprocess.DEVNULL,
                                   stdout=output, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 10
        with log.open('rb') as output:
            marker = f'OOTServer: listening on port {PORT}'.encode()
            while process.poll() is None and time.monotonic() < deadline:
                if any(marker in line for line in output):
                    print(tr('Story Co-op : serveur local prêt sur {p0}:{p1}.',
                             p0=lan.address(0), p1=PORT), flush=True)
                    return process
                time.sleep(.15)
        raise RuntimeError(tr('Story Co-op : le serveur ne démarre pas. Consultez {p0}.', p0=log))
    except BaseException:
        stop_server(process)
        raise


def configure_client(player, rom, directory, root):
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
    if not client.is_file() or digest(client) != CLIENT_DIGEST:
        raise ValueError(tr('Story Co-op : soh.exe {p0} est requis dans le dossier du jeu.', p0=VERSION))
    if not any((directory / asset).is_file() for asset in ASSETS):
        raise ValueError(tr('Story Co-op : ouvrez d’abord le jeu en solo pour générer oot.o2r.'))
    path = directory / 'shipofharkinian.json'
    if path.is_symlink():
        raise ValueError(tr('Le fichier est un lien symbolique : {p0}', p0=path))
    data = json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    cvars = data.setdefault('CVars', {})
    online = cvars.setdefault('gZeldaOnline', {})
    address = f'127.0.0.1:{PORT}'
    online.update(Enabled=1, AutoConnect=1, Host='127.0.0.1', Port=PORT, Nickname=player.name.upper())
    party = online.setdefault('Party', {})
    party['StoryCoop'] = 1
    party['StoryCode'] = party.get('StoryCode') or 'partydeck'
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
    print(tr('Story Co-op {p0} : connexion automatique à {p1}.',
             p0=player.name.upper(), p1=address), flush=True)


def install_hook(base, rom, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import atomic_write, profile_path, read_profile

    if (os.environ.get('PARTYDECK_STORY_COOP') != '1' or not profile_path(base, rom).is_file()
            or read_profile(base, rom).get('adapter') != ADAPTER):
        return
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    replacement = player / 'batocera-wine-story-coop'
    hook = [sys.executable, str(base / 'partydeck_story_coop.py'), '_client', str(player), str(rom)]
    atomic_write(replacement, instrument_native(binary.read_text(), hook, prefix_argument=True), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    try:
        if len(sys.argv) == 6 and sys.argv[1] == '_client':
            configure_client(*(Path(value) for value in sys.argv[2:]))
        else:
            parser = argparse.ArgumentParser(description=LABEL)
            parser.add_argument('source', type=Path)
            parser.add_argument('output', type=Path)
            args = parser.parse_args()
            prepare(args.source, args.output)
    except (OSError, RuntimeError, ValueError, AttributeError, TypeError, subprocess.SubprocessError) as error:
        print(f'Windows Party / Story Co-op : {error}', file=sys.stderr)
        raise SystemExit(1)
