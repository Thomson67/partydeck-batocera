"""Private Goldberg/gbe_fork identities for Left 4 Dead 2 (AppID 550).

No emulator, Steam binary or user-supplied configuration is distributed.
Identity, language, controller and viewport settings are applied privately.
"""
from partydeck_i18n import tr
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import uuid

from partydeck_borderlands2 import child, decode, patch_ini, write_bytes, PRIVATE_BINDS

STEAM64_BASE = 76561197960265728  # Public, individual, desktop instance.
ACCOUNT_MAX = (1 << 32)-1
LANGUAGES = dict(zip(('keep','french','english','german','italian','spanish','portuguese',
                     'dutch','polish','czech','russian','japanese'),
                    ('Conserver','Français','Anglais','Allemand','Italien','Espagnol','Portugais',
                     'Néerlandais','Polonais','Tchèque','Russe','Japonais')))
WINE_LOCALES = dict(zip(tuple(LANGUAGES)[1:],('fr_FR.UTF-8','en_US.UTF-8','de_DE.UTF-8',
    'it_IT.UTF-8','es_ES.UTF-8','pt_PT.UTF-8','nl_NL.UTF-8','pl_PL.UTF-8',
    'cs_CZ.UTF-8','ru_RU.UTF-8','ja_JP.UTF-8')))
BEGIN = '// Windows Party begin'
END = '// Windows Party end'
CAMPAIGN_MODES = {'coop': 'Campagne', 'realism': 'Réalisme', 'versus': 'Versus'}
SESSION_MODES = {
    'coop':'Campagne', 'mutation':'Mutation', 'realism':'Réalisme',
    'versus':'Versus', 'mutation12':'Versus Réalisme', 'survival':'Survie',
    'mutation15':'Survie versus', 'scavenge':'Collecte',
}
DIFFICULTIES = {'easy':'Facile', 'normal':'Normal', 'hard':'Avancé', 'impossible':'Expert'}
CAMPAIGNS = {'menu':'Choisir dans le jeu', 'c1m1_hotel':'Dead Center',
    'c2m1_highway':'Dark Carnival','c3m1_plankcountry':'Swamp Fever',
    'c4m1_milltown_a':'Hard Rain','c5m1_waterfront':'The Parish',
    'c6m1_riverbank':'The Passing','c7m1_docks':'The Sacrifice',
    'c8m1_apartment':'No Mercy','c9m1_alleys':'Crash Course',
    'c10m1_caves':'Death Toll','c11m1_greenhouse':'Dead Air',
    'c12m1_hilltop':'Blood Harvest','c13m1_alpinecreek':'Cold Stream',
    'c14m1_junkyard':'The Last Stand'}
