"""D2RLoader in PartyDeck's per-player Wine views."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from partydeck_borderlands2 import child, patch_ini, write_bytes
from partydeck_bottles import private_windows_paths
from partydeck_i18n import tr
from partydeck_l4d2 import safe_path


ADAPTER = 'd2rloader'
LABEL = 'Diablo II: Resurrected · D2RLoader LAN'
PORT = 4000
PLUGIN = 'd2rl-partydeck-lan.dll'
CORE_131 = '2a868d013d2e0830bd2d9e04b918b19e46a73cf726c833e70d089b948fdeb5a2'


def matches(rom):
    name = re.sub(r'[^a-z0-9]', '', rom.stem.casefold())
    return name.startswith('d2r') or 'diabloiiresurrected' in name or 'diablo2resurrected' in name


def defaults():
    return {'automatic': True}


def validate(options):
    if options is None:
        return defaults()
    if not isinstance(options, dict) or type(options.get('automatic', True)) is not bool:
        raise ValueError(tr('Réglages D2RLoader invalides.'))
    return defaults() | {'automatic': options.get('automatic', True)}


def readiness_dir(player, token):
    if not re.fullmatch(r'[0-9a-f]{32}', token or ''):
        raise ValueError('Invalid D2RLoader session token')
    return player.parent / f'd2r-lan-{token}'


def sync_readiness(marker, namespace_pid, proc=Path('/proc')):
    """Check the host namespace's listening sockets without opening a game connection."""
    listening = False
    for table in ('tcp', 'tcp6'):
        try:
            with (proc / str(namespace_pid) / 'net' / table).open() as stream:
                next(stream, None)
                listening = any(
                    address.rsplit(':', 1)[-1] == f'{PORT:04X}' and state == '0A'
                    for _, address, _, state, *_ in (line.split() for line in stream)
                )
        except FileNotFoundError:
            continue
        if listening:
            marker.touch(exist_ok=True)
            return
    marker.unlink(missing_ok=True)


def prepare(directory, prefix, player, plugin_source, automatic, rom):
    mounted_content = (rom,) if rom.suffix.casefold() == '.pc' else ()
    allowed = tuple(root.resolve() for root in (prefix, player, *mounted_content, *private_windows_paths(player)))
    directory = safe_path(directory, allowed)

    def path(parent, name):
        return safe_path(child(parent, name), allowed)

    loader = path(directory, 'D2RLoader.exe')
    core = path(directory, 'D2RCore.dll')
    if not all(file.is_file() for file in (loader, core, path(directory, 'D2R.exe'))):
        raise ValueError(tr('D2RLoader absent du dossier du jeu indiqué par DIR dans autorun.cmd.'))

    loader_dir = path(directory, 'd2rloader')
    settings = path(path(loader_dir, 'config'), 'd2rloader.toml')
    plugin = path(path(loader_dir, 'plugins'), PLUGIN)
    use_plugin = False
    if automatic:
        with core.open('rb') as source:
            use_plugin = hashlib.file_digest(source, 'sha256').hexdigest() == CORE_131
        if not use_plugin:
            print(tr('D2RLoader : automatisation disponible avec la version 1.3.1-beta. Utilisez le menu LAN.'),
                  file=sys.stderr, flush=True)

    text = settings.read_text(encoding='utf-8-sig') if settings.is_file() else ''
    # These options belong to this LAN session. Preserve the mod, language,
    # extensions, backup preferences and the rest of the player's TOML.
    text = patch_ini(text, {
        'd2rloader': {'show_tcpip_button': 'true', 'check_for_updates': 'false'},
        'd2rloader.advanced': {'game_port': str(PORT), 'automatic_port_mapping': 'false',
                               'hosting_check': 'false'},
    })
    if use_plugin:
        address = str(ipaddress.IPv4Address(os.environ['PARTYDECK_D2R_HOST']))
        count = int(os.environ['PARTYDECK_SESSION_PLAYERS'])
        if not 2 <= count <= 4:
            raise ValueError(tr('Réglages D2RLoader invalides.'))
        state_path = path(path(loader_dir, 'data'), 'state.json')
        state = json.loads(state_path.read_text(encoding='utf-8-sig')) if state_path.is_file() else {'version': 1}
        if not isinstance(state, dict) or not isinstance(state.get('multiplayer', {}), dict):
            raise ValueError(tr('Réglages D2RLoader invalides.'))
        multiplayer = state.setdefault('multiplayer', {})
        capacity = multiplayer.get('maxPlayers', 8)
        if type(capacity) is not int or not count <= capacity <= 8:
            capacity = max(4, count)
        multiplayer.update(lanOnly=True, unlisted=False, password='', directJoinAddress=address, maxPlayers=capacity)
        dll = plugin_source.read_bytes()
        write_bytes(state_path, (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode())
        write_bytes(plugin, dll)
    else:
        plugin.unlink(missing_ok=True)
    write_bytes(settings, text.encode('utf-8'))
    return loader.name


def instrument_native(source, hook):
    from partydeck_anchor import instrument_native as before_wine

    rewritten = before_wine(source, hook, prefix_argument=True)
    # The hook prints the verified executable filename. Keep any arguments
    # already supplied to D2RLoader through autorun.cmd.
    command = shlex.join(hook)
    prefix = command + ' "$PWD" "${WINEPOINT:-${GAMENAME}}" && '
    launcher = ('partydeck_d2r=$(' + prefix.removesuffix(' && ') + ') && '
                'if [[ ${WINE_CMD,,} != *d2rloader.exe* ]]; then WINE_CMD="$partydeck_d2r"; fi && ')
    return ''.join(line.replace(prefix, launcher).rstrip('\n') + ' || return $?\n'
                   if prefix in line else line for line in rewritten.splitlines(keepends=True))


def install_hook(base, original, player):
    from partydeck_profiles import atomic_write

    mode = os.environ.get('PARTYDECK_D2R')
    if mode not in ('automatic', 'manual'):
        return
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    plugin = base / 'plugins' / PLUGIN
    replacement = player / 'batocera-wine-d2rloader'
    hook = [sys.executable, str(base / 'partydeck_d2rloader.py'), str(player), str(plugin), mode, str(original)]
    atomic_write(replacement, instrument_native(binary.read_text(), hook), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)


if __name__ == '__main__':
    try:
        player, plugin, mode, rom, directory, prefix = sys.argv[1:]
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != player:
            raise ValueError(tr('D2RLoader : espace privé du joueur requis.'))
        print(prepare(Path(directory), Path(prefix), Path(player), Path(plugin), mode == 'automatic', Path(rom)))
    except (OSError, ValueError, KeyError) as error:
        print(f'D2RLoader: {error}', file=sys.stderr, flush=True)
        raise SystemExit(1)
