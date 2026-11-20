"""HKMultiplayerMOD 0.36.2: native API bridge in each player's existing COW view."""
from partydeck_i18n import tr
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import uuid
from partydeck_borderlands2 import child, decode, patch_ini, write_bytes, PRIVATE_BINDS
from partydeck_l4d2 import safe_path
from partydeck_nfsmw import finish_launch
from partydeck_bottles import private_windows_paths
from partydeck_hkmp import check_dimensions, matches as hollow_knight

CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
HOST_CHOICES = {
    'bossHealth': (1, 1.25, 1.5, 2, 2.5, 3, 4),
    'enemyHealth': (1, 1.25, 1.5, 2),
    'revive': (0, 1), 'reviveSeconds': (1, 2, 3, 5), 'reviveSoul': (0, 33, 66, 99),
    'sharedMap': (0, 1), 'stagTogether': (0, 1), 'showNames': (0, 1), 'showPartnerHealth': (0, 1),
}


def matches(rom):
    return hollow_knight(rom) and bool(re.search(r'multiplayer|1[._ ]5[._ ]12620', rom.stem, re.I))


def defaults():
    return dict(automatic=True, port=26950, names=['J1', 'J2', 'J3', 'J4'],
                world='latest', world_name='Windows Party', fix_controllers=True, ultrawide=True,
                host=dict(bossHealth=1.5, enemyHealth=1, revive=1, reviveSeconds=2, reviveSoul=33,
                          sharedMap=1, stagTogether=1, showNames=1, showPartnerHealth=1))


def validate(data):
    if not isinstance(data, dict):
        raise ValueError(tr('Réglages HKMultiplayer invalides.'))
    out = {k: data.get(k, v) for k, v in defaults().items()}
    if (any(type(out[k]) is not bool for k in ('automatic', 'fix_controllers', 'ultrawide'))
            or type(out['port']) is not int or not 1024 <= out['port'] <= 65535
            or out['world'] not in ('latest', 'named')
            or not isinstance(out['world_name'], str) or not 1 <= len(out['world_name'].strip()) <= 40
            or any(ord(c) < 32 or c in '\r\n=' for c in out['world_name'])):
        raise ValueError(tr('Réglages HKMultiplayer invalides.'))
    names = out['names']
    if (not isinstance(names, list) or len(names) != 4
            or any(not isinstance(n, str) or not re.fullmatch(r'[A-Za-z0-9]{1,20}', n) for n in names)
            or len({n.casefold() for n in names}) != 4):
        raise ValueError(tr('HKMP : quatre noms différents de 1 à 20 lettres ASCII ou chiffres.'))
    if (not isinstance(out['host'], dict) or set(out['host']) != set(HOST_CHOICES)
            or any(type(out['host'][key]) not in (int, float) or out['host'][key] not in choices
                   for key, choices in HOST_CHOICES.items())):
        raise ValueError(tr('Réglages HKMultiplayer invalides.'))
    out['world_name'] = out['world_name'].strip()
    return out


def session_code():
    """Called once by the coordinator, before starting any player namespace."""
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def instrument_display(source, width, height):
    check_dimensions(width, height, 0)
    pattern = re.compile(r'(?m)^([ \t]*)WINE_CMD=\$\(getWine_var [^\r\n]+\)[ \t]*$')
    parts = re.split(r'(?m)^(?=\w+\(\) \{)', source)
    for name in ('play_wine', 'play_pc', 'play_squashfs'):
        indices = [i for i, body in enumerate(parts) if body.startswith(name + '() {')]
        if len(indices) != 1 or len(pattern.findall(parts[indices[0]])) != 1:
            raise RuntimeError(tr('Lanceur Hollow Knight non reconnu ; adaptation refusée.'))
        i = indices[0]
        extra = ('\ncase "$WINE_CMD" in\n'
                 '*[Hh][Oo][Ll][Ll][Oo][Ww]_[Kk][Nn][Ii][Gg][Hh][Tt].[Ee][Xx][Ee]*) '
                 f'WINE_CMD="${{WINE_CMD}} -screen-fullscreen 0 -popupwindow -screen-width {width} -screen-height {height}" ;;\n'
                 'esac')
        parts[i] = pattern.sub(lambda m: m[0] + extra, parts[i])
    return ''.join(parts)


