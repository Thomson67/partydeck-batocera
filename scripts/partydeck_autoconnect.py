"""Per-session launch coordination; edits only the current player's game view."""
from pathlib import Path
import hashlib
import ipaddress
import json
import os
import re
import shlex
import socket
import struct
import subprocess
import sys
import time

from partydeck_i18n import tr
from partydeck_borderlands2 import child, decode, safe_path, write_bytes, PRIVATE_BINDS

ADAPTERS = {'sm64coopdx': 'sm64coopdx', 'l4d2-goldberg': 'l4d2', 'borderlands2': 'borderlands2'}
EXECUTABLES = {'sm64coopdx': ('sm64coopdx.exe',), 'l4d2': ('left4dead2.exe',),
               'borderlands2': ('borderlands2.exe',)}
SDK_SHA256 = 'e1862ddb282cf845369c9ca1ca70ac180d6104cce25d8a133557fc74e157b4c7'
SDK_URL = 'https://github.com/bl-sdk/willow2-mod-manager/releases/download/v3.8/willow2-sdk.zip'
SOURCE_POLL = 'partydeck_l4d2_poll.cfg'
SOURCE_JOIN = 'partydeck_l4d2_join.cfg'
SOURCE_STOP = 'alias partydeck_l4d2_tick ""\n'
SOURCE_HOST = 'partydeck_l4d2_host.cfg'
SOURCE_LOG = 'partydeck_l4d2_console.log'


def context(player):
    token = os.environ.get('PARTYDECK_SESSION_TOKEN', '')
    count = os.environ.get('PARTYDECK_SESSION_PLAYERS', '1')
    if not re.fullmatch('[0-9a-f]{32}', token) or count not in ('2','3','4'):
        return None
    return dict(token=token, count=int(count), player=str(player))


def options(data, kind):
    out = dict(automatic=data.get('automatic', True), host_player=data.get('host_player', 1),
               port=data.get('port', 7777 if kind!='l4d2' else 27015))
    if (type(out['automatic']) is not bool or type(out['host_player']) is not int
            or out['host_player'] not in range(1,5) or type(out['port']) is not int
            or not 1024<=out['port']<=65535):
        raise ValueError(tr('Réglages de connexion automatique invalides.'))
    return out


def prepare_sdk(base, profile):
    """Download a pinned, checksum-verified SDK once, outside the Wine sandbox."""
    if not profile or profile.get('adapter')!='borderlands2' or not options(profile['borderlands2'],'borderlands2')['automatic']:
        return
    import tempfile
    import urllib.request
    root = base/'dependencies'; root.mkdir(exist_ok=True)
    archive = root/'willow2-sdk-v3.8.zip'
    if archive.is_file() and hashlib.sha256(archive.read_bytes()).hexdigest()==SDK_SHA256:
        return
    print(tr('Borderlands 2 : préparation du SDK privé pour le LAN automatique.'),flush=True)
    fd,name = tempfile.mkstemp(dir=root,prefix='.willow2-')
    try:
        with os.fdopen(fd,'wb') as stream, urllib.request.urlopen(SDK_URL,timeout=45) as response:
            total=0
            while chunk:=response.read(1024*1024):
                total+=len(chunk)
                if total>32*1024*1024:raise ValueError(tr('Archive SDK Borderlands 2 invalide.'))
                stream.write(chunk)
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=SDK_SHA256:
            raise ValueError(tr('Archive SDK Borderlands 2 invalide.'))
        os.replace(name,archive)
    finally:Path(name).unlink(missing_ok=True)


