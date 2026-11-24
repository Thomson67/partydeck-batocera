"""Prepare the installed Black Ops II client in each player's private view."""
import hashlib
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from partydeck_borderlands2 import child, decode, patch_ini, write_bytes
from partydeck_i18n import tr
from partydeck_l4d2 import ACCOUNT_MAX, STEAM64_BASE

ADAPTER = 'black-ops-2'
MODES = {
    'plutonium-mp': 'Multijoueur · Plutonium LAN',
    'plutonium-zm': 'Zombies · Plutonium LAN',
    'original': 'Lancement d’origine',
}
EXECUTABLES = {'mp': 't6mp.exe', 'zm': 't6zm.exe'}
PLUTONIUM_MODES = {'plutonium-mp': 't6mp', 'plutonium-zm': 't6zm'}
BOOTSTRAPPER = 'plutonium-bootstrapper-win32.exe'
HOST_PORT = 1111
JOIN_HOST = f'connect 192.168.247.11:{HOST_PORT}'
DEFAULT_RENDER_SIZE = (1280, 720)


def render_size(width, height):
    if width >= 1280 and height >= 720 and width * 9 == height * 16:
        return width, height
    return DEFAULT_RENDER_SIZE


def display_arguments():
    width, height = DEFAULT_RENDER_SIZE
    resolution = os.environ.get('PARTYDECK_BO2_RESOLUTION', f'{width}x{height}')
    return ['+set', 'r_fullscreen', '2', '+set', 'r_mode', resolution]



def matches(rom):
    return bool(re.search(r'\bblack[\s_-]*ops[\s_-]*(?:ii|2)\b|\bbo2\b', rom.stem.casefold()))


def defaults(rom=None):
    mode = 'plutonium-zm' if rom and re.search(r'\bzombies?\b', rom.stem.casefold()) else 'plutonium-mp'
    return {'mode': mode}


def validate(data):
    mode = data.get('mode') if isinstance(data, dict) else None
    if mode in ('mp', 'zm'):
        mode = f'plutonium-{mode}'
    if mode not in tuple(MODES):
        raise ValueError(tr('Mode Black Ops II invalide.'))
    return {'mode': mode}


def private_child(directory, name):
    path = child(directory, name)
    if path.is_symlink():
        raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=path))
    return path


def find_game(directory, root, mode, allowed):
    names = (EXECUTABLES[mode],) if mode in EXECUTABLES else tuple(EXECUTABLES.values())

    def search(folder):
        for name in names:
            exe = private_child(folder, name)
            if exe.is_file():
                return exe
        return None

    exe = search(directory)
    if exe is not None:
        return exe
    game = child(child(root, 'drive_c'), 'game').resolve()
    if any(game.is_relative_to(path) for path in allowed):
        exe = search(game)
        if exe is not None:
            return exe
    exe = search(root)
    if exe is not None:
        return exe
    if mode == 'original':
        return None
    raise ValueError(tr('Black Ops II : {p0} introuvable. Vérifiez DIR dans autorun.cmd ou essayez le lancement d’origine.',
                        p0=names[0]))