def apply_config(directory, prefix, payload, private_binds=PRIVATE_BINDS):
    player = Path(payload['player']).resolve()
    prefix = prefix.resolve()
    allowed = tuple(p.resolve() for p in (prefix, player, *private_binds, *private_windows_paths(player)))
    directory = safe_path(directory, allowed)
    index, width, height = payload['index'], payload['width'], payload['height']
    check_dimensions(width, height, index)
    options = validate(payload['settings'])
    code = payload['code']
    if not isinstance(code, str) or not re.fullmatch('[' + CODE_ALPHABET + ']{8}', code):
        raise ValueError(tr('Code de session HKMultiplayer invalide.'))

    def path(root, *names):
        for name in names:
            root = safe_path(child(root, name), allowed)
        return root

    managed = path(directory, 'hollow_knight_Data', 'Managed')
    mods = path(managed, 'Mods')
    if (not path(directory, 'hollow_knight.exe').is_file()
            or not path(mods, 'HKMultiplayer', 'HKMultiplayer.dll').is_file()):
        raise ValueError(tr('HKMultiplayer.dll absent ; installez HKMultiplayerMOD 0.36.2 et son API.'))
    companion = Path(payload['plugin'])
    wide = Path(payload['wide_plugin'])
    if not companion.is_file() or (options['ultrawide'] and not wide.is_file()):
        raise ValueError(tr('Plugin compagnon Hollow Knight absent.'))
    identity = path(prefix, 'drive_c', 'windows', 'windows-party-hkmultiplayer-identity.json')
    saved = json.loads(identity.read_text()) if identity.is_file() else {}
    if (not isinstance(saved, dict) or saved.get('player') != index
            or not isinstance(saved.get('key'), str) or not re.fullmatch(r'[0-9a-f]{32}', saved['key'])):
        saved = dict(player=index, key=secrets.token_hex(16))

    targets = []
    users = path(prefix, 'drive_c', 'users')
    for user in sorted(users.iterdir()) if users.is_dir() else []:
        if not user.is_dir() or user.name.casefold() in ('public', 'default', 'default user', 'all users'):
            continue
        target = path(user, 'AppData', 'LocalLow', 'Team Cherry', 'Hollow Knight',
                      'HKMultiplayerMod.GlobalSettings.json')
        data = json.loads(target.read_text(encoding='utf-8-sig')) if target.is_file() else {}
        if not isinstance(data, dict):
            raise ValueError(tr('Réglages HKMultiplayer invalides.'))
        data.update(PlayerKey=saved['key'], PlayerName=options['names'][index],
                    LastAddress='127.0.0.1', Port=options['port'], SteamAccess=2, CheckForUpdates=False)
        if target not in [p for p, _ in targets]:
            targets.append((target, data))
    if not targets:
        raise ValueError(tr('Hollow Knight : utilisateur Wine absent ; lancez le jeu en solo une fois.'))

    # All validation is complete before touching the private player view.
    # Doorstop stays installed but disabled; HKMultiplayer has its own native API.
    doorstop = path(directory, 'doorstop_config.ini')
    if doorstop.is_file():
        text, codec = decode(doorstop.read_bytes())
        write_bytes(doorstop, patch_ini(text, {'General': {'enabled': 'false'}}).encode(codec))
    bridge_dir = path(mods, 'WindowsPartyHKMultiplayer')
    configuration = dict(Enabled='true', Automatic=str(options['automatic']).lower(), Player=index + 1,
                         Width=width, Height=height, Address='127.0.0.1', Port=options['port'], Code=code,
                         Username=options['names'][index], World=options['world'], WorldName=options['world_name'],
                         FixControllers=str(options['fix_controllers']).lower())
    configuration.update({'Host.' + k: v for k, v in options['host'].items()})
    write_bytes(path(bridge_dir, 'WindowsParty.HKMultiplayer.dll'), companion.read_bytes())
    write_bytes(path(bridge_dir, 'windows-party.cfg'),
                ''.join(f'{k}={v}\n' for k, v in configuration.items()).encode())
    wide_dll = path(mods, 'WindowsPartyNativeWide', 'WindowsParty.NativeWide.dll')
    disabled_wide = path(mods, 'WindowsPartyNativeWide', 'WindowsParty.NativeWide.dll.windows-party-disabled')
    if options['ultrawide']:
        write_bytes(wide_dll, wide.read_bytes())
        disabled_wide.unlink(missing_ok=True)
    elif wide_dll.is_file():
        wide_dll.rename(disabled_wide)
    write_bytes(identity, (json.dumps(saved) + '\n').encode())
    for target, data in targets:
        write_bytes(target, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode())
    print(tr('HKMultiplayer J{p0} : {p1}×{p2}, réseau automatique {p3}, entrée native désactivée {p4}.',
             p0=index + 1, p1=width, p2=height, p3=options['automatic'], p4=options['fix_controllers']), flush=True)