def game_arguments(plan):
    host = plan['index']+1==plan['host_player']
    port = str(plan['port'])
    if plan['kind']=='sm64coopdx':
        return ['--server',port] if host else ['--client','127.0.0.1',port]
    if plan['kind']=='l4d2':
        result=['-port',port if host else str(0),'+con_logfile',SOURCE_LOG,
                '+sv_lan','1','+sv_allow_lobby_connect_only','0']
        if host:
            result+=['+lservercfgfile',SOURCE_HOST]
            campaign=plan.get('campaign','menu')
            if campaign!='menu':
                mode=plan.get('campaign_mode','coop')
                if mode in ('coop','realism') and plan.get('difficulty'):
                    result+=['+z_difficulty',plan['difficulty']]
                result+=['+map',campaign,mode]
        else:result+=['+exec',SOURCE_POLL]
        return result
    return [f'-port={port}'] if host and port!='7777' else []


def command_arguments(command, plan):
    """Preserve the original command; recognize only a real target executable."""
    if not plan['automatic']:return command,False
    names='|'.join(re.escape(x) for x in EXECUTABLES[plan['kind']])
    pattern=re.compile(r'(?i)(?:^|[\\/\s\"])(?:'+names+r')(?=[\"\s]|$)')
    if not pattern.search(command):return command,False
    if any(char in command for char in '&|<>\r\n'):return command,False
    flags=game_arguments(plan)
    if not flags:
        return command,True
    # Do not let two conflicting session controllers silently compete.
    if re.search(r'(?i)(?:^|\s)(?:--server|--client|--coopnet|\+connect|\+map|-port)(?:[=\s]|$)',command):
        raise ValueError(tr('Le lanceur du jeu contient déjà des options réseau ; choisissez le mode manuel ou retirez ces options.'))
    if '+lservercfgfile' in flags and re.search(r'(?i)(?:^|\s)"?\+lservercfgfile(?:["\s=]|$)',command):
        host_cfg=flags.index('+lservercfgfile')
        del flags[host_cfg:host_cfg+2]
    return command.rstrip()+' '+' '.join(flags),True


def marker(plan):
    return Path(plan['player']).parent/f'j{plan["host_player"]}'/'autoconnect-host.json'


def bl2_lan_address():
    # Route lookup selects a source address without sending traffic.
    commands=(['route','get','1.1.1.1'],['addr','show','scope','global'])
    for command in commands:
        try:
            rows=json.loads(subprocess.check_output(['ip','-j','-4',*command],text=True,timeout=3,
                                                    stderr=subprocess.DEVNULL))
            candidates={ipaddress.IPv4Address(value) for row in rows for value in
                        ([row.get('prefsrc') or row.get('src')] if 'get' in command else
                         [item['local'] for item in row.get('addr_info',[])]) if value}
        except (OSError,ValueError,subprocess.SubprocessError):
            continue
        candidates={address for address in candidates if not address.is_loopback and
                    not address.is_unspecified and not address.is_multicast}
        if len(candidates)==1:return str(candidates.pop())
    raise ValueError(tr('Borderlands 2 : adresse IPv4 LAN introuvable. Utilisez le LAN manuel.'))


def bl2_owns_port(player, address, port, proc=Path('/proc')):
    """Find the host player's actual game socket in the shared network."""
    try:
        rows=(proc/'net/udp').read_text().splitlines()[1:]
    except OSError:
        return False
    local={f'00000000:{port:04X}',f'{socket.inet_aton(address)[::-1].hex().upper()}:{port:04X}'}
    sockets=set()
    for row in rows:
        fields=row.split()
        if len(fields)>9 and fields[1] in local and fields[3]=='07':
            sockets.add(f'socket:[{fields[9]}]')
    if not sockets:return False
    identity=b'PARTYDECK_PRIVATE_PLAYER='+os.fsencode(player)
    for process in proc.glob('[0-9]*/environ'):
        try:
            if identity not in process.read_bytes().split(b'\0'):continue
            for fd in (process.parent/'fd').iterdir():
                try:
                    if os.readlink(fd) in sockets:return True
                except OSError:
                    continue
        except OSError:
            continue
    return False


