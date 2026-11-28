"""D2RLoader profile, private launch and passive LAN readiness."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_d2rloader as d2r
from partydeck_catalog import recipe_for
from partydeck_profiles import defaults, private_lan_enabled, validate
from partydeck_couch import fields
from partydeck_i18n import set_language

rom = Path('/userdata/roms/windows/Diablo II Resurrected [Reimagined].wsquashfs')
profile = defaults(rom)
assert recipe_for(rom).adapter == profile['adapter'] == d2r.ADAPTER
display_defaults = {'legacy_resolution': 'keep', 'large_font': 'keep', 'chat_font': 'keep', 'ultrawide_hud': 'keep'}
assert validate(profile, rom)[d2r.ADAPTER] == {'automatic': True, 'horizontal_ultrawide': False, **display_defaults}
assert d2r.validate({'automatic': False}) == {'automatic': False, 'horizontal_ultrawide': False, **display_defaults}
assert private_lan_enabled(profile, 2) and private_lan_enabled(profile, 4)
assert not private_lan_enabled(profile, 1)
assert not d2r.matches(Path('Diablo II.wine'))
for lang, label in (('fr', 'Hébergement et jonction LAN automatiques'), ('en', 'Automatic LAN hosting and joining')):
    set_language(lang)
    assert fields(1, d2r.ADAPTER) == [('d2rloader.automatic', label, [True, False])]
assert d2r.ultrawide_mode(1920, 540) == (2560, 720)
assert d2r.ultrawide_mode(2560, 720) == (2560, 720)
assert d2r.ultrawide_mode(3440, 720) == (2560, 720)
assert d2r.ultrawide_mode(960, 540) is None

with TemporaryDirectory() as tmp:
    base = Path(tmp)
    player = base / 'j2'
    prefix = player / 'prefix'
    pc = base / 'Diablo II Resurrected.pc'
    plugin = base / d2r.PLUGIN
    plugin.write_bytes(b'bridge')
    dll = b'official fixture'
    host = b'loader executable fixture'
    retail = b'retail game executable fixture'
    archive = base / 'ultrawide.zip'
    with ZipFile(archive, 'w') as package:
        package.writestr('d2rloader/plugins/Ultrawide.dll', b'wide plugin')
        package.writestr('d2rloader/data/hd/tc22sh/terrain.bin', b'wide shader')
        package.writestr('unexpected.txt', b'other data')
    exported = base / 'private-saves'
    player_saves = exported / 'Diablo II Resurrected'
    mod_saves = player_saves / 'mods' / 'Reimagined'
    mod_saves.mkdir(parents=True)
    user = prefix / 'drive_c/users/steamuser'
    user.mkdir(parents=True)
    (user / 'Saved Games').symlink_to(exported, target_is_directory=True)
    native_settings = player_saves / 'Settings.json'
    mod_settings = mod_saves / 'settings.json'
    for target in (native_settings, mod_settings):
        target.write_text(json.dumps({'Resolution Scale': 75, 'Game Resolution': 1, 'Low Vision Mode': 0}))
    display = {'legacy_resolution': '640x480', 'large_font': 'on', 'chat_font': 'extra_large', 'ultrawide_hud': 'full'}
    with patch.object(d2r, 'WINDOWS_SAVES', exported):
        assert d2r.prepare(prefix, prefix, player, plugin, False, rom, display=display, lan=False) is None
        for target in (native_settings, mod_settings):
            assert json.loads(target.read_text()) == {
                'Resolution Scale': 75, 'Game Resolution': 0, 'Low Vision Mode': 1, 'Chat Font Size': 3,
            }
        before = native_settings.read_bytes()
        d2r.prepare(prefix, prefix, player, plugin, False, rom, lan=False)
        assert native_settings.read_bytes() == before
    for entry, original, game in (
        ('play_wine', rom.with_suffix('.wine'), prefix / 'drive_c' / 'game'),
        ('play_pc', pc, pc),
        ('play_squashfs', rom, prefix / 'drive_c' / 'game'),
    ):
        game.mkdir(parents=True, exist_ok=True)
        (game / 'D2R.exe').write_bytes(retail)
        (game / 'D2RLoader.exe').write_bytes(host)
        (game / 'D2RCore.dll').write_bytes(dll)
        loader = game / 'd2rloader'
        config = loader / 'config' / 'd2rloader.toml'
        state = loader / 'data' / 'state.json'
        config.parent.mkdir(parents=True, exist_ok=True)
        state.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[d2rloader]\ndefault_mod = "Reimagined"\n[d2rloader.advanced]\ngame_port = 4555\n')
        state.write_text(json.dumps({'version': 1, 'tutorialSeen': True,
                                     'multiplayer': {'maxPlayers': 2, 'difficulty': 'nightmare'}}))
        with patch.object(d2r, 'CORE_131', hashlib.sha256(dll).hexdigest()), patch.dict(
            os.environ, PARTYDECK_D2R_HOST='192.168.247.11', PARTYDECK_SESSION_PLAYERS='3',
        ):
            assert d2r.prepare(game, prefix, player, plugin, True, original) == 'D2RLoader.exe'
        cfg = tomllib.loads(config.read_text())['d2rloader']
        assert cfg == {'default_mod': 'Reimagined', 'show_tcpip_button': True, 'check_for_updates': False,
                       'advanced': {'game_port': 4000, 'automatic_port_mapping': False, 'hosting_check': False}}
        data = json.loads(state.read_text())
        assert data['tutorialSeen']
        assert data['multiplayer'] == {'maxPlayers': 4, 'difficulty': 'nightmare', 'lanOnly': True,
                                       'unlisted': False, 'password': '', 'directJoinAddress': '192.168.247.11'}
        assert (loader / 'plugins' / d2r.PLUGIN).read_bytes() == b'bridge'
        before = state.read_bytes()
        assert d2r.prepare(game, prefix, player, plugin, True, original) == 'D2RLoader.exe'
        assert not (loader / 'plugins' / d2r.PLUGIN).exists()
        assert state.read_bytes() == before

        wide_dll = loader / 'plugins' / d2r.ULTRAWIDE_PLUGIN
        assert d2r.prepare(game, prefix, player, plugin, False, original, ultrawide=archive) == 'D2RLoader.exe'
        assert not wide_dll.exists()
        view = base / f'ultrawide-{entry}'
        view.mkdir()
        other_plugin = wide_dll.with_name('Other.dll')
        other_plugin.write_bytes(b'user plugin')
        with (patch.object(d2r, 'CORE_131', hashlib.sha256(dll).hexdigest()),
              patch.object(d2r, 'ULTRAWIDE_LOADER', hashlib.sha256(host).hexdigest()),
              patch.object(d2r, 'mkdtemp', return_value=str(view)),
              patch.object(d2r.subprocess, 'run') as mount):
            assert d2r.prepare(game, prefix, player, plugin, False, original, ultrawide=archive) == 'D2RLoader.exe'
            assert not wide_dll.exists()
            assert (view / d2r.ULTRAWIDE_PLUGIN).read_bytes() == b'wide plugin'
            assert [call.args[0] for call in mount.call_args_list] == [
                ['mount', '--bind', str(other_plugin), str(view / other_plugin.name)],
                ['mount', '--rbind', str(view), str(wide_dll.parent)],
            ]
            assert (loader / 'data/hd/tc22sh/terrain.bin').read_bytes() == b'wide shader'
            wide_cfg = tomllib.loads((loader / 'config/ultrawide.toml').read_text())['ultrawide']
            assert wide_cfg == {'enable_monster_pop_in_fix': False, 'enable_monster_ai_range': False}
            assert not (game / 'unexpected.txt').exists() and (game / 'D2R.exe').read_bytes() == retail
            assert (game / 'D2RLoader.exe').read_bytes() == host
            wide_dll.write_bytes(b'user ultrawide')
            mount.reset_mock()
            wide_config = loader / 'config/ultrawide.toml'
            wide_config.write_text('[ultrawide]\nhud_mode = "centered"\nenable_corner_minimap = false\n')
            d2r.prepare(game, prefix, player, plugin, False, original, ultrawide=archive,
                        display={'ultrawide_hud': 'full'})
            assert wide_dll.read_bytes() == b'user ultrawide'
            assert tomllib.loads(wide_config.read_text())['ultrawide'] == {
                'hud_mode': 'full', 'enable_corner_minimap': False,
            }
            mount.assert_not_called()
        d2r.prepare(game, prefix, player, plugin, False, original)
        assert wide_dll.read_bytes() == b'user ultrawide' and other_plugin.read_bytes() == b'user plugin'
        wide_dll.unlink()
        other_plugin.unlink()
        wide_config.unlink()

        launcher = base / 'launcher.sh'
        shell = ''
        for function in ('play_wine', 'play_pc', 'play_squashfs'):
            mount = 'GAMENAME' if function == 'play_pc' else 'WINEPOINT'
            shell += f'{function}() {{\n    if [[ -n "$USE_LANGUAGE" ]]; then\n'
            shell += f'        (cd "${{{mount}}}/${{WINE_DIR}}" && printf "%s\\n" ${{WINE_CMD}})\n    else\n'
            shell += f'        (cd "${{{mount}}}/${{WINE_DIR}}" && printf "%s\\n" ${{WINE_CMD}})\n    fi\n}}\n'
        launcher.write_text(d2r.instrument_native(shell, ['prepare'])
                            + 'prepare() { printf "%s\\n" D2RLoader.exe; }\n"$1"\n')
        env = dict(os.environ, WINEPOINT=str(prefix), GAMENAME=str(pc), WINE_DIR='' if entry == 'play_pc' else 'drive_c/game')
        assert subprocess.check_output(['bash', str(launcher), entry], env=env | {'WINE_CMD': 'D2R.exe'}, text=True).splitlines() == ['D2RLoader.exe']
        assert subprocess.check_output(['bash', str(launcher), entry], env=env | {
            'WINE_CMD': 'D2RLoader.exe -mod Reimagined', 'USE_LANGUAGE': '1',
        }, text=True).splitlines() == ['D2RLoader.exe', '-mod', 'Reimagined']
        launcher.write_text(d2r.instrument_native(shell, ['prepare'], lan=False)
                            + 'prepare() { [[ "$2" == "$WINEPOINT" ]]; }\n"$1"\n')
        assert subprocess.check_output(['bash', str(launcher), entry], env=env | {'WINE_CMD': 'D2R.exe -direct'},
                                       text=True).splitlines() == ['D2R.exe', '-direct']

    ready_dir = d2r.readiness_dir(player, 'f' * 32)
    ready_dir.mkdir()
    marker = ready_dir / 'ready'
    proc = base / 'proc'
    tables = proc / '508' / 'net'
    tables.mkdir(parents=True)
    listening = 'header\n  0: 00000000:0FA0 00000000:0000 0A 00000000:00000000\n'
    (tables / 'tcp').write_text(listening)
    d2r.sync_readiness(marker, 508, proc)
    assert marker.is_file()
    (tables / 'tcp').write_text(listening.replace(' 0A ', ' 01 '))
    d2r.sync_readiness(marker, 508, proc)
    assert not marker.exists()
    (tables / 'tcp6').write_text(listening)
    d2r.sync_readiness(marker, 508, proc)
    assert marker.is_file()

print('D2RLoader: profile, private launcher configuration, and passive readiness verified.')