MUTATIONS = {
    'mutation2':'Headshot!', 'mutation3':'Bleed Out', 'mutation4':'Hard Eight',
    'mutation5':'Four Swordsmen', 'mutation7':'Chainsaw Massacre', 'mutation8':'Iron Man',
    'mutation9':'Last Gnome On Earth', 'mutation11':'Healthpackalypse!',
    'mutation13':'Follow the Liter', 'mutation14':'Gib Fest', 'mutation16':'Hunting Party',
    'mutation18':'Bleed Out Versus', 'mutation19':'Taaannnkk!', 'mutation20':'Healing Gnome',
    'community1':'Special Delivery', 'community2':'Flu Season', 'community3':'Riding My Survivor',
    'community4':'Nightmare', 'community5':"Death's Door", 'community6':'Confogl',
}
ARENAS = {
    'c1m3_mall':('c1m1_hotel','Armurerie'),
    'c1m4_atrium':('c1m1_hotel','Atrium'),
    'c2m1_highway':('c2m1_highway','Motel'),
    'c2m5_concert':('c2m1_highway','Concert'),
    'c3m1_plankcountry':('c3m1_plankcountry','Village'),
    'c4m1_milltown_a':('c4m1_milltown_a','Bourg'),
    'c4m2_sugarmill_a':('c4m1_milltown_a','Sucrerie'),
    'c5m2_park':('c5m1_waterfront','Parc'),
    'c6m1_riverbank':('c6m1_riverbank','Rive'),
    'c6m2_bedlam':('c6m1_riverbank','Souterrains'),
    'c6m3_port':('c6m1_riverbank','Port'),
    'c7m1_docks':('c7m1_docks','Briqueterie'),
    'c7m2_barge':('c7m1_docks','Barge'),
    'c8m1_apartment':('c8m1_apartment','Appartements'),
    'c8m5_rooftop':('c8m1_apartment','Toit'),
    'c9m1_alleys':('c9m1_alleys','Ruelles'),
    'c9m2_lots':('c9m1_alleys','Dépôt de camions'),
    'c10m3_ranchhouse':('c10m1_caves','Église'),
    'c11m4_terminal':('c11m1_greenhouse','Terminal'),
    'c12m5_cornfield':('c12m1_hilltop','Ferme'),
    'c14m1_junkyard':('c14m1_junkyard','Village'),
    'c14m2_lighthouse':('c14m1_junkyard','Phare'),
}
SCAVENGE_MAPS = tuple(key for key in ARENAS if key not in
                      ('c1m3_mall','c2m5_concert','c9m2_lots'))
SURVIVAL_MAPS = (
    'c1m3_mall','c1m4_atrium','c2m1_highway','c2m5_concert','c3m1_plankcountry',
    'c4m2_sugarmill_a','c7m2_barge','c8m5_rooftop','c9m2_lots','c11m4_terminal',
    'c12m5_cornfield','c14m1_junkyard','c14m2_lighthouse',
)
ARENA_MODES = {
    'survival':SURVIVAL_MAPS, 'mutation15':SURVIVAL_MAPS, 'community4':SURVIVAL_MAPS,
    'scavenge':SCAVENGE_MAPS, 'mutation13':SCAVENGE_MAPS,
}
CAMPAIGN_MAPS = tuple(key for key in CAMPAIGNS if key!='menu')
SOURCE_MODES = (SESSION_MODES.keys() - {'mutation'}) | MUTATIONS.keys()


def mode_maps(mode):
    return ARENA_MODES.get(mode,CAMPAIGN_MAPS)


def matches(rom):
    return bool(re.search(r'(?<![a-z0-9])(?:left[\s_-]*4[\s_-]*dead[\s_-]*(?:2|ii)|l4d2)(?![a-z0-9])',rom.stem.casefold()))


def defaults():
    return dict(names=[tr('Joueur{p0}',p0=i) for i in range(1,5)],language='keep',gamepad=True,
                automatic=True,host_player=1,port=27015,campaign='menu',campaign_mode='coop')


def launch_options(data):
    if not isinstance(data,dict):
        raise ValueError(tr('Réglages Left 4 Dead 2 invalides.'))
    campaign=data.get('campaign','menu')
    mode=data.get('campaign_mode','coop')
    if not isinstance(mode,str) or mode not in SOURCE_MODES:
        raise ValueError(tr('Mode de campagne Left 4 Dead 2 invalide.'))
    if campaign!='menu' and campaign not in mode_maps(mode):
        raise ValueError(tr('Campagne Left 4 Dead 2 invalide.'))
    difficulty=data.get('difficulty')
    if difficulty is not None and (not isinstance(difficulty,str) or difficulty not in DIFFICULTIES):
        raise ValueError(tr('Difficulté Left 4 Dead 2 invalide.'))
    return dict(campaign=campaign,campaign_mode=mode,difficulty=difficulty)