def identity(player):
    if player.name not in ('j1', 'j2', 'j3', 'j4'):
        raise ValueError(tr('Black Ops II : joueur privé invalide.'))
    index = int(player.name[1:]) - 1
    digest = hashlib.sha256(os.fsencode(player.parent)).digest()
    account = int.from_bytes(digest[:8], 'big') % (ACCOUNT_MAX // 4) * 4 + index + 1
    return account, STEAM64_BASE + account, f'Player {index + 1}'


def configure_client(directory, player):
    account, steamid, name = identity(player)
    ayria = private_child(directory, 'Ayria')
    plugins = private_child(ayria, 'Plugins')
    if private_child(plugins, 'Localnetworking.Ayria32').is_file():
        platform = private_child(private_child(ayria, 'Assets'), 'Platformwrapper')
        platform.mkdir(parents=True, exist_ok=True)
        write_bytes(private_child(platform, 'Username.txt'), f'{name}\r\n'.encode())
        nova_id = 11111110 + (account - 1) % 100000000
        write_bytes(private_child(platform, 'UserID.txt'), f'{nova_id}\r\n'.encode())
        return 'Project Nova'

    settings = private_child(directory, 'steam_settings')
    if not settings.is_dir():
        return None
    ini = private_child(settings, 'configs.user.ini')
    legacy = {private_child(settings, 'force_steamid.txt'): str(steamid),
              private_child(settings, 'force_account_name.txt'): name}
    modern = ini.is_file() or private_child(settings, 'configs.main.ini').is_file()
    if modern:
        before, encoding = decode(ini.read_bytes() if ini.is_file() else b'')
        after = patch_ini(before, {'user::general': {'account_steamid': str(steamid), 'account_name': name}})
        if after != before or not ini.is_file():
            write_bytes(ini, after.encode(encoding))
    for path, value in legacy.items():
        if not modern or path.exists():
            write_bytes(path, f'{value}\n'.encode())
    return 'Goldberg'


def prepare(player, mode, directory, root, plutonium_source):
    if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player):
        raise ValueError(tr('Black Ops II : espace privé du joueur requis.'))
    from partydeck_bottles import private_windows_paths

    directory, root = directory.resolve(strict=True), root.resolve(strict=True)
    allowed = (root, *private_windows_paths(player))
    if not any(directory.is_relative_to(path) for path in allowed):
        raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=directory))
    plutonium_mode = PLUTONIUM_MODES.get(mode)
    game_mode = plutonium_mode[2:] if plutonium_mode else mode
    exe = find_game(directory, root, game_mode, allowed)
    if plutonium_mode:
        return prepare_plutonium(player, exe.parent, root, plutonium_source, plutonium_mode)

    client = configure_client(exe.parent if exe else directory, player)
    status = (tr('Black Ops II {p0} : profil privé {p1} appliqué.', p0=player.name.upper(), p1=client)
              if client else tr('Black Ops II : aucun client LAN reconnu dans le dossier du jeu.'))
    print(status, file=sys.stderr, flush=True)
    return None, None


def copy_client_files(source, destination, *, sync):
    destination.mkdir(exist_ok=True)
    for entry in source.iterdir():
        target = private_child(destination, entry.name)
        if entry.is_symlink():
            raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=entry))
        if entry.is_dir():
            copy_client_files(entry, target, sync=sync)
        elif entry.is_file() and (not target.is_file() or
                                 (sync and (target.stat().st_size, target.stat().st_mtime_ns)
                                  != (entry.stat().st_size, entry.stat().st_mtime_ns))):
            with tempfile.NamedTemporaryFile(dir=destination, prefix='.plutonium-', delete=False) as stream:
                temporary = Path(stream.name)
            try:
                shutil.copy2(entry, temporary)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)


def windows_game_path(game, root):
    drive = child(root, 'drive_c').resolve()
    if game.is_relative_to(drive):
        # The UMU wrapper preserves the drive_c game path when it builds its
        # materialized prefix. The original Linux mount path can disappear.
        return str(PureWindowsPath('C:/', *game.relative_to(drive).parts))
    return str(PureWindowsPath('Z:/', *game.parts[1:]))


