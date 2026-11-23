#!/usr/bin/env python3
"""Persistent Windows Party profiles and their optional graphical editor."""
from partydeck_i18n import tr, choice_label
import hashlib
import fcntl
import copy
import html
import json
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen
from urllib.error import URLError

from partydeck_migrate import MEDIA_FIELDS, PARTY_ROMS

ROM_TYPES = {".wine", ".pc", ".wsquashfs"}
MARKER = "# Entrée gérée par PartyDeck Wine"


# Capability opt-in belongs to game profiles, never to the generic namespace
# implementation. Additional adapters can reuse PrivateLAN after validation.
PRIVATE_LAN_PROFILES = {'nfsmw-lan': 'nfsmw'}


def private_lan_enabled(profile,count):
    if not profile or count not in (2,3,4):return False
    section=PRIVATE_LAN_PROFILES.get(profile.get('adapter'))
    if section is None:return False
    return profile.get(section,{}).get('private_lan',True) is True


def profile_path(base, rom):
    digest = hashlib.sha256(os.fsencode(rom)).hexdigest()[:16]
    return base / "profiles" / f"{digest}.json"


def defaults(rom):
    data = dict(version=1, rom=str(rom), players="auto", split="horizontal",
                input="auto", configure_before_launch=False, keyboard_player=True,gpu='auto')
    from partydeck_borderlands2 import matches, defaults as bl2_defaults
    if matches(rom):
        data.update(adapter='borderlands2',borderlands2=bl2_defaults())
    from partydeck_sm64coopdx import matches as matches_sm64, defaults as sm64_defaults
    if matches_sm64(rom):
        data.update(adapter='sm64coopdx',sm64coopdx=sm64_defaults())
    from partydeck_l4d2 import matches as matches_l4d2, defaults as l4d2_defaults
    if matches_l4d2(rom):
        data.update(adapter='l4d2-goldberg',l4d2=l4d2_defaults())
    from partydeck_nfsmw import matches as matches_mw, defaults as mw_defaults
    if matches_mw(rom):
        data.update(adapter='nfsmw-lan',nfsmw=mw_defaults())
    from partydeck_hkmp import matches as matches_hkmp, defaults as hkmp_defaults
    if matches_hkmp(rom):
        data.update(adapter="hollowknight-hkmp",hkmp=hkmp_defaults())
    from partydeck_hkmultiplayer import matches as matches_multi, defaults as multi_defaults
    if matches_multi(rom):
        data.update(adapter="hollowknight-hkmultiplayer",hkmultiplayer=multi_defaults())
    from partydeck_celestenet import ADAPTER as celestenet, matches as matches_celeste, defaults as celeste_defaults
    if matches_celeste(rom):
        data.update(adapter=celestenet, celestenet=celeste_defaults())
    return data


