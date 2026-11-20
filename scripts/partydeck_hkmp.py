"""Hollow Knight / HKMP: private viewport, identities and BepInEx bridge.

The user supplies the working Modding API, HKMP and ultrawide installation.
Only our own companion is installed in the existing per-player COW game view.
"""
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


def matches(rom):
    return bool(re.search(r'(?<![a-z0-9])hollow[ _-]*knight(?![a-z0-9])',rom.stem.casefold())) and 'silksong' not in rom.stem.casefold()


def defaults():
    return dict(automatic=True,port=7777,names=['J1','J2','J3','J4'],pvp=False,
                body_damage=False,map_icons=True,display_names=True,skins=True,enemy_health='keep',enemy_ghosts='keep')


def validate(data):
    if not isinstance(data,dict):raise ValueError(tr('Réglages Hollow Knight HKMP invalides.'))
    out={k:data.get(k,v) for k,v in defaults().items()}
    if (any(type(out[k]) is not bool for k in ('automatic','pvp','body_damage','map_icons','display_names','skins'))
            or type(out['port']) is not int or not 1024<=out['port']<=65535):
        raise ValueError(tr('Réglages Hollow Knight HKMP invalides.'))
    if any(out[k] not in ('keep','on','off') for k in ('enemy_health','enemy_ghosts')):
        raise ValueError(tr('Réglages Hollow Knight HKMP invalides.'))
    names=out['names']
    if (not isinstance(names,list) or len(names)!=4 or any(not isinstance(n,str) or not re.fullmatch(r'[A-Za-z0-9]{1,20}',n) for n in names)
            or len(set(n.casefold() for n in names))!=4):
        raise ValueError(tr('HKMP : quatre noms différents de 1 à 20 lettres ASCII ou chiffres.'))
    return out


def check_dimensions(width,height,index):
    if (type(index) is not int or index not in range(4)
            or any(type(v) is not int or not 64<=v<=16384 for v in (width,height))):
        raise ValueError(tr('Dimensions ou joueur Hollow Knight invalides.'))


def instrument_display(source,width,height):
    """Preserve native autorun; also handle start.bat via the in-game bridge."""
    check_dimensions(width,height,0)
    pattern=re.compile(r'(?m)^([ \t]*)WINE_CMD=\$\(getWine_var [^\r\n]+\)[ \t]*$')
    parts=re.split(r'(?m)^(?=\w+\(\) \{)',source)
    for name in ('play_wine','play_pc','play_squashfs'):
        indices=[i for i,body in enumerate(parts) if body.startswith(name+'() {')]
        if len(indices)!=1 or len(pattern.findall(parts[indices[0]]))!=1:
            raise RuntimeError(tr('Lanceur Hollow Knight non reconnu ; adaptation refusée.'))
        i=indices[0]
        # Append only when the native command directly names the game. A batch
        # may ignore arguments: the companion enforces size in that case too.
        extra=('\n'+r'\1'+ 'case "$WINE_CMD" in\n'
               '*[Hh][Oo][Ll][Ll][Oo][Ww]_[Kk][Nn][Ii][Gg][Hh][Tt].[Ee][Xx][Ee]*) '
               f'WINE_CMD="${{WINE_CMD}} -screen-fullscreen 0 -popupwindow -screen-width {width} -screen-height {height}" ;;\n'
               'esac\nexport WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+${WINEDLLOVERRIDES};}winhttp=n,b"')
        parts[i]=pattern.sub(lambda m:m[0]+extra.replace(r'\1',m[1]),parts[i])
    return ''.join(parts)


