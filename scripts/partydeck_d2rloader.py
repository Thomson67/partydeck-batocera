"""D2RLoader in PartyDeck's per-player Wine views."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from tempfile import mkdtemp
from urllib.request import urlopen
from zipfile import ZipFile

from partydeck_borderlands2 import child, patch_ini, write_bytes
from partydeck_bottles import private_windows_paths
from partydeck_i18n import tr
from partydeck_l4d2 import safe_path


ADAPTER = 'd2rloader'
LABEL = 'Diablo II: Resurrected · D2RLoader LAN'
PORT = 4000
PLUGIN = 'd2rl-partydeck-lan.dll'
CORE_131 = '2a868d013d2e0830bd2d9e04b918b19e46a73cf726c833e70d089b948fdeb5a2'
ULTRAWIDE_PLUGIN = 'Ultrawide.dll'
ULTRAWIDE_LOADER = '93021dad48533bcfca8a95c69a0cc00cdb9008a3ce6ceba1d04c7aca71985a10'
ULTRAWIDE_RELEASE = ('https://github.com/Pyre-Flies/D2R-Mods/releases/download/'
                     'ultrawide-1.3.5%2Brev.3/Ultrawide-1.3.5%2Brev.3-PyreFly.zip')
ULTRAWIDE_SIZE = 2273420
ULTRAWIDE_SHA256 = '7f8d57adca250c3f1badbdc7cc01b439ca86057faa6cf20aab404e3a6214363b'


def matches(rom):
    name = re.sub(r'[^a-z0-9]', '', rom.stem.casefold())
    return name.startswith('d2r') or 'diabloiiresurrected' in name or 'diablo2resurrected' in name


def defaults():
    return {'automatic': True, 'horizontal_ultrawide': False}


def validate(options):
    if options is None:
        return defaults()
    if not isinstance(options, dict):
        raise ValueError(tr('Réglages D2RLoader invalides.'))
    values = {key: options.get(key, default) for key, default in defaults().items()}
    if any(type(value) is not bool for value in values.values()):
        raise ValueError(tr('Réglages D2RLoader invalides.'))
    return values


def ultrawide_mode(width, height):
    if width * 9 <= height * 19:
        return None
    render_height = max(height, 720)
    render_width = min(width * render_height // height, render_height * 32 // 9)
    return render_width, render_height


def ultrawide_archive(base):
    return base / 'dependencies' / 'd2rloader-ultrawide-1.3.5-rev.3.zip'


def prepare_ultrawide(base):
    archive = ultrawide_archive(base)
    if archive.is_file() and archive.stat().st_size == ULTRAWIDE_SIZE:
        with archive.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() == ULTRAWIDE_SHA256:
                return
    print(tr('Diablo II : téléchargement du plugin Ultrawide de PyreFly.'), flush=True)
    with urlopen(ULTRAWIDE_RELEASE, timeout=20) as source:
        data = source.read(ULTRAWIDE_SIZE + 1)
    if len(data) != ULTRAWIDE_SIZE or hashlib.sha256(data).hexdigest() != ULTRAWIDE_SHA256:
        raise ValueError('Invalid PyreFly Ultrawide archive')
    write_bytes(archive, data)


def install_ultrawide(loader_dir, path, plugins, archive):
    settings = path(path(loader_dir, 'config'), 'ultrawide.toml')
    if not settings.exists():
        write_bytes(settings, b'[ultrawide]\nenable_monster_pop_in_fix = false\nenable_monster_ai_range = false\n')
    with ZipFile(archive) as release:
        shaders = path(path(path(loader_dir, 'data'), 'hd'), 'tc22sh')
        for name in release.namelist():
            if Path(name).parent.as_posix() == 'd2rloader/data/hd/tc22sh' and name.endswith('.bin'):
                shader = path(shaders, Path(name).name)
                if not shader.exists():
                    write_bytes(shader, release.read(name))
        binary = release.read(f'd2rloader/plugins/{ULTRAWIDE_PLUGIN}')
    # /tmp is private to this Wine instance. The mount disappears with the session.
    view = Path(mkdtemp(prefix='partydeck-ultrawide-', dir='/tmp'))
    plugins.mkdir(parents=True, exist_ok=True)
    for installed in plugins.iterdir():
        entry = view / installed.name
        if installed.is_symlink():
            entry.symlink_to(os.readlink(installed))
        elif installed.is_dir():
            entry.mkdir()
            subprocess.run(['mount', '--rbind', str(installed), str(entry)], check=True)
        elif installed.is_file():
            entry.touch()
            subprocess.run(['mount', '--bind', str(installed), str(entry)], check=True)
    write_bytes(view / ULTRAWIDE_PLUGIN, binary)
    subprocess.run(['mount', '--rbind', str(view), str(plugins)], check=True)


def readiness_dir(player, token):
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        raise ValueError('Invalid D2RLoader session token')
    return player.parent / f'd2r-lan-{token}'


def sync_readiness(marker, namespace_pid, proc=Path('/proc')):
    """Check the host namespace's listening sockets without opening a game connection."""
    listening = False
    for table in ('tcp', 'tcp6'):
        try:
            with (proc / str(namespace_pid) / 'net' / table).open() as stream:
                next(stream, None)
                listening = any(
                    address.rsplit(':', 1)[-1] == f'{PORT:04X}' and state == '0A'
                    for _, address, _, state, *_ in (line.split() for line in stream)
                )
        except FileNotFoundError:
            continue
        if listening:
            marker.touch(exist_ok=True)
            return
    marker.unlink(missing_ok=True)


