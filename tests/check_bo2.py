"""Exercise the native launcher contract and each supported client layout."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_bo2 as bo2
from partydeck_catalog import recipe_for
from partydeck_profiles import defaults, private_lan_enabled, profile_path, read_profile, save_profile

source = """
play_wine() {
    WINE_CMD='t6sp.exe -solo'
    WINE_DIR=drive_c/game
    if [[ -n "${WINE_LANG}" ]]; then
        (cd "${WINEPOINT}/${WINE_DIR}" && LC_ALL=${WINE_LANG} eval wine ${WINE_CMD})
    else
        (cd "${WINEPOINT}/${WINE_DIR}" && eval wine ${WINE_CMD})
    fi
    return 0
}
"""
source = (source + source.replace('play_wine', 'play_squashfs')
          + source.replace('play_wine', 'play_pc').replace('WINEPOINT', 'GAMENAME').replace('drive_c/game', ''))
source += """
wine() { printf '%s\\n' "$PWD" "$@"; }
WINEPOINT=$1
GAMENAME=$1
"$2"
"""

with TemporaryDirectory() as folder:
    base = Path(folder)
    for suffix in ('.wine', '.pc', '.wsquashfs'):
        rom = base / ('Call of Duty - Black Ops II [GE-Proton]' + suffix)
        assert recipe_for(rom).adapter == bo2.ADAPTER
        data = defaults(rom)
        assert private_lan_enabled(data, 2)
        assert not private_lan_enabled(data, 1)
        assert data['bo2'] == {'mode': 'plutonium-mp', 'horizontal_render': 'native', 'automatic_join': True,
                               'open_custom_lobby': False, 'language': 'keep'}
        for old_mode in ('mp', 'zm', 'original'):
            data['bo2'] = {'mode': old_mode}
            path = profile_path(base, rom)
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(data))
            expected_mode = old_mode if old_mode == 'original' else f'plutonium-{old_mode}'
            migrated = read_profile(base, rom)
            assert migrated['bo2'] == {'mode': expected_mode, 'horizontal_render': 'native', 'automatic_join': True,
                                       'open_custom_lobby': False, 'language': 'keep'}
            save_profile(base, rom, migrated)
            assert json.loads(path.read_text())['bo2']['mode'] == expected_mode
        migrated['bo2'].update(mode='plutonium-mp', open_custom_lobby=True, automatic_join=False, language='english')
        save_profile(base, rom, migrated)
        assert read_profile(base, rom)['bo2'] == migrated['bo2']
    assert defaults(base / 'BO2 Zombies.wsquashfs')['bo2']['mode'] == 'plutonium-zm'
    assert not bo2.matches(base / 'Black Ops III.wsquashfs')
    for title in ('Call of Duty - Black Ops', 'Black Ops 1', 'BO1 [GE-Proton]'):
        rom1 = base / f'{title}.wsquashfs'
        assert recipe_for(rom1).adapter == bo2.BO1
        profile = defaults(rom1)
        assert profile['bo1']['mode'] == 't5mp' and not profile['bo1']['vertical_native']
        assert profile['bo1']['vertical_fov'] == profile['bo1']['horizontal_fov'] == 0
        assert profile['bo1']['zombie_bots'] == 0
        assert private_lan_enabled(profile, 2) and not private_lan_enabled(profile, 1)
    assert defaults(base / 'BO1 Zombies.wsquashfs')['bo1']['mode'] == 't5sp'
    assert not bo2.matches_bo1(base / 'Black Ops Cold War.wsquashfs')
    assert not bo2.matches_bo1(base / 'Black Ops II.wsquashfs')

    native = base / 'batocera-wine'
    native.write_text(source)
    player = base / 'mode-hook' / 'j1'
    player.mkdir(parents=True)
    with patch.dict(os.environ, {bo2.SESSION_MODE: 'plutonium-zm'}), \
         patch.object(bo2.shutil, 'which', return_value=str(native)), \
         patch.object(bo2, 'client_path', return_value=None) as client, \
         patch.object(bo2.subprocess, 'run'):
        bo2.install_hook(base, rom, player)
        client.assert_called_once_with(base, 't6zm')
        assert "--language english" in (player / 'batocera-wine-bo2').read_text()
        assert "plutonium-zm" in (player / 'batocera-wine-bo2').read_text()
        assert read_profile(base, rom)['bo2']['mode'] == 'plutonium-mp'

    bo1_rom = base / 'Black Ops.wsquashfs'
    bo1_profile = defaults(bo1_rom)
    bo1_profile['bo1'].update(mode='t5sp', private_bots=5, allies_bots=2, axis_bots=4, zombie_bots=3)
    save_profile(base, bo1_rom, bo1_profile)
    with patch.object(bo2.shutil, 'which', return_value=str(native)), \
         patch.object(bo2, 'client_path', return_value=None), patch.object(bo2.subprocess, 'run'):
        for selected_mode, player_number, expected in (('t5mp', 'j1', True), ('t5mp', 'j2', False),
                                                       ('t5sp', 'j1', False), ('t5sp', 'j2', False)):
            slot = player.parent / player_number
            slot.mkdir(exist_ok=True)
            with patch.dict(os.environ, {bo2.SESSION_MODE: selected_mode}):
                bo2.install_hook(base, bo1_rom, slot)
            hook = (slot / 'batocera-wine-bo2').read_text()
            assert ('--bots 5 2 4 0' in hook) == expected
            assert ('--zombie-bots 3' in hook) == (selected_mode == 't5sp' and player_number == 'j1')

    installed_client = base / 'Plutonium from Windows'
    (installed_client / 'bin').mkdir(parents=True)
    (installed_client / 'games').mkdir()
    (installed_client / 'storage/t6').mkdir(parents=True)
    (installed_client / 'bin' / bo2.BOOTSTRAPPER).write_text('bootstrapper')
    (installed_client / 'games/t6mp.exe').write_text('multiplayer')
    (installed_client / 'games/t6zm.exe').write_text('zombies')
    (installed_client / 'storage/t6/players.cfg').write_text('seed')
    (installed_client / 'config.json').write_text('launcher config')

    for mode, exe in bo2.T5_EXECUTABLES.items():
        player = base / mode / 'j1'
        prefix = player / 'prefix'
        game = prefix / 'drive_c' / 'game'
        (game / 'zone' / 'french').mkdir(parents=True)
        (game / exe).touch()
        (game / 'binkw32.dll').touch()
        (game / 'localization.txt').write_bytes(b'english\r\n')
        (installed_client / 'games' / f'{mode}.exe').touch()
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player), PARTYDECK_SESSION_PLAYERS='2'):
            cwd, command = bo2.prepare(player, mode, game, prefix, installed_client, 'french')
        args = shlex.split(command)
        assert cwd == game / '.partydeck-plutonium'
        assert args[1:6] == [mode, r'C:\game', '-name', 'Player 1', '-lan']
        assert args[args.index('r_fullscreen') + 1] == '0'
        assert args[args.index('r_noborder') + 1] == '1'
        assert ['+set', 'loc_language', '1'] == args[args.index('loc_language') - 1:args.index('loc_language') + 2]
        assert ('sp_minplayers' in args) == (mode == 't5sp')
        assert 'developer' not in args
        assert 'con_minicon' not in args
        assert 'con_errormessagetime' not in args
        with patch.dict(os.environ, {'PARTYDECK_PRIVATE_PLAYER': str(player), 'PARTYDECK_SESSION_PLAYERS': '2',
                                    'PARTYDECK_PRIVATE_LAN_IP': '192.168.247.11', bo2.PUBLISH_DISPLAY: '1'}):
            _, private_command = bo2.prepare(player, mode, game, prefix, installed_client)
        assert ('+set developer 1' in private_command) == (mode == 't5sp')
        assert ('+set con_minicon 0' in private_command) == (mode == 't5sp')
        assert ('+set con_errormessagetime 0' in private_command) == (mode == 't5sp')
        assert (game / 'localization.txt').read_bytes() == b'french\r\n'

        configs = cwd / 'storage/t5/players'
        configs.mkdir(parents=True)
        file = configs / ('config_mp.cfg' if mode == 't5mp' else 'conLZM.cfg')
        old_fov = b'seta cg_fov_default "85"\r\n'
        new_fov = b'seta cg_fov_default "100"\r\nseta cg_fov "100"\r\n'
        other = b'seta cg_fovScale "1.25"\r\n'
        file.write_bytes(old_fov)
        with patch.dict(os.environ, {'PARTYDECK_PRIVATE_PLAYER': str(player), bo2.T5_FOV_OVERRIDE: '100'}):
            _, command = bo2.prepare(player, mode, game, prefix, installed_client)
        assert '+set cg_fov 100 +set cg_fov_default 100' in command
        file.write_bytes(new_fov + other)
        generated = configs / 'config.cfg'
        generated.write_bytes(new_fov + other)
        with patch.dict(os.environ, {'PARTYDECK_PRIVATE_PLAYER': str(player), bo2.T5_FOV_OVERRIDE: '105'}):
            _, command = bo2.prepare(player, mode, game, prefix, installed_client)
        assert '+set cg_fov 105 +set cg_fov_default 105' in command
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player)):
            _, command = bo2.prepare(player, mode, game, prefix, installed_client)
        assert 'cg_fov' not in command
        assert file.read_bytes() == other + old_fov
        assert generated.read_bytes() == other
        assert not (cwd / 'partydeck-t5-fov.json').exists()

    for mode, slot, enabled in (('t5mp', 'j1', True), ('t5mp', 'j2', False), ('t5sp', 'j1', False)):
        player = base / 'bots' / slot
        prefix = player / 'prefix'
        game = prefix / 'drive_c' / 'game'
        game.mkdir(parents=True, exist_ok=True)
        (game / bo2.T5_EXECUTABLES[mode]).touch()
        (game / 'binkw32.dll').touch()
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player)):
            cwd, _ = bo2.prepare(player, mode, game, prefix, installed_client, bot_counts=(5, 2, 4, 0))
            script = cwd / 'storage/t5/scripts/mp/partydeck_bots.gsc'
            assert script.is_file() == enabled
            if enabled:
                code = script.read_text()
                for line in ('if (!level.teambased)', 'targets[0] = 2;', 'targets[1] = 4;',
                             'fill_bots("free", 5 - bots.size);', 'total = 0;',
                             'bot = AddTestClient();', '::changeTeam(team);', '::bot_spawn_think(team);'):
                    assert line in code
                bo2.prepare(player, mode, game, prefix, installed_client, bot_counts=(5, 0, 0, 6))
                code = script.read_text()
                assert 'total = 6;' in code
                assert 'targets[0] = 0;' in code
                assert 'targets[1] = 0;' in code
                # T5 supports subtraction here, not prefix negation of a variable.
                assert not re.search(r'[(,=]\s*-[a-zA-Z_]', code)
                bo2.prepare(player, mode, game, prefix, installed_client)
                assert not script.exists()

    for humans, slot, expected in (('1', 'j1', 3), ('2', 'j1', 2), ('3', 'j1', 1),
                                    ('4', 'j1', 0), ('2', 'j2', 0)):
        player = base / 'zombie-bots' / slot
        prefix = player / 'prefix'
        game = prefix / 'drive_c' / 'game'
        game.mkdir(parents=True, exist_ok=True)
        (game / bo2.T5_EXECUTABLES['t5sp']).touch()
        (game / 'binkw32.dll').touch()
        old_script = game / '.partydeck-plutonium/storage/t5/scripts' / bo2.T5_ZOMBIE_BOT_SCRIPT
        old_script.parent.mkdir(parents=True, exist_ok=True)
        old_script.write_text('previous global script')
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player), PARTYDECK_SESSION_PLAYERS=humans):
            cwd, command = bo2.prepare(player, 't5sp', game, prefix, installed_client, zombie_bots=3)
        assert not old_script.exists()
        script = cwd / 'storage/t5/scripts/sp/zom' / bo2.T5_ZOMBIE_BOT_SCRIPT
        assert script.is_file() == bool(expected)
        if expected:
            code = script.read_text()
            assert 'MIT License' in code and 'reee23463-debug' in code
            assert 'while(bo1bots_humans_connected() < humans && gettime() < deadline)' in code
            assert set(re.findall(r'\bbo1_(?:on|off)\("([^"]+)"\)', code)) == {
                'activate', 'ads', 'attack', 'frag', 'gostand', 'melee', 'reload', 'smoke', 'sprint',
            }
            assert re.findall(r'\bbotaction\(([^)]*)\)', code) == ['"+" + n', '"-" + n']
            assert f'+set bo1_bots_count {expected}' in command
            assert f'+set partydeck_bo1_humans {humans}' in command
            assert f'+set sp_minplayers {humans}' in command
        else:
            assert 'bo1_bots_count' not in command

    player = base / 't5mp' / 'j1'
    prefix = player / 'prefix'
    game = prefix / 'drive_c' / 'game'
    # A shared BO1 installation may have all MP data beside the campaign
    # executable even when the original BlackOpsMP.exe is absent.
    (game / bo2.T5_EXECUTABLES['t5mp']).unlink()
    (game / bo2.T5_EXECUTABLES['t5sp']).touch()
    common = game / 'zone' / 'common'
    common.mkdir()
    (common / 'common_mp.ff').touch()
    with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player)):
        try:
            bo2.prepare(player, 't5mp', game, prefix, installed_client)
        except ValueError as error:
            assert 'ui_mp.ff' in str(error)
        else:
            raise AssertionError('Expected incomplete T5 multiplayer data to be reported')
        (common / 'ui_mp.ff').touch()
        cwd, command = bo2.prepare(player, 't5mp', game, prefix, installed_client)
    assert cwd == game / '.partydeck-plutonium'
    assert shlex.split(command)[1:3] == ['t5mp', r'C:\game']
    assert not (game / bo2.T5_EXECUTABLES['t5mp']).exists()

    assert bo2.render_size(1920, 540) == (1280, 720)
    assert bo2.render_size(960, 1080) == (1280, 720)
    assert bo2.render_size(960, 540) == (1280, 720)
    assert bo2.render_size(1920, 1080) == (1920, 1080)
    assert bo2.render_size(1920, 540, horizontal_render='720p') == (2560, 720)
    assert bo2.render_size(2560, 720, horizontal_render='720p') == (2560, 720)
    assert bo2.render_size(3840, 1080, horizontal_render='720p') == (3840, 1080)
    assert bo2.render_size(1366, 384, horizontal_render='720p') == (2561, 720)
    assert bo2.render_size(1920, 540, horizontal_render='native') == (1920, 540)
    assert bo2.desktop_size(1920, 540) == (2560, 720)
    assert bo2.desktop_size(800, 600) == (800, 600)
    assert bo2.desktop_size(2560, 720) == (2560, 720)
    assert bo2.validate({'mode': 'plutonium-mp', 'fill_horizontal': False})['horizontal_render'] == 'standard'
    assert bo2.validate({'mode': 'plutonium-zm', 'fill_horizontal': True})['horizontal_render'] == 'native'

    hits = []
    for player_name, entry, tag in (('j1', 'play_wine', 't6zm'),
                                    ('j2', 'play_squashfs', 't6mp'),
                                    ('j3', 'play_pc', 't6mp')):
        player = base / player_name
        player.mkdir()
        prefix = player / "Wine's prefix & game"
        game = prefix if entry == 'play_pc' else prefix / 'drive_c/game'
        settings = game / 'STEAM_SETTINGS'
        settings.mkdir(parents=True)
        for exe in ('t6sp.exe', 't6sp_o.exe', 'T6MP.EXE', 't6zm.exe'):
            (game / exe).touch()
        bink = game / 'BINKW32.DLL'
        bink.write_bytes(b'_BinkWaitStopAsyncThread@4\0')
        ini = settings / 'configs.user.ini'
        ini.write_text('[user::general]\naccount_steamid=0\nlanguage=french\n')
        (settings / 'force_steamid.txt').write_text('0\n')
        hook = [sys.executable, str(Path(bo2.__file__)), str(player), str(installed_client)]
        launcher = player / 'native.sh'
        launcher.write_text(bo2.instrument_native(source, hook, 'original'))
        resolution = '1920x540' if entry == 'play_squashfs' else '1280x720'
        env = dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player),
                   WINE_LANG='C' if entry == 'play_squashfs' else '', PARTYDECK_BO2_RESOLUTION=resolution)
        env[bo2.DESKTOP_MODE] = '2560x720' if entry == 'play_squashfs' else resolution
        command = ['bash', str(launcher), str(prefix), entry]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
        assert result.stdout.splitlines() == [str(game), 't6sp.exe', '-solo']
        steamid = (settings / 'force_steamid.txt').read_text().strip()
        assert steamid in ini.read_text() and 'language=french' in ini.read_text()
        hits.append(steamid)

        pluto_mode = 'plutonium-' + tag[2:]
        player_log = player / 'only this player.log'
        launcher.write_text(bo2.instrument_native(source, hook, pluto_mode, log=player_log))
        subprocess.run(['bash', '-n', str(launcher)], check=True)
        env['PARTYDECK_SESSION_PLAYERS'] = '2'
        env[bo2.PUBLISH_DISPLAY] = '1'
        for locale in ('english', 'french'):
            (game / 'zone' / locale).mkdir(parents=True)
        localization = game / 'localization.txt'
        localization.write_bytes(b'french\r\nenglish\r\n')
        original = b'french\r\n\r\n"Param\xe8tres"\r\n'
        for language_file in ('localization_mp.txt', 'localization_zm.txt'):
            (game / language_file).write_bytes(original)
        launcher.write_text(bo2.instrument_native(source, hook[:2] + ['--language', 'english'] + hook[2:],
                                                  pluto_mode, log=player_log))
        launched = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
        assert localization.read_bytes() == b'english\r\nenglish\r\n'
        for suffix in ('mp', 'zm'):
            expected = original.replace(b'french', b'english', 1) if suffix == tag[2:] else original
            assert (game / f'localization_{suffix}.txt').read_bytes() == expected
        runtime = game / '.partydeck-plutonium'
        windows_game = 'Z:' + str(game).replace('/', chr(92)) if entry == 'play_pc' else r'C:\game'
        expected_pluto = [str(runtime), './bin/' + bo2.BOOTSTRAPPER, tag, windows_game,
                          '+name', f'Player {player_name[1]}', '-lan']
        if entry == 'play_squashfs':
            expected_pluto += ['+set', 'r_fullscreen', '0', '+set', 'r_mode', '2560x720',
                               '+set', 'r_customMode', '1920x540', '+set', 'r_aspectRatio', 'auto',
                               '+set', 'vid_xpos', '0', '+set', 'vid_ypos', '0']
        else:
            expected_pluto += ['+set', 'r_fullscreen', '2', '+set', 'r_mode', '1280x720',
                               '+set', 'r_customMode', '1280x720', '+set', 'r_aspectRatio', 'auto']
        expected_pluto += ['+set', 'net_port', str(bo2.HOST_PORT + int(player_name[1]) - 1)]
        if player_name == 'j1':
            expected_pluto += ['+set', 'sp_minplayers', '2']
        else:
            assert bo2.JOIN_HOST in launched.stderr
        assert launched.stdout.splitlines() == expected_pluto
        assert player_log.read_text() == launched.stdout
        assert windows_game in launched.stderr
        assert bink.read_bytes() == b'_BinkWaitStopAsyncThread@4\0'
        assert (runtime / 'games' / f'{tag}.exe').is_file()
        assert not (runtime / 'config.json').exists()
        settings_copy = runtime / 'storage/t6/players.cfg'
        settings_copy.write_text('private')
        bink.write_bytes(b'bad DLL')
        retried = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
        assert 'BINKW32.DLL' in retried.stderr
        assert settings_copy.read_text() == 'private'
        assert (installed_client / 'storage/t6/players.cfg').read_text() == 'seed'
        bink.unlink()
        failed = subprocess.run(command, capture_output=True, text=True, env=env)
        assert failed.returncode == 1 and not failed.stdout and 'binkw32.dll' in failed.stderr
    assert len(set(hits)) == 3

    game = base / 'nova'
    plugins = game / 'Ayria/Plugins'
    plugins.mkdir(parents=True)
    (plugins / 'Localnetworking.Ayria32').touch()
    assert bo2.configure_client(game, base / 'j4') == 'Project Nova'
    platform = game / 'Ayria/Assets/Platformwrapper'
    assert (platform / 'Username.txt').read_text().strip() == 'Player 4'
    assert (platform / 'UserID.txt').read_text().strip().isdecimal()

    classic = base / 'classic'
    (classic / 'steam_settings').mkdir(parents=True)
    assert bo2.configure_client(classic, base / 'j1') == 'Goldberg'
    assert (classic / 'steam_settings/force_steamid.txt').read_text().strip() == hits[0]

    with patch.dict(os.environ, {'PARTYDECK_PRIVATE_PLAYER': str(base / 'j1')}):
        try:
            bo2.prepare(base / 'j1', 'plutonium-mp', classic, game, installed_client)
        except ValueError:
            pass
        else:
            raise AssertionError('Expected rejection outside the private content root')

    outside = base / 'outside'
    outside.write_text('unchanged')
    redirected = classic / 'steam_settings/force_account_name.txt'
    redirected.unlink()
    redirected.symlink_to(outside)
    try:
        bo2.configure_client(classic, base / 'j1')
    except ValueError:
        assert outside.read_text() == 'unchanged'
    else:
        raise AssertionError('Expected rejection of a redirected identity file')

with TemporaryDirectory() as folder:
    base = Path(folder)
    players = [base / 'j1', base / 'j2', base / 'j3']
    host, guest, other = players
    for player in players:
        player.mkdir()
    token = '1' * 32
    log = bo2.automatic_path(host, token, 'log')
    display = bo2.automatic_path(guest, token, 'display')
    initialization = b'------- Game Initialization -------\n'
    t5_frontend_initialization = (b"------ Server Initialization ------\nServer: frontend\n"
                                  + initialization + b'Going from CS_CONNECTED to CS_CLIENTLOADING for Player 1\n')
    t5_zombies_initialization = b'------ Server Initialization ------\nServer: zombie_theater\n'
    log.write_bytes(b'Loading fastfile code_post_gfx_mp\nCould not load image "$lineargray".\n')
    assert not bo2.startup_ready(host, token, 0, 't6mp')
    with log.open('ab') as stream:
        stream.write(b"Loading fastfile 'common_mp'\n")
    assert bo2.startup_ready(host, token, 0, 't6mp')
    assert not bo2.startup_ready(host, token, 0, 't6zm')
    for title in ('Plutonium T6 Multiplayer (r5369 LAN)', 'Plutonium T6: Zombies',
                  'Plutonium T6 MP', 'Call of Duty(R): Black Ops II - Multiplayer'):
        assert re.search(bo2.GAME_WINDOW, title, re.I), title
    assert not re.search(bo2.GAME_WINDOW, 'Plutonium T6 Console (r5369)', re.I)
    assert re.search(bo2.GAME_WINDOW, 'Plutonium T5 Singleplayer (r5369)', re.I)
    assert re.search(bo2.GAME_WINDOW, 'Plutonium T5 Multiplayer (r5369)', re.I)
    assert re.search(bo2.GAME_WINDOW, 'Plutonium T5 Campaign (r5369 LAN)', re.I)
    assert re.search(bo2.GAME_WINDOW, 'Plutonium T5 Co-Op (r5369) (LAN)', re.I)
    assert not re.search(bo2.GAME_WINDOW, 'Plutonium T5 Console (r5369)', re.I)
    assert 't5sp' not in bo2.T5_LOBBY_COMMANDS
    for mode in ('t5sp', 't5mp', 'plutonium-mp', 'plutonium-zm', 'original'):
        for private_lan in (True, False):
            enabled = bo2.custom_lobby_enabled({'mode': mode, 'open_custom_lobby': True}, private_lan)
            assert enabled is (mode in ('t5sp', 't5mp') or (private_lan and mode.startswith('plutonium-')))
    assert len(bo2.T5_LOBBY_COMMANDS['t5mp']) < 256
    assert bo2.t5_bot_counts(bo2.validate({'mode': 't5mp'}, bo2.BO1)) == ()
    assert bo2.t5_bot_counts(bo2.validate(
        {'mode': 't5mp', 'private_bots': 5, 'allies_bots': 2, 'axis_bots': 4}, bo2.BO1)) == (5, 2, 4, 0)
    assert bo2.t5_bot_counts(bo2.validate(
        {'mode': 't5mp', 'private_bots': 5, 'allies_bots': 2, 'axis_bots': 4, 'team_total_bots': 6},
        bo2.BO1)) == (5, 0, 0, 6)
    assert bo2.t5_bot_counts({'mode': 't5sp', 'private_bots': 5}) == ()
    for mode, asset in (('t5mp', 'plutonium_ui_mp'),):
        log.write_bytes(b"Loading fastfile 'common_mp'\n")
        t5 = bo2.AutoJoin([host, guest], token, mode, ':0', 0, open_custom_lobby=True)
        with patch.object(bo2, 'send_console_command', return_value=True) as send, \
             patch.object(bo2, 'join_window', return_value=True) as join:
            t5.poll(1)
            t5.poll(6)
            send.assert_not_called()
            with log.open('ab') as stream:
                stream.write(f"Loading fastfile '{asset}'\n".encode())
            t5.poll(7)
            t5.poll(12)
            if mode == 't5mp':
                send.assert_called_once_with(bo2.automatic_path(host, token, 'display'), ':0',
                                             bo2.T5_LOBBY_COMMANDS[mode])
            else:
                send.assert_not_called()
            join.assert_not_called()
            with log.open('ab') as stream:
                stream.write(t5_zombies_initialization if mode == 't5sp' else initialization)
            t5.poll(13)
            t5.poll(15)
            join.assert_called_once()
            t5.poll(34)
            with log.open('ab') as stream:
                stream.write(t5_zombies_initialization if mode == 't5sp' else initialization)
            t5.poll(35)
            t5.poll(37)
            join.assert_called_once()
            with log.open('ab') as stream:
                stream.write(b'----- Server Shutdown -----\n'
                             + (t5_zombies_initialization if mode == 't5sp' else initialization))
            t5.poll(40)
            t5.poll(42)
            assert join.call_count == 2
    # Never open a private lobby after merely issuing a key. The native
    # Zombies action must be confirmed by reading the engine's mode.
    t5 = bo2.AutoJoin([host], token, 't5sp', ':0', 0, open_custom_lobby=True)
    host_display = bo2.automatic_path(host, token, 'display')
    log.write_bytes(b"Loading fastfile 'plutonium_ui'\n")
    mode_off = b'"zombiemode" is: "0^7" default: "0^7"\n'
    title = b'"ui_skipMainLockout" is: "0^7"\n'
    menu = title.replace(b'"0^7"', b'"1^7"')
    with patch.object(bo2, 'send_console_command', return_value=True) as send, \
         patch.object(bo2, 'press_menu_keys', return_value=True) as keys:
        t5.poll(1)
        t5.poll(6)
        query = call(host_display, ':0', 'zombiemode; ui_skipMainLockout')
        assert send.call_args_list == [query]
        for now in (9, 12, 15):
            t5.poll(now)
        assert send.call_args_list == [query]
        with log.open('ab') as stream:
            stream.write(mode_off + title)
        t5.poll(16)
        keys.assert_called_once_with(host_display, ':0', ('Return',))
        t5.poll(18)
        with log.open('ab') as stream:
            stream.write(mode_off + menu)
        t5.poll(21)
        assert keys.call_args_list[-1] == call(host_display, ':0', ('Down', 'Return'))
        t5.poll(23)
        with log.open('ab') as stream:
            stream.write(mode_off.replace(b'is: "0^7"', b'is: "1^7"'))
        t5.poll(26)
        assert send.call_args_list == [query, query, query, call(host_display, ':0', bo2.T5_ZOMBIES_HOST_LOBBY)]
    assert 'set zombiemode' not in bo2.T5_ZOMBIES_HOST_LOBBY
    for marker in (b'LOADING... maps/zombie_theater.d3dbsp', rb'g_gametype\zom\mapname\zombie_theater\protocol'):
        assert t5.match_starting(marker)
    for marker in (b'LOADING... maps/frontend.d3dbsp', rb'g_gametype\cmp\mapname\frontend\protocol',
                   b'Loading fastfile zombie_theater_patch'):
        assert not t5.match_starting(marker)

    # Replay the terminal bytes from the Batocera T5 Zombies journal.
    color = b'\x1b[38;2;255;255;255m'
    redraw = color + b'\r\x1b[2K' + color
    initial = b"Loading fastfile 'plutonium_ui'\r\n"
    log.write_bytes(redraw + initial)
    assert bo2.startup_ready(host, token, 0, 't5sp')
    t5 = bo2.AutoJoin([host, guest], token, 't5sp', ':0', 0, open_custom_lobby=True)
    with patch.object(bo2, 'send_console_command', return_value=True) as send, \
         patch.object(bo2, 'press_menu_keys', return_value=True) as keys, \
         patch.object(bo2, 'join_window', return_value=True) as join:
        t5.poll(1)
        t5.poll(6)
        with log.open('ab') as stream:
            stream.write(redraw + b'"zombiemode" is: "0' + color + b'" default: "0' + color + b'"\r\n')
            stream.write(redraw + b'"ui_skipMainLockout" is: "1' + color + b'" default: "0' + color + b'"\r\n')
        t5.poll(9)
        keys.assert_called_once_with(host_display, ':0', ('Down', 'Return'))
        t5.poll(11)
        with log.open('ab') as stream:
            stream.write(redraw + b'"zombiemode" is: "1' + color + b'" default: "0' + color + b'"\r\n')
        t5.poll(14)
        assert send.call_args_list == [query, query, call(host_display, ':0', bo2.T5_ZOMBIES_HOST_LOBBY)]
        join.assert_not_called()
        with log.open('ab') as stream:
            stream.write(redraw + b'Server: zombie_theater\r\n')
            stream.write(redraw + b'LOADING... maps/zombie_theater.d3dbsp\r\n')
        t5.poll(20)
        t5.poll(22)
        join.assert_called_once_with(display, ':0')
        with log.open('ab') as stream:
            stream.write(redraw + b'Going from CS_CONNECTED to CS_CLIENTLOADING for Player 2\r\n')
        t5.poll(23)
        assert t5.connected == {'j2'}

    with patch.object(bo2, 'join_window', return_value=True) as join:
        t5 = bo2.AutoJoin([host, guest], token, 't5sp', ':0', 0)
        log.write_bytes(b'Loading fastfile plutonium_ui\n' + b' ' * 1100000)
        t5.poll(1)
        with log.open('ab') as stream:
            stream.write(b'\rServer: zombie_theater\r')
        t5.poll(2)
        t5.poll(3)
        t5.poll(5)
        join.assert_called_once_with(display, ':0')
    with patch.object(bo2, 'join_window', return_value=True) as join:
        t5 = bo2.AutoJoin([host, guest], token, 't5sp', ':0', 0)
        log.write_bytes(t5_frontend_initialization * 20)
        t5.poll(1)
        log.write_bytes(t5_zombies_initialization)
        t5.poll(2)
        t5.poll(4)
        join.assert_called_once_with(display, ':0')
    with patch.object(bo2, 'join_window', return_value=True) as join:
        t5 = bo2.AutoJoin([host, guest], token, 't5sp', ':0', 0)
        # UMU may log only the end of a frontend while the Wine tee records gameplay.
        runner_log = host / 'umu-logs/runner-frontend.log'
        runner_log.parent.mkdir(exist_ok=True)
        runner_log.write_bytes(b'----- Server Shutdown -----\n' + t5_frontend_initialization)
        log.write_bytes(b'')
        t5.poll(1)
        assert t5.host_log is None
        with log.open('ab') as stream:
            stream.write(b'LOADING... maps/zombie_theater.d3dbsp\n')
        t5.poll(3)
        t5.poll(5)
        join.assert_called_once_with(display, ':0')
        assert t5.host_log == log
        runner_log.unlink()
        runner_log.parent.rmdir()
    with patch.object(bo2, 'join_window', return_value=True) as join:
        t5 = bo2.AutoJoin([host, guest], token, 't5sp', ':0', 0)
        log.write_bytes(b"Loading fastfile 'plutonium_ui'\n" + t5_frontend_initialization)
        t5.poll(1)
        t5.poll(7)
        join.assert_not_called()
        with log.open('ab') as stream:
            stream.write(t5_zombies_initialization)
        t5.poll(8)
        t5.poll(10)
        join.assert_called_once_with(display, ':0')
        # A slow guest can be loading long after the T6 retry interval.
        t5.poll(28)
        with log.open('ab') as stream:
            stream.write(t5_zombies_initialization)
        t5.poll(29)
        t5.poll(31)
        join.assert_called_once_with(display, ':0')
        with log.open('ab') as stream:
            stream.write(b'Going from CS_CONNECTED to CS_CLIENTLOADING for Player 2\n')
        t5.poll(49)
        join.assert_called_once_with(display, ':0')
        assert t5.connected == {'j2'}
        with log.open('ab') as stream:
            stream.write(b'----- Server Shutdown -----\n' + t5_frontend_initialization)
        t5.poll(52)
        t5.poll(54)
        join.assert_called_once_with(display, ':0')
        with log.open('ab') as stream:
            stream.write(b'----- Server Shutdown -----\n'
                         b'------ Server Initialization ------\nServer: zombie_coast\n')
        t5.poll(55)
        t5.poll(57)
        assert join.call_args_list == [call(display, ':0'), call(display, ':0')]
    log.write_bytes(b"Loading fastfile 'common_mp'\n")
    display.write_text(json.dumps({'DISPLAY': ':0.0'}))
    with patch.object(bo2.subprocess, 'run') as run:
        assert not bo2.join_window(display, ':0')
        run.assert_not_called()
        display.write_text(json.dumps({'DISPLAY': ':2', 'XAUTHORITY': '/tmp/player-auth'}))
        run.side_effect = [Mock(returncode=0, stdout='2518\n2718\n')]
        assert not bo2.join_window(display, ':0')
        assert run.call_count == 1
        run.reset_mock()

        def guest_xdotool(command, **kwargs):
            if command[1] != 'search':
                return Mock(returncode=0)
            windows = {'2718': 'Plutonium T5 Co-Op (r5369) (LAN)',
                       '2518': 'Plutonium T5 Console (r5369)'}
            matches = [wid for wid, title in windows.items() if re.search(command[-1], title, re.I)]
            return Mock(returncode=0 if matches else 1, stdout='\n'.join(matches))

        run.side_effect = guest_xdotool
        assert bo2.join_window(display, ':0')
        search, focus, typing, submit = run.call_args_list
        assert search.args[0] == ['xdotool', 'search', '--onlyvisible', '--name', bo2.GAME_WINDOW]
        assert focus.args[0] == ['xdotool', 'windowfocus', '--sync', '2718', 'sleep', '0.2',
                                 'key', '--clearmodifiers', '49', 'sleep', '0.3']
        assert typing.args[0] == ['xdotool', 'type', '--clearmodifiers', '--delay', '20', bo2.JOIN_HOST]
        assert submit.args[0] == ['xdotool', 'key', '--clearmodifiers', '--delay', '50', 'Return', '49']
        assert all(call.kwargs['env']['DISPLAY'] == ':2' and
                   call.kwargs['env']['XAUTHORITY'] == '/tmp/player-auth' for call in run.call_args_list)

    host_display = bo2.automatic_path(host, token, 'display')
    host_display.write_text(json.dumps({'DISPLAY': ':1'}))
    with patch.object(bo2.subprocess, 'run') as run:
        run.side_effect = [Mock(returncode=0, stdout='2718\n'), Mock(stdout='WIDTH=2560\nHEIGHT=720\n'), Mock()]
        assert bo2.click_menu_button(host_display, ':0', bo2.ONLINE_BUTTON)
        assert run.call_args.args[0] == ['xdotool', 'windowfocus', '--sync', '2718',
                                        'mousemove', '--window', '2718', '891', '435',
                                        'sleep', '0.2', 'click', '1']
        assert all(item.kwargs['env']['DISPLAY'] == ':1' for item in run.call_args_list)
        run.reset_mock()
        run.side_effect = [Mock(returncode=0, stdout='2718\n'), Mock(stdout='WIDTH=1280\nHEIGHT=720\n'), Mock()]
        assert bo2.click_menu_button(host_display, ':0', bo2.CUSTOM_GAMES_BUTTONS['plutonium-zm'])
        assert run.call_args.args[0] == ['xdotool', 'windowfocus', '--sync', '2718',
                                        'mousemove', '--window', '2718', '293', '180',
                                        'sleep', '0.2', 'click', '1']
        run.reset_mock()
        run.side_effect = [Mock(returncode=0, stdout='2718\n'), Mock(stdout='WIDTH=960\nHEIGHT=1080\n')]
        assert not bo2.click_menu_button(host_display, ':0', bo2.ONLINE_BUTTON)
        assert run.call_count == 2

    with patch.object(bo2, 'click_menu_button', return_value=True) as click:
        online_click = call(host_display, ':0', bo2.ONLINE_BUTTON)
        custom_click = call(host_display, ':0', bo2.CUSTOM_GAMES_BUTTONS['plutonium-mp'])
        startup = log.read_bytes()
        observer = bo2.AutoJoin(players, token, 'plutonium-mp', ':0', 0, open_custom_lobby=True)
        observer.poll(1)
        observer.poll(5)
        click.assert_not_called()
        observer.poll(6)
        observer.poll(7)
        assert click.call_args_list == [online_click]
        log.write_bytes(startup + b'Unknown command "session_rejoinsession"\n')
        observer.poll(8)
        observer.poll(9)
        observer.poll(10)
        assert click.call_args_list == [online_click, custom_click]

        observer = bo2.AutoJoin(players, token, 'plutonium-mp', ':0', 0, open_custom_lobby=True)
        observer.poll(1)
        observer.poll(7)
        assert click.call_count == 2  # J1 already opened the online menu.
        log.write_bytes(startup)
        observer = bo2.AutoJoin(players, token, 'plutonium-mp', ':0', 0, open_custom_lobby=True)
        observer.poll(1)
        observer.poll(6)
        observer.poll(26)
        assert observer.lobby_button is None
        assert click.call_args_list == [online_click, custom_click, online_click]

        click.reset_mock()
        observer = bo2.AutoJoin([host], token, 'plutonium-zm', ':0', 0, open_custom_lobby=True)
        observer.poll(1)
        observer.poll(7)
        click.assert_not_called()  # Multiplayer startup is not a Zombies signal.
        with log.open('ab') as stream:
            stream.write(b'Loading fastfile common_zm\n')
        observer.poll(8)
        with log.open('ab') as stream:
            stream.write(b'Loading fastfile fr_seasonpass_load_zm\n')
        observer.poll(12)
        observer.poll(13)
        click.assert_not_called()
        observer.poll(17)
        with log.open('ab') as stream:
            stream.write(b'Unknown command: "session_rejoinsession"\n')
        observer.poll(18)
        observer.poll(19)
        assert click.call_args_list == [online_click,
            call(host_display, ':0', bo2.CUSTOM_GAMES_BUTTONS['plutonium-zm'])]

    with patch.object(bo2, 'join_window', return_value=True) as join:
        observer = bo2.AutoJoin(players, token, 'plutonium-mp', ':0', 0)
        log.write_bytes(initialization)
        observer.poll(1)
        join.assert_not_called()
        with log.open('ab') as stream:
            stream.write(b"client 'Player 1' connected\nclient 'Player 3' connected")
        observer.poll(2)
        with log.open('ab') as stream:
            stream.write(b'\n')
        observer.poll(4)
        join.assert_called_once_with(display, ':0')
        observer.poll(10)
        assert join.call_count == 1
        with log.open('ab') as stream:
            stream.write(b"client 'Player 2' connected\n")
        observer.poll(30)

        # A delayed UMU copy can't replay old match events. Rotation keeps
        # connected guests in the match, while leaving it suppresses retries.
        (host / 'umu-logs').mkdir()
        runner_log = host / 'umu-logs/runner-session.log'
        runner_log.write_bytes(b'SV_Shutdown: EXE_SERVERQUIT\n')
        with log.open('ab') as stream:
            stream.write(b'==== ShutdownGame (1) ====\n' + initialization)
        observer.poll(35)
        observer.poll(37)
        with log.open('ab') as stream:
            stream.write(b"client 'Player 2' disconnected\n")
        observer.poll(40)
        join.assert_called_once_with(display, ':0')

        # A new private match re-arms every guest that is no longer connected.
        with log.open('ab') as stream:
            stream.write(b"SV_Shutdown: EXE_SERVERQUIT\n==== ShutdownGame (1) ====\n")
        observer.poll(45)
        with log.open('ab') as stream:
            stream.write(initialization)
        observer.poll(50)
        observer.poll(55)
        join.assert_called_once_with(display, ':0')
        with log.open('ab') as stream:
            stream.write(b"client 'Player 1' connected\nclient 'Player 3' connected\n")
        observer.poll(60)
        observer.poll(62)
        assert join.call_args_list == [call(display, ':0'), call(display, ':0')]
        with log.open('ab') as stream:
            stream.write(b"client 'Player 2' connected\n")
        observer.poll(64)
        assert observer.connected == {'j1', 'j2', 'j3'}
        runner_log.unlink()

    with patch.object(bo2, 'join_window', return_value=True) as join:
        observer = bo2.AutoJoin([host, guest], token, 'plutonium-zm', ':0', 0)
        log.write_bytes(initialization)
        for now in (1, 3, 21, 39, 57, 65):
            observer.poll(now)
        assert join.call_count == 3
        with log.open('ab') as stream:
            stream.write(b'SV_Shutdown: EXE_SERVERQUIT\n' + initialization)
        observer.poll(66)
        observer.poll(68)
        assert join.call_count == 4

    with patch.object(bo2, 'join_window', return_value=False) as join:
        observer = bo2.AutoJoin([host, guest], token, 'plutonium-mp', ':0', 0)
        log.write_bytes(b"client 'Player 1' connected\n")
        for now in (1, 3, 93, 94):
            observer.poll(now)
        join.assert_called_once_with(display, ':0')
        assert observer.attempts['j2'] == 4

    with patch.object(bo2, 'join_window', return_value=True) as join:
        observer = bo2.AutoJoin([host, guest], token, 'plutonium-mp', ':0', 0)
        log.write_bytes(b'Preparing UMU\n')
        runner_log.write_bytes(initialization + b"client 'Player 1' connected\n")
        with runner_log.open('ab') as stream:
            stream.write(b'Loading fastfile common_zm\n')
        assert bo2.startup_ready(host, token, runner_log.stat().st_mtime_ns, 't6zm')
        assert not bo2.startup_ready(host, token, runner_log.stat().st_mtime_ns + 1, 't6zm')
        observer.poll(1)
        observer.poll(3)
        with runner_log.open('ab') as stream:
            stream.write(b"client 'Player 2' connected\nclient 'Player 1' disconnected\n"
                         + initialization + b"client 'Player 1' connected\n")
        observer.poll(5)
        observer.poll(7)
        assert join.call_args_list == [call(display, ':0'), call(display, ':0')]

print('BO2: profile migration, absolute Plutonium paths, Bink diagnostics, original autorun, private identities and automatic join verified.')