def validate(options):
    names = options.get('names') if isinstance(options,dict) else None
    if (not isinstance(names,list) or len(names)!=4
            or any(not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>63
                   or any(ord(c)<32 or ord(c)==127 or c in ';#' for c in name) for name in names)
            or len(set(names))!=4):
        raise ValueError(tr('Left 4 Dead 2 : quatre noms différents, non vides, de 63 octets UTF-8 maximum, sans caractères de contrôle ni ; #.'))
    language=options.get('language','keep')
    gamepad=options.get('gamepad',True)
    if not isinstance(language,str) or language not in LANGUAGES or type(gamepad) is not bool:
        raise ValueError(tr('Réglages Left 4 Dead 2 invalides.'))
    from partydeck_autoconnect import options as network_options
    startup=launch_options(options)
    if startup['campaign_mode'] not in CAMPAIGN_MODES:
        raise ValueError(tr('Mode de campagne Left 4 Dead 2 invalide.'))
    return dict(names=list(names),language=language,gamepad=gamepad,
                campaign=startup['campaign'],campaign_mode=startup['campaign_mode'],
                **network_options(options,'l4d2'))


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
                # Goldberg reads steam_settings before falling back to the
                # working/executable directory. A leftover root AppID must not
                # override a valid local AppID. Do not rewrite any of them.
                for parent in dict.fromkeys((settings,directory,folder)):
                    appid=child(parent,'steam_appid.txt')
                    if not appid.is_file():
                        continue
                    text=safe_path(appid,allowed).read_text(encoding='utf-8-sig')
                    match=re.match(r'\s*(\d+)',text)
                    number=int(match[1]) if match else 0
                    if not number:
                        continue
                    if number!=550:
                        raise ValueError(tr('AppID Goldberg {p0} incompatible avec Left 4 Dead 2 : {p1}',p0=number,p1=appid))
                    print(tr('Goldberg : AppID 550 confirmé dans {p0}.',p0=appid),flush=True)
                    break
                files.append(target)
        if depth<3:
            for name in sorted(roots):
                candidate=child(folder,name)
                if candidate.is_dir():
                    queue.append((candidate,depth+1))
    return list(dict.fromkeys(files))


def dimensions(payload):
    width,height=payload.get('width'),payload.get('height')
    if any(type(n) is not int or not 1 <= n <= 16384 for n in (width,height)):
        raise ValueError(tr('Dimensions de la fenêtre Left 4 Dead 2 indisponibles ou invalides.'))
    return width,height


def patch_video(text, width, height):
    """Patch root display keys in a Source video KeyValues object."""
    values={'setting.defaultres':str(width),'setting.defaultresheight':str(height),
            'setting.fullscreen':'0','setting.nowindowborder':'1'}
    if not text.strip():
        text='"VideoConfig"\n{\n}\n'
    # Accept Source KeyValues variants while changing only root-level settings.
    # Keep comments, nesting, conditionals and Windows EOF markers verbatim.
    parsed=text.rstrip('\x00\x1a\r\n\t ')
    token=re.compile(r'\s+|//[^\r\n]*|/\*[\s\S]*?\*/|"(?:[^"\\]|\\.)*"|[{}]|[^\s{}"]+')
    tokens=[];end=0
    def invalid():
        raise ValueError(tr('Fichier video.txt Left 4 Dead 2 invalide ; fichier conservé.'))
    for m in token.finditer(parsed):
        if m.start()!=end:invalid()
        end=m.end()
        if m[0].isspace() or m[0].startswith(('//','/*')):continue
        tokens.append(m)
    def plain(m):return m[0].strip('"').casefold()
    if (end!=len(parsed) or len(tokens)<3
            or plain(tokens[0]) not in ('videoconfig','video.cfg','video.txt')
            or tokens[1][0]!='{'):invalid()
    edits=[];seen=set();pos=2
    def scope(depth):
        nonlocal pos
        if depth>32:invalid()
        while pos<len(tokens) and tokens[pos][0]!='}':
            key=tokens[pos];pos+=1
            if key[0]=='{' or pos>=len(tokens):invalid()
            val=tokens[pos];pos+=1
            if val[0]=='{':
                scope(depth+1)
            elif val[0]=='}':invalid()
            elif depth==0 and plain(key) in values:
                name=plain(key)
                edits.append((val.start(),val.end(),'"'+values[name]+'"'));seen.add(name)
            if pos<len(tokens) and re.fullmatch(r'\[!?\$[A-Za-z0-9_]+\]',tokens[pos][0]):pos+=1
        if pos>=len(tokens):invalid()
        closing=tokens[pos];pos+=1
        return closing
    closing=scope(0)
    if pos!=len(tokens):invalid()
    nl='\r\n' if '\r\n' in text else '\n'
    missing=''.join(f'\t"{k}"\t"{v}"{nl}' for k,v in values.items() if k not in seen)
    if missing:edits.append((closing.start(),closing.start(),nl+missing))
    for start,end,replacement in sorted(edits,reverse=True):text=text[:start]+replacement+text[end:]
    return text


