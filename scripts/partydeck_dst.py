"""Private LAN startup for Don't Starve Together."""
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile


ADAPTER = 'dont-starve-together'
BUNDLE = Path('data/databundles/scripts.zip')
TITLE = 'screens/redux/mainscreen.lua'
MENU = 'screens/redux/multiplayermainscreen.lua'
MAIN = 'main.lua'
FRONTEND = 'frontend.lua'
TEXT = 'widgets/text.lua'
PLAYER_HUD = 'screens/playerhud.lua'
PLAYER_STATUS = 'screens/playerstatusscreen.lua'
HUD_SIZES = (100, 115, 125, 140)
TEXT_SIZES = (100, 110, 120, 130)
LANGUAGES = {'keep': 'Conserver', 'english': 'Anglais', 'french': 'Français',
             'german': 'Allemand', 'spanish': 'Espagnol', 'italian': 'Italien',
             'portuguese_br': 'Portugais brésilien', 'polish': 'Polonais',
             'russian': 'Russe', 'korean': 'Coréen',
             'chinese_s': 'Chinois simplifié', 'chinese_t': 'Chinois traditionnel'}


def defaults():
    return dict(language='keep', music_j1_only=False, fullscreen=True, hud_scale=125, text_scale=110,
                resume_last_world=False)


def validate(options):
    if options is None:
        return defaults()
    if (not isinstance(options, dict) or not isinstance(options.get('language'), str)
            or options['language'] not in LANGUAGES or type(options.get('music_j1_only')) is not bool
            or type(options.get('fullscreen', True)) is not bool
            or type(options.get('resume_last_world', False)) is not bool
            or type(options.get('hud_scale', 125)) is not int or options.get('hud_scale', 125) not in HUD_SIZES
            or type(options.get('text_scale', 110)) is not int or options.get('text_scale', 110) not in TEXT_SIZES):
        from partydeck_i18n import tr
        raise ValueError(tr('Réglages de Don’t Starve Together invalides.'))
    return {**defaults(), **options}


def matches(rom):
    name = re.sub(r'[^a-z0-9]', '', rom.stem.lower())
    return 'dontstarvetogether' in name or 'donotstarvetogether' in name


def insert(data, anchor, addition):
    if data.count(anchor) != 1:
        raise ValueError('unrecognized DST menu script')
    return data.replace(anchor, anchor + addition, 1)


def patch_title(data, mute_music=False):
    audio = b''
    if mute_music:
        audio = b'''
    if not self.partydeck_music_muted then
        self.partydeck_music_muted = true
        TheMixer:SetLevel("set_music", 0)
    end
'''
    data = insert(data, b'function MainScreen:OnUpdate(dt)', audio + b'''
    if not self.partydeck_started and TheFrontEnd:GetActiveScreen() == self then
        self.partydeck_delay = (self.partydeck_delay or 0) + dt
        if self.partydeck_delay >= 2 then
            self.partydeck_started = true
            self.inst:DoTaskInTime(0, function()
                if TheFrontEnd:GetActiveScreen() == self then
                    print("[PartyDeck] Starting offline menu")
                    self:OnLoginButton(true)
                else
                    self.partydeck_started = nil
                end
            end)
        end
    end
''')
    # Select the game's existing offline choice, only in the branch where the
    # native login code already offers it. Preserve license and consent checks.
    pattern = rb'(local title = STRINGS\.UI\.MAINSCREEN\.STEAMOFFLINEMODE\b[\s\S]*?TheFrontEnd:PushScreen\(confirm\))'
    data, count = re.subn(pattern, lambda m: m[1] + b'''
        TheFrontEnd:PopScreen()
        GoToMultiplayerMainMenu(true)
        return
''', data)
    if count != 1:
        raise ValueError('unrecognized DST offline prompt')
    # The same offline choice can be offered later by the login callback.
    pattern = rb'(print\s*\(\s*"failed_communication"\s*\)[\s\S]*?TheFrontEnd:PushScreen\(confirm\))'
    # The original failure branch already notifies the engine after this
    # popup is shown. Run the offline choice immediately afterwards.
    data = re.sub(pattern + rb'(\s*TheNet:NotifyAuthenticationFailure\(\))',
                  lambda m: m[0] + b'''
            TheFrontEnd:PopScreen()
            GoToMultiplayerMainMenu(true)
''', data, count=1)
    # A cached login can succeed even in the private LAN. Keep that native
    # login flow but still enter the offline menu.
    data = re.sub(rb'GoToMultiplayerMainMenu\(\s*forceOffline or false\s*\)',
                  b'GoToMultiplayerMainMenu(true)', data)
    return data


