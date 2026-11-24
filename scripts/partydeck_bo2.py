"""Prepare the installed Black Ops II client in each player's private view."""
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from partydeck_borderlands2 import child, decode, patch_ini, write_bytes
from partydeck_i18n import tr
from partydeck_l4d2 import ACCOUNT_MAX, STEAM64_BASE

ADAPTER = 'black-ops-2'
MODES = {'mp': 'Multijoueur', 'zm': 'Zombies', 'original': 'Lancement d’origine'}
EXECUTABLES = {'mp': 't6mp.exe', 'zm': 't6zm.exe'}


def matches(rom):
    return bool(re.search(r'\bblack[\s_-]*ops[\s_-]*(?:ii|2)\b|\bbo2\b', rom.stem.casefold()))


def defaults(rom=None):
    return {'mode': 'zm' if rom and re.search(r'\bzombies?\b', rom.stem.casefold()) else 'mp'}


def validate(data):
    if not isinstance(data, dict) or data.get('mode') not in tuple(MODES):
        raise ValueError(tr('Mode Black Ops II invalide.'))
    return {'mode': data['mode']}


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


def prepare(player, mode, directory, root):
    if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player):
        raise ValueError(tr('Black Ops II : espace privé du joueur requis.'))
    from partydeck_bottles import private_windows_paths

    directory, root = directory.resolve(strict=True), root.resolve(strict=True)
    allowed = (root, *private_windows_paths(player))
    if not any(directory.is_relative_to(path) for path in allowed):
        raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=directory))
    exe = find_game(directory, root, mode, allowed)
    client = configure_client(exe.parent if exe else directory, player)
    status = (tr('Black Ops II {p0} : profil privé {p1} appliqué.', p0=player.name.upper(), p1=client)
              if client else tr('Black Ops II : aucun client LAN reconnu dans le dossier du jeu.'))
    print(status, file=sys.stderr, flush=True)
    if mode != 'original':
        print(tr('Black Ops II {p0} : lancement de {p1}.', p0=player.name.upper(), p1=exe.name),
              file=sys.stderr, flush=True)
    return exe


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
        setup = (f'    local partydeck_bo2_exe\n'
                 f'    partydeck_bo2_exe=$({launch} "{root}/${{WINE_DIR}}" "{root}") || return 1\n')
        if mode != 'original':
            setup += '    printf -v WINE_CMD "%q +set r_fullscreen 0" "./${partydeck_bo2_exe##*/}"\n'
            body = pattern.sub('(cd "${partydeck_bo2_exe%/*}" && ', body)
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
    hook = [sys.executable, str(base / 'partydeck_bo2.py'), str(player)]
    replacement = player / 'batocera-wine-bo2'
    atomic_write(replacement, instrument_native(binary.read_text(), hook, profile['bo2']['mode']), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    player, mode, directory, root = sys.argv[1:]
    try:
        exe = prepare(Path(player), mode, Path(directory), Path(root))
        if exe is not None:
            print(exe)
    except (OSError, ValueError) as error:
        print(f'Windows Party / Black Ops II : {error}', file=sys.stderr)
        raise SystemExit(1)
