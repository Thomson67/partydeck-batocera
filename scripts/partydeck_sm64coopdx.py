"""SM64CoopDX common configuration in each private Batocera Wine view.

Keys and ranges follow coop-deluxe/sm64coopdx v1.5.1 configfile.c and DJUI.
The common template is user supplied; no game assets are distributed.
"""
from partydeck_i18n import tr
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

from partydeck_borderlands2 import child, write_bytes, PRIVATE_BINDS

LANGUAGES = ('French', 'English', 'German', 'Italian', 'Spanish', 'Portuguese',
             'Dutch', 'Polish', 'Czech', 'Russian', 'Japanese')
LANGUAGE_LABELS = dict(zip(LANGUAGES,('Français','Anglais','Allemand','Italien','Espagnol',
                                    'Portugais','Néerlandais','Polonais','Tchèque','Russe','Japonais')))
VOLUME_FIELDS = (('master_volume','Volume général'),('music_volume','Musique'),
                 ('sfx_volume','Bruitages'),('env_volume','Ambiance'))
BASE_VOLUMES = dict(master_volume=63,music_volume=100,sfx_volume=100,env_volume=100)
DRAW_LABELS = ('0,5×','1×','1,5×','3×','10×','100×','Infinie')


def safe_path(path, allowed):
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError(tr('Configuration SM64CoopDX hors de la vue privée : {p0}',p0=path))
    return resolved


def matches(rom):
    name = rom.stem.casefold()
    return bool(re.search(r'(?<![a-z0-9])(?:sm64[\s_-]*coop[\s_-]*(?:dx|deluxe)|'
                          r'(?:super[\s_-]*)?mario[\s_-]*64[\s_-]*coop[\s_-]*(?:dx|deluxe))(?![a-z0-9])',name))


def defaults():
    return dict(vsync=True,msaa=8,texture_filtering=2,coop_draw_distance=6,
                free_camera=True,sensitivity_x=20,sensitivity_y=20,invert_x=True,invert_y=True,
                names=[tr('Joueur{p0}',p0=i) for i in range(1,5)],language='French',
                music_j1_only=True,volumes={})


def validate(options):
    if not isinstance(options,dict):
        raise ValueError(tr('Réglages SM64CoopDX invalides.'))
    normalized = {key:options.get(key,value) for key,value in defaults().items()}
    for key in ('vsync','free_camera','invert_x','invert_y','music_j1_only'):
        if type(normalized[key]) is not bool:
            raise ValueError(tr('Réglages SM64CoopDX invalides.'))
    for key,values in (('msaa',(0,2,4,8,16)),('texture_filtering',range(3)),
                       ('coop_draw_distance',range(7)),('sensitivity_x',range(1,101)),
                       ('sensitivity_y',range(1,101))):
        if type(normalized[key]) is not int or normalized[key] not in values:
            raise ValueError(tr('Réglages SM64CoopDX invalides.'))
    if normalized['language'] not in LANGUAGES:
        raise ValueError(tr('Langue SM64CoopDX invalide.'))
    names = normalized['names']
    if (not isinstance(names,list) or len(names) != 4
            or any(not isinstance(name,str) or not name.strip() or len(name.encode('utf-8')) > 63
                   or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in name) for name in names)
            or len(set(names)) != 4):
        raise ValueError(tr('SM64CoopDX : quatre noms différents, non vides, de 63 octets UTF-8 maximum, sans espaces (utilisez _).'))
    volumes = normalized['volumes']
    if (not isinstance(volumes,dict) or any(key not in BASE_VOLUMES for key in volumes)
            or any(type(value) is not int or not 0 <= value <= 100 for value in volumes.values())):
        raise ValueError(tr('Les volumes SM64CoopDX doivent être des entiers de 0 à 100 %.'))
    return normalized


def patch_config(text, values):
    """Keep every repeated mod/pack/save-name line and the template's newlines."""
    pending = dict(values)
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = []
    for line in text.splitlines(keepends=True):
        match = re.match(r'^(\s*)([^\s#]+)([ \t]+)([^\r\n]*)(\r?\n)?$',line)
        if match and match[2] in values:
            value = values[match[2]]
            value = str(value).lower() if type(value) is bool else str(value)
            line = match[1]+match[2]+match[3]+value+(match[5] or '')
            pending.pop(match[2],None)
        lines.append(line)
    if lines and pending and not lines[-1].endswith(('\r','\n')):
        lines[-1] += newline
    for key,value in pending.items():
        value = str(value).lower() if type(value) is bool else str(value)
        lines.append(f'{key} {value}{newline}')
    return ''.join(lines)


def configured_template(template, settings, index, width, height):
    options = validate(settings)
    if type(index) is not int or index not in range(4):
        raise ValueError(tr('Numéro de joueur SM64CoopDX invalide.'))
    if (type(width) is not int or type(height) is not int
            or not 64 <= width <= 32768 or not 64 <= height <= 32768):
        raise ValueError(tr('Dimensions de la fenêtre SM64CoopDX indisponibles.'))
    if not isinstance(template,str) or not all(re.search(r'^'+key+r'\s+',template,re.M)
                                              for key in ('vsync','coop_player_name','language','music_volume')):
        raise ValueError(tr('Configuration commune SM64CoopDX invalide.'))
    values = {key:options[key] for key in ('vsync','msaa','texture_filtering','coop_draw_distance')}
    values.update(window_w=width,window_h=height,bettercam_enable=options['free_camera'],
                  bettercam_xsens=options['sensitivity_x'],bettercam_ysens=options['sensitivity_y'],
                  bettercam_invertx=options['invert_x'],bettercam_inverty=options['invert_y'],
                  coop_player_name=options['names'][index],language=options['language'])
    values.update({key:round(value*127/100) for key,value in options['volumes'].items()})
    if options['music_j1_only'] and index > 0:
        values['music_volume'] = 0
    return patch_config(template,values)


