"""Prepare Wine's exact Mono installer outside the multiplayer sandbox."""
import hashlib
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


PACKAGE = re.compile(r'wine-mono-(\d+\.\d+\.\d+)(?:-x86)?\.msi')
SHA256 = re.compile(rb'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])')


def runner_root(rom):
    from partydeck_profiles import selected_party_runner

    def setting(*keys):
        tool = shutil.which('batocera-settings-get')
        if not tool:
            return ''
        result = subprocess.run([tool, *keys], capture_output=True, text=True, timeout=3)
        return result.stdout.strip() if result.returncode == 0 and isinstance(result.stdout, str) else ''

    name = f'windows["{rom.name}"]'
    runner = (selected_party_runner(rom) or setting(f'{name}.wine-runner', 'windows.wine-runner', 'global.wine-runner')
              or setting(f'{name}.core', 'windows.core', 'global.core'))
    if not runner:
        gamescope = os.environ.get('XDG_CURRENT_DESKTOP') == 'gamescope'
        runner = 'wine-proton' if gamescope and Path('/usr/wine/wine-proton/bin/wine').is_file() else 'wine-tkg'
    runner = {'lutris': 'wine-tkg', 'proton': 'wine-proton'}.get(runner, runner)
    if not re.fullmatch(r'[\w. +()-]+', runner) or runner in ('.', '..') or runner.endswith('-UMU'):
        return None
    for root in (Path('/userdata/system/wine/custom')/runner, Path('/usr/wine')/runner):
        if root.is_dir():
            return root
    fallback = Path('/usr/wine/wine-tkg')
    return fallback if runner not in ('wine-tkg', 'wine-proton') and fallback.is_dir() else None


def installer(root):
    for lib in ('lib', 'lib64', 'lib32'):
        for dll in (root/lib/'wine').glob('*-windows/appwiz.cpl'):
            data = dll.read_bytes()
            for offset in (0, 1):
                filename = PACKAGE.search(data[offset:].decode('utf-16-le', errors='replace'))
                if filename:
                    return filename[0], filename[1], set(SHA256.findall(data))
    return None


def shared_mono(root, version, filename):
    for directory in (root/'share/wine/mono', Path('/usr/share/wine/mono'), Path('/opt/wine/mono')):
        if (directory/f'wine-mono-{version}').is_dir() or (directory/filename).is_file():
            return True
    return False


def verified(path, hashes):
    if path.is_symlink() or not path.is_file() or not hashes:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest().encode('ascii') in hashes


def prepare_mono(rom, cache):
    try:
        root = runner_root(rom)
        wanted = installer(root) if root else None
        if not wanted:
            return
        filename, version, hashes = wanted
        existing = cache/'wine'/filename
        if shared_mono(root, version, filename) or verified(existing, hashes) or not hashes:
            return
        cache_dir = existing.parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache_dir, prefix='.mono-') as stage:
            download = Path(stage)/filename
            status = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                                     '--proto', '=https', '--proto-redir', '=https',
                                     '--connect-timeout', '4', '--max-time', '25',
                                     '--max-filesize', '268435456', '--output', str(download),
                                     f'https://dl.winehq.org/wine/wine-mono/{version}/{filename}'], timeout=27)
            if status.returncode == 0 and verified(download, hashes):
                download.replace(existing)
                print(f'Windows Party: cached {filename}.', flush=True)
                return
        print(f'Windows Party: {filename} unavailable; skipping Mono at Wine startup.', flush=True)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f'Windows Party: Mono preparation unavailable: {error}', flush=True)


def mode(root, cache):
    wanted = installer(root)
    if wanted:
        filename, version, hashes = wanted
        if shared_mono(root, version, filename):
            return 'system'
        if verified(cache/'wine'/filename, hashes):
            return 'cache'
    return 'skip'


def instrument_boot(source, cache):
    block = re.compile(r'(?ms)^createOrUpdatePrefix\(\) \{\n.*?^\}')
    match = block.search(source)
    if not match:
        return source
    commands = re.compile(r'(WINEDLLOVERRIDES="\$\{OVERRIDES\}" )?(\$\{CMD_PREFIX\} "\$\{WINE\}" wineboot -u)\b')
    boot, count = commands.subn(lambda found: 'partydeck_mono_boot '
                               + ('"${OVERRIDES}" ' if found[1] else '"${WINEDLLOVERRIDES:-}" ')
                               + found[2], match[0])
    if count != 2:
        return source
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), str(cache)])
    helper = f'''partydeck_mono_boot() {{
    local overrides="$1" mono_mode
    shift
    if [[ "${{WINE_VERSION}}" == *-UMU ]]; then
        WINEDLLOVERRIDES="$overrides" "$@"
        return $?
    fi
    mono_mode="$({command} "${{DIR}}/${{WINE_VERSION}}")" || mono_mode=skip
    case "$mono_mode" in
        cache) XDG_CACHE_HOME={shlex.quote(str(cache))} WINEDLLOVERRIDES="$overrides" "$@" ;;
        system) WINEDLLOVERRIDES="$overrides" "$@" ;;
        *) printf '%s\\n' 'Windows Party: Mono unavailable; continuing Wine boot without it.' >&2
           WINEDLLOVERRIDES="${{overrides:+$overrides;}}mscoree=" "$@" ;;
    esac
}}

'''
    return source[:match.start()] + helper + boot + source[match.end():]


if __name__ == '__main__':
    try:
        print(mode(Path(sys.argv[2]), Path(sys.argv[1])))
    except OSError as error:
        print(f'Windows Party: Mono cache unreadable: {error}', file=sys.stderr)
        print('skip')
