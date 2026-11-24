from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_dst as dst
from partydeck_catalog import recipe_for
from partydeck_profiles import defaults, validate

title = b'''local title = STRINGS.UI.MAINSCREEN.STEAMOFFLINEMODE
TheFrontEnd:PushScreen(confirm)
print ( "failed_communication" )
TheFrontEnd:PushScreen(confirm)
TheNet:NotifyAuthenticationFailure()
GoToMultiplayerMainMenu(forceOffline or false)
function MainScreen:OnUpdate(dt)
end
'''
menu = b'function MultiplayerMainScreen:OnUpdate(dt)\nend\n'
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    rom = root/"Don't Starve Together.wsquashfs"
    assert recipe_for(rom).id == 'dst'
    assert validate(defaults(rom), rom)['adapter'] == dst.ADAPTER
    assert not dst.matches(root/'Dont Starve.wine')
    game = root/'drive_c'/'dst'
    bin64 = game/'bin64'
    bin64.mkdir(parents=True)
    (bin64/'dontstarve_steam_x64.exe').touch()
    bundle = game/dst.BUNDLE
    bundle.parent.mkdir(parents=True)
    with zipfile.ZipFile(bundle, 'w') as archive:
        archive.writestr('scripts/'+dst.TITLE, title)
        archive.writestr(dst.MENU, menu)
        archive.writestr('scripts/main.lua', b'LOC = require("languages/loc")\nrequire("languages/language")')
        archive.writestr('unrelated.lua', b'unmodified')
    assert dst.find_bundle(bin64, root) == bundle
    assert dst.find_bundle(bin64, root/'elsewhere') is None
    guest = root/'guest.zip'
    host = root/'host.zip'
    dst.patch_bundle(bundle, guest, '192.168.247.11', language='french', mute_music=True)
    dst.patch_bundle(bundle, host, language='french')
    with zipfile.ZipFile(guest) as output:
        assert b'server.ip == "192.168.247.11"' in output.read(dst.MENU)
        assert b'JoinServer(server)' in output.read(dst.MENU)
        assert b'self.partydeck_wait - self.partydeck_first_seen >= 15' in output.read(dst.MENU)
        patched = output.read('scripts/'+dst.TITLE)
        assert patched.count(b'GoToMultiplayerMainMenu(true)') == 3
        assert b'SetDisplayMode' not in patched
        assert b'self.inst:DoTaskInTime' in patched
        assert b'TheMixer:SetLevel("set_music", 0)' in patched
        assert b'LANGUAGE.FRENCH' in output.read('scripts/main.lua')
        assert output.read('unrelated.lua') == b'unmodified'
    with zipfile.ZipFile(host) as output:
        assert output.read(dst.MENU) == menu
        assert b'set_music' not in output.read('scripts/'+dst.TITLE)
        assert b'Profile.GetVolume' not in output.read('scripts/main.lua')
    with zipfile.ZipFile(bundle) as stock:
        assert stock.read('scripts/'+dst.TITLE) == title
    try:
        dst.patch_title(b'unsupported')
    except ValueError:
        pass
    else:
        raise AssertionError('unknown title layout accepted')
print('DST: catalog detection, isolated host/client bundles and unknown-layout fallback verified.')
