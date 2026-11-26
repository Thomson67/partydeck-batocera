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
BO1 = 'black-ops-1'
PROFILE_KEYS = {BO1: 'bo1', ADAPTER: 'bo2'}
TITLES = {BO1: 'Black Ops', ADAPTER: 'Black Ops II'}
MODES = {
    'plutonium-mp': 'Multijoueur · Plutonium LAN',
    'plutonium-zm': 'Zombies · Plutonium LAN',
    'original': 'Lancement d’origine',
    't5mp': 'Multijoueur · Plutonium LAN',
    't5sp': 'Zombies · Plutonium LAN',
}
EXECUTABLES = {'mp': 't6mp.exe', 'zm': 't6zm.exe'}
PLUTONIUM_MODES = {'plutonium-mp': 't6mp', 'plutonium-zm': 't6zm', 't5mp': 't5mp', 't5sp': 't5sp'}
SELECTABLE_MODES = {BO1: ('t5mp', 't5sp'), ADAPTER: ('plutonium-mp', 'plutonium-zm')}
T5_EXECUTABLES = {'t5sp': 'BlackOps.exe', 't5mp': 'BlackOpsMP.exe'}
LANGUAGES = {'keep': 'Conserver', 'french': 'Français', 'english': 'Anglais'}
HOST_PORT = 1111
T5_BOT_COUNTS = tuple(range(13))
T5_TEAM_BOT_COUNTS = tuple(range(7))
T5_FOV_OVERRIDE = 'PARTYDECK_BO1_FOV'
T5_ZOMBIE_BOT_COUNTS = tuple(range(4))
T5_ZOMBIE_BOT_SCRIPT = 'partydeck_bo1_zombies.gsc'
T5_FOV_CHOICES = (0, *range(65, 111, 5))
T5_CONFIG_NAMES = {'config.cfg', 'config_mp.cfg', 'conlzm.cfg'}
T5_FOV_LINE = re.compile(rb'^[ \t]*seta?[ \t]+"?cg_fov(?:_default)?"?[ \t]+', re.I)
JOIN_HOST = f'connect 192.168.247.11:{HOST_PORT}'
PUBLISH_DISPLAY = 'PARTYDECK_BO2_AUTO_JOIN'
SESSION_MODE = 'PARTYDECK_BO2_MODE'
GAME_WINDOW = (r'^Plutonium T[56][ :_]+(MP|SP|ZM|Singleplayer|Single Player|Multiplayer|Multijoueur|Zombies)([^a-z0-9]|$)'
               r'|^Plutonium T5[ :_]+(Co-Op|Campaign)([^a-z0-9]|$)'
               r'|Black Ops (II|2).*(Multiplayer|Multijoueur|Zombies)'
               r'|^Call of Duty(\(R\))?[: ]+Black Ops( - (Multiplayer|Zombies))?$')
# Positions of the two native buttons in the verified 1920x540 layout.
MENU_SIZE = (1920, 540)
ONLINE_BUTTON = (668, 326)
CUSTOM_GAMES_BUTTONS = {'plutonium-mp': (700, 99), 'plutonium-zm': (700, 135)}
# Plutonium's terminal output includes color and erase sequences even when
# stdout is redirected. Strip them before matching words and dvar values.
TERMINAL_CSI = re.compile(rb'\x1b\[[0-?]*[ -/]*[@-~]')
STARTUP_MARKERS = {mode: re.compile(rb"Loading fastfile '?" + asset + rb"(?![a-zA-Z0-9_])")
                   for mode, asset in (('t6mp', b'common_mp'), ('t6zm', b'common_zm'),
                                       ('t5mp', b'plutonium_ui_mp'), ('t5sp', rb'(?:common|plutonium_ui)'))}
# Plutonium r5369 issues this command as it enters the online menu.
ONLINE_MENU_MARKER = re.compile(rb'Unknown command:? "session_rejoinsession"')
GAME_INITIALIZATION = b'------- Game Initialization -------'
T5_ZOMBIES_MAP = re.compile(
    rb'(?:\bServer:\s+|\bLOADING\.\.\. maps/|\\mapname\\)(?:zombie_[a-z0-9_]+|zombietron)(?![a-z0-9_])',
    re.I)
T5_MENU_DVAR = re.compile(rb'"(zombiemode|ui_skipMainLockout)"\s+is:\s+"(0|1|true|false)(?:\^7)?"', re.I)
T5_ZOMBIES_HOST_LOBBY = ('setclientbeingusedandprimary; set ui_gametype zom; '
                         'xblive_privatematch 1; xblive_rankedmatch 0; xstartpartyhost; '
                         'closemenu main_online; closemenu menu_xboxlive; openmenu menu_xboxlive_privatelobby')
