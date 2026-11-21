"""Experimental MW 2005 LAN recipe derived from Nucleus handler v10 settings.

No Nucleus code, game binaries, saves or mod binaries are redistributed.
"""
from partydeck_i18n import tr
from pathlib import Path
import ipaddress,json,os,re,shutil,subprocess,sys,time,uuid,hashlib
from partydeck_borderlands2 import child,decode,patch_ini,write_bytes,PRIVATE_BINDS
from partydeck_l4d2 import safe_path


def matches(rom):
    name=rom.stem.casefold()
    return bool(re.search(r'(?:most[ _-]*wanted|nfsmw)',name) and re.search(r'(?<!\d)2005(?!\d)',name))


def defaults():return dict(host='auto',throttle=6,music_j1_only=True,start_delay=0,private_lan=True,controller_enter=True)


def validate(data):
    if not isinstance(data,dict):raise ValueError(tr('Réglages Most Wanted LAN invalides.'))
    out={k:data.get(k,v) for k,v in defaults().items()}
    if not isinstance(out['host'],str):raise ValueError(tr('Adresse LAN Most Wanted invalide.'))
    if out['host']!='auto':
        try:
            ip=ipaddress.IPv4Address(out['host'])
            if ip.is_unspecified or ip.is_loopback or ip.is_multicast or int(ip)==0xffffffff:raise ValueError()
        except ValueError:raise ValueError(tr('Adresse LAN Most Wanted invalide.')) from None
    if (type(out['throttle']) is not int or not 1<=out['throttle']<=1000
            or type(out['private_lan']) is not bool or type(out['controller_enter']) is not bool or type(out['music_j1_only']) is not bool or type(out['start_delay']) is not int
            or out['start_delay'] not in (0,15,30,60)):
        raise ValueError(tr('Réglages Most Wanted LAN invalides.'))
    return out


def host_ip(setting):
    if setting!='auto':return validate(dict(host=setting))['host']
    try:
        data=json.loads(subprocess.check_output(['ip','-j','-4','route','get','1.1.1.1'],text=True,timeout=3))
        if not isinstance(data,list):data=[]
        for row in data:
            if not isinstance(row,dict):continue
            value=row.get('prefsrc') or row.get('src')
            if value:return validate(dict(host=value))['host']
    except (OSError,ValueError,subprocess.SubprocessError):pass
    raise ValueError(tr('IP LAN introuvable ; renseignez l’adresse du PC dans Réseau Most Wanted.'))


def apply_config(directory,prefix,payload,private_binds=PRIVATE_BINDS):
    player=Path(payload['player']).resolve();prefix=prefix.resolve()
    allowed=tuple(p.resolve() for p in (prefix,player,*private_binds))
    directory=safe_path(directory,allowed)
    cfg=safe_path(child(directory,'server.cfg'),allowed)
    dll=safe_path(child(directory,'server.dll'),allowed)
    # The Most Wanted adapter is selected by the profile, not by an optional
    # repack icon. Only require the files used by the LAN adapter itself.
    if not cfg.is_file() or not dll.is_file():raise ValueError(tr('Most Wanted : server.cfg ou server.dll absent.'))
    options=validate(payload['settings']);index=payload['index']
    if type(index) is not int or index not in range(4):raise ValueError(tr('Numéro de joueur Most Wanted invalide.'))
    width,height=payload['width'],payload['height']
    if any(type(v) is not int or not 64<=v<=16384 for v in (width,height)):
        raise ValueError(tr('Dimensions Most Wanted invalides.'))
    host=payload['host'];validate(dict(host=host))
    if host=='auto':raise ValueError(tr('Adresse LAN Most Wanted invalide.'))
    port=9900 if payload.get('private_lan') else 9900+index
    edits=[]
    def prepare(path,changes):
        path=safe_path(path,allowed)
        original=path.read_bytes();text,codec=decode(original)
        after=patch_ini(text,changes).encode(codec)
        backup=safe_path(player/'nfsmw-before'/(hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'.bak'),(player,))
        edits.append((path,original,after,backup))
    # Nucleus uses IniSaveInfo("SERVER", ...); retain that section and its
    # original unsectioned defaults, rather than guessing a flat-file parser.
    prepare(cfg,{'SERVER':dict(PORT=port,LAN_THROTTLE=options['throttle'],TRUST='255.255.255.255',
        ADDR=f'%%bind("{host}:{port}")',TRUST_MATCH=f'%%bind("{host}")')})
    scripts=safe_path(child(directory,'scripts'),allowed)
    extra=safe_path(child(scripts,'NFSMWExtraOptionsSettings.ini'),allowed)
    wide=safe_path(child(scripts,'NFSMostWanted.WidescreenFix.ini'),allowed)
    if extra.is_file():
        misc=dict(AllowMultipleInstances=1,WindowedMode=2,
            EnableMusic=int(not options['music_j1_only'] or index==0))
        prepare(extra,{'Misc':misc})
    if wide.is_file():prepare(wide,{'MAIN':dict(ResX=width,ResY=height)})
    for name in ('NFSMWExtraOptions.asi','NFSMostWanted.WidescreenFix.asi','NFSMWHUDAdapter.asi'):
        if not safe_path(child(scripts,name),allowed).is_file():
            print(tr('Most Wanted : mod absent ({p0}) ; adaptation réseau seule, compatibilité non garantie.',p0=name),flush=True)
    # Match Nucleus's real per-player server.dll copy, rather than leaving
    # the library mapped from the shared read-only game layer. Bytes unchanged.
    dll_data=dll.read_bytes()
    for path,before,after,backup in edits:
        if before!=after and not backup.exists():write_bytes(backup,before)
    write_bytes(dll,dll_data)
    for path,before,after,backup in edits:
        if before!=after:write_bytes(path,after)
    print(tr('Most Wanted J{p0} : {p1}:{p2}, TRUST_MATCH sans port, LAN_THROTTLE={p3}.',p0=index+1,p1=host,p2=port,p3=options['throttle']),flush=True)