def readiness_dir(player, token):
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        raise ValueError('invalid DST session token')
    return player.parent/f'dst-world-{token}'


def ready_path(directory):
    # Wine's Z: maps the sandbox filesystem. Decimal Lua escapes preserve
    # arbitrary UTF-8 path bytes without relying on Lua Unicode escape syntax.
    raw = os.fsencode('Z:' + str(directory/'ready'))
    return b'"' + b''.join(f'\\{byte:03d}'.encode('ascii') for byte in raw) + b'"'


def patch_host_ready(data, marker):
    data = insert(data, b'function PlayerHud:SetMainCharacter(maincharacter)', b'''
    if maincharacter then
        self.inst:DoTaskInTime(1, function()
            if self.owner == maincharacter and maincharacter:IsValid() then
                local ok, written = pcall(function()
                    local file = assert(io.open(''' + marker + b''', "w"))
                    local result, err = file:write("ready")
                    local closed, close_err = file:close()
                    assert(result, err)
                    return assert(closed, close_err)
                end)
                self.partydeck_world_ready = ok and written
                if self.partydeck_world_ready then
                    print("[PartyDeck] J1 world ready")
                else
                    print("[PartyDeck] Could not signal J1 world readiness:", tostring(written))
                end
            end
        end)
    end
''')
    return insert(data, b'function PlayerHud:OnDestroy()', b'''
    if self.partydeck_world_ready then
        pcall(os.remove, ''' + marker + b''')
    end
''')


def resume_code(token):
    if not re.fullmatch(r'[0-9a-f]{32}', token):
        raise ValueError('invalid DST session token')
    return b'''
    if self.partydeck_resume_checked or not self.offline or self.leaving
            or TheFrontEnd:GetActiveScreen() ~= self then return end
    self.partydeck_resume_delay = (self.partydeck_resume_delay or 0) + dt
    if self.partydeck_resume_delay < 2.5 then return end
    self.partydeck_resume_checked = true

    -- Keep this choice across SimReset when the host returns from the world.
    local key, token = "partydeck_resume_session", "''' + token.encode('ascii') + b'''"
    TheSim:GetPersistentString(key, function(found, previous)
        if (found and previous == token) or self.leaving or TheFrontEnd:GetActiveScreen() ~= self then return end
        TheSim:SetPersistentString(key, token, false, function()
            if self.leaving or TheFrontEnd:GetActiveScreen() ~= self then return end
            local slot, newest
            for _, candidate in ipairs(ShardSaveGameIndex:GetValidSlots()) do
                local played = ShardSaveGameIndex:GetSlotLastTimePlayed(candidate)
                if type(played) == "number" and played > 0 and
                        (not newest or played > newest or (played == newest and candidate < slot)) then
                    slot, newest = candidate, played
                end
            end
            if not slot then
                print("[PartyDeck] No previously played world to resume")
                return
            end

            local ServerCreationScreen = require("screens/redux/servercreationscreen")
            self:_GoToOnlineScreen(function(previous_screen)
                local screen = ServerCreationScreen(previous_screen, slot)
                screen.inst:DoTaskInTime(SCREEN_FADE_TIME + 0.25, function()
                    if TheFrontEnd:GetActiveScreen() ~= screen or not screen:CanResume() then return end
                    if screen.server_settings_tab:GetOnlineMode() then
                        print("[PartyDeck] Last world is online; waiting for host settings")
                        return
                    end
                    print("[PartyDeck] Resuming last offline world", slot)
                    screen:Create(true)
                end)
                return screen
            end, {})
        end)
    end)
'''