PLAYER_CONNECTION = re.compile(rb"client 'Player ([1-4])' (connected|disconnected)\b")
T5_ZOMBIES_CLIENT_LOADING = re.compile(rb'Going from CS_CONNECTED to CS_CLIENTLOADING for Player ([1-4])\b')
T5_LOBBY_COMMANDS = {
    # Match the Multiplayer "Private Match" action in ui_mp/main.menu.
    't5mp': ('setclientbeingusedandprimary; set systemlink 0; set splitscreen 0; '
             'set onlinegame 1; set xblive_privatematch 1; '
             'exec default_xboxlive.cfg; set ui_mapname mp_mountain; set ui_gametype tdm; '
             'closemenu live_flyout; openmenu menu_xboxlive_privatelobby'),
}
CUSTOM_LOBBY_MODES = CUSTOM_GAMES_BUTTONS.keys() | T5_EXECUTABLES.keys()
ZOMBIES_DLC_LOAD = re.compile(rb"Loading fastfile '?\w+_load_zm\b")
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


def display_arguments(*, t5=False):
    width, height = DEFAULT_RENDER_SIZE
    resolution = os.environ.get('PARTYDECK_BO2_RESOLUTION', f'{width}x{height}')
    width, height = map(int, resolution.split('x'))
    desktop_mode = os.environ.get(DESKTOP_MODE, resolution)
    custom_mode = resolution != desktop_mode or width * 9 != height * 16
    # T6 computes the aspect ratio from the active resolution. Use a window
    # for custom modes inside Gamescope's borderless player viewport.
    args = ['+set', 'r_fullscreen', '0' if t5 or custom_mode else '2',
            '+set', 'r_mode', desktop_mode, '+set', 'r_customMode', resolution,
            '+set', 'r_aspectRatio', 'auto']
    if t5:
        args.extend(['+set', 'r_noborder', '1'])
    if t5 or custom_mode:
        args.extend(['+set', 'vid_xpos', '0', '+set', 'vid_ypos', '0'])
    return args


def matches(rom):
    return bool(re.search(r'\bblack[\s_-]*ops[\s_-]*(?:ii|2)\b|\bbo2\b', rom.stem.casefold()))


def matches_bo1(rom):
    name = rom.stem.casefold()
    return bool(re.search(r'\bbo1\b|\bblack[\s_-]*ops\b(?![\s_-]*(?:[2-9]|ii|iii|iv|v|vi|vii|cold[\s_-]*war)\b)', name))


def defaults(rom=None, adapter=ADAPTER):
    mode = 'plutonium-zm' if rom and re.search(r'\bzombies?\b', rom.stem.casefold()) else 'plutonium-mp'
    if adapter == BO1:
        mode = 't5sp' if mode == 'plutonium-zm' else 't5mp'
        return {'mode': mode, 'horizontal_render': 'native', 'automatic_join': True,
                'open_custom_lobby': False, 'language': 'keep', 'vertical_native': False,
                'horizontal_fov': 0, 'vertical_fov': 0,
                'private_bots': 0, 'allies_bots': 0, 'axis_bots': 0, 'team_total_bots': 0, 'zombie_bots': 0}
    return {'mode': mode, 'horizontal_render': 'native', 'automatic_join': True, 'open_custom_lobby': False,
            'language': 'keep'}


def validate(data, adapter=ADAPTER):
    mode = data.get('mode') if isinstance(data, dict) else None
    if mode in ('mp', 'zm'):
        mode = f'plutonium-{mode}'
    if mode not in (*SELECTABLE_MODES[adapter], 'original'):
        raise ValueError(tr('Mode Black Ops II invalide.'))
    horizontal_render = data.get('horizontal_render', 'standard' if data.get('fill_horizontal') is False else 'native')
    if horizontal_render not in tuple(HORIZONTAL_RENDER):
        raise ValueError(tr('Option de partage horizontal Black Ops II invalide.'))
    automatic_join = data.get('automatic_join', True)
    if type(automatic_join) is not bool:
        raise ValueError(tr('Option de connexion automatique Black Ops II invalide.'))
    open_custom_lobby = data.get('open_custom_lobby', False)
    if type(open_custom_lobby) is not bool:
        raise ValueError(tr('Option d’ouverture du salon Black Ops II invalide.'))
    language = data.get('language', 'keep')
    if language not in tuple(LANGUAGES):
        raise ValueError(tr('Langue Black Ops II invalide.'))
    settings = {'mode': mode, 'horizontal_render': horizontal_render, 'automatic_join': automatic_join,
                'open_custom_lobby': open_custom_lobby, 'language': language}
    if adapter == BO1:
        vertical_native = data.get('vertical_native', False)
        if type(vertical_native) is not bool:
            raise ValueError(tr('Format vertical Black Ops invalide.'))
        settings['vertical_native'] = vertical_native
        for key in ('horizontal_fov', 'vertical_fov'):
            fov = data.get(key, 0)
            if type(fov) is not int or fov not in T5_FOV_CHOICES:
                raise ValueError(tr('Champ de vision Black Ops invalide.'))
            settings[key] = fov
        for key, choices in (('private_bots', T5_BOT_COUNTS), ('allies_bots', T5_TEAM_BOT_COUNTS),
                             ('axis_bots', T5_TEAM_BOT_COUNTS), ('team_total_bots', T5_BOT_COUNTS),
                             ('zombie_bots', T5_ZOMBIE_BOT_COUNTS)):
            count = data.get(key, 0)
            if type(count) is not int or count not in choices:
                raise ValueError(tr('Nombre de bots Black Ops invalide.'))
            settings[key] = count
    return settings


