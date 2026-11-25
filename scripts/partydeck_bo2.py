"""Prepare the installed Black Ops II client in each player's private view."""
import hashlib
import json
from math import ceil
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from partydeck_borderlands2 import child, decode, patch_ini, write_bytes
from partydeck_i18n import tr
from partydeck_l4d2 import ACCOUNT_MAX, STEAM64_BASE
from partydeck_plutonium import BOOTSTRAPPER, client_path

ADAPTER = 'black-ops-2'
MODES = {
    'plutonium-mp': 'Multijoueur · Plutonium LAN',
    'plutonium-zm': 'Zombies · Plutonium LAN',
    'original': 'Lancement d’origine',
}
EXECUTABLES = {'mp': 't6mp.exe', 'zm': 't6zm.exe'}
PLUTONIUM_MODES = {'plutonium-mp': 't6mp', 'plutonium-zm': 't6zm'}
HOST_PORT = 1111
JOIN_HOST = f'connect 192.168.247.11:{HOST_PORT}'
AUTO_JOIN = 'PARTYDECK_BO2_AUTO_JOIN'
GAME_WINDOW = (r'^Plutonium T6[ :]+(MP|ZM|Multiplayer|Multijoueur|Zombies)([^a-z0-9]|$)'
               r'|Black Ops (II|2).*(Multiplayer|Multijoueur|Zombies)')
# Xwayland's evdev keycode for the physical key under Escape (grave or ²).
CONSOLE_KEYCODE = '49'
DEFAULT_RENDER_SIZE = (1280, 720)
MIN_DISPLAY_SIZE = (800, 600)
DESKTOP_MODE = 'PARTYDECK_BO2_DESKTOP_MODE'
HORIZONTAL_RENDER = {'native': 'Résolution de chaque moitié',
                     '720p': 'Ultrawide · hauteur minimale 720p',
                     'standard': 'Format 16:9'}


def render_size(width, height, *, horizontal_render='standard'):
    if horizontal_render == 'native':
        return width, height
    if horizontal_render == '720p':
        minimum_width, minimum_height = DEFAULT_RENDER_SIZE
        render_height = max(height, minimum_height, ceil(minimum_width * height / width))
        return round(width * render_height / height), render_height
    if width >= 1280 and height >= 720 and width * 9 == height * 16:
        return width, height
    return DEFAULT_RENDER_SIZE


def desktop_size(width, height):
    # T6 aborts video initialization if DXGI exposes no mode of at least
    # 800x600. Its custom window can still use a smaller back buffer.
    minimum_width, minimum_height = MIN_DISPLAY_SIZE
    if width < minimum_width or height < minimum_height:
        return render_size(width, height, horizontal_render='720p')
    return width, height


def display_arguments():
    width, height = DEFAULT_RENDER_SIZE
    resolution = os.environ.get('PARTYDECK_BO2_RESOLUTION', f'{width}x{height}')
    width, height = map(int, resolution.split('x'))
    desktop_mode = os.environ.get(DESKTOP_MODE, resolution)
    custom_mode = resolution != desktop_mode or width * 9 != height * 16
    # T6 computes the aspect ratio from the active resolution. Use a window
    # for custom modes inside Gamescope's borderless player viewport.
    args = ['+set', 'r_fullscreen', '0' if custom_mode else '2',
            '+set', 'r_mode', desktop_mode, '+set', 'r_customMode', resolution,
            '+set', 'r_aspectRatio', 'auto']
    if custom_mode:
        args.extend(['+set', 'vid_xpos', '0', '+set', 'vid_ypos', '0'])
    return args


def matches(rom):
    return bool(re.search(r'\bblack[\s_-]*ops[\s_-]*(?:ii|2)\b|\bbo2\b', rom.stem.casefold()))


def defaults(rom=None):
    mode = 'plutonium-zm' if rom and re.search(r'\bzombies?\b', rom.stem.casefold()) else 'plutonium-mp'
    return {'mode': mode, 'horizontal_render': 'native', 'automatic_join': True}