def patch_menu(data, host, size=None, marker=None, resume_token=None):
    code = b''
    if size:
        width, height = size
        code = f'''
    if TheFrontEnd:GetActiveScreen() == self and not self.partydeck_display then
        self.partydeck_display_delay = (self.partydeck_display_delay or 0) + dt
        if self.partydeck_display_delay >= 1.5 then
            self.partydeck_display = true
            self.inst:DoTaskInTime(0, function()
                if TheFrontEnd:GetActiveScreen() ~= self then
                    self.partydeck_display = nil
                    return
                end
                local ok, err = pcall(function()
                    local graphics = TheFrontEnd:GetGraphicsOptions()
                    local mode = graphics:GetCurrentDisplayModeID(0)
                    local w, h = graphics:GetDisplayMode(0, mode)
                    if not (graphics:IsFullScreen() and w == {width} and h == {height}) then
                        for i = 0, graphics:GetNumDisplayModes(0) - 1 do
                            w, h = graphics:GetDisplayMode(0, i)
                            if w == {width} and h == {height} then
                                graphics:SetDisplayMode(0, i, true)
                                return
                            end
                        end
                        print("[PartyDeck] Split fullscreen mode unavailable")
                    end
                end)
                if not ok then print("[PartyDeck] Fullscreen:", err) end
            end)
        end
    end
'''.encode('ascii')
    if not host:
        if resume_token:
            code += resume_code(resume_token)
        return insert(data, b'function MultiplayerMainScreen:OnUpdate(dt)', code)
    gate = b''
    if marker:
        gate = b'''
    self.partydeck_ready_poll = (self.partydeck_ready_poll or 0) + dt
    if self.partydeck_ready_poll >= 1 then
        self.partydeck_ready_poll = 0
        local ok, ready = pcall(function()
            local file = io.open(''' + marker + b''', "r")
            if not file then return false end
            local data = file:read("*a")
            file:close()
            return data == "ready"
        end)
        if ok and ready then
            if not self.partydeck_world_ready then print("[PartyDeck] J1 ready; searching LAN") end
            self.partydeck_world_ready = true
        elseif self.partydeck_world_ready then
            self.partydeck_world_ready = nil
            self.partydeck_search = nil
            self.partydeck_first_seen = nil
            TheNet:StopSearchingServers()
        end
    end
'''
    fallback_delay = b'45' if marker else b'15'
    return insert(data, b'function MultiplayerMainScreen:OnUpdate(dt)', code + b'''
    if not self.offline or TheFrontEnd:GetActiveScreen() ~= self
            or self.partydeck_joined or TheNet:HasPendingConnection() then
        return
    end
    self.partydeck_wait = (self.partydeck_wait or 0) + dt
    if self.partydeck_wait > 600 then
        TheNet:StopSearchingServers()
        self.partydeck_joined = true
        print("[PartyDeck] LAN search timed out")
        return
    end
''' + gate + b'''
    if self.partydeck_search and TheNet:GetServerListingReadDirty() then
        for index, server in ipairs(TheNet:GetServerListings() or {}) do
            if server.offline and server.ip == "''' + host.encode('ascii') + b'''" then
                if self.partydeck_port ~= server.port or not self.partydeck_first_seen then
                    self.partydeck_port = server.port
                    self.partydeck_first_seen = self.partydeck_wait
                    if not self.partydeck_world_ready then
                        print("[PartyDeck] J1 advertised; waiting for world startup")
                    end
                end
                if self.partydeck_world_ready or self.partydeck_wait - self.partydeck_first_seen >= ''' + fallback_delay + b''' then
                    local selected = TheNet:GetServerListingFromActualIndex(index)
                    if selected and selected.ip == server.ip and selected.port == server.port then
                        self.partydeck_joined = true
                        if not self.partydeck_world_ready then
                            print("[PartyDeck] Joining via LAN readiness fallback")
                        end
                        print("[PartyDeck] Joining J1 over LAN", selected.ip, selected.port)
                        JoinServer(selected)
                        return
                    end
                end
            end
        end
    end
    if not self.partydeck_search or self.partydeck_wait - self.partydeck_search > 5 then
        if self.partydeck_search then TheNet:StopSearchingServers() end
        self.partydeck_search = self.partydeck_wait
        TheNet:SearchLANServers(true)
    end
''')