def custom_lobby_enabled(settings, private_lan):
    mode = settings['mode']
    return (settings['open_custom_lobby'] and mode in CUSTOM_LOBBY_MODES
            and (private_lan or mode in T5_EXECUTABLES))


def t5_bot_counts(settings):
    if settings['mode'] != 't5mp':
        return ()
    total = settings.get('team_total_bots', 0)
    allies = settings.get('allies_bots', 0) if not total else 0
    axis = settings.get('axis_bots', 0) if not total else 0
    counts = (settings.get('private_bots', 0), allies, axis, total)
    return counts if any(counts) else ()


def private_child(directory, name):
    path = child(directory, name)
    if path.is_symlink():
        raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=path))
    return path


def find_game(directory, root, mode, allowed):
    exe_name = (EXECUTABLES | T5_EXECUTABLES).get(mode)
    names = (exe_name,) if exe_name else tuple(EXECUTABLES.values())

    def search(folder):
        for name in names:
            exe = private_child(folder, name)
            if exe.is_file():
                return exe
        return None

    exe = search(directory)
    if exe is not None:
        return exe
    folders = [directory]
    game = child(child(root, 'drive_c'), 'game').resolve()
    if any(game.is_relative_to(path) for path in allowed):
        exe = search(game)
        if exe is not None:
            return exe
        folders.append(game)
    exe = search(root)
    if exe is not None:
        return exe
    if mode == 't5mp':
        # Plutonium launches its own t5mp.exe. The campaign executable
        # can locate the shared game directory when the MP assets are present.
        for folder in dict.fromkeys([*folders, root]):
            campaign = private_child(folder, T5_EXECUTABLES['t5sp'])
            if not campaign.is_file():
                continue
            common = private_child(private_child(folder, 'zone'), 'Common')
            if all(private_child(common, name).is_file() for name in ('common_mp.ff', 'ui_mp.ff')):
                return campaign
        raise ValueError(tr('Black Ops : BlackOpsMP.exe introuvable et données Multijoueur incomplètes dans zone/Common (common_mp.ff, ui_mp.ff).'))
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


def prepare(player, mode, directory, root, plutonium_source, language='keep', *, bot_counts=(), zombie_bots=0):
    if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player):
        raise ValueError(tr('Black Ops II : espace privé du joueur requis.'))
    from partydeck_bottles import private_windows_paths

    directory, root = directory.resolve(strict=True), root.resolve(strict=True)
    allowed = (root, *private_windows_paths(player))
    if not any(directory.is_relative_to(path) for path in allowed):
        raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=directory))
    plutonium_mode = PLUTONIUM_MODES.get(mode)
    game_mode = plutonium_mode[2:] if plutonium_mode and plutonium_mode.startswith('t6') else mode
    exe = find_game(directory, root, game_mode, allowed)
    if plutonium_mode:
        return prepare_plutonium(player, exe.parent, root, plutonium_source, plutonium_mode, language,
                                 bot_counts=bot_counts, zombie_bots=zombie_bots)

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


def apply_language(game, mode, language):
    zone = private_child(game, 'zone')
    if not private_child(zone, language).is_dir():
        raise ValueError(tr('Black Ops II : fichiers de langue {p0} introuvables dans {p1}.',
                            p0=tr(LANGUAGES[language]), p1=zone))
    # T6 has a mode-specific file. Keep the generic file in sync for clients
    # that use it as a fallback, preserving each file's existing byte encoding.
    names = ['localization.txt']
    if mode.startswith('t6'):
        names.append(f'localization_{mode[2:]}.txt')
    paths = [private_child(game, name) for name in names]
    changes = []
    for path in paths:
        previous = path.read_bytes() if path.is_file() else b''
        if previous:
            updated, replaced = re.subn(rb'\A((?:\xef\xbb\xbf)?[ \t]*)[A-Za-z]+(?=[ \t\r\n]|$)',
                                        lambda m: m[1] + language.encode('ascii'), previous, count=1)
            if not replaced:
                raise ValueError(tr('Black Ops II : fichier de langue invalide dans {p0}.', p0=path))
        else:
            updated = language.encode('ascii') + b'\r\n'
        if updated != previous:
            changes.append((path, updated))
    for path, updated in changes:
        write_bytes(path, updated)


