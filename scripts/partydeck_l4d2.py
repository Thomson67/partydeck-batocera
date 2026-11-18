"""Private Goldberg/gbe_fork identities for Left 4 Dead 2 (AppID 550).

No emulator, Steam binary or user-supplied configuration is distributed.
Only existing local account_steamid/account_name values are patched.
"""
from partydeck_i18n import tr
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from partydeck_borderlands2 import child, decode, patch_ini, write_bytes, PRIVATE_BINDS

STEAM64_BASE = 76561197960265728  # Public, individual, desktop instance.
ACCOUNT_MAX = (1 << 32)-1


def matches(rom):
    return bool(re.search(r'(?<![a-z0-9])(?:left[\s_-]*4[\s_-]*dead[\s_-]*(?:2|ii)|l4d2)(?![a-z0-9])',rom.stem.casefold()))


def defaults():
    return dict(names=[tr('Joueur{p0}',p0=i) for i in range(1,5)])


def validate(options):
    names = options.get('names') if isinstance(options,dict) else None
    if (not isinstance(names,list) or len(names)!=4
            or any(not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>63
                   or any(ord(c)<32 or ord(c)==127 or c in ';#' for c in name) for name in names)
            or len(set(names))!=4):
        raise ValueError(tr('Left 4 Dead 2 : quatre noms différents, non vides, de 63 octets UTF-8 maximum, sans caractères de contrôle ni ; #.'))
    return dict(names=list(names))


def valid_id(value):
    return isinstance(value,str) and value.isascii() and value.isdigit() and STEAM64_BASE < int(value) <= STEAM64_BASE+ACCOUNT_MAX


def player_id(seed, index):
    if not valid_id(seed) or type(index) is not int or index not in range(4):
        raise ValueError(tr('Identifiant ou numéro de joueur Goldberg invalide pour Left 4 Dead 2.'))
    account = (int(seed)-STEAM64_BASE+index-1)%ACCOUNT_MAX+1
    return str(STEAM64_BASE+account)


def safe_path(path, allowed):
    resolved = path.resolve()
    if not any(resolved.is_relative_to(root) for root in allowed):
        raise ValueError(tr('Configuration Goldberg hors de la vue privée : {p0}',p0=path))
    return resolved


def value(text, section, key):
    active, result = None, None
    for line in text.splitlines():
        header = re.match(r'^\s*\[([^\]]+)\]',line)
        if header:
            active=header[1].casefold()
        match = re.match(r'^\s*([^;#=\s]+)\s*=\s*(.*?)\s*$',line)
        if active==section.casefold() and match and match[1].casefold()==key.casefold():
            result=match[2]
    return result


def config_files(directory, allowed):
    """Look beside the known Windows DLL locations, never recurse into assets."""
    directory = safe_path(directory,allowed)
    root_appid=child(directory,'steam_appid.txt')
    if root_appid.is_file() and safe_path(root_appid,allowed).read_text(encoding='utf-8-sig').strip()!='550':
        raise ValueError(tr('Configuration Goldberg destinée à un autre jeu : {p0}',p0=root_appid))
    queue,visited,files = [(directory,0)],set(),[]
    roots={'bin','x64','x86','win64','win32','left4dead2'}
    while queue:
        folder,depth=queue.pop(0)
        folder=safe_path(folder,allowed)
        if folder in visited or not folder.is_dir():
            continue
        visited.add(folder)
        settings=child(folder,'steam_settings')
        if settings.exists():
            settings=safe_path(settings,allowed)
            target=child(settings,'configs.user.ini')
            if target.is_file():
                target=safe_path(target,allowed)
                # AppID identifies the game; it must never be individualized.
                for appid in (child(settings,'steam_appid.txt'),child(folder,'steam_appid.txt')):
                    if appid.is_file() and safe_path(appid,allowed).read_text(encoding='utf-8-sig').strip()!='550':
                        raise ValueError(tr('Configuration Goldberg destinée à un autre jeu : {p0}',p0=appid))
                files.append(target)
        if depth<3:
            for name in sorted(roots):
                candidate=child(folder,name)
                if candidate.is_dir():
                    queue.append((candidate,depth+1))
    return list(dict.fromkeys(files))