def validate(data, rom):
    if (not isinstance(data, dict) or data.get("version") != 1
            or data.get("rom") != str(rom)
            or data.get("players") not in ("auto", "1", "2", "3", "4")
            or data.get("split") not in ("horizontal", "vertical")
            or data.get("input") not in ("auto", "clavier-j1", "clavier-j2")
            or type(data.get("configure_before_launch")) is not bool):
        raise ValueError(tr('Profil Windows Party invalide pour {p0}', p0=rom))
    if type(data.get("keyboard_player", True)) is not bool:
        raise ValueError(tr("Option clavier comme joueur invalide."))
    if data.get('gpu','auto') not in ('auto','system','nvidia'):
        raise ValueError(tr('Choix du GPU invalide.'))
    if data.get("adapter", "standard") not in ("standard", "soh-anchor", "borderlands2", "sm64coopdx", "l4d2-goldberg", "nfsmw-lan", "hollowknight-hkmp", "hollowknight-hkmultiplayer", "celestenet"):
        raise ValueError(tr("Adaptateur Windows Party inconnu."))
    if data.get("adapter") == "soh-anchor":
        from partydeck_anchor import validate as validate_anchor
        validate_anchor(data.get("anchor"))
    if data.get('adapter') == 'borderlands2':
        from partydeck_borderlands2 import validate as validate_bl2
        data['borderlands2'] = validate_bl2(data.get('borderlands2'))
    if data.get('adapter') == 'sm64coopdx':
        from partydeck_sm64coopdx import validate as validate_sm64
        data['sm64coopdx'] = validate_sm64(data.get('sm64coopdx'))
    if data.get('adapter') == 'l4d2-goldberg':
        from partydeck_l4d2 import validate as validate_l4d2
        data['l4d2'] = validate_l4d2(data.get('l4d2'))
    if data.get('adapter') == 'nfsmw-lan':
        from partydeck_nfsmw import validate as validate_mw
        data['nfsmw']=validate_mw(data.get('nfsmw'))
    if data.get('adapter') == 'hollowknight-hkmp':
        from partydeck_hkmp import validate as validate_hkmp
        data['hkmp']=validate_hkmp(data.get('hkmp'))
    if data.get('adapter') == 'hollowknight-hkmultiplayer':
        from partydeck_hkmultiplayer import validate as validate_multi
        data['hkmultiplayer']=validate_multi(data.get('hkmultiplayer'))
    if data.get('adapter') == 'celestenet':
        from partydeck_celestenet import validate as validate_celeste
        data['celestenet'] = validate_celeste(data.get('celestenet'))
    return data


def read_profile(base, rom):
    path = profile_path(base, rom)
    if path.is_symlink():
        raise ValueError(tr('Le profil est un lien symbolique : {p0}', p0=path))
    return validate(json.loads(path.read_text()), rom)