def preserve_t5_fov(runtime, override):
    # The game archives cg_fov_default. Save only the affected lines so the
    # next launch without an override keeps all other changes made in game.
    snapshot = private_child(runtime, 'partydeck-t5-fov.json')
    if snapshot.is_file() == override:
        return
    configs = runtime
    for folder in ('storage', 't5', 'players'):
        configs = private_child(configs, folder)
    paths = {path.name.casefold(): private_child(configs, path.name)
             for path in configs.iterdir() if path.name.casefold() in T5_CONFIG_NAMES} if configs.is_dir() else {}
    saved = {} if override else json.loads(snapshot.read_bytes())
    for name, path in paths.items():
        if not path.is_file():
            continue
        original = path.read_bytes()
        lines = original.splitlines(keepends=True)
        if override:
            saved[name] = b''.join(line for line in lines if T5_FOV_LINE.match(line)).decode('latin-1')
        else:
            other_settings = b''.join(line for line in lines if not T5_FOV_LINE.match(line))
            fov_settings = saved.get(name, '').encode('latin-1')
            if fov_settings and other_settings and not other_settings.endswith(b'\n'):
                other_settings += b'\n'
            restored = other_settings + fov_settings
            if restored != original:
                write_bytes(path, restored)
    if override:
        write_bytes(snapshot, json.dumps(saved).encode('ascii'))
    else:
        snapshot.unlink()


def configure_t5_bots(runtime, counts):
    folder = runtime
    for name in ('storage', 't5', 'scripts', 'mp'):
        folder = private_child(folder, name)
    script = private_child(folder, 'partydeck_bots.gsc')
    if not any(counts):
        script.unlink(missing_ok=True)
        return

    free, allies, axis, total = counts
    if (free not in T5_BOT_COUNTS or total not in T5_BOT_COUNTS
            or allies not in T5_TEAM_BOT_COUNTS or axis not in T5_TEAM_BOT_COUNTS):
        raise ValueError(tr('Nombre de bots Black Ops invalide.'))
    # T5 owns the team/class transitions. Set the team once the bot finishes
    # connecting, before its regular class and respawn logic starts.
    write_bytes(script, (r"""
init()
{
    level thread start_bots();
}

start_bots()
{
    level endon("game_ended");
    wait 1;
    if (!isSubStr(getdvar("mapname"), "mp_"))
        return;

    while (!isdefined(level.teambased) || !isdefined(level.players) || level.players.size == 0)
        wait 0.25;

    if (!level.teambased)
    {
        bots = team_bots("free");
        fill_bots("free", %d - bots.size);
        return;
    }

    total = %d;
    for (;;)
    {
        if (game["state"] == "postgame")
            return;

        targets = team_targets(total, human_team("allies"), human_team("axis"));
        if (targets.size != 0)
            balance_bots(targets);
        wait 2;
    }
}

team_targets(total, allies, axis)
{
    targets = [];
    if (!total)
    {
        targets[0] = %d;
        targets[1] = %d;
        return targets;
    }
    if (allies + axis == 0)
        return targets;
    targets[0] = 0;
    targets[1] = 0;
    for (i = 0; i < total; i++)
    {
        if (allies + targets[0] <= axis + targets[1])
            targets[0]++;
        else
            targets[1]++;
    }
    return targets;
}

human_team(team)
{
    count = 0;
    players = level.players;
    for (i = 0; i < players.size; i++)
    {
        player = players[i];
        if (!player IsTestClient() && isdefined(player.team) && player.team == team)
            count++;
    }
    return count;
}

team_bots(team)
{
    bots = [];
    players = level.players;
    for (i = 0; i < players.size; i++)
    {
        player = players[i];
        if (player IsTestClient() && (team == "free" || (isdefined(player.team) && player.team == team)))
            bots[bots.size] = player;
    }
    return bots;
}

balance_bots(targets)
{
    allies = team_bots("allies");
    axis = team_bots("axis");
    allies_needed = targets[0] - allies.size;
    axis_needed = targets[1] - axis.size;
    if (allies_needed > 0 && axis.size > targets[1])
    {
        axis_surplus = axis.size - targets[1];
        allies_needed -= transfer_bots(axis, "allies", min(allies_needed, axis_surplus));
    }
    else if (axis_needed > 0 && allies.size > targets[0])
    {
        allies_surplus = allies.size - targets[0];
        axis_needed -= transfer_bots(allies, "axis", min(axis_needed, allies_surplus));
    }

    // Reserve the remaining slots against bots still connecting or supplied
    // by another mod. A change in team sizes must not create extra bots.
    bots = team_bots("free");
    remaining = targets[0] + targets[1] - bots.size;
    added = fill_bots("allies", min(allies_needed, remaining));
    fill_bots("axis", min(axis_needed, remaining - added));
}

transfer_bots(bots, team, count)
{
    moved = 0;
    for (i = 0; i < bots.size && moved < count; i++)
    {
        bot = bots[i];
        if (!isdefined(bot) || !isdefined(bot.pers["partydeck_bot"]))
            continue;
        assign_bot(bot, team);
        bot notify("menuresponse", "changeclass", "smg_mp");
        moved++;
    }
    return moved;
}

fill_bots(team, count)
{
    added = 0;
    for (i = 0; i < count; i++)
    {
        bot = AddTestClient();
        if (!isdefined(bot))
        {
            println("PartyDeck bots: could not add a client to " + team);
            break;
        }
        added++;
        for (attempt = 0; attempt < 30 && isdefined(bot) && !isdefined(bot.pers["team"]); attempt++)
            wait 0.1;
        if (!isdefined(bot) || !isdefined(bot.pers["team"]))
            continue;
        bot.pers["isBot"] = true;
        bot.pers["partydeck_bot"] = true;
        bot.equipment_enabled = false;
        if (team != "free")
            assign_bot(bot, team);
        bot thread maps\mp\gametypes\_bot::bot_spawn_think(team);
        wait 0.25;
    }
    return added;
}

assign_bot(bot, team)
{
    if (!isdefined(bot.team) || bot.team != team)
        bot maps\mp\gametypes\_teams::changeTeam(team);
    bot.pers["dont_autobalance"] = true;
}
""" % (free, total, allies, axis)).encode('ascii'))


