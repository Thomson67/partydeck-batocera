"""Exercise the native launcher contract and each supported client layout."""
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
from partydeck_profiles import defaults, private_lan_enabled, read_profile, save_profile

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
        data['bo2']['mode'] = 'zm'
        save_profile(base, rom, data)
        assert read_profile(base, rom)['bo2'] == {'mode': 'zm'}
    assert defaults(base / 'BO2 Zombies.wsquashfs')['bo2']['mode'] == 'zm'
    assert not bo2.matches(base / 'Black Ops III.wsquashfs')

    hits = []
    for player_name, entry, mode in (('j1', 'play_wine', 'mp'), ('j2', 'play_squashfs', 'zm'),
                                     ('j3', 'play_pc', 'original')):
        player = base / player_name
        player.mkdir()
        prefix = player / 'Wine prefix'
        game = prefix if entry == 'play_pc' else prefix / 'drive_c/game'
        settings = game / 'STEAM_SETTINGS'
        settings.mkdir(parents=True)
        (game / 't6sp.exe').touch()
        (game / 't6sp_o.exe').touch()
        (game / 'T6MP.EXE').touch()
        (game / 't6zm.exe').touch()
        ini = settings / 'configs.user.ini'
        ini.write_text('[user::general]\naccount_steamid=76561197960265729\nlanguage=french\n')
        (settings / 'force_steamid.txt').write_text('76561197960265729\n')
        hook = [sys.executable, str(Path(bo2.__file__)), str(player)]
        launcher = player / 'native.sh'
        launcher.write_text(bo2.instrument_native(source, hook, mode))
        subprocess.run(['bash', '-n', str(launcher)], check=True)
        env = dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player),
                   WINE_LANG='C' if entry == 'play_squashfs' else '')
        result = subprocess.run(['bash', str(launcher), str(prefix), entry], check=True,
                                capture_output=True, text=True, env=env)
        expected = {'mp': ['./T6MP.EXE', '+set', 'r_fullscreen', '0'],
                    'zm': ['./t6zm.exe', '+set', 'r_fullscreen', '0'],
                    'original': ['t6sp.exe', '-solo']}
        assert result.stdout.splitlines() == [str(game), *expected[mode]]
        steamid = (settings / 'force_steamid.txt').read_text().strip()
        assert steamid in ini.read_text() and 'language=french' in ini.read_text()
        hits.append(steamid)
        if mode == 'zm':
            (game / 't6zm.exe').unlink()
            failed = subprocess.run(['bash', str(launcher), str(prefix), entry], capture_output=True,
                                    text=True, env=env)
            assert failed.returncode == 1 and not failed.stdout and 't6zm.exe' in failed.stderr
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
            bo2.prepare(base / 'j1', 'mp', classic, game)
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

print('BO2: MP, Zombies, original autorun, private LAN, classic/modern Goldberg and Nova verified.')