def validate(data):
    mode = data.get('mode') if isinstance(data, dict) else None
    if mode in ('mp', 'zm'):
        mode = f'plutonium-{mode}'
    if mode not in tuple(MODES):
        raise ValueError(tr('Mode Black Ops II invalide.'))
    horizontal_render = data.get('horizontal_render', 'standard' if data.get('fill_horizontal') is False else 'native')
    if horizontal_render not in tuple(HORIZONTAL_RENDER):
        raise ValueError(tr('Option de partage horizontal Black Ops II invalide.'))
    automatic_join = data.get('automatic_join', True)
    if type(automatic_join) is not bool:
        raise ValueError(tr('Option de connexion automatique Black Ops II invalide.'))
    return {'mode': mode, 'horizontal_render': horizontal_render, 'automatic_join': automatic_join}


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


def instrument_native(source, hook, mode, *, log=None):
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
        if log is not None:
            # Each player has its own output stream. Keep the main session
            # journal intact and preserve the native Wine exit status.
            body = re.sub(r'(?m)^( *\(cd "\$\{partydeck_bo2_cwd\}".*)\)$',
                          lambda match: f'{match[1]} > >(tee -- {shlex.quote(str(log))}) 2>&1)', body)
        parts[index] = body.replace(marker, setup + marker)
    return ''.join(parts)


def automatic_path(player, token, kind):
    if not re.fullmatch(r'[0-9a-f]{32}', token) or kind not in ('display', 'log'):
        raise ValueError('Invalid Black Ops II session state')
    return player / f'bo2-{token}.{kind}'


def session_logs(player, token, started):
    yield automatic_path(player, token, 'log')
    # UMU can capture Wine's stdout in the runner's per-player log.
    for path in (player / 'umu-logs').glob('runner-*.log'):
        try:
            if path.stat().st_mtime_ns >= started:
                yield path
        except OSError:
            continue


def startup_ready(player, token, started, mode):
    asset = mode[2:].encode()
    marker = re.compile(rb"Loading fastfile '?common_" + asset + rb"\b")
    for path in session_logs(player, token, started):
        try:
            with path.open('rb') as stream:
                if any(marker.search(line) for line in stream):
                    return True
        except OSError:
            continue
    return False