def configure_t5_zombie_bots(runtime, count, humans):
    folder = runtime
    for name in ('storage', 't5', 'scripts'):
        folder = private_child(folder, name)
    # The global scripts directory is read while T5 is still loading its
    # frontend. Move our previous copy out of that path before Wine starts.
    private_child(folder, T5_ZOMBIE_BOT_SCRIPT).unlink(missing_ok=True)
    zombies = private_child(private_child(folder, 'sp'), 'zom')
    script = private_child(zombies, T5_ZOMBIE_BOT_SCRIPT)
    count = min(count, 4 - humans)
    if not count:
        script.unlink(missing_ok=True)
        return []

    # Reuse an existing copy of the upstream mod when one was installed
    # manually, to avoid loading two scripts that define the same routines.
    if any(private_child(directory, 'zm_bo1_bots.gsc').is_file()
           for directory in (folder, zombies, private_child(folder, 'zm'))):
        script.unlink(missing_ok=True)
    else:
        bundled = Path(__file__).with_name(T5_ZOMBIE_BOT_SCRIPT)
        if not bundled.is_file():
            bundled = bundled.parent.parent / 'plugins' / bundled.name
        write_bytes(script, bundled.read_bytes())
    return ['+set', 'bo1_bots_enabled', '1', '+set', 'bo1_bots_count', str(count),
            '+set', 'bo1_bots_max_players', '4', '+set', 'partydeck_bo1_humans', str(humans)]


def prepare_plutonium(player, game, root, source, mode, language='keep', *, bot_counts=(), zombie_bots=0):
    binaries = private_child(source, 'bin')
    games = private_child(source, 'games')
    bootstrapper = private_child(binaries, BOOTSTRAPPER)
    if not (bootstrapper.is_file() and private_child(games, f'{mode}.exe').is_file()):
        raise ValueError(tr('Black Ops II : copiez bin et games de Plutonium dans {p0}.', p0=source))
    t5 = mode.startswith('t5')
    title = TITLES[BO1 if t5 else ADAPTER]
    bink = private_child(game, 'binkw32.dll')
    if not bink.is_file():
        raise ValueError(tr('Black Ops II : binkw32.dll introuvable dans {p0}.', p0=game))
    if not t5 and b'_BinkWaitStopAsyncThread@4\0' not in bink.read_bytes():
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
    session_players = os.environ.get('PARTYDECK_SESSION_PLAYERS', '1')
    zombie_args = []
    if t5:
        configure_t5_bots(runtime, bot_counts if mode == 't5mp' and player.name == 'j1' else ())
        humans = int(session_players) if session_players in ('1', '2', '3', '4') else 1
        zombie_count = zombie_bots if mode == 't5sp' and player.name == 'j1' else 0
        zombie_args = configure_t5_zombie_bots(runtime, zombie_count, humans)
    if language != 'keep':
        apply_language(game, mode, language)

    _, _, name = identity(player)
    port = HOST_PORT + int(player.name[1:]) - 1
    name_option = '-name' if t5 else '+name'
    args = [f'./{binaries.name}/{bootstrapper.name}',
            mode, game_path, name_option, name, '-lan', *display_arguments(t5=t5),
            '+set', 'net_port', str(port)]
    if t5:
        args += ['+set', 'gpad_enabled', '1', *zombie_args]
        fov = os.environ.get(T5_FOV_OVERRIDE, '0')
        override_fov = fov in {str(value) for value in T5_FOV_CHOICES if value}
        preserve_t5_fov(runtime, override_fov)
        if override_fov:
            args += ['+set', 'cg_fov', fov, '+set', 'cg_fov_default', fov]
        if language != 'keep':
            args += ['+set', 'loc_language', '1' if language == 'french' else '0']
    if mode in ('t6zm', 't5sp') and player.name == 'j1':
        count = session_players
        if count in ('1', '2', '3', '4'):
            args += ['+set', 'sp_minplayers', count]
        if (mode == 't5sp' and count in ('2', '3', '4')
                and os.environ.get(PUBLISH_DISPLAY) == '1'
                and os.environ.get('PARTYDECK_PRIVATE_LAN_IP')):
            # T5 emits the client-loading acknowledgement in developer output.
            # Keep the output available to AutoJoin without drawing it over the game.
            args += ['+set', 'developer', '1', '+set', 'con_minicon', '0']
    if player.name != 'j1':
        print(tr('Black Ops II {p0} : rejoindre J1 avec {p1}.', p0=player.name.upper(),
                 p1=JOIN_HOST), file=sys.stderr, flush=True)
    print(tr('{p0} {p1} · Plutonium LAN ({p2}, port {p3}).',
             p0=title, p1=player.name.upper(), p2=mode, p3=port), file=sys.stderr, flush=True)
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
                          lambda match: f'{match[1]} > >(tee -a -- {shlex.quote(str(log))}) 2>&1)', body)
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
    marker = STARTUP_MARKERS[mode]
    for path in session_logs(player, token, started):
        try:
            with path.open('rb') as stream:
                if any(marker.search(TERMINAL_CSI.sub(b'', line)) for line in stream):
                    return True
        except OSError:
            continue
    return False