def prepare(directory, prefix, player, plugin_source, automatic, rom, *, ultrawide=None):
    mounted_content = (rom,) if rom.suffix.casefold() == '.pc' else ()
    allowed = tuple(root.resolve() for root in (prefix, player, *mounted_content, *private_windows_paths(player)))
    directory = safe_path(directory, allowed)

    def path(parent, name):
        return safe_path(child(parent, name), allowed)

    loader = path(directory, 'D2RLoader.exe')
    core = path(directory, 'D2RCore.dll')
    executable = path(directory, 'D2R.exe')
    if not all(file.is_file() for file in (loader, core, executable)):
        raise ValueError(tr('D2RLoader absent du dossier du jeu indiqué par DIR dans autorun.cmd.'))

    loader_dir = path(directory, 'd2rloader')
    settings = path(path(loader_dir, 'config'), 'd2rloader.toml')
    plugins = path(loader_dir, 'plugins')
    plugin = path(plugins, PLUGIN)
    supported_core = False
    if automatic or ultrawide is not None:
        with core.open('rb') as source:
            supported_core = hashlib.file_digest(source, 'sha256').hexdigest() == CORE_131
    if automatic and not supported_core:
        print(tr('D2RLoader : automatisation disponible avec la version 1.3.1-beta. Utilisez le menu LAN.'),
              file=sys.stderr, flush=True)

    text = settings.read_text(encoding='utf-8-sig') if settings.is_file() else ''
    # These options belong to this LAN session. Preserve the mod, language,
    # extensions, backup preferences and the rest of the player's TOML.
    text = patch_ini(text, {
        'd2rloader': {'show_tcpip_button': 'true', 'check_for_updates': 'false'},
        'd2rloader.advanced': {'game_port': str(PORT), 'automatic_port_mapping': 'false',
                               'hosting_check': 'false'},
    })
    if automatic and supported_core:
        address = str(ipaddress.IPv4Address(os.environ['PARTYDECK_D2R_HOST']))
        count = int(os.environ['PARTYDECK_SESSION_PLAYERS'])
        if not 2 <= count <= 4:
            raise ValueError(tr('Réglages D2RLoader invalides.'))
        state_path = path(path(loader_dir, 'data'), 'state.json')
        state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.is_file() else {'version': 1}
        if not isinstance(state, dict) or not isinstance(state.get('multiplayer', {}), dict):
            raise ValueError(tr('Réglages D2RLoader invalides.'))
        multiplayer = state.setdefault('multiplayer', {})
        capacity = multiplayer.get('maxPlayers', 8)
        if type(capacity) is not int or not count <= capacity <= 8:
            capacity = max(4, count)
        multiplayer.update(lanOnly=True, unlisted=False, password='', directJoinAddress=address, maxPlayers=capacity)
        dll = plugin_source.read_bytes()
        write_bytes(state_path, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
        write_bytes(plugin, dll)
    else:
        plugin.unlink(missing_ok=True)
    write_bytes(settings, text.encode('utf-8'))
    if ultrawide is not None and not path(plugins, ULTRAWIDE_PLUGIN).is_file():
        # The native host fingerprint belongs to the executable shipped by D2RLoader.
        with loader.open('rb') as source:
            supported_loader = hashlib.file_digest(source, 'sha256').hexdigest() == ULTRAWIDE_LOADER
        if not (supported_core and supported_loader):
            print(tr('Diablo II : plugin Ultrawide incompatible avec ce D2RLoader.exe ou D2RCore.dll.'),
                  file=sys.stderr, flush=True)
        else:
            try:
                install_ultrawide(loader_dir, path, plugins, ultrawide)
            except (OSError, subprocess.SubprocessError) as error:
                print(tr('Diablo II : plugin Ultrawide indisponible ({p0}). Affichage standard.',
                         p0=error), file=sys.stderr, flush=True)
            else:
                print(tr('Diablo II {p0} : plugin Ultrawide prêt pour D2RLoader.', p0=player.name.upper()),
                      file=sys.stderr, flush=True)
    return loader.name


def instrument_native(source, hook):
    from partydeck_anchor import instrument_native as before_wine

    rewritten = before_wine(source, hook, prefix_argument=True)
    # The hook prints the verified executable filename. Keep any arguments
    # already supplied to D2RLoader through autorun.cmd.
    command = shlex.join(hook)
    prefix = command + ' "$PWD" "${WINEPOINT:-${GAMENAME}}" && '
    launcher = ('partydeck_d2r=$(' + prefix.removesuffix(' && ') + ') && '
                'if [[ ${WINE_CMD,,} != *d2rloader.exe* ]]; then WINE_CMD="$partydeck_d2r"; fi && ')
    return ''.join(line.replace(prefix, launcher).rstrip('\n') + ' || return $?\n'
                   if prefix in line else line for line in rewritten.splitlines(keepends=True))


def install_hook(base, original, player):
    from partydeck_profiles import atomic_write

    mode = os.environ.get('PARTYDECK_D2R')
    if mode not in ('automatic', 'manual'):
        return
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    plugin = base / 'plugins' / PLUGIN
    replacement = player / 'batocera-wine-d2rloader'
    hook = [sys.executable, str(base / 'partydeck_d2rloader.py'), str(player), str(plugin), mode, str(original)]
    atomic_write(replacement, instrument_native(binary.read_text(), hook), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    try:
        player, plugin, mode, rom, directory, prefix = sys.argv[1:]
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != player:
            raise ValueError(tr('D2RLoader : espace privé du joueur requis.'))
        ultrawide = (ultrawide_archive(Path(__file__).resolve().parent)
                     if os.environ.get('PARTYDECK_D2R_ULTRAWIDE') == '1' else None)
        print(prepare(Path(directory), Path(prefix), Path(player), Path(plugin), mode == 'automatic',
                      Path(rom), ultrawide=ultrawide))
    except (OSError, ValueError, KeyError) as error:
        print(f'D2RLoader: {error}', file=sys.stderr, flush=True)
        raise SystemExit(1)