def apply_config(directory, prefix, payload, private_binds=PRIVATE_BINDS):
    player=Path(payload['player']).resolve()
    prefix=prefix.resolve()
    allowed=tuple(p.resolve() for p in (prefix,player,*private_binds))
    options=validate(payload['settings'])
    index=payload['index']
    if type(index) is not int or index not in range(4):
        raise ValueError(tr('Identifiant ou numéro de joueur Goldberg invalide pour Left 4 Dead 2.'))
    targets=config_files(directory,allowed)
    if not targets:
        raise ValueError(tr('Left 4 Dead 2 : steam_settings/configs.user.ini Goldberg introuvable dans la vue privée du jeu.'))
    sources=[]
    for path in targets:
        before=path.read_bytes()
        text,encoding=decode(before)
        seed=value(text,'user::general','account_steamid')
        if not valid_id(seed):
            raise ValueError(tr('Steam ID Goldberg absent ou invalide : {p0}',p0=path))
        sources.append((path,before,text,encoding,seed))
    identity_path=safe_path(player/'l4d2-goldberg-identity.json',(player,))
    if identity_path.exists():
        try:
            identity=json.loads(identity_path.read_text())
        except (ValueError,UnicodeError):
            raise ValueError(tr('Identité Goldberg privée invalide ; fichier conservé : {p0}',p0=identity_path)) from None
        if (not isinstance(identity,dict) or identity.get('version')!=1
                or type(identity.get('index')) is not int or identity['index']!=index
                or not valid_id(identity.get('steamid'))):
            raise ValueError(tr('Identité Goldberg privée invalide ; fichier conservé : {p0}',p0=identity_path))
    else:
        seeds={source[4] for source in sources}
        if len(seeds)!=1:
            raise ValueError(tr('Plusieurs Steam ID Goldberg différents sont présents dans le jeu ; initialisation refusée.'))
        identity=dict(version=1,index=index,steamid=player_id(seeds.pop(),index))
    changes={'user::general':dict(account_name=options['names'][index],account_steamid=identity['steamid'])}
    edits=[]
    # Prepare every encoded edit before changing any config/identity. Other
    # Goldberg files, language, ports and save paths are not rewritten.
    for path,before,text,encoding,_ in sources:
        after=patch_ini(text,changes).encode(encoding)
        backup=safe_path(player/'l4d2-goldberg-before'/(hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'.ini'),(player,))
        edits.append((path,before,after,backup))
    for path,before,after,backup in edits:
        if before!=after and not backup.exists():
            write_bytes(backup,before)
    # Persist the choice first, so an interrupted partial config update cannot
    # apply the player offset a second time on the next launch.
    if not identity_path.exists():
        write_bytes(identity_path,(json.dumps(identity)+'\n').encode())
    for path,before,after,backup in edits:
        if before!=after:
            write_bytes(path,after)
    print(tr('Left 4 Dead 2 J{p0} : identité Goldberg privée {p1} · {p2} configuration(s).',
             p0=index+1,p1=identity['steamid'],p2=len(edits)),flush=True)


def install_hook(base, rom, player):
    from partydeck_anchor import instrument_native
    from partydeck_profiles import profile_path,read_profile,atomic_write
    if not profile_path(base,rom).exists():
        return
    profile=read_profile(base,rom)
    if profile.get('adapter')!='l4d2-goldberg':
        return
    settings=validate(profile['l4d2'])
    index=int(player.name.removeprefix('j'))-1
    if index not in range(4):
        raise ValueError(tr('Identifiant ou numéro de joueur Goldberg invalide pour Left 4 Dead 2.'))
    payload=player/'l4d2-goldberg-launch.json'
    atomic_write(payload,json.dumps(dict(player=str(player),index=index,settings=settings),ensure_ascii=False))
    binary=shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve()
    replacement=player/'batocera-wine-l4d2'
    hook=[sys.executable,str(base/'partydeck_l4d2.py'),str(payload)]
    atomic_write(replacement,instrument_native(binary.read_text(),hook,prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)


if __name__=='__main__':
    try:
        payload=json.loads(Path(sys.argv[1]).read_text())
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER')!=payload['player']:
            raise ValueError(tr('Le profil Left 4 Dead 2 doit être appliqué dans la session Wine privée du joueur.'))
        apply_config(Path(sys.argv[2]),Path(sys.argv[3]),payload)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / Left 4 Dead 2 : {error}',file=sys.stderr)
        raise SystemExit(1)
