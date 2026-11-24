"""Exercise the native launcher contract and each supported client layout."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

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
        assert data['bo2'] == {'mode': 'plutonium-mp'}
        for old_mode in ('mp', 'zm', 'original'):
            data['bo2']['mode'] = old_mode
            path = profile_path(base, rom)
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(data))
            expected_mode = old_mode if old_mode == 'original' else f'plutonium-{old_mode}'
            migrated = read_profile(base, rom)
            assert migrated['bo2'] == {'mode': expected_mode}
            save_profile(base, rom, migrated)
            assert json.loads(path.read_text())['bo2']['mode'] == expected_mode
    assert defaults(base / 'BO2 Zombies.wsquashfs')['bo2']['mode'] == 'plutonium-zm'
    assert not bo2.matches(base / 'Black Ops III.wsquashfs')

    installed_client = base / 'Plutonium from Windows'
    (installed_client / 'bin').mkdir(parents=True)
    (installed_client / 'games').mkdir()
    (installed_client / 'storage/t6').mkdir(parents=True)
    (installed_client / 'bin' / bo2.BOOTSTRAPPER).write_text('bootstrapper')
    (installed_client / 'games/t6mp.exe').write_text('multiplayer')
    (installed_client / 'games/t6zm.exe').write_text('zombies')
    (installed_client / 'storage/t6/players.cfg').write_text('seed')
    (installed_client / 'config.json').write_text('launcher config')

    assert bo2.render_size(1920, 540) == (1280, 720)
    assert bo2.render_size(960, 1080) == (1280, 720)
    assert bo2.render_size(960, 540) == (1280, 720)
    assert bo2.render_size(1920, 1080) == (1920, 1080)

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
        ini.write_text('[user::general]\naccount_steamid=76561197960265729\nlanguage=french\n')
        (settings / 'force_steamid.txt').write_text('76561197960265729\n')
        hook = [sys.executable, str(Path(bo2.__file__)), str(player), str(installed_client)]
        launcher = player / 'native.sh'
        launcher.write_text(bo2.instrument_native(source, hook, 'original'))
        env = dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player),
                   WINE_LANG='C' if entry == 'play_squashfs' else '', PARTYDECK_BO2_RESOLUTION='1280x720')
        command = ['bash', str(launcher), str(prefix), entry]
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
        assert result.stdout.splitlines() == [str(game), 't6sp.exe', '-solo']
        steamid = (settings / 'force_steamid.txt').read_text().strip()
        assert steamid in ini.read_text() and 'language=french' in ini.read_text()
        hits.append(steamid)

        pluto_mode = 'plutonium-' + tag[2:]
        launcher.write_text(bo2.instrument_native(source, hook, pluto_mode))
        subprocess.run(['bash', '-n', str(launcher)], check=True)
        env['PARTYDECK_SESSION_PLAYERS'] = '2'
        launched = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
        runtime = game / '.partydeck-plutonium'
        windows_game = 'Z:' + str(game).replace('/', chr(92)) if entry == 'play_pc' else r'C:\game'
        expected_pluto = [str(runtime), './bin/' + bo2.BOOTSTRAPPER, tag, windows_game,
                          '+name', f'Player {player_name[1]}', '-lan',
                          '+set', 'r_fullscreen', '2', '+set', 'r_mode', '1280x720', '+set', 'net_port',
                          str(bo2.HOST_PORT + int(player_name[1]) - 1)]
        if player_name == 'j1':
            expected_pluto += ['+set', 'sp_minplayers', '2']
        else:
            assert bo2.JOIN_HOST in launched.stderr
        assert launched.stdout.splitlines() == expected_pluto
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

print('BO2: profile migration, absolute Plutonium paths, Bink diagnostics, original autorun and private identities verified.')