def prepare_plutonium(player, game, root, source, mode):
    binaries = private_child(source, 'bin')
    games = private_child(source, 'games')
    bootstrapper = private_child(binaries, BOOTSTRAPPER)
    if not (bootstrapper.is_file() and private_child(games, f'{mode}.exe').is_file()):
        raise ValueError(tr('Black Ops II : copiez bin et games de Plutonium dans {p0}.', p0=source))
    bink = private_child(game, 'binkw32.dll')
    if not bink.is_file():
        raise ValueError(tr('Black Ops II : binkw32.dll introuvable dans {p0}.', p0=game))
    if b'_BinkWaitStopAsyncThread@4\0' not in bink.read_bytes():
        print(tr('Black Ops II : symbole Bink attendu absent de {p0}. Vérifiez les fichiers du jeu.',
                 p0=bink), file=sys.stderr, flush=True)
    game_path = windows_game_path(game, root)

    # Put the executable inside the private game view so UMU can relocate
    # the executable and its working directory together into Proton.
    runtime = private_child(game, '.partydeck-plutonium')
    runtime.mkdir(exist_ok=True)
    for folder in (binaries, games):
        copy_client_files(folder, private_child(runtime, folder.name), sync=True)
    storage = private_child(source, 'storage')
    if storage.is_dir():
        copy_client_files(storage, private_child(runtime, storage.name), sync=False)

    _, _, name = identity(player)
    port = HOST_PORT + int(player.name[1:]) - 1
    args = [f'./{binaries.name}/{bootstrapper.name}',
            mode, game_path, '+name', name, '-lan', *display_arguments(),
            '+set', 'net_port', str(port)]
    if mode == 't6zm' and player.name == 'j1':
        count = os.environ.get('PARTYDECK_SESSION_PLAYERS', '1')
        if count in ('1', '2', '3', '4'):
            args += ['+set', 'sp_minplayers', count]
    if player.name != 'j1':
        print(tr('Black Ops II {p0} : rejoindre J1 avec {p1}.', p0=player.name.upper(),
                 p1=JOIN_HOST), file=sys.stderr, flush=True)
    print(tr('Black Ops II {p0} : Plutonium LAN ({p1}, port {p2}).',
             p0=player.name.upper(), p1=mode, p2=port), file=sys.stderr, flush=True)
    print(tr('Black Ops II : dossier transmis à Plutonium {p0}.', p0=game_path), file=sys.stderr, flush=True)
    return runtime, shlex.join(args)


def instrument_native(source, hook, mode):
    """Keep Batocera's mounts, Wine setup and runner choice for all ROM types."""
    pattern = re.compile(r'(\(cd "(\$\{(?:WINEPOINT|GAMENAME)\})/\$\{WINE_DIR\}" && )')
    parts = re.split(r'(?m)^(?=[a-zA-Z_][a-zA-Z_0-9]*\(\) \{)', source)
    launch = shlex.join(hook + [mode])
    for name in ('play_wine', 'play_pc', 'play_squashfs'):
        indices = [i for i, part in enumerate(parts) if part.startswith(name + '() {')]
        if len(indices) != 1:
            raise RuntimeError(tr('Lanceur batocera-wine non reconnu ({p0}) : adaptateur de jeu refusé.', p0=name))
        index = indices[0]
        body = parts[index]
        calls = list(pattern.finditer(body))
        marker = '    if [[ -n "${WINE_LANG}" ]]; then'
        if (len(calls) != 2 or calls[0][2] != calls[1][2] or body.count(marker) != 1
                or body.index(marker) > calls[0].start()):
            raise RuntimeError(tr('Lanceur batocera-wine non reconnu ({p0}) : adaptateur de jeu refusé.', p0=name))
        root = calls[0][2]
        setup = ('    local partydeck_bo2_launch partydeck_bo2_cwd\n'
                 f'    partydeck_bo2_launch=$({launch} "{root}/${{WINE_DIR}}" "{root}") || return 1\n')
        if mode != 'original':
            setup += ("    partydeck_bo2_cwd=${partydeck_bo2_launch%%$'\\n'*}\n"
                      "    WINE_CMD=${partydeck_bo2_launch#*$'\\n'}\n")
            body = pattern.sub('(cd "${partydeck_bo2_cwd}" && ', body)
        parts[index] = body.replace(marker, setup + marker)
    return ''.join(parts)


def install_hook(base, rom, player):
    from partydeck_profiles import atomic_write, profile_path, read_profile

    if not profile_path(base, rom).exists():
        return
    profile = read_profile(base, rom)
    if profile.get('adapter') != ADAPTER:
        return
    binary = shutil.which('batocera-wine')
    if binary is None:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    hook = [sys.executable, str(base / 'partydeck_bo2.py'), str(player), str(base / 'plutonium')]
    replacement = player / 'batocera-wine-bo2'
    atomic_write(replacement, instrument_native(binary.read_text(), hook, profile['bo2']['mode']), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    player, source, mode, directory, root = sys.argv[1:]
    try:
        mode = validate({'mode': mode})['mode']
        cwd, command = prepare(Path(player), mode, Path(directory), Path(root), Path(source))
        if cwd is not None:
            if '\n' in str(cwd):
                raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=cwd))
            print(cwd, command, sep='\n')
    except (OSError, ValueError) as error:
        print(f'Windows Party / Black Ops II : {error}', file=sys.stderr)
        raise SystemExit(1)