def managed_cfg(text, commands):
    nl='\r\n' if '\r\n' in text else '\n'
    block=re.compile(r'(?m)^'+re.escape(BEGIN)+r'\r?\n.*?^'+re.escape(END)+r'[^\r\n]*(?:\r?\n|$)',re.S)
    text=block.sub('',text)
    if BEGIN in text or END in text:
        raise ValueError(tr('Bloc Windows Party Left 4 Dead 2 incomplet ; fichier conservé.'))
    return text.rstrip('\r\n')+nl+BEGIN+nl+nl.join(commands)+nl+END+nl


def language_batch(text, language):
    """Remove the retired registry preamble, preserving the batch body."""
    begin='@rem Windows Party language begin'
    end='@rem Windows Party language end'
    if begin in text or end in text:
        expected=re.compile(r'\A'+re.escape(begin)+r'\r?\n'
            +re.escape('@reg add "HKCU\\Software\\Valve\\Steam" /v Language /t REG_SZ /d ')
            +r'(?:'+ '|'.join(re.escape(x) for x in LANGUAGES if x!='keep')+r')'
            +re.escape(' /f >nul')+r'\r?\n'+re.escape(end)+r'\r?\n')
        text,count=expected.subn('',text,count=1)
        if count!=1 or begin in text or end in text:
            raise ValueError(tr('Bloc de langue Left 4 Dead 2 incomplet ; fichier conservé.'))
    return text