def patch_startup(data, language, mute_music):
    code = b''
    if language != 'keep':
        code += b'\nProfile.GetLanguageID = function() return LANGUAGE.' + language.upper().encode('ascii') + b' end\n'
    if mute_music:
        code += b'''
local partydeck_get_volume = Profile.GetVolume
Profile.GetVolume = function(self)
    local ambience, effects = partydeck_get_volume(self)
    return ambience, effects, 0
end
'''
    return insert(data, b'LOC = require("languages/loc")', code)


def patch_hud(data, hud_scale):
    methods = ('GetHUDScale', 'GetProportionalHUDScale', 'GetCraftingMenuScale')
    for method in methods:
        if f'function FrontEnd:{method}()'.encode('ascii') not in data:
            raise ValueError('unrecognized DST HUD methods')
    names = ', '.join(f'"{method}"' for method in methods)
    return data + f'''

local function partydeck_scale_hud(method)
    local original = FrontEnd[method]
    FrontEnd[method] = function(self)
        return original(self) * ({hud_scale} / 100)
    end
end
for _, method in ipairs({{{names}}}) do
    partydeck_scale_hud(method)
end
'''.encode('ascii')


def patch_text(data, scale):
    call = b'self.inst.TextWidget:SetSize(sz)'
    if data.count(call) != 1:
        raise ValueError('unrecognized DST text widget')
    # Keep the logical size intact for widgets that read it back to shrink or
    # animate labels. Scaling the input would compound on those repeated calls.
    return data.replace(call, f'self.inst.TextWidget:SetSize(sz * ({scale} / 100))'.encode('ascii'))


def patch_player_status(data, scale):
    anchor = b'self.root:SetScaleMode(SCALEMODE_PROPORTIONAL)'
    if data.count(anchor) != 1:
        return data
    amount = f'{scale / 100:g}'
    return insert(data, anchor, f'\n        self.root:SetScale({amount}, {amount}, 1)'.encode('ascii'))


def patch_bundle(source, destination, host=None, *, language='keep', mute_music=False,
                 fullscreen_size=None, hud_scale=100, text_scale=100, marker=None, resume_token=None):
    changes = {TITLE: lambda data: patch_title(data, mute_music)}
    if language != 'keep' or mute_music:
        changes[MAIN] = lambda data: patch_startup(data, language, mute_music)
    if host or fullscreen_size or resume_token:
        changes[MENU] = lambda data: patch_menu(data, host, fullscreen_size, marker, resume_token)
    if marker and not host:
        changes[PLAYER_HUD] = lambda data: patch_host_ready(data, marker)
    if hud_scale != 100:
        changes[FRONTEND] = lambda data: patch_hud(data, hud_scale)
    if text_scale != 100:
        changes[TEXT] = lambda data: patch_text(data, text_scale)
    with zipfile.ZipFile(source) as stock, zipfile.ZipFile(destination, 'w') as output:
        members = {}
        for name, patch in changes.items():
            candidates = [entry for entry in stock.infolist() if entry.filename in (name, 'scripts/' + name)]
            if len(candidates) != 1:
                raise ValueError('DST menu scripts not found')
            members[candidates[0].filename] = patch
        for entry in stock.infolist():
            data = stock.read(entry)
            if entry.filename in members:
                data = members[entry.filename](data)
            if hud_scale != 100 and entry.filename in (PLAYER_STATUS, 'scripts/' + PLAYER_STATUS):
                data = patch_player_status(data, hud_scale)
            if entry.filename in ('mainfunctions.lua', 'scripts/mainfunctions.lua'):
                disconnect = b'function OnNetworkDisconnect( message, should_reset, force_immediate_reset, details, miscdata)'
                if data.count(disconnect) == 1:
                    data = insert(data, disconnect, b'\n    print("[PartyDeck] Network disconnect", tostring(message))\n')
            output.writestr(entry, data)