def atomic_write(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(tr('Le fichier est un lien symbolique : {p0}', p0=path))
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".partydeck-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def save_profile(base, rom, data):
    validate(data, rom)
    atomic_write(profile_path(base, rom), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prepare_profile(base, rom, count, split, input_mode):
    path = profile_path(base, rom)
    data = read_profile(base, rom) if path.exists() or path.is_symlink() else defaults(rom)
    data.update(players=count, split=split, input=input_mode)
    save_profile(base, rom, data)


def remove_profile(base, rom, roms=None):
    """Remove only our generated launcher and its settings; never ROM/save data."""
    roms = PARTY_ROMS if roms is None else roms
    with (base/'session.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(tr('Attendez la fin de la session ou de l’installation avant de retirer ce jeu.')) from None
        path = profile_path(base,rom)
        if path.exists() or path.is_symlink():
            read_profile(base,rom)
        digest = hashlib.sha256(os.fsencode(rom)).hexdigest()[:10]
        entry = roms/party_entry_name(rom)
        if entry.is_symlink():
            raise ValueError(tr('Le lanceur est un lien utilisateur ; retrait refusé.'))
        if entry.exists():
            lines = entry.read_text().splitlines()
            command = shlex.split(lines[2]) if len(lines) == 3 else []
            expected = ['exec',str(base/'windows-party'),'profil',str(rom)]
            legacy = len(command)==7 and command[:4] == ['exec',str(base/'windows-party'),'party',str(rom)]
            if len(lines)!=3 or lines[1]!=MARKER or (command!=expected and not legacy):
                raise ValueError(tr('Le lanceur a été personnalisé ; retrait automatique refusé.'))
        previous = entry.read_text() if entry.exists() else None
        entry.unlink(missing_ok=True)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            if previous is not None:
                atomic_write(entry,previous,0o755)
            raise


# Metadata is shared by reference; local play history and user flags stay local.
SCRAPE_FIELDS = MEDIA_FIELDS | {'name','desc','rating','releasedate','developer',
    'publisher','genre','genres','family','players','lang','region','arcadesystemname'}


def absolute_path(value, folder):
    return Path(os.path.abspath(folder/Path(value).expanduser()))


def source_scrape(rom, cache):
    """Match exact paths first, then a unique symlink alias; never guess titles."""
    rom=Path(os.path.abspath(rom))
    windows=Path('/userdata/roms/windows')
    for folder in rom.parents:
        path=folder/'gamelist.xml'
        if path not in cache:
            if path.is_file():
                root=ET.parse(path).getroot()
                if root.tag!='gameList':raise ValueError(str(path))
                cache[path]=[(absolute_path(game.findtext('path'),folder),game)
                    for game in root.findall('game') if game.findtext('path')]
            else:cache[path]=[]
        candidates=cache[path]
        exact=[game for target,game in candidates if target==rom]
        matches=exact or [game for target,game in candidates if target.resolve()==rom.resolve()]
        if len(matches)==1:return folder,matches[0]
        if len(matches)>1:return None
        if folder==windows:break
    return None


def sync_scrapes(pairs, roms):
    """Update only generated entries, atomically, including live ES when available."""
    pairs=list(pairs)
    if not pairs:return 0
    roms.mkdir(parents=True,exist_ok=True)
    path=roms/'gamelist.xml'
    if path.is_symlink():raise ValueError(str(path))
    with (roms/'.partydeck-metadata.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        before=path.read_bytes() if path.exists() else None
        root=ET.fromstring(before) if before is not None else ET.Element('gameList')
        if root.tag!='gameList':raise ValueError(str(path))
        cache={};changed=[]
        for original,entry in pairs:
            if entry.parent.absolute()!=roms.absolute() or entry.is_symlink():continue
            found=source_scrape(original,cache)
            if found is None:continue
            folder,source=found
            matches=[g for g in root.findall('game')
                     if g.findtext('path') and absolute_path(g.findtext('path'),roms)==entry.absolute()]
            if len(matches)>1:continue
            game=matches[0] if matches else ET.Element('game')
            previous=ET.tostring(game)
            if not matches:
                ET.SubElement(game,'path').text='./'+entry.name
                root.append(game)
            # Keep Party flags, counts, last played, per-entry emulator settings,
            # and any unknown/custom metadata. Never copy the Windows ROM path.
            for field in SCRAPE_FIELDS:
                value=source.find(field)
                if value is None or not value.text or not value.text.strip():continue
                value=copy.deepcopy(value)
                if field in MEDIA_FIELDS:
                    text=value.text.strip()
                    if not (text.startswith(':') or '://' in text):
                        value.text=str(absolute_path(text,folder))
                for old in list(game.findall(field)):game.remove(old)
                game.append(value)
            # Ignore child ordering when checking for an actual metadata change.
            def contents(node):
                children=copy.deepcopy(list(node))
                for child in children:
                    for part in child.iter():part.tail=None
                return sorted(ET.tostring(child) for child in children)
            if contents(ET.fromstring(previous))!=contents(game):changed.append(game)
        if not changed:return 0
        backup=roms/'gamelist.xml.partydeck-before'
        if before is not None and not backup.exists():
            if backup.is_symlink():raise ValueError(str(backup))
            atomic_write(backup,before.decode('utf-8'))
        partial=ET.Element('gameList')
        for game in changed:
            node=copy.deepcopy(game)
            # ES merges known fields. Omit volatile local state so its current
            # in-memory counts/favorites win over an older on-disk snapshot.
            for field in ('playcount','lastplayed','gametime','favorite','hidden',
                          'kidgame','completed','emulator','core','ratio'):
                for old in list(node.findall(field)):node.remove(old)
            partial.append(node)
        # ES's native import updates its in-memory metadata and saves it, avoiding
        # stale metadata being written back at exit. No reload during gameplay.
        if roms.absolute()==PARTY_ROMS:
            request=Request('http://127.0.0.1:1234/addgames/windows-party',
                data=ET.tostring(partial,encoding='utf-8'),
                headers={'Content-Type':'application/xml'},method='POST')
            try:
                with urlopen(request,timeout=2) as response:
                    live=response.status in (200,201)
                if live:return len(changed)
            except (OSError,URLError):pass
        ET.indent(root,space='  ')
        atomic_write(path,ET.tostring(root,encoding='unicode')+'\n',0o644)
        return len(changed)


def inherit_scrapes(pairs, roms):
    """Missing/bad source metadata must never block adding or launching a game."""
    try:
        count=sync_scrapes(pairs,roms)
        if count:print(tr('Scraps Windows repris pour {p0} jeu(x), sans copier les médias.',p0=count),flush=True)
        return count
    except (OSError,ValueError,ET.ParseError) as error:
        print(tr('Reprise des scraps différée : {p0}',p0=error),file=sys.stderr)
        return 0


def sync_library_scrapes(base, roms=PARTY_ROMS):
    pairs=[]
    for entry in sorted(roms.glob('*.sh')):
        if entry.is_symlink():continue
        lines=entry.read_text().splitlines()
        if len(lines)!=3 or lines[1]!=MARKER:continue
        try:command=shlex.split(lines[2])
        except ValueError:continue
        if len(command)==4 and command[:3]==['exec',str(base/'windows-party'),'profil']:
            pairs.append((Path(command[3]),entry))
    return inherit_scrapes(pairs,roms)


ES_RUNNER_MARKER = 'Options ES gérées par Windows Party'


def install_runner_editor(config_dir):
    """Add native Wine settings, scoped to the sh/windows-party system."""
    path=config_dir/'es_features_windows-party.cfg'
    if path.is_symlink() or (path.exists() and ES_RUNNER_MARKER not in path.read_text()):
        raise ValueError(tr('Configuration ES Windows Party personnalisée ; fichier conservé : {p0}',p0=path))
    root=ET.Element('features');root.append(ET.Comment(' '+ES_RUNNER_MARKER+' '))
    emulator=ET.SubElement(root,'emulator',name='sh')
    systems=ET.SubElement(emulator,'systems')
    system=ET.SubElement(systems,'system',name='windows-party')
    ET.SubElement(system,'feature',name=tr('RUNNER WINE'),value='wine-runner',preset='runners',
        description=tr('Runner propre à Windows Party. Auto : utiliser le runner du jeu Windows d’origine.'))
    feature=ET.SubElement(system,'feature',name=tr('ACTIVER HIDRAW'),value='enable_hidraw',
        description=tr('Accès HID brut de la manette attribuée au joueur. Auto : reprendre le réglage du jeu Windows d’origine.'))
    ET.SubElement(feature,'choice',name=tr('Désactivé'),value='0')
    ET.SubElement(feature,'choice',name=tr('Activé'),value='1')
    feature=ET.SubElement(system,'feature',name='MangoHud',value='mangohud',
        description=tr('Afficher MangoHud dans chaque instance. Auto : conserver le réglage Windows/toolbox.'))
    ET.SubElement(feature,'choice',name=tr('Désactivé'),value='0')
    ET.SubElement(feature,'choice',name=tr('Activé'),value='1')
    feature=ET.SubElement(system,'feature',name=tr('Profil MangoHud'),value='mangohud_profile',
        description=tr('Standard par défaut lorsque MangoHud est activé dans Windows Party.'))
    for value,label in (('default','Standard'),('minimal','Minimal'),('detailed','Détaillé')):
        ET.SubElement(feature,'choice',name=tr(label),value=value)
    ET.indent(root,space='  ')
    atomic_write(path,ET.tostring(root,encoding='unicode')+'\n',0o644)
    return path


def party_entry_name(rom):
    digest=hashlib.sha256(os.fsencode(rom)).hexdigest()[:10]
    return f'{rom.stem[:90]} [{digest}].sh'


def selected_party_runner(rom):
    binary=shutil.which('batocera-settings-get')
    if binary is None:return None
    # Match FileData::getConfigurationName(), including its filename cleanup.
    name=party_entry_name(rom).replace('=','').replace('#','')
    for key in (f'windows-party["{name}"].wine-runner','windows-party.wine-runner'):
        result=subprocess.run([binary,key],capture_output=True,text=True,check=False)
        if result.returncode!=0 or not isinstance(result.stdout,str):continue
        value=result.stdout.strip()
        if not value or value=='auto':continue
        if len(value)>512 or any(c in value for c in '\r\n\0'):
            raise ValueError(tr('Runner Windows Party invalide.'))
        return value
    return None


def selected_party_hidraw(rom):
    return selected_party_switch(rom,'enable_hidraw')


def selected_party_switch(rom,key):
    if key not in ('enable_hidraw','mangohud'):raise ValueError('Unsupported Windows Party switch')
    binary=shutil.which('batocera-settings-get')
    if binary is None:return None
    name=party_entry_name(rom).replace('=','').replace('#','')
    for setting in (f'windows-party["{name}"].{key}',f'windows-party.{key}'):
        result=subprocess.run([binary,setting],capture_output=True,text=True,check=False)
        if result.returncode!=0 or not isinstance(result.stdout,str):continue
        value=result.stdout.strip()
        if not value or value=='auto':continue
        if value not in ('0','1'):
            raise ValueError(tr('Réglage Windows Party invalide : {p0}',p0=key))
        return value
    return None


def instrument_runner(source, runner, hidraw=None):
    pattern=re.compile(r'(?m)^get_setting\(\) \{[ \t]*$')
    if len(pattern.findall(source))!=1:
        raise RuntimeError(tr('Lanceur Wine non reconnu ; sélection du runner Windows Party refusée.'))
    override='\n'
    if runner is not None:
        override+='    if [[ "${1:-}" == wine-runner || "${1:-}" == core ]]; then\n'
        override+="        printf '%s\\n' "+shlex.quote(runner)+'; return 0\n    fi\n'
    if hidraw is not None:
        if hidraw not in ('0','1'):raise ValueError(tr('Réglage HIDRAW Windows Party invalide.'))
        override+='    if [[ "${1:-}" == enable_hidraw ]]; then\n'
        override+="        printf '%s\\n' "+shlex.quote(hidraw)+'; return 0\n    fi\n'
    return pattern.sub(lambda m:m[0]+override,source)


def install_party_runner_hook(rom, player):
    runner=selected_party_runner(rom)
    hidraw=selected_party_hidraw(rom)
    if runner is None and hidraw is None:return
    binary=shutil.which('batocera-wine')
    if binary is None:raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve()
    replacement=player/'batocera-wine-party-runner'
    atomic_write(replacement,instrument_runner(binary.read_text(),runner,hidraw),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    if runner is not None:print(tr('Windows Party : runner dédié {p0}.',p0=runner),flush=True)
    if hidraw is not None:print(tr('Windows Party : HIDRAW={p0}.',p0=hidraw),flush=True)


def yad(arguments):
    binary = shutil.which("yad")
    if binary is None:
        raise RuntimeError(tr("Yad est requis pour l'éditeur graphique. Les profils JSON restent modifiables dans le dossier profiles."))
    return subprocess.run([binary, "--title=Windows Party", "--center", "--on-top",
                           *arguments], text=True, stdout=subprocess.PIPE)


def edit_profile(base, rom):
    if os.environ.get("PARTYDECK_UI") == "legacy":
        return edit_profile_legacy(base, rom)
    from partydeck_couch import configure as couch_configure
    return couch_configure(base, rom, single=True)


def edit_profile_legacy(base, rom):
    if shutil.which("batocera-mouse"):
        subprocess.run(["batocera-mouse", "show"], check=False)
    path = profile_path(base, rom)
    data = read_profile(base, rom) if path.exists() or path.is_symlink() else defaults(rom)
    def choices(key, values):
        return "!".join(choice_label(key,v) for v in [data[key], *(v for v in values if v != data[key])])
    result = yad(["--form", "--width=620", "--separator=\x1f",
                  "--text=" + html.escape(rom.name),
                  tr("--field=Joueurs:CB"), choices("players", ["auto", "1", "2", "3", "4"]),
                  tr("--field=Disposition:CB"), choices("split", ["horizontal", "vertical"]),
                  tr("--field=Entrées:CB"), choices("input", ["auto", "clavier-j1", "clavier-j2"]),
                  tr("--field=Afficher ces réglages avant chaque lancement:CHK"),
                  str(data["configure_before_launch"]).upper(),
                  tr("--button=Annuler:1"), "--button=SoH / Anchor:2", tr("--button=Enregistrer:0")])
    if result.returncode in {1, 252}:
        return False
    if result.returncode not in {0, 2}:
        raise RuntimeError(tr("Impossible d'ouvrir l'éditeur Yad (code {p0}).", p0=result.returncode))
    fields = result.stdout.rstrip("\n").split("\x1f")
    if len(fields) == 5 and not fields[-1]:
        fields.pop()
    if len(fields) != 4 or fields[3].upper() not in {"TRUE", "FALSE"}:
        raise ValueError(tr("Réponse de l'éditeur Windows Party invalide."))
    for index,(key,raw) in enumerate((('players',['auto','1','2','3','4']),('split',['horizontal','vertical']),
                                      ('input',['auto','clavier-j1','clavier-j2']))):
        fields[index] = {choice_label(key,v):v for v in raw}.get(fields[index],fields[index])
    data.update(players=fields[0], split=fields[1], input=fields[2],
                configure_before_launch=fields[3].upper() == "TRUE")
    if result.returncode == 2 and not edit_anchor(data):
        return False
    save_profile(base, rom, data)
    return True


def edit_anchor(data):
    from partydeck_anchor import defaults as anchor_defaults, validate as validate_anchor
    settings = dict(data.get("anchor") or anchor_defaults())
    labels = {
        "pvp": [tr("Désactivé"), tr("Activé"), tr("Activé + tirs alliés")],
        "locations": [tr("Personne"), tr("Même équipe"), tr("Tous")],
        "teleport": [tr("Personne"), tr("Même équipe"), tr("Tous")],
    }
    fields = ["--form", "--width=960", "--columns=2", "--separator=\x1f",
              tr("--text=SoH / Anchor — règles communes et identité de chaque joueur.\n"
              "Les règles de salle dépendent des droits administrateur sur le serveur.\n"
              "Le chemin JSON est relatif au dossier de lancement du jeu."),
              tr("--field=Gérer ce jeu avec le profil Anchor:CHK"), str(data.get("adapter") == "soh-anchor").upper(),
              tr("--field=Connexion automatique:CHK"), str(settings["enabled"]).upper(),
              tr("--field=Room ID commun"), settings["room"],
              tr("--field=Serveur"), settings["host"],
              tr("--field=Port"), str(settings["port"]),
              tr("--field=Configuration SoH (chemin relatif)"), settings["config"]]
    for key, label in (("pvp", tr("PvP")), ("locations", tr("Afficher les positions")), ("teleport", tr("Autoriser la téléportation"))):
        values = labels[key]
        current = values[settings[key]]
        fields.extend([f"--field={label}:CB", "!".join([current, *(v for v in values if v != current)])])
    fields.extend([tr("--field=Synchroniser objets et progression:CHK"), str(settings["sync"]).upper()])
    for index in range(4):
        fields.extend([tr('--field=J{p0} — nom', p0=index + 1), settings["names"][index],
                       tr('--field=J{p0} — Team ID', p0=index + 1), settings["teams"][index]])
    result = yad([*fields, tr("--button=Annuler:1"), tr("--button=Graphismes / Audio:2"), tr("--button=Enregistrer:0")])
    if result.returncode in {1, 252}:
        return False
    if result.returncode not in {0, 2}:
        raise RuntimeError(tr("Impossible d'ouvrir les paramètres Anchor."))
    values = result.stdout.rstrip("\n").split("\x1f")
    if values and not values[-1]:
        values.pop()
    if len(values) != 18 or any(values[i].upper() not in {"TRUE", "FALSE"} for i in (0, 1, 9)):
        raise ValueError(tr("Réponse de l'éditeur Anchor invalide."))
    settings.update(enabled=values[1].upper() == "TRUE", room=values[2], host=values[3],
                    port=int(values[4]), config=values[5], sync=values[9].upper() == "TRUE",
                    names=values[10::2], teams=values[11::2])
    for index, key in enumerate(("pvp", "locations", "teleport"), 6):
        settings[key] = labels[key].index(values[index])
    validate_anchor(settings)
    if result.returncode == 2 and not edit_soh_graphics(settings):
        return False
    data.update(adapter="soh-anchor" if values[0].upper() == "TRUE" else "standard", anchor=settings)
    return True


def edit_soh_graphics(settings):
    from partydeck_anchor import graphics_defaults, validate_graphics, VOLUME_FIELDS
    current = settings.get("graphics", graphics_defaults())
    filters = [tr("Trois points (N64)"), tr("Linéaire"), tr("Aucun")]
    selected = filters[current["texture_filter"]]
    arguments = ["--form", "--width=700", "--separator=\x1f",
                  tr("--text=Réglages communs à tous les joueurs SoH.\n"
                  "Résolution interne : multiplicateur de la fenêtre de chaque joueur.\n"
                  "La musique peut être réservée à J1 ; les bruitages restent actifs pour tous.\n"
                  "Volumes : de 0 à 100 %, ou vide pour conserver la valeur du JSON commun.\n"
                  "SoH regroupe les voix et les bruitages dans le même volume."),
                  tr("--field=Résolution interne (0,5 à 2)"), str(current["internal_resolution"]),
                  tr("--field=Anti-aliasing MSAA (1 = désactivé, 2 à 8)"), str(current["msaa"]),
                  tr("--field=VSync:CHK"), str(current["vsync"]).upper(),
                  tr("--field=Filtre des textures:CB"), "!".join([selected, *(v for v in filters if v != selected)]),
                  tr("--field=Musique uniquement pour J1:CHK"), str(current["music_j1_only"]).upper()]
    for key, label in VOLUME_FIELDS:
        arguments.extend([f"--field={tr(label)} (%)", str(current.get("volumes", {}).get(key, ""))])
    result = yad([*arguments, tr("--button=Annuler:1"), tr("--button=Enregistrer:0")])
    if result.returncode in {1, 252}:
        return False
    if result.returncode:
        raise RuntimeError(tr("Impossible d'ouvrir les réglages graphiques SoH."))
    values = result.stdout.rstrip("\n").split("\x1f")
    if values and not values[-1]:
        values.pop()
    if len(values) != 10 or any(values[i].upper() not in {"TRUE", "FALSE"} for i in (2, 4)):
        raise ValueError(tr("Réponse des réglages graphiques SoH invalide."))
    options = dict(internal_resolution=float(values[0].replace(",", ".")),
                                                msaa=int(values[1]), vsync=values[2].upper() == "TRUE",
                                                texture_filter=filters.index(values[3]),
                   music_j1_only=values[4].upper() == "TRUE")
    volumes = {key: int(value.strip()) for (key, _), value in zip(VOLUME_FIELDS, values[5:]) if value.strip()}
    if volumes:
        options["volumes"] = volumes
    settings["graphics"] = validate_graphics(options)
    return True


def launch_profile(base, rom):
    path = profile_path(base, rom)
    missing = not path.exists()
    data = defaults(rom) if missing else read_profile(base, rom)
    if missing or data["configure_before_launch"]:
        if not edit_profile(base, rom):
            return 0
        data = read_profile(base, rom)
    command = [str(base / "windows-party"), "party", str(rom),
               data["players"], data["split"], data["input"]]
    os.execv(command[0], command)


def install_menu(base, roms=PARTY_ROMS):
    # Upgrade only the exact command format produced by the previous installer.
    # JSON data already edited by the user takes priority on reinstall.
    for entry in sorted(roms.glob("*.sh")):
        if entry.is_symlink():
            continue
        lines = entry.read_text().splitlines()
        if len(lines) != 3 or lines[1] != MARKER or not lines[2].startswith("exec "):
            continue
        command = shlex.split(lines[2])
        if len(command) != 7 or command[:3] != ["exec", str(base / "windows-party"), "party"]:
            continue
        rom = Path(command[3])
        path = profile_path(base, rom)
        if not path.exists() and not path.is_symlink():
            prepare_profile(base, rom, *command[4:])
        else:
            read_profile(base, rom)
        atomic_write(entry, f"#!/bin/bash\n{MARKER}\nexec " +
                     shlex.join([str(base / "windows-party"), "profil", str(rom)]) + "\n", 0o755)
    sync_library_scrapes(base,roms)
    menu = roms / "Configurer Windows Party.sh"
    marker = "# Configuration gérée par Windows Party"
    if menu.exists() and marker not in menu.read_text().splitlines()[:2]:
        raise ValueError(tr('Une entrée utilisateur existe déjà : {p0}', p0=menu))
    atomic_write(menu, f"#!/bin/bash\n{marker}\nexec " +
                 shlex.join([str(base / "windows-party"), "configurer"]) + "\n", 0o755)


def choose_rom():
    kind = yad([tr("--text=Choisissez le format du jeu Windows."),
                tr("--button=Annuler:1"), tr("--button=Dossier .wine ou .pc:2"),
                tr("--button=Archive .wsquashfs:0")])
    if kind.returncode in {1, 252}:
        return None
    if kind.returncode not in {0, 2}:
        raise RuntimeError(tr("Le sélecteur de format n'a pas pu s'ouvrir."))
    options = ["--file-selection", "--filename=/userdata/roms/windows/"]
    if kind.returncode == 2:
        options.append("--directory")
    else:
        options.append(tr("--file-filter=Jeux Wine | *.wsquashfs *.WSQUASHFS"))
    result = yad(options)
    if result.returncode in {1, 252}:
        return None
    if result.returncode:
        raise RuntimeError(tr("Le sélecteur de jeu n'a pas pu s'ouvrir."))
    rom = Path(result.stdout.rstrip("\n")).absolute()
    if (rom.suffix.lower() not in ROM_TYPES or not rom.exists()
            or (rom.suffix.lower() == ".wsquashfs") != rom.is_file()):
        raise ValueError(tr("Choisissez une archive .wsquashfs ou un dossier .wine ou .pc."))
    return rom


def configure(base, rom=None):
    sync_library_scrapes(base)
    if os.environ.get("PARTYDECK_UI") != "legacy":
        from partydeck_couch import configure as couch_configure
        couch_configure(base, rom)
        return 0
    return configure_legacy(base, rom)


def configure_legacy(base, rom=None):
    if shutil.which("batocera-mouse"):
        subprocess.run(["batocera-mouse", "show"], check=False)
    while True:
        if rom is None:
            rows = []
            for path in sorted((base / "profiles").glob("*.json")):
                data = json.loads(path.read_text())
                source = Path(data["rom"])
                validate(data, source)
                rows.extend([str(source), source.stem])
            result = yad(["--list", "--width=760", "--height=440", "--separator=\x1f",
                          "--column=ROM", tr("--column=Jeu"), "--hide-column=1", "--print-column=1",
                          tr("--button=Fermer:1"), tr("--button=Ajouter un jeu:2"), tr("--button=Configurer:0"),
                          *rows])
            if result.returncode in {1, 252}:
                return 0
            if result.returncode == 2:
                selected = choose_rom()
            elif result.returncode == 0:
                value = result.stdout.rstrip("\n").removesuffix("\x1f")
                selected = Path(value) if value else None
            else:
                raise RuntimeError(tr("Le gestionnaire Windows Party n'a pas pu s'ouvrir."))
        else:
            selected = rom
        if selected is not None and edit_profile(base, selected):
            data = read_profile(base, selected)
            subprocess.run([str(base / "windows-party"), "ajouter", str(selected),
                            data["players"], data["split"], data["input"]], check=True)
        if rom is not None:
            return 0


def main():
    mode, folder, *arguments = sys.argv[1:]
    base = Path(folder)
    if mode == "installer":
        install_menu(base)
        return 0
    rom = Path(arguments[0]).absolute() if arguments else None
    if mode == "configurer":
        return configure(base, rom)
    if mode == "profil" and rom is not None:
        return launch_profile(base, rom)
    raise ValueError(tr("Commande de profil Windows Party invalide."))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Windows Party : {error}", file=sys.stderr)
        if shutil.which("yad") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            yad(["--error", "--text=" + html.escape(str(error))])
        raise SystemExit(1)
