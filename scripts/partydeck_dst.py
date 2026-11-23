"""Private LAN startup for Don't Starve Together."""
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


def matches(rom):
    name = re.sub(r'[^a-z0-9]', '', rom.stem.lower())
    return 'dontstarvetogether' in name or 'donotstarvetogether' in name


def insert(data, anchor, addition):
    if data.count(anchor) != 1:
        raise ValueError('unrecognized DST menu script')
    return data.replace(anchor, anchor + addition, 1)


def patch_title(data):
    data = insert(data, b'function MainScreen:OnUpdate(dt)', b'''
    if not self.partydeck_started and TheFrontEnd:GetActiveScreen() == self then
        self.partydeck_delay = (self.partydeck_delay or 0) + dt
        if self.partydeck_delay >= 2 then
            self.partydeck_started = true
            self.partydeck_choose_offline = true
            self:OnLoginButton(true)
            self.partydeck_choose_offline = nil
            return
        end
    end
''')
    # Select the game's existing offline choice, only in the branch where the
    # native login code already offers it. Preserve license and consent checks.
    pattern = rb'(local title = STRINGS\.UI\.MAINSCREEN\.STEAMOFFLINEMODE\b[\s\S]*?TheFrontEnd:PushScreen\(confirm\))'
    data, count = re.subn(pattern, lambda m: m[1] + b'''
        if self.partydeck_choose_offline then
            TheFrontEnd:PopScreen()
            GoToMultiplayerMainMenu(true)
            return
        end
''', data)
    if count != 1:
        raise ValueError('unrecognized DST offline prompt')
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
                self.partydeck_joined = true
                print("[PartyDeck] Joining J1 over LAN")
                TheNet:StopSearchingServers()
                JoinServer(server)
                return
            end
        end
    end
    if not self.partydeck_search or self.partydeck_wait - self.partydeck_search > 5 then
        if self.partydeck_search then TheNet:StopSearchingServers() end
        self.partydeck_search = self.partydeck_wait
        TheNet:SearchLANServers(true)
    end
''')


def patch_bundle(source, destination, host=None):
    changes = {TITLE: patch_title}
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


def prepare(player, directory, prefix):
    source = player/'dst-scripts.zip'
    source.unlink(missing_ok=True)
    bundle = find_bundle(directory, prefix)
    if bundle is None:
        print('PartyDeck DST: private script bundle not found; manual LAN available.', flush=True)
        return
    fd, tmp = tempfile.mkstemp(dir=player, prefix='.dst-')
    os.close(fd)
    temp = Path(tmp)
    try:
        patch_bundle(bundle, temp, None if player.name == 'j1' else '192.168.247.11')
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


def install_hook(base, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import atomic_write

    binary = Path(shutil.which('batocera-wine') or '/usr/bin/batocera-wine').resolve()
    launcher = player/'batocera-wine-dst'
    hook = [sys.executable, str(base/'partydeck_dst.py'), str(player)]
    try:
        atomic_write(launcher, instrument_native(binary.read_text(), hook, prefix_argument=True), 0o755)
        subprocess.run(['bash', '-n', str(launcher)], check=True)
        overlay(binary, launcher)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(f'PartyDeck DST: {error}; manual LAN available.', flush=True)


if __name__ == '__main__':
    player, directory, prefix = (Path(arg) for arg in sys.argv[1:])
    if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player):
        raise SystemExit('PartyDeck DST: player namespace required')
    prepare(player, directory.resolve(), prefix.resolve())