def find_bundle(directory, prefix):
    for root in (directory, directory.parent):
        bundle = root / BUNDLE
        if bundle.is_relative_to(prefix) and bundle.resolve() == bundle and bundle.is_file():
            if any(root.glob('bin*/dontstarve_steam*.exe')):
                return bundle
    return None


def overlay(bundle, source):
    subprocess.run(['mount', '--bind', str(source), str(bundle)], check=True)


def configure_goldberg(player, root):
    from partydeck_borderlands2 import decode, patch_ini, write_bytes
    from partydeck_l4d2 import ACCOUNT_MAX, STEAM64_BASE, player_id, valid_id, value
    from partydeck_profiles import atomic_write

    folders = [root, *(path.parent for path in root.glob('bin*/dontstarve_steam*.exe'))]
    targets = []
    seed = None
    for folder in dict.fromkeys(folders):
        settings = folder/'steam_settings'
        if not settings.is_dir() or settings.resolve() != settings:
            continue
        ini, legacy = settings/'configs.user.ini', settings/'force_steamid.txt'
        appid = settings/'steam_appid.txt'
        if any(path.is_symlink() for path in (ini, legacy, appid)):
            continue
        if appid.is_file() and appid.read_text(encoding='utf-8-sig').strip() != '322330':
            continue
        if not (ini.is_file() or legacy.is_file() or appid.is_file()
                or (settings/'configs.main.ini').is_file() or (settings/'force_account_name.txt').is_file()):
            continue
        data, encoding = decode(ini.read_bytes() if ini.is_file() else b'')
        configured = value(data, 'user::general', 'account_steamid')
        if not valid_id(configured) and legacy.is_file():
            configured = legacy.read_text(encoding='utf-8-sig').strip()
        if seed is None and valid_id(configured):
            seed = configured
        targets.append((ini, legacy, data, encoding))
    if not targets:
        print('PartyDeck DST: no local Goldberg settings detected.', flush=True)
        return
    index = int(player.name.removeprefix('j')) - 1
    identity = player/'dst-goldberg-steamid'
    if identity.is_symlink():
        raise ValueError('redirected Goldberg identity')
    if identity.is_file():
        steamid = identity.read_text().strip()
        if not valid_id(steamid):
            raise ValueError('invalid saved Goldberg Steam ID')
    else:
        if seed is None:
            digest = hashlib.sha256(os.fsencode(player.parent)).digest()
            seed = str(STEAM64_BASE + int.from_bytes(digest[:8], 'big') % ACCOUNT_MAX + 1)
        steamid = player_id(seed, index)
        atomic_write(identity, steamid + '\n')
    for ini, legacy, before, encoding in targets:
        after = patch_ini(before, {'user::general': {'account_steamid': steamid}}).encode(encoding)
        if not ini.is_file() or ini.read_bytes() != after:
            # Atomic replacement within the player's writable game overlay.
            write_bytes(ini, after)
        if not legacy.is_file() or legacy.read_text(encoding='utf-8-sig').strip() != steamid:
            atomic_write(legacy, steamid + '\n')
    print(f'PartyDeck DST {player.name.upper()}: Goldberg Steam ID {steamid}.', flush=True)


