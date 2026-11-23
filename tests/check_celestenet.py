"""CelesteNet profile, private configuration, rendering and console exchange."""
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import tempfile
from threading import Thread
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_celestenet as celeste
from partydeck_couch import fields, label_value
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
    assert [key for key, _, _ in fields(1, celeste.ADAPTER)] == [
        'celestenet.language', 'celestenet.skip_setup', 'celestenet.automatic']
    from partydeck_i18n import set_language
    set_language('en')
    assert label_value('celestenet.language', 'french') == 'French'
    set_language('fr')
    assert label_value('celestenet.language', 'french') == 'Français'
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
    core_path.write_bytes(b'DebugModeInEverest: true\nAutoUpdateModsOnStartup: true\nCurrentVersion: null\n')
    with patch.object(celeste.subprocess,'run') as run:
        celeste.configure_client(game, prefix, player, dict(celeste.defaults(), language='french'), lan=True)
        run.assert_called_once_with(['mount','--bind',str(player/'celestenet-everest-launch.txt'),str(flags)],check=True)
    assert b'--loglevel verbose  --disable-splash' in (player/'celestenet-everest-launch.txt').read_bytes()
    assert b'<Language>french</Language>' in game_settings.read_bytes()
    assert b'<LaunchInDebugMode>false</LaunchInDebugMode>' in game_settings.read_bytes()
    assert b'<Fullscreen>true</Fullscreen>' in game_settings.read_bytes()
    assert b'DebugModeInEverest: false' in core_path.read_bytes()
    assert b"CurrentVersion: '0.0.0'" in core_path.read_bytes()
    assert b'AutoUpdateModsOnStartup: false' in core_path.read_bytes()
    core_path.write_bytes(core_path.read_bytes().replace(b"'0.0.0'", b"'1.6000.0'"))
    with patch.object(celeste.subprocess,'run') as run:
        celeste.configure_client(game,prefix,player,dict(celeste.defaults(), automatic=True),lan=True)
        run.assert_called_once_with(['mount','--bind',str(player/'celestenet-everest-launch.txt'),str(flags)],check=True)
    assert flags.read_bytes() == original_flags
    assert (player/'celestenet-everest-launch.txt').read_bytes().endswith(b'--debug\n')
    assert (player/'celestenet-client-before.celeste').read_bytes()==original
    assert b'Name: J2\r\nClientIDSending: Off\r\nExtraServers:\r\n- localhost\r\n' in settings.read_bytes()
    assert b'LoginMode: Guest' in settings.read_bytes()
    assert b'SettingsVersionDoNotEdit: 2' in celeste.patch_client_settings(b'', 'j1')
    core=(settings.parent/'modsettings-Everest.celeste').read_bytes()
    assert b'DebugRCPort: 32271' in core and b'DebugModeInEverest: true' in core
    assert b"CurrentVersion: '1.6000.0'" in core
    assert celeste.patch_game_settings(b'', 'keep', False) == b''
    assert b'<Language>english</Language>' in celeste.patch_game_settings(b'', 'english', False)
    variant=game/'PartyDeck-32x9'
    variant.mkdir()
    for name in celeste.WIDE_ASSEMBLIES:
        (game/name).write_bytes(b'standard')
        (variant/name).write_bytes(b'wide')
    fingerprint=variant/'normal.sha256'
    fingerprint.write_text(hashlib.sha256(b'standard').hexdigest(),encoding='utf-8-sig')
    with patch.object(celeste.subprocess,'run') as mount:
        for width,height in ((1920,1080),(960,1080),(960,540)):
            celeste.configure_wide_view(game,(prefix,),player.name,width,height)
        mount.assert_not_called()
        celeste.configure_wide_view(game,(prefix,),player.name,1920,540)
        assert [call.args[0] for call in mount.call_args_list]==[
            ['mount','--bind',str(variant/name),str(game/name)] for name in celeste.WIDE_ASSEMBLIES
        ]
    fingerprint.write_text('0'*64)
    with patch.object(celeste.subprocess,'run') as mount:
        celeste.configure_wide_view(game,(prefix,),player.name,1920,540)
        mount.assert_not_called()
    assert (game/'Celeste.dll').read_bytes()==b'standard'


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