def game_edits(directory, player, payload, allowed):
    width,height=dimensions(payload)
    options=validate(payload['settings'])
    folder=directory if directory.name.casefold()=='left4dead2' else child(directory,'left4dead2')
    folder=safe_path(folder,allowed)
    if not folder.is_dir():
        raise ValueError(tr('Dossier left4dead2 introuvable dans la vue privée du jeu.'))
    cfg=safe_path(child(folder,'cfg'),allowed)
    edits=[]
    for name in ('video.txt','config.cfg','autoexec.cfg'):
        path=safe_path(child(cfg,name),allowed)
        before=path.read_bytes() if path.exists() else b''
        if name=='video.txt':
            try:
                text,encoding=decode(before)
                after=patch_video(text,width,height).encode(encoding)
            except ValueError:
                # An unsupported video format is not a failure to launch Wine.
                # Never replace the user's video settings with a guessed file.
                after=before
                print(tr('Left 4 Dead 2 : format vidéo non reconnu : {p0} ; fichier conservé, lancement poursuivi. Sans bordure non réappliqué ; résolution demandée : {p1}×{p2}.',p0=path,p1=width,p2=height),flush=True)
        else:
            text,encoding=decode(before)
            commands=['joystick "'+str(int(options['gamepad']))+'"']
            if options['gamepad']:commands.append('+jlook')
            if name=='autoexec.cfg':commands.append(f'mat_setvideomode {width} {height} 1')
            after=managed_cfg(text,commands).encode(encoding)
        backup=safe_path(player/'l4d2-settings-before'/(hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'-'+name),(player,))
        edits.append((path,before,after,backup))
    batch=safe_path(child(directory,'start.bat'),allowed)
    if batch.is_file():
        before=batch.read_bytes()
        text,encoding=decode(before)
        cleaned=language_batch(text,options['language'])
        after=before if cleaned==text else cleaned.encode(encoding)
        backup=safe_path(player/'l4d2-settings-before'/(hashlib.sha256(os.fsencode(batch)).hexdigest()[:16]+'-start.bat'),(player,))
        edits.append((batch,before,after,backup))
    return edits


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
    general=dict(account_name=options['names'][index],account_steamid=identity['steamid'])
    if options['language']!='keep':general['language']=options['language']
    changes={'user::general':general}
    edits=[]
    # Prepare all edits before modifying files. Ports and save paths stay intact.
    for path,before,text,encoding,_ in sources:
        after=patch_ini(text,changes).encode(encoding)
        backup=safe_path(player/'l4d2-goldberg-before'/(hashlib.sha256(os.fsencode(path)).hexdigest()[:16]+'.ini'),(player,))
        edits.append((path,before,after,backup))
        if options['language']!='keep':
            whitelist=safe_path(child(path.parent,'supported_languages.txt'),allowed)
            if whitelist.is_file():
                original=whitelist.read_bytes()
                languages,codec=decode(original)
                if options['language'] not in [line.strip().casefold() for line in languages.splitlines()]:
                    nl='\r\n' if '\r\n' in languages else '\n'
                    updated=languages.rstrip('\r\n')+nl+options['language']+nl
                    backup=safe_path(player/'l4d2-settings-before'/(hashlib.sha256(os.fsencode(whitelist)).hexdigest()[:16]+'-supported_languages.txt'),(player,))
                    edits.append((whitelist,original,updated.encode(codec),backup))
    edits.extend(game_edits(directory,player,payload,allowed))
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


def result_path(payload):
    path=Path(payload['result'])
    if path.parent.resolve()!=Path(payload['player']).resolve() or not re.fullmatch(r'l4d2-result-[0-9a-f]{32}\.json',path.name):
        raise ValueError(tr('État Goldberg hors du dossier privé du joueur.'))
    return path


def apply_launch(directory, prefix, payload):
    # Pending is a failure unless this exact hook invocation completes. Native
    # batocera-wine can otherwise swallow a failed hook while waiting for Wine.
    result=result_path(payload) if payload.get('result') else None
    if result is not None:
        write_bytes(result,b'{"version":1,"code":1}\n')
    apply_config(directory,prefix,payload)
    if result is not None:
        write_bytes(result,b'{"version":1,"code":0}\n')


def finish_launch(path, native_status):
    try:
        try:
            data=json.loads(path.read_text())
        except (OSError,ValueError):
            raise RuntimeError(tr('Résultat du profil Goldberg absent ou invalide : {p0}',p0=path)) from None
        if not isinstance(data,dict) or data.get('version')!=1 or type(data.get('code')) is not int or data['code'] not in (0,1):
            raise RuntimeError(tr('Résultat du profil Goldberg absent ou invalide : {p0}',p0=path))
        if data['code']:
            print(tr('Profil Goldberg non appliqué ; échec conservé malgré le code natif {p0}.',p0=native_status),flush=True)
            return data['code']
        return native_status
    finally:
        path.unlink(missing_ok=True)