class BL2Host:
    def __init__(self, player, port, token, address):
        self.player=player
        self.address=address
        self.port=port
        self.token=token
        self.path=player/'autoconnect-host.json'
        self.next_check=0
        self.ready=False
        self.path.unlink(missing_ok=True)

    def poll(self):
        now=time.monotonic()
        if now<self.next_check:return
        self.next_check=now+1
        ready=bl2_owns_port(self.player,self.address,self.port)
        if ready==self.ready:return
        if ready:
            data=dict(token=self.token,ready=True,address=self.address,port=self.port)
            write_bytes(self.path,json.dumps(data).encode())
            print(tr('Borderlands 2 : {p0} écoute sur {p1}:{p2}.',
                     p0=self.player.name.upper(),p1=self.address,p2=self.port),flush=True)
        else:
            self.path.unlink(missing_ok=True)
        self.ready=ready

    def close(self):
        self.path.unlink(missing_ok=True)


def udp_bound(port):
    # /proc/net belongs to the shared network namespace even in a private PID ns.
    for table in ('/proc/net/udp','/proc/net/udp6'):
        try:
            for row in Path(table).read_text().splitlines()[1:]:
                address=row.split()[1].split(':')
                if int(address[1],16)==port and int(address[0],16) in (0,0x0100007f):return True
        except (OSError,ValueError,IndexError):pass
    return False


def source_ready(port, timeout=.4):
    """A2S_INFO, including the modern challenge round-trip; verify AppID 550."""
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout);sock.connect(('127.0.0.1',port))
            request=b'\xff\xff\xff\xffTSource Engine Query\0'
            sock.send(request);data=sock.recv(4096)
            if data[:5]==b'\xff\xff\xff\xffA' and len(data)==9:
                sock.send(request+data[5:]);data=sock.recv(4096)
            if data[:5]!=b'\xff\xff\xff\xffI':return False
            offset=6;fields=[]
            for _ in range(4):
                end=data.index(b'\0',offset);fields.append(data[offset:end]);offset=end+1
            return (struct.unpack_from('<H',data,offset)[0]==550 and bool(fields[1])
                    and not fields[1].lower().startswith((b'background',b'menu',b'startup')))
    except (OSError,ValueError,struct.error):return False


def wait_host(plan, timeout=120):
    if plan['index']+1==plan['host_player']:return True
    deadline=time.monotonic()+timeout
    print(tr('J{p0} : attente de la partie de J{p1}.',p0=plan['index']+1,p1=plan['host_player']),flush=True)
    while time.monotonic()<deadline:
        try:started=json.loads(marker(plan).read_text()).get('token')==plan['token']
        except (OSError,ValueError):started=False
        if started and (source_ready(plan['port']) if plan['kind']=='l4d2' else udp_bound(plan['port'])):
            return True
        time.sleep(.5)
    print(tr('Hôte non prêt : connexion automatique abandonnée ; utilisez les menus du jeu.'),flush=True)
    return False


def source_cfg(directory, allowed):
    game=directory if directory.name.casefold()=='left4dead2' else child(directory,'left4dead2')
    return safe_path(child(game,'cfg'),allowed)


def configure_source_host(cfg, allowed):
    commands=[]
    if child(cfg,'listenserver.cfg').is_file():
        commands.append('exec listenserver.cfg')
    commands.extend(('sv_lan 1','sv_allow_lobby_connect_only 0',
                     'echo PARTYDECK_L4D2_HOST_CFG','status'))
    write_bytes(safe_path(cfg/SOURCE_HOST,allowed),('\n'.join(commands)+'\n').encode())


def arm_source_join(cfg, allowed, plan):
    poll=safe_path(cfg/SOURCE_POLL,allowed)
    join=safe_path(cfg/SOURCE_JOIN,allowed)
    # Keep the command queue bounded even if the engine ignores wait.
    tick='partydeck_l4d2_tick'
    ten='partydeck_l4d2_ten'
    hundred='partydeck_l4d2_hundred'
    script=[
        'echo PARTYDECK_L4D2_CLIENT_CFG',
        f'alias {tick} "exec {SOURCE_JOIN}; wait 60"',
        f'alias {ten} "'+'; '.join([tick]*10)+'"',
        f'alias {hundred} "'+'; '.join([ten]*10)+'"',
        *([hundred]*20),
    ]
    write_bytes(join,b'// Waiting for the LAN host.\n')
    write_bytes(poll,('\n'.join(script)+'\n').encode())
    payload=Path(plan['player'])/'autoconnect-launch.json'
    subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'_source_join',str(payload),str(join)],
                     stdin=subprocess.DEVNULL)