def config_targets(prefix, directory, allowed):
    """Cover portable savepaths and Windows' Roaming AppData, never scan assets."""
    paths = []
    if directory is not None:
        directory = safe_path(directory,allowed)
        # Existing portable config in the launch directory or beside a root exe.
        paths.append(safe_path(child(directory,'sm64config.txt'),allowed))
        for folder in sorted(directory.iterdir()):
            if folder.is_dir() and not folder.is_symlink():
                path = child(folder,'sm64config.txt')
                if path.is_file():
                    paths.append(safe_path(path,allowed))
    users = safe_path(child(child(prefix,'drive_c'),'users'),allowed)
    actual = [p for p in users.iterdir() if p.is_dir()
              and p.name.casefold() not in ('public','default','default user','all users')] if users.is_dir() else []
    if not actual:
        raise ValueError(tr('Préfixe SM64CoopDX sans utilisateur Wine. Lancez d’abord le jeu une fois en solo.'))
    for user in actual:
        user_paths = []
        for parts in (('AppData','Roaming','sm64coopdx','sm64config.txt'),
                      ('AppData','Roaming','sm64ex-coop','sm64config.txt'),
                      ('Application Data','sm64coopdx','sm64config.txt'),
                      ('Application Data','sm64ex-coop','sm64config.txt')):
            path = user
            for part in parts:
                path = child(path,part)
                safe_path(path,allowed)
            user_paths.append(safe_path(path,allowed))
        # Match the game's choice: don't create a new nonempty canonical folder
        # that would hide existing sm64ex-coop save data on the next launch.
        canonical,legacy = user_paths[:2]
        canonical_nonempty = canonical.parent.is_dir() and any(canonical.parent.iterdir())
        fallback = (legacy if not canonical_nonempty and legacy.parent.is_dir()
                    and any(legacy.parent.iterdir()) else canonical)
        paths.extend([fallback,*[path for path in user_paths if path.is_file()]])
    return paths


def apply_config(directory, prefix, payload, private_binds=PRIVATE_BINDS):
    player = Path(payload['player']).resolve()
    prefix = prefix.resolve()
    after = configured_template(payload['template'],payload['settings'],payload['index'],
                                payload['width'],payload['height']).encode('utf-8')
    allowed = tuple(p.resolve() for p in (prefix,player,*private_binds))
    prefixes = [prefix]
    for kind in ('materialized-prefixes','compatdata','merged-prefixes'):
        root = player/'umu-private'/kind
        if root.is_dir():
            for folder in root.iterdir():
                for candidate in (folder,folder/'pfx'):
                    if (candidate/'drive_c/users').is_dir():
                        prefixes.append(safe_path(candidate,(player,)))
    paths = []
    for candidate in dict.fromkeys(prefixes):
        paths.extend(config_targets(candidate,directory if candidate==prefix else None,allowed))
    # Validate all redirects/read originals before changing any private file.
    edits = [(path,path.read_bytes() if path.exists() else b'') for path in dict.fromkeys(paths)]
    for path,before in edits:
        if before == after:
            continue
        backup = safe_path(player/'sm64coopdx-before'/(hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'.txt'),(player,))
        if before and not backup.exists():
            write_bytes(backup,before)
        write_bytes(path,after)
        print(tr('SM64CoopDX J{p0} : configuration appliquée · {p1}',p0=payload['index']+1,p1=path),flush=True)


def install_hook(base, rom, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import profile_path, read_profile, atomic_write
    if not profile_path(base,rom).exists():
        return
    profile = read_profile(base,rom)
    if profile.get('adapter') != 'sm64coopdx':
        return
    template = base/'templates/sm64coopdx-common.txt'
    if not template.is_file():
        raise ValueError(tr('Configuration commune SM64CoopDX absente : réinstallez Windows Party.'))
    index = int(player.name.removeprefix('j'))-1
    width,height = (int(os.environ.get('PARTYDECK_PLAYER_'+key,'0')) for key in ('WIDTH','HEIGHT'))
    common = template.read_bytes().decode('utf-8-sig')
    options = validate(profile['sm64coopdx'])
    configured_template(common,options,index,width,height)
    payload = player/'sm64coopdx-launch.json'
    atomic_write(payload,json.dumps(dict(player=str(player),settings=options,template=common,
                                         index=index,width=width,height=height),ensure_ascii=False))
    binary = shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary = Path(binary).resolve()
    replacement = player/'batocera-wine-sm64coopdx'
    hook = [sys.executable,str(base/'partydeck_sm64coopdx.py'),str(payload)]
    atomic_write(replacement,instrument_native(binary.read_text(),hook,prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)


if __name__ == '__main__':
    try:
        payload = json.loads(Path(sys.argv[1]).read_text())
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER') != payload['player']:
            raise ValueError(tr('Le profil SM64CoopDX doit être appliqué dans la session Wine privée du joueur.'))
        apply_config(Path(sys.argv[2]),Path(sys.argv[3]),payload)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / SM64CoopDX : {error}',file=sys.stderr)
        raise SystemExit(1)