def game_display(display_file, outer_display):
    try:
        display = json.loads(display_file.read_text())
    except (OSError, ValueError):
        return None
    screen = display.get('DISPLAY') if isinstance(display, dict) else None
    if (not isinstance(screen, str) or not re.fullmatch(r':[0-9]+(?:\.[0-9]+)?', screen)
            or screen.split('.')[0] == outer_display.split('.')[0]):
        return None
    env = {**os.environ, 'DISPLAY': screen}
    env.pop('XAUTHORITY', None)
    if display.get('XAUTHORITY'):
        env['XAUTHORITY'] = display['XAUTHORITY']
    return env


def game_window(env):
    windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--name', GAME_WINDOW],
                             env=env, timeout=2, capture_output=True, text=True)
    ids = windows.stdout.split()
    if windows.returncode == 0 and len(ids) == 1 and ids[0].isdecimal():
        return ids[0]
    return None


def join_window(display_file, outer_display):
    return send_console_command(display_file, outer_display, JOIN_HOST)


def send_console_command(display_file, outer_display, text):
    env = game_display(display_file, outer_display)
    if env is None:
        return False
    try:
        window = game_window(env)
        if window is None:
            return False
        # Gameplay binds are ignored in the main menu. Use the console with
        # XTEST on this guest's display. Passing --window to key/type would
        # make xdotool send synthetic XSendEvent events instead.
        for command in (
            ['windowfocus', '--sync', window, 'sleep', '0.2',
             'key', '--clearmodifiers', CONSOLE_KEYCODE, 'sleep', '0.3'],
            ['type', '--clearmodifiers', '--delay', '20', text],
            ['key', '--clearmodifiers', '--delay', '50', 'Return', CONSOLE_KEYCODE],
        ):
            timeout = max(2, len(text) * .02 + 1) if command[0] == 'type' else 2
            subprocess.run(['xdotool', *command], env=env, timeout=timeout, capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def press_menu_keys(display_file, outer_display, keys):
    env = game_display(display_file, outer_display)
    if env is None:
        return False
    try:
        window = game_window(env)
        if window is None:
            return False
        subprocess.run(['xdotool', 'windowfocus', '--sync', window, 'sleep', '0.2',
                        'key', '--clearmodifiers', '--delay', '150', *keys],
                       env=env, timeout=2, capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def click_menu_button(display_file, outer_display, button):
    env = game_display(display_file, outer_display)
    if env is None:
        return False
    try:
        window = game_window(env)
        if window is None:
            return False
        geometry = subprocess.run(['xdotool', 'getwindowgeometry', '--shell', window],
                                  env=env, timeout=2, capture_output=True, text=True, check=True)
        dimensions = dict(re.findall(r'^(WIDTH|HEIGHT)=([0-9]+)$', geometry.stdout, re.M))
        width, height = (int(dimensions.get(key, '0')) for key in ('WIDTH', 'HEIGHT'))
        measured_width, measured_height = MENU_SIZE
        if height < measured_height or width * 9 not in (height * 16, height * 32):
            return False
        x, y = button
        # The menu's 16:9 layout is centered in both normal and ultrawide game windows.
        scale = height / measured_height
        x = round(width / 2 + (x - measured_width / 2) * scale)
        y = round(y * scale)
        subprocess.run(['xdotool', 'windowfocus', '--sync', window,
                        'mousemove', '--window', window, str(x), str(y), 'sleep', '0.2', 'click', '1'],
                       env=env, timeout=2, capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


class AutoJoin:
    """Track host matches for the lifetime of the split-screen session."""

    def __init__(self, players, token, mode, outer_display, started, *, open_custom_lobby=False):
        self.host, *self.guests = players
        self.token = token
        self.mode = mode
        self.outer_display = outer_display
        self.started = started
        self.log_positions = {}
        self.host_log = None
        self.host_ready = None
        self.lobby_button = ONLINE_BUTTON if open_custom_lobby and mode in CUSTOM_LOBBY_MODES else None
        self.lobby_click_at = None
        self.lobby_deadline = None
        self.t5_menu_dvars = {}
        self.t5_menu_keys = set()
        self.t5_menu_query = False
        self.connected = set()
        self.attempts = dict.fromkeys((guest.name for guest in self.guests), 0)
        self.retry_at = dict.fromkeys(self.attempts, 0)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        if self.guests:
            print(tr('Black Ops II : les invités attendent le lancement de la partie de J1.'), flush=True)
        if self.lobby_button is not None:
            print(tr('Black Ops II J1 : ouverture automatique du salon activée.'), flush=True)
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
                    stat = os.fstat(stream.fileno())
                    identity = (stat.st_dev, stat.st_ino)
                    previous, offset = self.log_positions.get(path, (None, 0))
                    if identity != previous or stat.st_size < offset:
                        offset = 0
                    stream.seek(offset)
                    limit = 1048576
                    data = stream.read(limit)
                    end = max(data.rfind(b'\n'), data.rfind(b'\r')) + 1
                    if not end and len(data) == limit:
                        # A long diagnostic must not block all later events.
                        end = limit - 1024
                    self.log_positions[path] = (identity, offset + end)
            except OSError:
                continue
            for line in data[:end].splitlines():
                yield path, TERMINAL_CSI.sub(b'', line)
            # Stick to the stream that reports the game events. A runner log
            # can repeat the native tee's output later and replay an old match.
            if self.host_log is not None:
                return

    def match_starting(self, line):
        if self.mode == 't5sp':
            # T5 starts a local listen server for its frontend too.
            return T5_ZOMBIES_MAP.search(line) is not None
        return GAME_INITIALIZATION in line

    def observe_host(self, line, now):
        if b'SV_Shutdown:' in line or (self.mode in T5_EXECUTABLES and b'Server Shutdown' in line):
            self.connected.clear()
            self.host_ready = None
            return True
        if b'==== ShutdownGame (' in line:
            # T6 also prints this on map rotation with clients still connected.
            self.host_ready = None
            return True
        if self.match_starting(line):
            # Zombies can wait for guests before the host is fully in-game.
            ready = self.mode in ('plutonium-zm', 't5sp', 't5mp') or 'j1' in self.connected
            if self.mode not in T5_EXECUTABLES:
                self.host_ready = None
        else:
            event = PLAYER_CONNECTION.search(line)
            action = event[2] if event is not None else b'connected'
            if event is None and self.mode == 't5sp':
                # T5 Zombies acknowledges its clients when it sends the game state.
                event = T5_ZOMBIES_CLIENT_LOADING.search(line)
            if event is None:
                return False
            player = 'j' + event[1].decode('ascii')
            if action == b'disconnected':
                if player == 'j1':
                    self.connected.clear()
                    self.host_ready = None
                elif player in self.connected and player in self.attempts:
                    # A guest can leave deliberately. Re-arm on the next map.
                    self.attempts[player] = 4
                    self.connected.remove(player)
                return True
            if self.mode == 't5sp' and (player == 'j1' or self.host_ready is None):
                return False
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

    def observe_lobby(self, line, now):
        if self.match_starting(line):
            self.lobby_button = None
        elif self.mode == 't5sp':
            if self.lobby_click_at is None and STARTUP_MARKERS['t5sp'].search(line):
                self.lobby_click_at = now + 5
                self.lobby_deadline = self.lobby_click_at + 25
            elif self.t5_menu_query and (state := T5_MENU_DVAR.search(line)):
                self.t5_menu_dvars[state[1].lower()] = state[2].lower() in (b'1', b'true')
        elif ONLINE_MENU_MARKER.search(line):
            if self.lobby_button == ONLINE_BUTTON:
                # J1 already navigated manually.
                self.lobby_button = None
            elif self.lobby_click_at is None:
                self.lobby_click_at = now + 1
        elif self.lobby_button == ONLINE_BUTTON:
            if self.lobby_click_at is None and STARTUP_MARKERS[PLUTONIUM_MODES[self.mode]].search(line):
                self.lobby_click_at = now + 5
                self.lobby_deadline = self.lobby_click_at + 20
            elif (self.lobby_click_at is not None and self.mode == 'plutonium-zm'
                  and ZOMBIES_DLC_LOAD.search(line)):
                # Zombies can still be loading DLC after common_zm, with a
                # visible window that does not yet accept menu input.
                self.lobby_click_at = now + 5
                self.lobby_deadline = self.lobby_click_at + 20

    def poll_t5_zombies_lobby(self, display, now):
        dvars = self.t5_menu_dvars
        if dvars.get(b'zombiemode'):
            # The native menu action sets this read-only dvar. Only open the
            # lobby after the engine confirms it will load Zombies assets.
            if send_console_command(display, self.outer_display, T5_ZOMBIES_HOST_LOBBY):
                print(tr('Black Ops J1 : ouverture du salon demandée.'), flush=True)
                self.lobby_button = None
            return
        if b'zombiemode' in dvars and b'ui_skipmainlockout' in dvars:
            keys = ('Down', 'Return') if dvars[b'ui_skipmainlockout'] else ('Return',)
            if keys not in self.t5_menu_keys:
                if press_menu_keys(display, self.outer_display, keys):
                    self.t5_menu_keys.add(keys)
                    self.t5_menu_query = False
                    dvars.clear()
                    self.lobby_click_at = now + 2
                return
        if self.t5_menu_query:
            return
        self.t5_menu_query = send_console_command(display, self.outer_display, 'zombiemode; ui_skipMainLockout')
        self.lobby_click_at = now + 3

    def poll_lobby(self, now):
        if self.lobby_deadline is None or self.stop.is_set():
            return
        if now >= self.lobby_deadline:
            self.lobby_button = None
            print(tr('Black Ops II J1 : passage automatique au salon interrompu.'), flush=True)
            return
        if self.lobby_click_at is None or now < self.lobby_click_at:
            return
        display = automatic_path(self.host, self.token, 'display')
        if self.mode == 't5sp':
            self.poll_t5_zombies_lobby(display, now)
            return
        if self.mode in T5_LOBBY_COMMANDS:
            if send_console_command(display, self.outer_display, T5_LOBBY_COMMANDS[self.mode]):
                print(tr('Black Ops J1 : ouverture du salon demandée.'), flush=True)
                self.lobby_button = None
            return
        if not click_menu_button(display, self.outer_display, self.lobby_button):
            return
        if self.lobby_button == ONLINE_BUTTON:
            print(tr('Black Ops II J1 : clic sur En ligne envoyé.'), flush=True)
            self.lobby_button = CUSTOM_GAMES_BUTTONS[self.mode]
            self.lobby_click_at = None
            self.lobby_deadline = now + 20
        else:
            print(tr('Black Ops II J1 : clic sur Parties personnalisées envoyé.'), flush=True)
            self.lobby_button = None

    def poll(self, now):
        for path, line in self.host_output():
            if self.lobby_button is not None:
                self.observe_lobby(line, now)
            if self.guests and self.observe_host(line, now):
                # A runner can echo a frontend shutdown while the native
                # Wine tee reports the real map. Lock to the stream that
                # reports a match, once the first Zombies map is observed.
                if self.mode != 't5sp' or self.match_starting(line):
                    self.host_log = path
        if self.lobby_button is not None:
            self.poll_lobby(now)
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
            # T5 may not acknowledge a guest in the host log while it is loading
            # or even after it has joined. Avoid interrupting it with another connect.
            elif (self.mode not in T5_EXECUTABLES or attempts == 0) and join_window(
                    automatic_path(player, self.token, 'display'), self.outer_display):
                self.attempts[name] += 1
                self.retry_at[name] = now + 18
                print(tr('Black Ops II {p0} : connexion à la partie de J1 demandée.',
                         p0=player.name.upper()), flush=True)

    def run(self):
        while not self.stop.is_set() and (self.guests or self.lobby_button is not None):
            self.poll(time.monotonic())
            self.stop.wait(1)


def install_hook(base, rom, player):
    from partydeck_profiles import atomic_write, profile_path, read_profile

    if not profile_path(base, rom).exists():
        return
    profile = read_profile(base, rom)
    adapter = profile.get('adapter')
    if adapter not in PROFILE_KEYS:
        return
    settings = profile[PROFILE_KEYS[adapter]]
    binary = shutil.which('batocera-wine')
    if binary is None:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    mode = validate({'mode': os.environ.get(SESSION_MODE, settings['mode'])}, adapter)['mode']
    source = client_path(base, PLUTONIUM_MODES.get(mode)) or base / 'plutonium'
    hook = [sys.executable, str(base / 'partydeck_bo2.py'), '--language', settings['language']]
    counts = t5_bot_counts(settings | {'mode': mode})
    if player.name == 'j1' and counts:
        hook.extend(('--bots', *map(str, counts)))
    if player.name == 'j1' and mode == 't5sp' and settings['zombie_bots']:
        hook.extend(('--zombie-bots', str(settings['zombie_bots'])))
    hook.extend((str(player), str(source)))
    replacement = player / 'batocera-wine-bo2'
    log = None
    token = os.environ.get('PARTYDECK_SESSION_TOKEN', '')
    if mode in PLUTONIUM_MODES and re.fullmatch(r'[a-f0-9]{32}', token):
        log = automatic_path(player, token, 'log')
    atomic_write(replacement, instrument_native(binary.read_text(), hook, mode, log=log), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--language', choices=LANGUAGES, default='keep')
    parser.add_argument('--bots', type=int, nargs=4, default=())
    parser.add_argument('--zombie-bots', type=int, choices=T5_ZOMBIE_BOT_COUNTS, default=0)
    for field in ('player', 'source', 'mode', 'directory', 'root'):
        parser.add_argument(field)
    args = parser.parse_args()
    try:
        mode = validate({'mode': args.mode}, BO1 if args.mode in T5_EXECUTABLES else ADAPTER)['mode']
        cwd, command = prepare(Path(args.player), mode, Path(args.directory), Path(args.root), Path(args.source),
                               args.language, bot_counts=args.bots, zombie_bots=args.zombie_bots)
        if cwd is not None:
            if '\n' in str(cwd):
                raise ValueError(tr('Black Ops II : chemin redirigé dans la vue du joueur ({p0}).', p0=cwd))
            print(cwd, command, sep='\n')
    except (OSError, ValueError) as error:
        print(f'Windows Party / Black Ops II : {error}', file=sys.stderr)
        raise SystemExit(1)