def apply_config(directory,prefix,payload,private_binds=PRIVATE_BINDS):
    player=Path(payload['player']).resolve();prefix=prefix.resolve()
    allowed=tuple(p.resolve() for p in (prefix,player,*private_binds,*private_windows_paths(player)))
    directory=safe_path(directory,allowed)
    index=payload['index'];width=payload['width'];height=payload['height']
    check_dimensions(width,height,index);options=validate(payload['settings'])
    def path(root,*names):
        for name in names:root=safe_path(child(root,name),allowed)
        return root
    bepin=path(directory,'BepInEx')
    if not path(directory,'hollow_knight.exe').is_file() or not path(bepin,'core','BepInEx.dll').is_file():
        raise ValueError(tr('Hollow Knight : installation BepInEx absente.'))
    if not path(directory,'winhttp.dll').is_file():raise ValueError(tr('Hollow Knight : winhttp.dll absent.'))
    managed=path(directory,'hollow_knight_Data','Managed')
    hkmp=path(managed,'Mods','HKMP','HKMP.dll')
    if not hkmp.is_file():raise ValueError(tr('Hollow Knight : HKMP.dll absent du dossier Mods/HKMP.'))
    addon_edits=[]
    mods=path(managed,'Mods')
    for key,name in (('enemy_health','ESoulLink'),('enemy_ghosts','GhostHunter')):
        mode=options[key]
        if mode=='keep':continue
        active=path(mods,name,name+'.dll')
        inactive=path(mods,name,name+'.dll.windows-party-disabled')
        if active.exists() and inactive.exists():
            raise ValueError(tr('HKMP : copies actives et désactivées ambiguës pour {p0}.',p0=name))
        if mode=='on':
            if not active.is_file() and not inactive.is_file():
                raise ValueError(tr('HKMP : installez et activez {p0} dans Lumafly avant de choisir Activé.',p0=name))
            for dependency in ('HkmpPouch','Satchel'):
                if not path(mods,dependency,dependency+'.dll').is_file():
                    raise ValueError(tr('HKMP : dépendance absente pour {p0} : {p1}.',p0=name,p1=dependency))
            if inactive.is_file():addon_edits.append((inactive,active))
        elif active.is_file():addon_edits.append((active,inactive))
    # Validate all external configuration before changing private launch files.
    users=path(prefix,'drive_c','users')
    targets=[]
    for user in sorted(users.iterdir()) if users.is_dir() else []:
        if not user.is_dir() or user.name.casefold() in ('public','default','default user','all users'):continue
        target=path(user,'AppData','LocalLow','Team Cherry','Hollow Knight','HKMP.GlobalSettings.json')
        if target in [p for p,_ in targets]:continue
        data=json.loads(target.read_text(encoding='utf-8-sig')) if target.is_file() else {}
        if not isinstance(data,dict):raise ValueError(tr('Réglages Hollow Knight HKMP invalides.'))
        if data.get('ServerSettings') is not None and not isinstance(data['ServerSettings'],dict):
            raise ValueError(tr('Réglages Hollow Knight HKMP invalides.'))
        targets.append((target,data))
    if not targets:raise ValueError(tr('Hollow Knight : utilisateur Wine absent ; lancez le jeu en solo une fois.'))
    doorstop=path(directory,'doorstop_config.ini')
    before=doorstop.read_bytes();text,codec=decode(before)
    doorstop_after=patch_ini(text,{'UnityMono':{'dll_search_path_override':r'BepInEx\core'}}).encode(codec)
    identity=path(prefix,'drive_c','windows','windows-party-hkmp-identity.json')
    saved=json.loads(identity.read_text()) if identity.is_file() else {}
    if (not isinstance(saved,dict) or saved.get('player')!=index or not isinstance(saved.get('key'),str)
            or not re.fullmatch(r'[A-Za-z0-9]{56}',saved['key'])):
        saved=dict(player=index,key=''.join(secrets.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(56)))
    companion=Path(payload['plugin'])
    # The payload is created in the private namespace by install_hook.
    if not companion.is_file():raise ValueError(tr('Plugin compagnon Hollow Knight absent.'))
    binary=companion.read_bytes()
    config=('[Session]\nEnabled = true\nPlayer = '+str(index+1)+
            f'\n[Display]\nWidth = {width}\nHeight = {height}\n[Network]\n'
            f'Automatic = {str(options["automatic"]).lower()}\nAddress = 127.0.0.1\nPort = {options["port"]}\nUsername = {options["names"][index]}\n')
    for target,data in targets:
        data.update(AuthKey=saved['key'],Username=options['names'][index],ConnectAddress='127.0.0.1',
                    ConnectPort=options['port'],AutoConnectWhenHosting=True)
        server=data.setdefault('ServerSettings',{})
        if server is None:server=data['ServerSettings']={}
        server.update(IsPvpEnabled=options['pvp'],IsBodyDamageEnabled=options['body_damage'],
                      AlwaysShowMapIcons=options['map_icons'],OnlyBroadcastMapIconWithWaywardCompass=not options['map_icons'],
                      DisplayNames=options['display_names'],AllowSkins=options['skins'])
    for src,dst in addon_edits:
        # Rename only inside the player COW layer; dependencies stay available.
        src.rename(dst)
    write_bytes(identity,(json.dumps(saved)+'\n').encode())
    if doorstop_after!=before:write_bytes(doorstop,doorstop_after)
    write_bytes(path(bepin,'plugins','WindowsParty.HKMP.dll'),binary)
    write_bytes(path(bepin,'config','windows.party.hkmp.cfg'),config.encode())
    for target,data in targets:write_bytes(target,(json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode())
    print(tr('Hollow Knight J{p0} : {p1}×{p2}, pseudo {p3}, connexion automatique {p4}.',
             p0=index+1,p1=width,p2=height,p3=options['names'][index],p4=options['automatic']),flush=True)


def install_hook(base,rom,player):
    from partydeck_profiles import profile_path,read_profile,atomic_write
    from partydeck_anchor import instrument_native
    if not profile_path(base,rom).exists():return
    profile=read_profile(base,rom)
    if profile.get('adapter')!='hollowknight-hkmp':return
    options=validate(profile['hkmp']);index=int(player.name.removeprefix('j'))-1
    width=int(os.environ.get('PARTYDECK_PLAYER_WIDTH','0'));height=int(os.environ.get('PARTYDECK_PLAYER_HEIGHT','0'))
    check_dimensions(width,height,index)
    plugin=base/'plugins'/'WindowsParty.HKMP.dll'
    if not plugin.is_file():raise ValueError(tr('Plugin compagnon Hollow Knight absent.'))
    result=player/f'hkmp-result-{uuid.uuid4().hex}.json';payload=player/'hkmp-launch.json'
    atomic_write(payload,json.dumps(dict(player=str(player),settings=options,index=index,width=width,height=height,
                                         plugin=str(plugin),result=str(result))))
    binary=shutil.which('batocera-wine')
    if not binary:raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve();replacement=player/'batocera-wine-hkmp'
    source=instrument_display(binary.read_text(),width,height)
    hook=[sys.executable,str(base/'partydeck_hkmp.py'),str(payload)]
    atomic_write(replacement,instrument_native(source,hook,prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    atomic_write(result,'{"version":1,"code":1}\n')
    try:subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    except Exception:result.unlink(missing_ok=True);raise
    return result


if __name__=='__main__':
    try:
        data=json.loads(Path(sys.argv[1]).read_text());player=Path(data['player']).resolve();result=Path(data['result'])
        if (os.environ.get('PARTYDECK_PRIVATE_PLAYER')!=str(player) or result.parent.resolve()!=player
                or not re.fullmatch(r'hkmp-result-[0-9a-f]{32}\.json',result.name)):
            raise ValueError(tr('Contexte privé Hollow Knight invalide.'))
        write_bytes(result,b'{"version":1,"code":1}\n')
        apply_config(Path(sys.argv[2]),Path(sys.argv[3]),data)
        write_bytes(result,b'{"version":1,"code":0}\n')
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / Hollow Knight : {error}',file=sys.stderr);raise SystemExit(1)