def join_window(display_file, outer_display):
    try:
        display = json.loads(display_file.read_text())
    except (OSError, ValueError):
        return False
    screen = display.get('DISPLAY') if isinstance(display, dict) else None
    if (not isinstance(screen, str) or not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', screen)
            or screen.split('.')[0] == outer_display.split('.')[0]):
        return False
    env = {**os.environ, 'DISPLAY': screen}
    env.pop('XAUTHORITY', None)
    if display.get('XAUTHORITY'):
        env['XAUTHORITY'] = display['XAUTHORITY']
    try:
        windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', GAME_WINDOW],
                                 env=env, timeout=2, capture_output=True, text=True)
        ids = windows.stdout.split()
        if windows.returncode or len(ids) != 1 or not ids[0].isdecimal():
            return False
        # Gameplay binds are ignored in the main menu. Use the console with
        # XTEST on this guest's display. Passing --window to key/type would
        # make xdotool send synthetic XSendEvent events instead.
        for command in (
            ['windowfocus', '--sync', ids[0], 'sleep', '0.2',
             'key', '--clearmodifiers', CONSOLE_KEYCODE, 'sleep', '0.3'],
            ['type', '--clearmodifiers', '--delay', '20', JOIN_HOST],
            ['key', '--clearmodifiers', '--delay', '50', 'Return', CONSOLE_KEYCODE],
        ):
            subprocess.run(['xdotool', *command], env=env, timeout=2, capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


class AutoJoin:
    """Track host matches for the lifetime of the split-screen session."""

    def __init__(self, players, token, mode, outer_display, started):
        self.host, *self.guests = players
        self.token = token
        self.mode = mode
        self.outer_display = outer_display
        self.started = started
        self.offsets = {}
        self.host_log = None
        self.host_ready = None
        self.connected = set()
        self.attempts = dict.fromkeys((guest.name for guest in self.guests), 0)
        self.retry_at = dict.fromkeys(self.attempts, 0)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        print(tr('Black Ops II : les invités attendent le lancement de la partie de J1.'), flush=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)

    def host_output(self):
        # Wine normally writes to our tee. UMU captures Proton output in
        # separate per-player runner logs, so include only logs of this run.
        logs = ([self.host_log] if self.host_log is not None else
                session_logs(self.host, self.token, self.started))
        for path in logs:
            try:
                with path.open('rb') as stream:
                    stream.seek(self.offsets.get(path, 0))
                    data = stream.read(262144)
                    end = data.rfind(b'\n') + 1
                    self.offsets[path] = stream.tell() - len(data) + end
            except OSError:
                continue
            for line in data[:end].splitlines():
                yield path, line
            # Stick to the stream that reports the game events. A runner log
            # can repeat the native tee's output later and replay an old match.
            if self.host_log is not None:
                return

    def observe_host(self, line, now):
        if b'SV_Shutdown:' in line:
            self.connected.clear()
            self.host_ready = None
            return True
        if b'==== ShutdownGame (' in line:
            # T6 also prints this on map rotation with clients still connected.
            self.host_ready = None
            return True
        if b'------- Game Initialization -------' in line:
            # Zombies can wait for guests before the host is fully in-game.
            ready = self.mode == 'plutonium-zm' or 'j1' in self.connected
            self.host_ready = None
        else:
            event = re.search(rb"client 'Player ([1-4])' (connected|disconnected)\b", line)
            if event is None:
                return False
            player = 'j' + event[1].decode('ascii')
            if event[2] == b'disconnected':
                if player == 'j1':
                    self.connected.clear()
                    self.host_ready = None
                elif player in self.connected and player in self.attempts:
                    # A guest can leave deliberately. Re-arm on the next map.
                    self.attempts[player] = 4
                    self.connected.remove(player)
                return True
            if player != 'j1' and player not in self.connected:
                print(tr('Black Ops II {p0} : connexion confirmée par J1.', p0=player.upper()), flush=True)
            self.connected.add(player)
            ready = player == 'j1'

        if ready and self.host_ready is None:
            self.host_ready = now + 2
            self.attempts = dict.fromkeys(self.attempts, 0)
            self.retry_at = dict.fromkeys(self.retry_at, 0)
            print(tr('Black Ops II : partie de J1 détectée.'), flush=True)
        return True

    def poll(self, now):
        for path, line in self.host_output():
            if self.observe_host(line, now):
                self.host_log = path
        if self.host_ready is None or now < self.host_ready:
            return

        for player in self.guests:
            if self.stop.is_set():
                return
            name = player.name
            attempts = self.attempts[name]
            if name in self.connected or now < self.retry_at[name] or attempts > 3:
                continue
            if attempts == 3 or now >= self.host_ready + 90:
                if attempts:
                    print(tr('Black Ops II {p0} : connexion automatique non confirmée. Utilisez {p1}.',
                             p0=player.name.upper(), p1=JOIN_HOST), flush=True)
                else:
                    print(tr('Black Ops II {p0} : impossible d’envoyer la commande de connexion à la console.',
                             p0=player.name.upper()), flush=True)
                self.attempts[name] = 4
            elif join_window(automatic_path(player, self.token, 'display'), self.outer_display):
                self.attempts[name] += 1
                self.retry_at[name] = now + 18
                print(tr('Black Ops II {p0} : connexion à la partie de J1 demandée.',
                         p0=player.name.upper()), flush=True)

    def run(self):
        while not self.stop.is_set():
            self.poll(time.monotonic())
            self.stop.wait(1)


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
    mode = profile['bo2']['mode']
    source = client_path(base, PLUTONIUM_MODES.get(mode)) or base / 'plutonium'
    hook = [sys.executable, str(base / 'partydeck_bo2.py'), str(player), str(source)]
    replacement = player / 'batocera-wine-bo2'
    log = None
    token = os.environ.get('PARTYDECK_SESSION_TOKEN', '')
    if mode in PLUTONIUM_MODES and re.fullmatch(r'[a-f0-9]{32}', token):
        log = automatic_path(player, token, 'log')
    atomic_write(replacement, instrument_native(binary.read_text(), hook, mode, log=log), 0o755)
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
