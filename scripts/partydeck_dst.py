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
LANGUAGES = {'keep': 'Conserver', 'english': 'Anglais', 'french': 'Français',
             'german': 'Allemand', 'spanish': 'Espagnol', 'italian': 'Italien',
             'portuguese_br': 'Portugais brésilien', 'polish': 'Polonais',
             'russian': 'Russe', 'korean': 'Coréen',
             'chinese_s': 'Chinois simplifié', 'chinese_t': 'Chinois traditionnel'}


def defaults():
    return dict(language='keep', music_j1_only=False)


def validate(options):
    if options is None:
        return defaults()
    if (not isinstance(options, dict) or not isinstance(options.get('language'), str)
            or options['language'] not in LANGUAGES or type(options.get('music_j1_only')) is not bool):
        from partydeck_i18n import tr
        raise ValueError(tr('Réglages de Don’t Starve Together invalides.'))
    return options


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


def patch_menu(data, host):
    return insert(data, b'function MultiplayerMainScreen:OnUpdate(dt)', b'''
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
    if self.partydeck_search and TheNet:GetServerListingReadDirty() then
        for _, server in ipairs(TheNet:GetServerListings() or {}) do
            if server.offline and server.ip == "''' + host.encode('ascii') + b'''" then
                if self.partydeck_port ~= server.port or not self.partydeck_first_seen then
                    self.partydeck_port = server.port
                    self.partydeck_first_seen = self.partydeck_wait
                    print("[PartyDeck] J1 advertised; waiting for world startup")
                elseif self.partydeck_wait - self.partydeck_first_seen >= 15 then
                    self.partydeck_joined = true
                    print("[PartyDeck] Joining J1 over LAN")
                    TheNet:StopSearchingServers()
                    JoinServer(server)
                    return
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


def patch_bundle(source, destination, host=None, *, language='keep', mute_music=False):
    changes = {TITLE: lambda data: patch_title(data, mute_music)}
    if language != 'keep' or mute_music:
        changes[MAIN] = lambda data: patch_startup(data, language, mute_music)
    if host:
        changes[MENU] = lambda data: patch_menu(data, host)
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
        patch_bundle(bundle, temp, None if player.name == 'j1' else '192.168.247.11',
                     language=settings['language'],
                     mute_music=settings['music_j1_only'] and player.name != 'j1')
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