def install_hook(base, rom, player):
    from partydeck_profiles import profile_path, read_profile, atomic_write
    from partydeck_anchor import instrument_native
    if not profile_path(base, rom).exists():
        return
    profile = read_profile(base, rom)
    if profile.get('adapter') != 'hollowknight-hkmultiplayer':
        return
    options = validate(profile['hkmultiplayer'])
    index = int(player.name.removeprefix('j')) - 1
    width = int(os.environ.get('PARTYDECK_PLAYER_WIDTH', '0'))
    height = int(os.environ.get('PARTYDECK_PLAYER_HEIGHT', '0'))
    check_dimensions(width, height, index)
    code = os.environ.get('PARTYDECK_HKMULTIPLAYER_CODE', '')
    if not re.fullmatch('[' + CODE_ALPHABET + ']{8}', code):
        raise ValueError(tr('Code de session HKMultiplayer invalide.'))
    result = player / f'hkmultiplayer-result-{uuid.uuid4().hex}.json'
    payload = player / 'hkmultiplayer-launch.json'
    atomic_write(payload, json.dumps(dict(player=str(player), settings=options, index=index, width=width,
                                         height=height, code=code, result=str(result),
                                         plugin=str(base / 'plugins' / 'WindowsParty.HKMultiplayer.dll'),
                                         wide_plugin=str(base / 'plugins' / 'WindowsParty.NativeWide.dll'))))
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    replacement = player / 'batocera-wine-hkmultiplayer'
    source = instrument_display(binary.read_text(), width, height)
    hook = [sys.executable, str(base / 'partydeck_hkmultiplayer.py'), str(payload)]
    atomic_write(replacement, instrument_native(source, hook, prefix_argument=True), 0o755)
    subprocess.run(['bash', '-n', str(replacement)], check=True)
    atomic_write(result, '{"version":1,"code":1}\n')
    try:
        subprocess.run(['mount', '--bind', str(replacement), str(binary)], check=True)
    except Exception:
        result.unlink(missing_ok=True)
        raise
    return result


if __name__ == '__main__':
    try:
        data = json.loads(Path(sys.argv[1]).read_text())
        player = Path(data['player']).resolve()
        result = Path(data['result'])
        if (os.environ.get('PARTYDECK_PRIVATE_PLAYER') != str(player) or result.parent.resolve() != player
                or not re.fullmatch(r'hkmultiplayer-result-[0-9a-f]{32}\.json', result.name)):
            raise ValueError(tr('Contexte privé Hollow Knight invalide.'))
        write_bytes(result, b'{"version":1,"code":1}\n')
        apply_config(Path(sys.argv[2]), Path(sys.argv[3]), data)
        write_bytes(result, b'{"version":1,"code":0}\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Windows Party / HKMultiplayer : {error}', file=sys.stderr)
        raise SystemExit(1)