def install_hook(base,rom,player):
    from partydeck_profiles import profile_path,read_profile,atomic_write
    from partydeck_anchor import instrument_native
    if not profile_path(base,rom).exists():return
    profile=read_profile(base,rom)
    if profile.get('adapter')!='nfsmw-lan':return
    settings=validate(profile['nfsmw']);index=int(player.name.removeprefix('j'))-1
    if index not in range(4):raise ValueError(tr('Numéro de joueur Most Wanted invalide.'))
    private_ip=os.environ.get('PARTYDECK_PRIVATE_LAN_IP')
    host=host_ip(private_ip or settings['host'])
    if index and settings['start_delay']:
        print(tr('Most Wanted J{p0} : attente de {p1} s pour préparer le salon J1.',p0=index+1,p1=index*settings['start_delay']),flush=True)
        time.sleep(index*settings['start_delay'])
    result=player/f'nfsmw-result-{uuid.uuid4().hex}.json'
    payload=player/'nfsmw-launch.json'
    atomic_write(payload,json.dumps(dict(player=str(player),settings=settings,index=index,
        host=host,private_lan=bool(private_ip),
        width=int(os.environ.get('PARTYDECK_PLAYER_WIDTH','0')),height=int(os.environ.get('PARTYDECK_PLAYER_HEIGHT','0')),result=str(result))))
    binary=shutil.which('batocera-wine')
    if not binary:raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve();replacement=player/'batocera-wine-nfsmw'
    hook=[sys.executable,str(base/'partydeck_nfsmw.py'),str(payload)]
    atomic_write(replacement,instrument_native(binary.read_text(),hook,prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    atomic_write(result,'{"version":1,"code":1}\n')
    try:subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    except Exception:result.unlink(missing_ok=True);raise
    return result


def finish_launch(path,status):
    try:
        try:data=json.loads(path.read_text())
        except (OSError,ValueError):return 1
        if not isinstance(data,dict):return 1
        if data.get('version')!=1 or type(data.get('code')) is not int or data['code'] not in (0,1):return 1
        return 1 if data['code'] else status
    finally:path.unlink(missing_ok=True)


if __name__=='__main__':
    try:
        data=json.loads(Path(sys.argv[1]).read_text());player=Path(data['player']).resolve();result=Path(data['result'])
        if (os.environ.get('PARTYDECK_PRIVATE_PLAYER')!=str(player) or result.parent.resolve()!=player
                or not re.fullmatch(r'nfsmw-result-[0-9a-f]{32}\.json',result.name)):
            raise ValueError(tr('Contexte privé Most Wanted invalide.'))
        write_bytes(result,b'{"version":1,"code":1}\n')
        apply_config(Path(sys.argv[2]),Path(sys.argv[3]),data)
        write_bytes(result,b'{"version":1,"code":0}\n')
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / Most Wanted : {error}',file=sys.stderr);raise SystemExit(1)
