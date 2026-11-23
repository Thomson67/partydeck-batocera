"""CelesteNet profile, private configuration, rendering and console exchange."""
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_celestenet as celeste
from partydeck_couch import Model, fields, label_value
from partydeck_profiles import defaults, read_profile, save_profile

with tempfile.TemporaryDirectory() as name:
    root = Path(name)
    rom = root/'Celeste [Everest].wsquashfs'
    rom.touch()
    profile = defaults(rom)
    assert profile['adapter'] == celeste.ADAPTER
    profile.pop('celestenet')  # Older profiles have no options section.
    save_profile(root,rom,profile)
    saved = read_profile(root,rom)
    assert saved['adapter'] == celeste.ADAPTER
    assert saved['celestenet'] == celeste.defaults()
    assert saved['celestenet']['automatic'] is True
    assert saved['celestenet']['music_j1_only'] is True
    saved['celestenet'].update(automatic=False, music_j1_only=False)
    save_profile(root, rom, saved)
    explicit = read_profile(root, rom)['celestenet']
    assert explicit['automatic'] is False
    assert explicit['music_j1_only'] is False
    assert [key for key, _, _ in fields(1, celeste.ADAPTER)] == [
        'celestenet.language', 'celestenet.skip_setup', 'celestenet.automatic', 'celestenet.music_j1_only']
    from partydeck_i18n import set_language
    set_language('en')
    assert label_value('celestenet.language', 'french') == 'French'
    set_language('fr')
    assert label_value('celestenet.language', 'french') == 'Français'
    assert len(fields(2, celeste.ADAPTER)) == 4
    names = ['Alpha', '  Étoile : 2  ', '', 'Quatre']
    assert celeste.validate({'names': names})['names'] == ['Alpha', 'Étoile : 2', 'J3', 'Quatre']
    assert 'Name: "Étoile : 2"' in celeste.patch_client_settings(b'', 'Étoile : 2').decode()
    quoted_name = 'Étoile "2" ' + chr(92)
    rewritten = celeste.patch_client_settings(b'Name: J2\n', quoted_name).decode().splitlines()
    assert json.loads(rewritten[0].removeprefix('Name: ')) == quoted_name

    directory_rom = root/'Celeste.wine'
    root_game = directory_rom/'drive_c'/'game'
    mods = root_game/'Mods'
    mods.mkdir(parents=True)
    (root_game/'Celeste.exe').touch()
    config = '''- SkinName: 'Tea: Green'
  Player_List: true
  Character_ID: custom_player
- SkinName: GeneralOnly
  General_List: true
- SkinName: Hidden
  Player_List: false
  Character_ID: another_player
'''
    with ZipFile(mods/'test-skins.zip', 'w') as archive:
        archive.writestr('SkinModHelperConfig.yaml', config)
    assert celeste.skin_choices(root, directory_rom) == ['Tea: Green']
    model = Model(root, directory_rom)
    assert model.celeste_skins == ['Tea: Green']
    assert fields(2, celeste.ADAPTER, model.celeste_skins)[4][2] == ['', 'Original', 'Tea: Green']
    assert label_value('celestenet.skins.0', 'Original') == 'Madeline standard'


    assert celeste.ADAPTER in next(values for key,_,values in fields(0) if key=='adapter')
    assert label_value('adapter',celeste.ADAPTER)=='Celeste / CelesteNet'

    player = root/'j2'
    prefix = player/'prefix'
    game = prefix/'drive_c'/'Celeste'
    (game/'Mods').mkdir(parents=True)
    (game/'Celeste.exe').touch()
    flags = game/'everest-launch.txt'
    original_flags = b'# --debug\r\n--loglevel verbose --debug --disable-splash\r\n'
    flags.write_bytes(original_flags)
    settings = game/'Saves'/celeste.SETTINGS_FILE
    settings.parent.mkdir()
    original = b'SettingsVersionDoNotEdit: 2\r\nName: Old\r\nClientIDSending: NotOnLocalhost\r\nExtraServers:\r\n- localhost\r\n'
    settings.write_bytes(original)
    game_settings = settings.parent/'settings.celeste'
    game_settings.write_bytes(b'<Settings><LaunchInDebugMode>true</LaunchInDebugMode><Fullscreen>true</Fullscreen></Settings>')
    core_path = settings.parent/'modsettings-Everest.celeste'
    core_path.write_bytes(b"DebugModeInEverest: true\nAutoUpdateModsOnStartup: true\nCurrentVersion: '0.0.0'\n")
    with patch.object(celeste.subprocess,'run') as run:
        celeste.configure_client(game, prefix, player, dict(celeste.defaults(), language='french', automatic=False, music_j1_only=False), lan=True)
        run.assert_called_once_with(['mount','--bind',str(player/'celestenet-everest-launch.txt'),str(flags)],check=True)
    assert b'--loglevel verbose  --disable-splash' in (player/'celestenet-everest-launch.txt').read_bytes()
    assert b'<Language>french</Language>' in game_settings.read_bytes()
    assert b'<LaunchInDebugMode>false</LaunchInDebugMode>' in game_settings.read_bytes()
    assert b'<Fullscreen>true</Fullscreen>' in game_settings.read_bytes()
    assert b'DebugModeInEverest: false' in core_path.read_bytes()
    assert b'CurrentVersion:' not in core_path.read_bytes()
    assert b'AutoUpdateModsOnStartup: false' in core_path.read_bytes()
    core_path.write_bytes(core_path.read_bytes() + b"CurrentVersion: '1.6000.0'\n")
    with patch.object(celeste.subprocess,'run') as run:
        celeste.configure_client(game,prefix,player,dict(celeste.defaults(), music_j1_only=False),lan=True)
        run.assert_called_once_with(['mount','--bind',str(player/'celestenet-everest-launch.txt'),str(flags)],check=True)
    assert flags.read_bytes() == original_flags
    assert (player/'celestenet-everest-launch.txt').read_bytes().endswith(b'--debug\n')
    assert (player/'celestenet-client-before.celeste').read_bytes()==original
    assert b'Name: "J2"\r\nClientIDSending: Off\r\nExtraServers:\r\n- localhost\r\n' in settings.read_bytes()
    assert b'LoginMode: Guest' in settings.read_bytes()
    assert b'SettingsVersionDoNotEdit: 2' in celeste.patch_client_settings(b'', 'j1')
    core=(settings.parent/'modsettings-Everest.celeste').read_bytes()
    assert b'DebugRCPort: 32271' in core and b'DebugModeInEverest: true' in core
    assert b"CurrentVersion: '1.6000.0'" in core
    assert celeste.patch_game_settings(b'', 'keep', False) == b''
    assert b'<Language>english</Language>' in celeste.patch_game_settings(b'', 'english', False)
    with patch.object(celeste, 'configure_startup', side_effect=PermissionError('read-only settings')):
        celeste.configure_client(game, prefix, player, celeste.defaults(), lan=True)

    game_settings.write_bytes(b'<Settings><MusicVolume>8</MusicVolume><SFXVolume>6</SFXVolume></Settings>')
    music_backup = game_settings.with_name('partydeck-celeste-music.json')
    for _ in range(2):
        celeste.configure_music(game_settings, music_backup, True)
        assert b'<MusicVolume>0</MusicVolume>' in game_settings.read_bytes()
        assert b'<SFXVolume>6</SFXVolume>' in game_settings.read_bytes()
    celeste.configure_music(game_settings, music_backup, False)
    assert b'<MusicVolume>8</MusicVolume>' in game_settings.read_bytes() and not music_backup.exists()
    game_settings.write_bytes(b'<Settings><SFXVolume>6</SFXVolume></Settings>')
    celeste.configure_music(game_settings, music_backup, True)
    celeste.configure_music(game_settings, music_backup, False)
    assert b'MusicVolume' not in game_settings.read_bytes()

    for name in celeste.VARIANT_ASSEMBLIES:
        (game/name).write_bytes(b'standard')
    for folder, dimensions in (('PartyDeck-32x9', (1920, 540)), ('PartyDeck-8x9', (960, 1080))):
        variant = game/folder
        variant.mkdir()
        for name in celeste.VARIANT_ASSEMBLIES:
            (variant/name).write_bytes(folder.encode())
        fingerprint = variant/'normal.sha256'
        fingerprint.write_text(hashlib.sha256(b'standard').hexdigest(), encoding='utf-8-sig')
        with patch.object(celeste.subprocess, 'run') as mount:
            for width, height in ((1920, 1080), (960, 540)):
                celeste.configure_viewport_variant(game, (prefix,), player.name, width, height)
            mount.assert_not_called()
            celeste.configure_viewport_variant(game, (prefix,), player.name, *dimensions)
            assert [call.args[0] for call in mount.call_args_list] == [
                ['mount', '--bind', str(variant/name), str(game/name)] for name in celeste.VARIANT_ASSEMBLIES
            ]
        with patch.object(celeste.subprocess, 'run') as mount:
            (variant/'Celeste.dll').write_bytes(b'standard')
            celeste.configure_viewport_variant(game, (prefix,), player.name, *dimensions)
            fingerprint.write_text('0'*64)
            celeste.configure_viewport_variant(game, (prefix,), player.name, *dimensions)
            mount.assert_not_called()
    assert (game/'Celeste.dll').read_bytes() == b'standard'

    compatdata = root/'compatdata'
    compat_prefix = compatdata/'Celeste'
    final_game = compat_prefix/'pfx'/'drive_c'/'Celeste'
    final_game.mkdir(parents=True)
    (final_game/'Celeste.exe').touch()
    final_variant = final_game/'PartyDeck-8x9'
    final_variant.mkdir()
    for assembly in celeste.VARIANT_ASSEMBLIES:
        (final_game/assembly).write_bytes(b'standard')
        (final_variant/assembly).write_bytes(b'portrait')
    (final_variant/'normal.sha256').write_text(hashlib.sha256(b'standard').hexdigest())
    environment = dict(PARTYDECK_PRIVATE_PLAYER=str(player), PARTYDECK_CELESTENET='1',
                       PARTYDECK_PLAYER_WIDTH='960', PARTYDECK_PLAYER_HEIGHT='1080',
                       WINEPREFIX=str(compat_prefix), PRESSURE_VESSEL_FILESYSTEMS_RO='/existing')
    with patch.dict(os.environ, environment, clear=True), \
            patch.object(celeste.Path, 'cwd', return_value=final_game), \
            patch.object(celeste.subprocess, 'run') as mount:
        mounted = celeste.prepare_umu_viewport(player, compatdata)
        assert mounted == tuple(final_game/name for name in celeste.VARIANT_ASSEMBLIES)
        assert [call.args[0] for call in mount.call_args_list] == [
            ['mount', '--bind', str(final_variant/name), str(final_game/name)]
            for name in celeste.VARIANT_ASSEMBLIES
        ]
        assert os.environ['PRESSURE_VESSEL_FILESYSTEMS_RO'].split(':') == [
            '/existing', *(str(final_game/name) for name in celeste.VARIANT_ASSEMBLIES)
        ]
        mount.return_value.returncode = 0
        mount.reset_mock()
        celeste.unmount_variant(mounted)
        assert [call.args[0] for call in mount.call_args_list] == [
            ['umount', '--', str(path)] for path in reversed(mounted)
        ]
        mount.reset_mock()
        os.environ['PARTYDECK_PRIVATE_PLAYER'] = str(root/'j1')
        celeste.prepare_umu_viewport(player, compatdata)
        mount.assert_not_called()

    # Exercise the actual hook as a separate process, including its imports.
    flags.write_bytes(b'--disable-splash\n')
    with ZipFile(game/'Mods'/'test-skins.zip', 'w') as archive:
        archive.writestr('SkinModHelperConfig.yaml', config)
    skin_settings = settings.parent/'modsettings-SkinModHelperPlus.celeste'
    skin_settings.write_text('Backpack: Default\nSelectedPlayerSkin: Original\n')
    env = dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player),
               PARTYDECK_CELESTE_OPTIONS=json.dumps(dict(celeste.defaults(), language='english', automatic=False,
                                                         names=names, music_j1_only=True,
                                                         skins=['', 'Tea: Green', '', ''])),
               PARTYDECK_CELESTENET='1', PARTYDECK_PLAYER_WIDTH='1920', PARTYDECK_PLAYER_HEIGHT='1080')
    subprocess.run([sys.executable, celeste.__file__, '_prepare', str(player), str(game), str(prefix)],
                   env=env, check=True, timeout=10)
    assert b'<Language>english</Language>' in game_settings.read_bytes()
    assert b'<MusicVolume>0</MusicVolume>' in game_settings.read_bytes()
    assert 'Name: "Étoile : 2"' in settings.read_text()
    assert skin_settings.read_text() == 'Backpack: Default\nSelectedPlayerSkin: "Tea: Green"\n'
    assert b'DebugModeInEverest: false' in core_path.read_bytes()


calls = []
class Console(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        assert url.path == '/console'
        calls.append(parse_qs(url.query))
        self.send_response(200)
        self.end_headers()
        if len(calls) == 2:
            self.wfile.write(b'<h3>con</h3><code>Usage: con server</code>')

    def log_message(self,*args):
        pass

with HTTPServer(('127.0.0.1',0),Console) as http:
    worker = Thread(target=http.serve_forever,daemon=True)
    worker.start()
    try:
        with patch.object(celeste,'DEBUG_PORT',http.server_port-1):
            celeste.join('127.0.0.1','j2',timeout=3)
    finally:
        http.shutdown()
        worker.join(timeout=3)
assert calls == [{},{},{'command':['con localhost']}]

from partydeck_private_lan import PrivateLAN
lan=PrivateLAN(2,shared=True)
assert lan.count==1 and lan.address(0)=='127.0.0.1'
assert PrivateLAN(2).address(1)=='192.168.247.12'
print('CelesteNet: profile, private client settings and automatic Everest console join verified.')
