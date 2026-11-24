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
    assert dst.validate({'language':'keep', 'music_j1_only':False}) == dst.defaults()
    assert not dst.defaults()['resume_last_world']
    assert dst.validate({**dst.defaults(), 'resume_last_world': True})['resume_last_world']
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
        archive.writestr(dst.PLAYER_HUD, 'function PlayerHud:SetMainCharacter(maincharacter) end\nfunction PlayerHud:OnDestroy() end\n')
        archive.writestr('scripts/'+dst.PLAYER_STATUS, b'self.root:SetScaleMode(SCALEMODE_PROPORTIONAL)\n')
        archive.writestr('scripts/'+dst.PLAYER_INFO, b'self.root = self.anchor:AddChild(Widget("root"))\n')
        archive.writestr(dst.TEXT, 'function Text:SetSize(sz)\n    self.inst.TextWidget:SetSize(sz)\n    self.size = sz\nend\n')
        archive.writestr(dst.FRONTEND, '\n'.join(
            f'function FrontEnd:{name}() return 1 end'
            for name in ('GetHUDScale', 'GetProportionalHUDScale', 'GetCraftingMenuScale')))
        archive.writestr('scripts/main.lua', b'LOC = require("languages/loc")\nrequire("languages/language")')
        archive.writestr('scripts/mainfunctions.lua', b'function OnNetworkDisconnect( message, should_reset, force_immediate_reset, details, miscdata)\nend\n')
        archive.writestr('unrelated.lua', b'unmodified')
    assert dst.find_bundle(bin64, root) == bundle
    assert dst.find_bundle(bin64, root/'elsewhere') is None
    guest = root/'guest.zip'
    host = root/'host.zip'
    marker = dst.ready_path(dst.readiness_dir(root/'j1', 'a'*32))
    dst.patch_bundle(bundle, guest, '192.168.247.11', language='french', mute_music=True,
                     fullscreen_size=(1920, 540), hud_scale=125, text_scale=120, marker=marker)
    dst.patch_bundle(bundle, host, language='french', marker=marker)
    with zipfile.ZipFile(guest) as output:
        assert b'server.ip == "192.168.247.11"' in output.read(dst.MENU)
        assert b'GetServerListingFromActualIndex(index)' in output.read(dst.MENU)
        assert b'JoinServer(selected)' in output.read(dst.MENU)
        client = output.read(dst.MENU)
        assert b'if not self.partydeck_world_ready then return end' not in client
        assert b'Joining via LAN readiness fallback' in client
        assert b'io.open(' + marker in client
        assert b'w == 1920 and h == 540' in output.read(dst.MENU)
        assert b'original(self) * (125 / 100)' in output.read(dst.FRONTEND)
        assert b'self.root:SetScale(1.25, 1.25, 1)' in output.read('scripts/'+dst.PLAYER_STATUS)
        assert b'self.root:SetScale(1.25, 1.25, 1)' in output.read('scripts/'+dst.PLAYER_INFO)
        assert b'SetSize(sz * (120 / 100))' in output.read(dst.TEXT)
        assert b'self.size = sz' in output.read(dst.TEXT)
        assert b'StopSearchingServers' not in output.read(dst.MENU).split(b'Joining J1 over LAN', 1)[1].split(b'JoinServer(selected)', 1)[0]
        assert b'Network disconnect' in output.read('scripts/mainfunctions.lua')
        assert b'self.partydeck_wait - self.partydeck_first_seen >= 45' in client
        patched = output.read('scripts/'+dst.TITLE)
        assert patched.count(b'GoToMultiplayerMainMenu(true)') == 3
        assert b'SetDisplayMode' not in patched
        assert b'self.inst:DoTaskInTime' in patched
        assert b'TheMixer:SetLevel("set_music", 0)' in patched
        assert b'LANGUAGE.FRENCH' in output.read('scripts/main.lua')
        assert output.read('unrelated.lua') == b'unmodified'
    with zipfile.ZipFile(host) as output:
        assert output.read(dst.MENU) == menu
        assert b'J1 world ready' in output.read(dst.PLAYER_HUD)
        assert b'pcall(os.remove, ' + marker in output.read(dst.PLAYER_HUD)
        assert b'SetSize(sz)' in output.read(dst.TEXT)
        assert b'self.root:SetScale(' not in output.read('scripts/'+dst.PLAYER_STATUS)
        assert b'self.root:SetScale(' not in output.read('scripts/'+dst.PLAYER_INFO)
        assert b'set_music' not in output.read('scripts/'+dst.TITLE)
        assert b'Profile.GetVolume' not in output.read('scripts/main.lua')
    dst.patch_bundle(bundle, host, marker=marker, resume_token='a'*32)
    with zipfile.ZipFile(host) as output:
        resume = output.read(dst.MENU)
        assert b'ShardSaveGameIndex:GetSlotLastTimePlayed(candidate)' in resume
        assert b'previous == token' in resume
        assert b'local slots_screen = ServerSlotScreen(previous_screen)' in resume
        assert b'ServerCreationScreen(slots_screen, slot)' in resume
        assert b'screen:CanResume()' in resume
        assert b'screen:Create(true)' in resume
    with zipfile.ZipFile(guest) as output:
        assert b'partydeck_resume_session' not in output.read(dst.MENU)
    with zipfile.ZipFile(bundle) as stock:
        assert stock.read('scripts/'+dst.TITLE) == title
    try:
        dst.patch_title(b'unsupported')
    except ValueError:
        pass
    else:
        raise AssertionError('unknown title layout accepted')
    original_id = '76561197960265768'
    assigned = []
    for index in (1, 2):
        player = root/f'j{index}'
        cfg = player/'game/bin64/steam_settings'
        cfg.mkdir(parents=True)
        (cfg.parent/'dontstarve_steam_x64.exe').touch()
        (cfg/'steam_appid.txt').write_text('322330\n')
        (cfg/'force_steamid.txt').write_text(original_id + '\n')
        (cfg/'configs.user.ini').write_text('[user::general]\naccount_name=Test\n')
        dst.configure_goldberg(player, player/'game')
        steamid = (cfg/'force_steamid.txt').read_text().strip()
        assert f'account_steamid={steamid}' in (cfg/'configs.user.ini').read_text().replace(' ', '')
        assert 'account_name=Test' in (cfg/'configs.user.ini').read_text()
        dst.configure_goldberg(player, player/'game')
        assert (cfg/'force_steamid.txt').read_text().strip() == steamid
        assigned.append(steamid)
    assert assigned == [original_id, str(int(original_id) + 1)]
print('DST: catalog detection, isolated host/client bundles and unknown-layout fallback verified.')