def source_join(plan, join):
    ready=wait_host(plan,timeout=300)
    command=SOURCE_STOP
    if ready:
        command+=f'echo PARTYDECK_L4D2_CONNECT\nconnect 127.0.0.1:{plan["port"]}\n'
    write_bytes(join,command.encode())
    if ready:
        print(tr('Left 4 Dead 2 J{p0} : partie locale prête, connexion demandée.',
                 p0=plan['index']+1),flush=True)


def restore_batches(directory, player, allowed):
    manifest=player/'autoconnect-batches.json'
    if not manifest.exists():return
    for item in json.loads(manifest.read_text()):
        path=safe_path(directory/item['path'],allowed)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==item['after']:
            write_bytes(path,bytes.fromhex(item['before']))
    write_bytes(manifest,b'[]')


def prepare_game(directory, prefix, plan):
    player=Path(plan['player']).resolve();directory=directory.resolve()
    allowed=tuple(p.resolve() for p in (prefix,player,*PRIVATE_BINDS))
    safe_path(directory,allowed)
    (player/'autoconnect-sdk-ready').unlink(missing_ok=True)
    restore_batches(directory,player,allowed)
    bl2=plan['kind']=='borderlands2'
    host=plan['index']+1==plan['host_player']
    if bl2:
        auto_lan=plan['automatic'] and (player.parent/'bl2-auto-lan.mode').is_file()
        use_sdk=plan['automatic'] and (not host or auto_lan)
        if configure_bl2(directory,player,dict(plan,automatic=use_sdk,auto_lan=auto_lan),allowed):
            write_bytes(player/'autoconnect-sdk-ready',b'1')
        if not host or plan['port']==7777:
            return
    if not plan['automatic']:
        return
    direct=plan.get('direct',False)
    edits=[]
    # Entry batches commonly wrap the actual EXE. Change only recognized game
    # invocations, never helper processes or the source archive/autorun settings.
    if not direct:
        batches=[]
        for token in re.findall(r'"[^"\r\n]*"|[^\s]+',plan.get('original_command','')):
            value=token.strip('"').replace('\\','/')
            if Path(value).suffix.casefold() in ('.bat','.cmd'):
                parts=Path(value).parts
                path=prefix/'drive_c' if parts and parts[0].casefold()=='c:' else directory
                if parts and parts[0].casefold()=='c:':parts=parts[1:]
                for part in parts:path=child(path,part)
                batches.append(path)
        for path in dict.fromkeys(batches):
            if not path.is_file():continue
            safe_path(path,allowed)
            before=path.read_bytes();text,codec=decode(before);lines=[];changed=False
            for line in text.splitlines(keepends=True):
                if re.match(r'\s*(?:@?(?:rem|echo|if|set)\b|::)',line,re.I):lines.append(line);continue
                ending='\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
                modified,found=command_arguments(line.rstrip('\r\n'),plan)
                changed|=found;lines.append(modified+ending)
            if changed:edits.append((path,before,''.join(lines).encode(codec)))
    if not direct and not edits:
        print(tr('Lanceur non reconnu : connexion automatique non appliquée ; utilisez les menus du jeu.'),flush=True)
        return
    if not bl2 and host:
        if udp_bound(plan['port']):raise ValueError(tr('Le port de la partie est déjà occupé. Changez le port dans le profil.'))
        if plan['kind']=='l4d2':
            configure_source_host(source_cfg(directory,allowed),allowed)
        write_bytes(marker(plan),json.dumps(dict(token=plan['token'])).encode())
    elif plan['kind']=='l4d2':
        arm_source_join(source_cfg(directory,allowed),allowed,plan)
    elif not bl2 and not wait_host(plan):
        # A batch can fall back cleanly; direct EXE arguments already include
        # connect, which the game can cancel back to its main menu.
        if not direct:return
    saved=[]
    for path,before,after in edits:
        saved.append(dict(path=str(path.relative_to(directory)),before=before.hex(),after=hashlib.sha256(after).hexdigest()))
        write_bytes(path,after)
    write_bytes(player/'autoconnect-batches.json',json.dumps(saved).encode())