def prepare(player, directory, prefix, settings):
    source = player/'dst-scripts.zip'
    source.unlink(missing_ok=True)
    bundle = find_bundle(directory, prefix)
    if bundle is None:
        print('PartyDeck DST: private script bundle not found; manual LAN available.', flush=True)
        return
    try:
        configure_goldberg(player, bundle.parents[2])
    except (OSError, ValueError) as error:
        print(f'PartyDeck DST {player.name.upper()}: Goldberg identity unavailable: {error}', flush=True)
    fd, tmp = tempfile.mkstemp(dir=player, prefix='.dst-')
    os.close(fd)
    temp = Path(tmp)
    try:
        size = tuple(int(os.environ.get(f'PARTYDECK_PLAYER_{axis}', '0')) for axis in ('WIDTH', 'HEIGHT'))
        token = os.environ.get('PARTYDECK_SESSION_TOKEN')
        marker = ready_path(readiness_dir(player, token))
        is_host = player.name == 'j1'
        patch_bundle(bundle, temp, None if is_host else '192.168.247.11',
                     language=settings['language'],
                     mute_music=settings['music_j1_only'] and player.name != 'j1',
                     fullscreen_size=size if settings['fullscreen'] and all(0 < n <= 16384 for n in size) else None,
                     hud_scale=settings['hud_scale'],
                     text_scale=settings['text_scale'], marker=marker,
                     resume_token=token if is_host and settings['resume_last_world'] else None)
        temp.replace(source)
        overlay(bundle, source)
        print(f'PartyDeck DST {player.name.upper()}: LAN menus prepared.', flush=True)
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        source.unlink(missing_ok=True)
        print(f'PartyDeck DST: {error}; manual LAN available.', flush=True)
    finally:
        temp.unlink(missing_ok=True)


def prepare_umu(player):
    prefix = Path(os.environ.get('WINEPREFIX', ''))
    if prefix.parent != Path('/userdata/system/umu/compatdata'):
        return ()
    source = player/'dst-scripts.zip'
    if not source.is_file() or source.is_symlink():
        return ()
    bundle = find_bundle(Path.cwd(), (prefix/'pfx'/'drive_c').resolve())
    if bundle is None or any(char in str(bundle) for char in ':\n\r'):
        return ()
    mounted = ()
    if not source.samefile(bundle):
        try:
            overlay(bundle, source)
            mounted = (bundle,)
        except subprocess.SubprocessError as error:
            print(f'PartyDeck DST: UMU script mount failed: {error}', flush=True)
            return ()
    from partydeck_umu import pressure_vessel_environment
    env = pressure_vessel_environment([bundle], writable=False)
    os.environ['PRESSURE_VESSEL_FILESYSTEMS_RO'] = env['PRESSURE_VESSEL_FILESYSTEMS_RO']
    return mounted


def install_hook(base, player, rom):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import atomic_write, read_profile

    binary = Path(shutil.which('batocera-wine') or '/usr/bin/batocera-wine').resolve()
    launcher = player/'batocera-wine-dst'
    settings = read_profile(base, rom)['dst']
    hook = [sys.executable, str(base/'partydeck_dst.py'), str(player), json.dumps(settings)]
    try:
        atomic_write(launcher, instrument_native(binary.read_text(), hook, prefix_argument=True), 0o755)
        subprocess.run(['bash', '-n', str(launcher)], check=True)
        overlay(binary, launcher)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f'PartyDeck DST: {error}; manual LAN available.', flush=True)


if __name__ == '__main__':
    player, settings, directory, prefix = sys.argv[1:]
    player = Path(player)
    if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player):
        raise SystemExit('PartyDeck DST: player namespace required')
    prepare(player, Path(directory).resolve(), Path(prefix).resolve(), validate(json.loads(settings)))
