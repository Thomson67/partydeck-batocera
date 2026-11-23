"""CelesteNet profile, private configuration, and Everest console exchange."""
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
    save_profile(root,rom,profile)
    assert read_profile(root,rom)['adapter'] == celeste.ADAPTER
    assert celeste.ADAPTER in next(values for key,_,values in fields(0) if key=='adapter')
    assert label_value('adapter',celeste.ADAPTER)=='Celeste / CelesteNet'

    player = root/'j2'
    prefix = player/'prefix'
    game = prefix/'drive_c'/'Celeste'
    (game/'Mods').mkdir(parents=True)
    (game/'Celeste.exe').touch()
    flags = game/'everest-launch.txt'
    flags.write_bytes(b'# custom\r\n--loglevel verbose\r\n')
    settings = game/'Saves'/celeste.SETTINGS_FILE
    settings.parent.mkdir()
    original = b'SettingsVersionDoNotEdit: 2\r\nName: Old\r\nClientIDSending: NotOnLocalhost\r\nExtraServers:\r\n- localhost\r\n'
    settings.write_bytes(original)
    with patch.object(celeste.subprocess,'run') as run:
        celeste.configure_client(game,prefix,player)
        run.assert_called_once_with(['mount','--bind',str(player/'celestenet-everest-launch.txt'),str(flags)],check=True)
    assert flags.read_bytes()==b'# custom\r\n--loglevel verbose\r\n'
    assert (player/'celestenet-everest-launch.txt').read_bytes().endswith(b'--debug\n')
    assert (player/'celestenet-client-before.celeste').read_bytes()==original
    assert b'Name: J2\r\nClientIDSending: Off\r\nExtraServers:\r\n- localhost\r\n' in settings.read_bytes()
    assert b'LoginMode: Guest' in settings.read_bytes()
    assert b'SettingsVersionDoNotEdit: 2' in celeste.patch_client_settings(b'', 'j1')


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
        with patch.object(celeste,'DEBUG_PORT',http.server_port):
            celeste.join('192.168.247.11','j2',timeout=3)
    finally:
        http.shutdown()
        worker.join(timeout=3)
assert calls == [{},{},{'command':['con 192.168.247.11:17230']}]
print('CelesteNet: profile, private client settings and automatic Everest console join verified.')