def configure_bl2(directory,player,plan,allowed):
    """Install the pinned SDK in the private overlay, preserving other loaders."""
    import zipfile
    root=directory
    if directory.name.casefold()=='win32':root=directory.parent.parent
    binary=safe_path(child(child(root,'Binaries'),'Win32'),allowed)
    cfg=safe_path(child(root,'sdk_mods')/'partydeck_session.json',allowed)
    if cfg.exists():write_bytes(cfg,b'{"automatic":false}')
    if not plan['automatic']:
        return False
    archive=Path(plan['base'])/'dependencies/willow2-sdk-v3.8.zip'
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest()!=SDK_SHA256:
        raise ValueError(tr('Archive SDK Borderlands 2 invalide.'))
    with zipfile.ZipFile(archive) as sdk:
        loader=safe_path(child(binary,'ddraw.dll'),allowed)
        expected=sdk.read('Binaries/Win32/ddraw.dll')
        if loader.exists() and loader.read_bytes()!=expected:
            print(tr('Borderlands 2 : ddraw.dll existant conservé ; SDK automatique non installé. Mode LAN manuel.'),flush=True)
            return False
        entries=[]
        for name in sdk.namelist():
            if name.endswith('/') or '/.stubs/' in name:continue
            relative=Path(name)
            if relative.is_absolute() or '..' in relative.parts:raise ValueError(tr('Archive SDK Borderlands 2 invalide.'))
            if not (name.startswith('Binaries/Win32/') or name.startswith('sdk_mods/')):continue
            target=root
            for part in relative.parts:target=child(target,part)
            target=safe_path(target,allowed);data=sdk.read(name)
            if target.exists() and target.read_bytes()!=data:
                print(tr('Borderlands 2 : SDK existant différent, fichiers conservés. Mode LAN manuel.'),flush=True)
                return False
            entries.append((target,data))
        for target,data in entries:
            if not target.exists():write_bytes(target,data)
    mod=safe_path(child(root,'sdk_mods')/'partydeck_session'/'__init__.py',allowed)
    write_bytes(mod,(Path(plan['base'])/'partydeck_bl2_session.py').read_bytes())
    data=dict(plan)
    data['host_marker']='Z:'+str(marker(plan)).replace('/','\\')
    write_bytes(cfg,json.dumps(data).encode())
    print(tr('Borderlands 2 : connexion automatique prête. Sélectionnez Réseau local dans le jeu.'),flush=True)
    return True