def language_arguments(command, language):
    """Replace Source language tokens without reserializing other arguments."""
    if language=='keep':return command
    if language not in WINE_LOCALES:raise ValueError(tr('Réglages Left 4 Dead 2 invalides.'))
    tokens=list(re.finditer(r'"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s]+',command))
    edits=[];skip=-1
    for i,token in enumerate(tokens):
        if i<=skip or token[0].strip('"\'').casefold()!='-language':continue
        end=token.end()
        if i+1<len(tokens) and not tokens[i+1][0].strip('"\'').startswith(('-','+')):
            skip=i+1;end=tokens[skip].end()
        edits.append((token.start(),end,'-language '+language if not edits else ''))
    if not edits:return command.rstrip()+' -language '+language
    for start,end,value in reversed(edits):command=command[:start]+value+command[end:]
    return command


def instrument_locale(source, language):
    """Use Batocera's native LANG -> WINE_LANG -> LC_ALL launch path.

    autorun.cmd has already been parsed by the time the game config hook runs.
    Set its derived value in the private launcher, before native Wine setup.
    """
    if language=='keep':return source
    locale=WINE_LOCALES[language]
    parts=re.split(r'(?m)^(?=\w+\(\) \{)',source)
    pattern=re.compile(r'(?m)^([ \t]*)WINE_LANG=\$\(getWine_var [^\r\n]+\)[ \t]*$')
    cmd_pattern=re.compile(r'(?m)^([ \t]*)WINE_CMD=\$\(getWine_var [^\r\n]+\)[ \t]*$')
    helper=shlex.join([sys.executable,str(Path(__file__).resolve()),'_language_args',language])
    for name in ('play_wine','play_pc','play_squashfs'):
        indices=[i for i,body in enumerate(parts) if body.startswith(name+'() {')]
        if (len(indices)!=1 or len(pattern.findall(parts[indices[0]]))!=1
                or len(cmd_pattern.findall(parts[indices[0]]))!=1):
            raise RuntimeError(tr('Lanceur batocera-wine non reconnu ({p0}) : langue Wine non appliquée.',p0=name))
        i=indices[0]
        parts[i]=pattern.sub(lambda m:m[1]+'WINE_LANG='+locale,parts[i])
        parts[i]=cmd_pattern.sub(lambda m:m[0]+'\n'+m[1]+'WINE_CMD=$('+helper+' "${WINE_CMD}") || return 1',parts[i])
    return ''.join(parts)


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
    result=player/f'l4d2-result-{uuid.uuid4().hex}.json'
    width=int(os.environ.get('PARTYDECK_PLAYER_WIDTH','0'))
    height=int(os.environ.get('PARTYDECK_PLAYER_HEIGHT','0'))
    dimensions(dict(width=width,height=height))
    atomic_write(payload,json.dumps(dict(player=str(player),index=index,settings=settings,result=str(result),width=width,height=height),ensure_ascii=False))
    binary=shutil.which('batocera-wine')
    if not binary:
        raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve()
    replacement=player/'batocera-wine-l4d2'
    hook=[sys.executable,str(base/'partydeck_l4d2.py'),str(payload)]
    source=instrument_locale(binary.read_text(),settings['language'])
    atomic_write(replacement,instrument_native(source,hook,prefix_argument=True),0o755)
    if settings['language']!='keep':
        print(tr('Left 4 Dead 2 : langue Wine native {p0}.',p0=WINE_LOCALES[settings['language']]),flush=True)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    atomic_write(result,'{"version":1,"code":1}\n')
    try:
        subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    except Exception:
        result.unlink(missing_ok=True)
        raise
    return result


if __name__=='__main__':
    try:
        if sys.argv[1]=='_language_args':
            print(language_arguments(sys.argv[3],sys.argv[2]))
            raise SystemExit(0)
        payload=json.loads(Path(sys.argv[1]).read_text())
        if os.environ.get('PARTYDECK_PRIVATE_PLAYER')!=payload['player']:
            raise ValueError(tr('Le profil Left 4 Dead 2 doit être appliqué dans la session Wine privée du joueur.'))
        apply_launch(Path(sys.argv[2]),Path(sys.argv[3]),payload)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Windows Party / Left 4 Dead 2 : {error}',file=sys.stderr)
        raise SystemExit(1)
