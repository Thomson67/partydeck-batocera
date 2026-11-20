"""HKMultiplayer: native bridge, common code, private identities and controller policy."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'
os.environ['SDL_VIDEODRIVER'] = 'dummy'
from pathlib import Path
import json
import subprocess
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_hkmultiplayer as h
from partydeck_profiles import defaults, save_profile, read_profile
from partydeck_catalog import recipe_for
from partydeck_couch import fields, Model

assert h.matches(Path('Hollow Knight 1.5.12620.wine'))
assert h.matches(Path('Hollow Knight Multiplayer.wsquashfs'))
assert not h.matches(Path('Hollow Knight.wine'))
assert not h.matches(Path('Hollow Knight Silksong Multiplayer.wine'))
for changes in (dict(port=True), dict(port=65536), dict(world='delete'), dict(world_name='a\nb'),
                dict(names=['J1'] * 4), dict(host={'revive': 1}), dict(fix_controllers=1)):
    try:
        h.validate(dict(h.defaults(), **changes))
        raise AssertionError(changes)
    except ValueError:
        pass
code = h.session_code()
assert len(code) == 8 and all(c in h.CODE_ALPHABET for c in code)
assert len({h.session_code() for _ in range(100)}) == 100

native = '#!/bin/bash\ngetWine_var() { printf "%s" "$COMMAND"; }\n'
for name in ('play_wine', 'play_pc', 'play_squashfs'):
    native += name + '() {\n WINE_CMD=$(getWine_var "${WINEPOINT}" "CMD" "explorer")\n printf "%s\\n%s\\n" "$WINE_CMD" "$WINEDLLOVERRIDES"\n}\n'
native += 'play_wine\nplay_pc\nplay_squashfs\n'
for command in ('hollow_knight.exe -keep', 'start.bat'):
    result = subprocess.run(['bash', '-c', h.instrument_display(native, 1920, 540)],
                            env=dict(os.environ, COMMAND=command, WINEDLLOVERRIDES='dinput8=n,b'),
                            text=True, capture_output=True, check=True)
    lines = result.stdout.splitlines()
    assert lines[0].startswith(command)
    assert ('-screen-width 1920' in lines[0]) == command.startswith('hollow_knight')
    assert all(lines[i] == 'dinput8=n,b' for i in (1, 3, 5))

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    base = root / 'base'
    rom = root / 'Hollow Knight Multiplayer.wine'
    rom.mkdir()
    profile = defaults(rom)
    assert profile['adapter'] == 'hollowknight-hkmultiplayer'
    assert recipe_for(rom).id == 'hkmultiplayer'
    save_profile(base, rom, profile)
    assert read_profile(base, rom)['hkmultiplayer']['fix_controllers']
    assert [len(fields(i, profile['adapter'])) for i in (1, 2, 3)] == [6, 7, 6]
    model = Model(base, rom, windows=root)
    assert model.data['adapter'] == profile['adapter']
    binaries = base / 'plugins'
    binaries.mkdir(parents=True)
    plugin = binaries / 'WindowsParty.HKMultiplayer.dll'
    plugin.write_bytes(b'BRIDGE')
    wide = binaries / 'WindowsParty.NativeWide.dll'
    wide.write_bytes(b'WIDE')
    keys = []
    for index in range(4):
        player = base / f'j{index+1}'
        prefix = player / 'prefix'
        game = prefix / 'drive_c/game'
        mods = game / 'hollow_knight_Data/Managed/Mods'
        (mods / 'HKMultiplayer').mkdir(parents=True)
        (mods / 'HKMultiplayer/HKMultiplayer.dll').write_bytes(b'USER MOD')
        (game / 'hollow_knight.exe').write_bytes(b'GAME')
        (game / 'doorstop_config.ini').write_bytes(b'[General]\r\nenabled=true\r\n[UnityMono]\r\ndll_search_path_override=BepInEx\\core\r\n')
        savedir = prefix / 'drive_c/users/steamuser/AppData/LocalLow/Team Cherry/Hollow Knight'
        savedir.mkdir(parents=True)
        settings = savedir / 'HKMultiplayerMod.GlobalSettings.json'
        settings.write_text(json.dumps(dict(PlayerKey='a'*32, Other=42, SkinName='UserSkin')))
        save = savedir / 'user1.dat'
        save.write_bytes(b'ORIGINAL SAVE')
        payload = dict(player=str(player), index=index, width=1920, height=540, settings=h.defaults(),
                       code=code, plugin=str(plugin), wide_plugin=str(wide))
        h.apply_config(game, prefix, payload, private_binds=())
        state = json.loads(settings.read_text())
        key = state['PlayerKey']
        keys.append(key)
        assert len(key) == 32 and key != 'a'*32 and state['PlayerName'] == f'J{index+1}'
        assert state['SkinName'] == 'UserSkin' and state['Other'] == 42 and state['SteamAccess'] == 2
        assert save.read_bytes() == b'ORIGINAL SAVE'
        assert (mods / 'HKMultiplayer/HKMultiplayer.dll').read_bytes() == b'USER MOD'
        cfg = mods / 'WindowsPartyHKMultiplayer/windows-party.cfg'
        assert 'Code=' + code in cfg.read_text() and 'FixControllers=true' in cfg.read_text()
        assert 'enabled=false' in (game / 'doorstop_config.ini').read_text()
        h.apply_config(game, prefix, payload, private_binds=())
        assert json.loads(settings.read_text())['PlayerKey'] == key
        payload['settings'].update(automatic=False, fix_controllers=False, ultrawide=False)
        h.apply_config(game, prefix, payload, private_binds=())
        assert 'FixControllers=false' in cfg.read_text() and 'Automatic=false' in cfg.read_text()
        assert not (mods / 'WindowsPartyNativeWide/WindowsParty.NativeWide.dll').exists()
        assert (mods / 'WindowsPartyNativeWide/WindowsParty.NativeWide.dll.windows-party-disabled').read_bytes() == b'WIDE'
        before = cfg.read_bytes()
        payload['code'] = 'invalid'
        try:
            h.apply_config(game, prefix, payload, private_binds=())
            raise AssertionError('invalid code accepted')
        except ValueError:
            pass
        assert cfg.read_bytes() == before
    assert len(set(keys)) == 4
    # A per-player namespace must not write through a link into a solo path.
    outside = root / 'solo'
    outside.mkdir()
    (outside / 'sentinel').write_bytes(b'UNCHANGED')
    link = prefix / 'drive_c/linked-game'
    link.symlink_to(outside, target_is_directory=True)
    payload['code'] = code
    try:
        h.apply_config(link, prefix, payload, private_binds=())
        raise AssertionError('outside link accepted')
    except ValueError:
        pass
    assert (outside / 'sentinel').read_bytes() == b'UNCHANGED'

print('HKMultiplayer: shared code, private state, native-input policy, command preservation and validation passed.')