def install_hook(base, rom, player):
    from partydeck_profiles import read_profile,profile_path,atomic_write
    from partydeck_anchor import instrument_native
    if not profile_path(base,rom).exists():return
    profile=read_profile(base,rom);kind=ADAPTERS.get(profile.get('adapter'))
    session=context(player)
    if kind is None:
        # Switching back to the default profile also restores our private edits.
        previous=player/'autoconnect-launch.json'
        if not previous.exists():return
        prior=json.loads(previous.read_text());kind=prior.get('kind')
        if kind not in EXECUTABLES:return
        settings=dict(automatic=False)
        session=dict(token='0'*32,count=1,player=str(player))
    else:settings=profile[kind]
    if session is None:
        if not (player/'autoconnect-launch.json').exists():return
        session=dict(token='0'*32,count=1,player=str(player))
    plan=dict(session,**options(settings,kind),kind=kind,base=str(base),
        index=int(player.name.removeprefix('j'))-1,campaign=settings.get('campaign','menu'))
    if kind=='l4d2':
        from partydeck_l4d2 import launch_options
        startup=os.environ.get('PARTYDECK_L4D2_LAUNCH')
        plan.update(launch_options(json.loads(startup) if startup and plan['automatic'] else settings))
    if session['count']==1:plan['automatic']=False
    if plan['automatic'] and plan['host_player']>plan['count']:raise ValueError(tr('Le joueur hôte choisi ne participe pas à cette session.'))
    payload=player/'autoconnect-launch.json';atomic_write(payload,json.dumps(plan))
    binary=__import__('shutil').which('batocera-wine')
    if not binary:raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve()
    source=binary.read_text();parts=re.split(r'(?m)^(?=\w+\(\) \{)',source)
    pattern=re.compile(r'(?m)^([ \t]*)WINE_CMD=\$\(getWine_var [^\r\n]+\)[ \t]*$')
    helper=shlex.join([sys.executable,str(base/'partydeck_autoconnect.py'),'_args',str(payload)])
    for name in ('play_wine','play_pc','play_squashfs'):
        positions=[i for i,part in enumerate(parts) if part.startswith(name+'() {')]
        if len(positions)!=1 or len(pattern.findall(parts[positions[0]]))!=1:
            raise RuntimeError(tr('Lanceur natif non reconnu : connexion automatique non appliquée.'))
        i=positions[0];parts[i]=pattern.sub(lambda m:m[0]+'\n'+m[1]+'WINE_CMD=$('+helper+' "${WINE_CMD}") || return 1',parts[i])
    hook=[sys.executable,str(base/'partydeck_autoconnect.py'),'_prepare',str(payload)]
    source=''.join(parts)
    if kind=='borderlands2':
        # The loader override is enabled only after the private install succeeds,
        # in the same shell as Wine. A conflicting DLL keeps its prior behavior.
        function=('partydeck_session_prepare() {\n '
            +shlex.join(hook)+' "$@" || return $?\n '
            +'if [[ -f '+shlex.quote(str(player/'autoconnect-sdk-ready'))+' ]]; then\n '
            +' case ";${WINEDLLOVERRIDES:-};" in *";ddraw="*) ;; *) '
            +'export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:+${WINEDLLOVERRIDES};}ddraw=n,b" ;; esac\n '
            +'fi\n}\n')
        lines=source.splitlines(keepends=True)
        source=lines[0]+function+''.join(lines[1:])
        hook=['partydeck_session_prepare']
    replacement=player/'batocera-wine-autoconnect'
    atomic_write(replacement,instrument_native(source,hook,prefix_argument=True),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    if kind=='borderlands2' and plan['automatic']:
        own=os.environ.get('PRESSURE_VESSEL_FILESYSTEMS_RW','')
        os.environ['PRESSURE_VESSEL_FILESYSTEMS_RW']=own+(':' if own else '')+str(player)
        if plan['index']+1!=plan['host_player']:
            shared=os.environ.get('PRESSURE_VESSEL_FILESYSTEMS_RO','')
            os.environ['PRESSURE_VESSEL_FILESYSTEMS_RO']=shared+(':' if shared else '')+str(marker(plan).parent)


if __name__=='__main__':
    try:
        action,path,*args=sys.argv[1:];path=Path(path);plan=json.loads(path.read_text())
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER')!=plan['player']:
            raise ValueError(tr('Contexte de connexion automatique invalide.'))
        if action=='_args':
            result,direct=command_arguments(args[0],plan)
            plan.update(direct=direct,original_command=args[0]);write_bytes(path,json.dumps(plan).encode());print(result)
        elif action=='_prepare':prepare_game(Path(args[0]),Path(args[1]),plan)
        elif action=='_source_join':source_join(plan,Path(args[0]))
        else:raise ValueError('unknown action')
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
