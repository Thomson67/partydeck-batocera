"""Windows Party's controller-first configurator. Original Pygame implementation."""
from partydeck_i18n import tr, detect_language, set_language, get_language
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import subprocess
import textwrap
import time
import xml.etree.ElementTree as ET

from partydeck_profiles import (defaults, read_profile, save_profile, profile_path,
                               validate, ROM_TYPES, remove_profile, atomic_write)
from partydeck_anchor import defaults as anchor_defaults, graphics_defaults, VOLUME_FIELDS
from partydeck_catalog import (CommonGame, COMMON, discover, matches_soh, is_rom,
                              recipe_for, unlinked, set_unlinked)
from partydeck_borderlands2 import defaults as bl2_defaults, PRESETS, PRESET_LABELS, matches as matches_bl2
from partydeck_nfsmw import defaults as mw_defaults, matches as matches_mw
from partydeck_hkmp import defaults as hkmp_defaults, matches as matches_hkmp
from partydeck_l4d2 import defaults as l4d2_defaults, matches as matches_l4d2, LANGUAGES as L4D2_LANGUAGES
from partydeck_sm64coopdx import (defaults as sm64_defaults, matches as matches_sm64, LANGUAGES as SM64_LANGUAGES,
                                  LANGUAGE_LABELS, DRAW_LABELS, BASE_VOLUMES as SM64_VOLUMES,
                                  VOLUME_FIELDS as SM64_VOLUME_FIELDS)
from partydeck_storage import (settings as storage_settings, save_settings as save_storage_settings,
                               snapshot as storage_snapshot, clean as clean_storage, prepare_launch, human)

from partydeck_display import (settings as desktop_settings, save_settings as save_desktop_settings,
                               discover_outputs, output_choices, output_label)

TABS = ['Session', 'Réseau', 'Joueurs', 'Image & son']
KEY_LABELS = {'ok':'Entrée', 'back':'Échap', 'save':'F2', 'search':'F3', 'add':'Inser', 'tabs':'PgUp/PgDn'}


def control_label(action, mode):
    if mode == 'keyboard':
        return tr(KEY_LABELS[action])
    if action == 'tabs':
        return 'L1/R1' if mode == 'ps' else 'LB/RB'
    if action == 'add':
        return 'OPTIONS' if mode == 'ps' else 'START'
    return ({'ok':tr('Croix'), 'back':tr('Cercle'), 'save':tr('Carré'), 'search':tr('Triangle')} if mode == 'ps'
            else {'ok':'A', 'back':'B', 'save':'X', 'search':'Y'})[action]


def context_hints(context, mode, has_tabs=True):
    if context == 'remove':
        return [('ok',tr('Confirmer')), ('back',tr('Annuler'))]
    if context == 'storage-error':
        return [('back',tr('Fermer'))]
    if context == 'desktop':
        return [('ok',tr('Choisir')), ('back',tr('Retour'))]
    if context == 'storage':
        return [('ok',tr('Choisir')), ('back',tr('Retour')), ('tabs',tr('Jeux par taille'))]
    if context == 'confirm':
        return [('ok',tr('Enregistrer')), ('search',tr('Abandonner')), ('back',tr('Annuler'))]
    if context == 'missing':
        return [('ok',tr('Choisir le jeu')), ('back',tr('Annuler'))]
    if context == 'keyboard':
        return [('ok',tr('Valider')), ('back',tr('Annuler'))] if mode == 'keyboard' else [('ok',tr('Saisir')), ('save',tr('Valider')), ('back',tr('Annuler'))]
    if context == 'browser':
        return [('ok',tr('Choisir')), ('back',tr('Annuler')), ('tabs',tr('Parcourir') if mode=='keyboard' else tr('Pages · maintenir'))]
    return [('ok',tr('Choisir')), ('back',tr('Retour')), ('save',tr('Enregistrer')), ('search',tr('Rechercher')),
            *([('tabs',tr('Onglets'))] if has_tabs else []), ('add',tr('Ajouter'))]
KEYS = [list('azertyuiop'), list('qsdfghjklm'), list('wxcvbn0123'),
        list('456789 .-_'), list('@:/\\!?éèàç'), list('[]()#&+=$%'),
        list("'\";<>^~{}|"), ['Maj', 'Espace', 'Effacer', 'Vider', 'Valider']]
EN_KEYS = [list('qwertyuiop'), list('asdfghjkl'), list('zxcvbnm012'),
           list('3456789 .-_'), *KEYS[4:]]


def fields(tab, adapter='standard'):
    if tab == 0:
        return [('players', tr('Joueurs'), ['auto', '1', '2', '3', '4']),
                ('split', tr('Partage de l’écran'), ['horizontal', 'vertical']),
                ('input', tr('Attribution des contrôles'), ['auto', 'clavier-j1', 'clavier-j2']),
                ('keyboard_player', tr('Clavier/souris utilisable comme joueur'), [True, False]),
                ('gpu',tr('GPU de rendu'),['auto','system','nvidia']),
                ('configure_before_launch', tr('Configurer avant chaque lancement'), [False, True]),
                ('adapter', tr('Profil du jeu'), ['standard', 'soh-anchor', 'borderlands2', 'sm64coopdx', 'l4d2-goldberg', 'nfsmw-lan', 'hollowknight-hkmp'])]
    if adapter == 'hollowknight-hkmp':
        if tab == 1:
            return [('hkmp.automatic',tr('Héberger et rejoindre automatiquement'),[True,False]),
                    ('hkmp.port',tr('Port du serveur HKMP'),None),
                    *[(f'hkmp.names.{i}',tr('J{p0} · {p1}',p0=i+1,p1=tr('Nom')),None) for i in range(4)]]
        return [('hkmp.pvp',tr('Dégâts entre joueurs (PvP)'),[False,True]),
                ('hkmp.body_damage',tr('Dégâts par contact entre joueurs'),[False,True]),
                ('hkmp.map_icons',tr('Joueurs toujours visibles sur la carte'),[True,False]),
                ('hkmp.display_names',tr('Afficher les noms des joueurs'),[True,False]),
                ('hkmp.skins',tr('Autoriser les skins HKMP'),[True,False]),
                ('hkmp.enemy_health',tr('PV partagés des ennemis · ESoulLink'),['keep','on','off']),
                ('hkmp.enemy_ghosts',tr('Fantômes des ennemis · GhostHunter'),['keep','on','off'])]
    if adapter == 'nfsmw-lan':
        return [('nfsmw.private_lan',tr('LAN privé local (sans Internet)'),[True,False]),
                ('nfsmw.host',tr('IP LAN du PC (auto : détection)'),None),
                ('nfsmw.throttle',tr('Fréquence du serveur LAN'),[1,6,10,30,60]),
                ('nfsmw.start_delay',tr('Délai entre joueurs (secondes)'),[0,15,30,60]),
                ('nfsmw.music_j1_only',tr('Musique uniquement pour J1'),[True,False]),
                ('nfsmw.controller_enter',tr('LB + RB / L1 + R1 : nom J1–J4 et validation'),[True,False])]
    if adapter == 'l4d2-goldberg':
        if tab==2:
            return [('l4d2.language',tr('Langue du jeu'),list(L4D2_LANGUAGES)),
                    ('l4d2.gamepad',tr('Activer la manette en jeu'),[True,False])]
        return [(f'l4d2.names.{i}',tr('J{p0} · {p1}',p0=i+1,p1=tr('Nom')),None) for i in range(4)]
    if adapter == 'sm64coopdx':
        if tab == 1:
            return [('sm64coopdx.vsync',tr('VSync'),[False,True]),
                    ('sm64coopdx.msaa',tr('Anti-aliasing MSAA'),[0,2,4,8,16]),
                    ('sm64coopdx.texture_filtering',tr('Filtre des textures'),[0,1,2]),
                    ('sm64coopdx.coop_draw_distance',tr('Distance d’affichage'),list(range(7)))]
        if tab == 2:
            return [('sm64coopdx.free_camera',tr('Caméra libre'),[False,True]),
                    ('sm64coopdx.sensitivity_x',tr('Sensibilité caméra · axe X'),list(range(1,101))),
                    ('sm64coopdx.sensitivity_y',tr('Sensibilité caméra · axe Y'),list(range(1,101))),
                    ('sm64coopdx.invert_x',tr('Inverser la caméra · axe X'),[False,True]),
                    ('sm64coopdx.invert_y',tr('Inverser la caméra · axe Y'),[False,True])]
        if tab == 3:
            return [('sm64coopdx.language',tr('Langue du jeu'),list(SM64_LANGUAGES)),
                    *[(f'sm64coopdx.names.{i}',tr('J{p0} · {p1}',p0=i+1,p1=tr('Nom')),None) for i in range(4)]]
        return [('sm64coopdx.music_j1_only',tr('Musique uniquement pour J1'),[True,False]),
                *[(f'sm64coopdx.volumes.{key}',tr(label)+' (%)',None) for key,label in SM64_VOLUME_FIELDS]]
    if adapter == 'borderlands2':
        if tab == 2:
            return [(f'borderlands2.names.{i}',tr('J{p0} · {p1}',p0=i+1,p1=tr('Nom')),None) for i in range(4)]
        return [('borderlands2.preset',tr('Préréglage graphique'),list(PRESETS)),
                ('borderlands2.vsync',tr('VSync'),['keep','on','off']),
                ('borderlands2.physx',tr('Qualité PhysX'),['keep','0','1','2'])]
    if tab == 1:
        return [('anchor.enabled', tr('Connexion automatique Anchor'), [False, True]),
                ('anchor.room', tr('Room ID commun'), None), ('anchor.host', tr('Serveur'), None),
                ('anchor.port', tr('Port'), None), ('anchor.config', tr('Chemin du JSON SoH'), None),
                ('anchor.pvp', tr('PvP'), [0, 1, 2]), ('anchor.locations', tr('Positions visibles'), [0, 1, 2]),
                ('anchor.teleport', tr('Téléportation'), [0, 1, 2]), ('anchor.sync', tr('Objets et progression partagés'), [False, True])]
    if tab == 2:
        return [(f'anchor.{key}.{i}', tr('J{p0} · {p1}', p0=i + 1, p1=label), None)
                for i in range(4) for key, label in [('names', tr('Nom')), ('teams', tr('Équipe'))]]
    return [('anchor.graphics.internal_resolution', tr('Résolution interne'), [.5, .75, 1., 1.25, 1.5, 1.75, 2.]),
            ('anchor.graphics.msaa', tr('Anti-aliasing MSAA'), list(range(1, 9))),
            ('anchor.graphics.vsync', tr('VSync'), [False, True]),
            ('anchor.graphics.texture_filter', tr('Filtre des textures'), [0, 1, 2]),
            ('anchor.graphics.music_j1_only', tr('Musique uniquement pour J1'), [False, True]),
            *[(f'anchor.graphics.volumes.{key}', tr(label) + ' (%)', None) for key, label in VOLUME_FIELDS]]


def get(data, key):
    node = data
    for part in key.split('.'):
        try:
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError):
            return ''
    return node


def put(data, key, value):
    parts = key.split('.')
    node = data
    for part in parts[:-1]:
        node = node[int(part)] if isinstance(node, list) else node.setdefault(part, {})
    if isinstance(node, list):
        node[int(parts[-1])] = value
    elif '.volumes.' in key and value == '':
        node.pop(parts[-1], None)
    else:
        node[parts[-1]] = value


def label_value(key, value):
    if key=='gpu':
        return {'auto':tr('Automatique'),'system':tr('Configuration système'),'nvidia':'NVIDIA'}[value]
    if key in ('players','input') and value == 'auto':
        return tr('Automatique')
    if key == 'split':
        return tr('Horizontal') if value == 'horizontal' else tr('Vertical')
    if key == 'input' and value in ('clavier-j1','clavier-j2'):
        return tr('Clavier/souris · J1') if value == 'clavier-j1' else tr('Clavier/souris · J2')
    if type(value) is bool:
        return tr('Activé') if value else tr('Désactivé')
    if key == 'adapter':
        return {'standard': 'Standard', 'soh-anchor': 'SoH / Anchor', 'borderlands2':'Borderlands 2', 'sm64coopdx':'SM64CoopDX', 'l4d2-goldberg':'Left 4 Dead 2 / Goldberg','nfsmw-lan':tr('Most Wanted 2005 · LAN expérimental'),'hollowknight-hkmp':'Hollow Knight / HKMP'}.get(value, value)
    if key in ('hkmp.enemy_health','hkmp.enemy_ghosts'):
        return tr({'keep':'Conserver','on':'Activé','off':'Désactivé'}[value])
    if key == 'l4d2.language':
        return tr(L4D2_LANGUAGES[value])
    if key == 'sm64coopdx.language':
        return tr(LANGUAGE_LABELS[value])
    if key == 'sm64coopdx.msaa':
        return tr('Désactivé') if value==0 else f'{value}×'
    if key == 'sm64coopdx.texture_filtering':
        return [tr('Au plus proche'),tr('Linéaire'),tr('Trois points N64')][value]
    if key == 'sm64coopdx.coop_draw_distance':
        return tr(DRAW_LABELS[value])
    if key == 'borderlands2.preset':
        return tr(PRESET_LABELS[value])
    if key == 'borderlands2.vsync':
        return {'keep':tr('Conserver'), 'on':tr('Activé'), 'off':tr('Désactivé')}[value]
    if key == 'borderlands2.physx':
        return {'keep':tr('Conserver'), '0':tr('Bas'),'1':tr('Moyen'),'2':tr('Élevé')}[value]
    if key.startswith('borderlands2.names.') and value == '':
        return tr('Conserver')
    if key in ('anchor.locations', 'anchor.teleport'):
        return [tr('Personne'), tr('Même équipe'), tr('Tous')][value]
    if key == 'anchor.pvp':
        return [tr('Désactivé'), tr('Activé'), tr('Avec tirs alliés')][value]
    if key.endswith('texture_filter'):
        return [tr('Trois points N64'), tr('Linéaire'), tr('Aucun')][value]
    return str(value) if value != '' else tr('JSON commun')


class Model:
    def __init__(self, base, rom=None, windows=Path('/userdata/roms/windows')):
        self.base, self.rom = Path(base), rom
        self.windows = windows
        self.selected = rom
        self.detected = {'soh':discover(windows), 'borderlands2':discover(windows,matches_bl2),
                         'sm64coopdx':discover(windows,matches_sm64),'l4d2':discover(windows,matches_l4d2),'nfsmw':discover(windows,matches_mw),'hkmp':discover(windows,matches_hkmp)}
        self.common_for_rom = {}
        self.data = None
        self.saved = None
        self.rows = []
        self.filter = ''
        self.reload()
        if rom is not None:
            self.select(Path(rom))

    def reload(self):
        self.rows = []
        self.common_for_rom = {}
        registered = set()
        for path in sorted((self.base / 'profiles').glob('*.json')):
            data = json.loads(path.read_text())
            rom = Path(data['rom'])
            validate(data, rom)
            recipe = recipe_for(rom,data.get('adapter')) or recipe_for(rom)
            if recipe:
                registered.add(recipe.id)
            if recipe and data.get('adapter') == recipe.adapter:
                self.common_for_rom[rom] = recipe
            if self.filter.casefold() in rom.stem.casefold():
                self.rows.append(rom)
        detached = unlinked(self.base)
        for recipe in COMMON:
            if recipe.id in registered:
                continue
            found = self.detected[recipe.id]
            if len(found) == 1 and recipe.id not in detached:
                rom = found[0]
                self.common_for_rom[rom] = recipe
                if self.filter.casefold() in (rom.stem + tr(recipe.name)).casefold():
                    self.rows.append(rom)
            elif self.filter.casefold() in tr(recipe.name).casefold():
                self.rows.append(CommonGame(recipe.id, recipe.name, recipe.adapter, found))
        self.rows.sort(key=lambda p: (isinstance(p,CommonGame),
                      str(next(i for i,r in enumerate(COMMON) if r.id==p.id)) if isinstance(p,CommonGame) else p.stem.casefold()))

    def select(self, rom, common=None):
        self.selected = rom
        if isinstance(rom, CommonGame):
            self.rom, self.data, self.saved = None, None, None
            return
        self.rom = rom
        recipe = common or self.common_for_rom.get(rom)
        detached = self.base/'detached-profiles'/f'{recipe.id}.json' if recipe else None
        if profile_path(self.base,rom).exists():
            self.data = read_profile(self.base,rom)
        elif detached is not None and detached.exists():
            self.data = json.loads(detached.read_text())
            self.data['rom'] = str(rom)
            validate(self.data,rom)
        else:
            self.data = defaults(rom)
        self.data.setdefault('adapter', 'standard')
        self.data.setdefault('keyboard_player', True)
        self.data.setdefault('gpu','auto')
        self.data.setdefault('anchor', anchor_defaults())
        self.data.setdefault('borderlands2', bl2_defaults())
        self.data.setdefault('sm64coopdx', sm64_defaults())
        self.data.setdefault('l4d2',l4d2_defaults())
        self.data.setdefault('nfsmw',mw_defaults())
        self.data.setdefault('hkmp',hkmp_defaults())
        self.data['anchor'].setdefault('graphics', graphics_defaults())
        if recipe:
            self.data['adapter'] = recipe.adapter
            self.common_for_rom[rom] = recipe
        self.saved = copy.deepcopy(self.data)

    def dirty(self):
        # Defaults displayed by the UI do not by themselves count as an edit.
        return self.saved != self.data

    def save(self):
        validate(self.data, self.rom)
        old = profile_path(self.base, self.rom)
        previous = old.read_bytes() if old.exists() else None
        stored = copy.deepcopy(self.data)
        if stored.get('adapter') != 'soh-anchor':
            stored.pop('anchor', None)
        if stored.get('adapter') != 'borderlands2':
            stored.pop('borderlands2', None)
        if stored.get('adapter') != 'sm64coopdx':
            stored.pop('sm64coopdx', None)
        if stored.get('adapter') != 'l4d2-goldberg':
            stored.pop('l4d2',None)
        if stored.get('adapter') != 'nfsmw-lan':stored.pop('nfsmw',None)
        if stored.get('adapter') != 'hollowknight-hkmp':stored.pop('hkmp',None)
        save_profile(self.base, self.rom, stored)
        try:
            subprocess.run([str(self.base / 'windows-party'), 'ajouter', str(self.rom),
                            self.data['players'], self.data['split'], self.data['input']], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except (OSError, subprocess.CalledProcessError):
            from partydeck_profiles import atomic_write
            if previous is None:
                old.unlink(missing_ok=True)
            else:
                atomic_write(old, previous.decode())
            raise
        self.saved = copy.deepcopy(self.data)
        self.reload()
        recipe = recipe_for(self.rom,self.data.get('adapter'))
        if recipe:
            set_unlinked(self.base,recipe,False)

    def remove(self, roms=None):
        rom = self.rom
        recipe = recipe_for(rom,self.data.get('adapter'))
        changes = []
        if recipe:
            validate(self.data,rom)
            for path in (self.base/'catalog.json',self.base/'detached-profiles'/f'{recipe.id}.json'):
                if path.is_symlink():
                    raise ValueError(tr('Métadonnées de catalogue liées à un autre emplacement ; dissociation refusée.'))
                changes.append((path,path.read_bytes() if path.exists() else None))
            stored = copy.deepcopy(self.data)
            stored.pop('rom')
            atomic_write(changes[1][0],json.dumps(stored,ensure_ascii=False,indent=2)+'\n')
            set_unlinked(self.base,recipe,True)
        elif recipe_for(rom):
            # A manually configured standard game can still match a catalogue
            # name. Removing it must not immediately re-add it by detection.
            path = self.base/'catalog.json'
            changes.append((path,path.read_bytes() if path.exists() else None))
            set_unlinked(self.base,recipe_for(rom),True)
        try:
            remove_profile(self.base,rom,roms)
        except Exception:
            for path,before in changes:
                path.unlink(missing_ok=True) if before is None else atomic_write(path,before.decode())
            raise
        self.rom = self.selected = self.data = self.saved = None
        self.filter = ''
        self.reload()
        if self.rows:
            self.select(next((p for p in self.rows if recipe and isinstance(p,CommonGame) and p.id==recipe.id),self.rows[0]))


class Pads:
    """SDL standardized mappings, with ES mappings for unrecognized devices."""
    def __init__(self, pg):
        self.pg, self.devices = pg, []
        self.previous = set()
        self.raw = []
        self.family = 'xbox'
        self.timers = {}
        try:
            from pygame._sdl2 import controller
            self.controllers = controller
            controller.init()
        except ImportError:
            self.controllers = None
        self.refresh()

    def refresh(self):
        self.devices = []
        self.raw = []
        cfg = Path('/userdata/system/configs/emulationstation/es_input.cfg')
        try:
            configs = ET.parse(cfg).findall('inputConfig') if cfg.exists() else []
        except ET.ParseError:
            configs = []
        for i in range(self.pg.joystick.get_count()):
            stick = self.pg.joystick.Joystick(i)
            stick.init()
            profile = next((c for c in configs if c.get('deviceGUID', '').lower() == stick.get_guid().lower()), None)
            mapping = {n.get('name'): n.attrib for n in profile} if profile is not None else {}
            self.raw.append((stick, mapping))
            if i == 0 and not self.previous:
                name = stick.get_name().lower()
                self.family = 'ps' if any(n in name for n in ('dualsense', 'dualshock', 'playstation', 'sony', 'ps4', 'ps5')) else 'xbox'
            if self.controllers and self.controllers.is_controller(i):
                self.devices.append(('sdl', self.controllers.Controller(i), mapping))
            else:
                stick = self.pg.joystick.Joystick(i)
                stick.init()
                profile = next((c for c in configs if c.get('deviceGUID', '').lower() == stick.get_guid().lower()), None)
                mapping = {n.get('name'): n.attrib for n in profile} if profile is not None else {}
                self.devices.append(('es', stick, mapping))
        self.previous.clear()

    @staticmethod
    def binding(pad, mapping):
        if not mapping:
            return False
        idx, value = int(mapping['id']), int(mapping['value'])
        if mapping['type'] == 'button':
            return bool(pad.get_button(idx))
        if mapping['type'] == 'axis':
            return pad.get_axis(idx)*value > .5
        if mapping['type'] == 'hat':
            x, y = pad.get_hat(idx)
            return {1:y>0, 2:x>0, 4:y<0, 8:x<0}.get(value, False)
        return False

    def poll(self, repeat_pages=False):
        held = set()
        for kind, pad, mapping in self.devices:
            try:
                device_name = str(getattr(pad, 'name', '')) if kind == 'sdl' else pad.get_name()
                family = 'ps' if any(n in device_name.lower() for n in ('dualsense', 'dualshock', 'playstation', 'sony', 'ps4', 'ps5')) else 'xbox'
                was_held = held.copy()
                if kind == 'sdl':
                    if not (mapping.get('hotkey') or mapping.get('hotkeyenable')) and pad.get_button(5) and pad.get_button(6):
                        held.add('quit')
                    for action, button in [('ok', 0), ('back', 1), ('save', 2), ('search', 3), ('add', 6),
                                           ('prev', 9), ('next', 10), ('up', 11), ('down', 12), ('left', 13), ('right', 14)]:
                        if pad.get_button(button):
                            held.add(action)
                    for axis, neg, pos in [(0, 'left', 'right'), (1, 'up', 'down')]:
                        value = pad.get_axis(axis)
                        if abs(value) > 16000:
                            held.add(neg if value < 0 else pos)
                else:
                    for action, name in [('ok', 'b'), ('back', 'a'), ('save', 'y'), ('search', 'x'),
                                         ('add', 'start'), ('prev', 'pageup'), ('next', 'pagedown'),
                                         *[(a, a) for a in ('up', 'down', 'left', 'right')]]:
                        m = mapping.get(name)
                        if not m:
                            continue
                        idx, value = int(m['id']), int(m['value'])
                        if m['type'] == 'button':
                            active = pad.get_button(idx)
                        elif m['type'] == 'axis':
                            active = pad.get_axis(idx) * value > .5
                        elif m['type'] == 'hat':
                            x, y = pad.get_hat(idx)
                            active = {1: y > 0, 2: x > 0, 4: y < 0, 8: x < 0}.get(value, False)
                        else:
                            active = False
                        if active:
                            held.add(action)
                if held != was_held:
                    self.family = family
            except (self.pg.error, IndexError):
                continue
        for pad, mapping in self.raw:
            try:
                if self.binding(pad, mapping.get('hotkey') or mapping.get('hotkeyenable')) and self.binding(pad, mapping.get('start')):
                    held.add('quit')
            except (self.pg.error, IndexError, ValueError):
                continue
        if 'quit' in held:
            held = {'quit'}  # Never open the file browser for the Start in HK+Start.
        now = time.monotonic()
        actions = []
        for action in held:
            if action not in self.previous:
                actions.append(action)
                self.timers[action] = now + .35
            elif (action in ('up','down','left','right') or (repeat_pages and action in ('prev','next'))) and now >= self.timers.get(action,now):
                actions.append(action)
                self.timers[action] = now + .12
        self.previous = held
        return actions


class App:
    def __init__(self, base, rom=None, windowed=False):
        set_language(detect_language())
        self.keys = KEYS if get_language() == 'fr' else EN_KEYS
        import pygame as pg
        self.pg = pg
        pg.display.init()
        pg.font.init()
        pg.joystick.init()
        self.screen = pg.display.set_mode((1280, 800) if windowed else (0, 0), 0 if windowed else pg.FULLSCREEN)
        pg.display.set_caption(tr('Windows Party · Configurateur'))
        pg.mouse.set_visible(False)
        self.canvas = pg.Surface((1440, 900))
        self.panels = {}
        self.background = pg.Surface((1440, 900))
        for y in range(900):
            pg.draw.line(self.background, (10+y//130, 14+y//140, 25+y//70), (0, y), (1440, y))
        for x in range(-900, 1600, 80):
            pg.draw.line(self.background, (20, 27, 43), (x, 900), (x+650, 0))
        pg.draw.polygon(self.background, (22, 45, 61), [(0,0),(450,0),(290,7),(0,7)])
        pg.draw.polygon(self.background, (60, 30, 82), [(1440,900),(1000,900),(1160,892),(1440,892)])
        self.fonts = {s: pg.font.SysFont('DejaVu Sans', s) for s in (16, 20, 24, 28, 36)}
        self.clock = pg.time.Clock()
        self.model = Model(base, rom)
        self.template_volumes = dict(Master=40, MainMusic=100, SubMusic=100, Fanfare=100, SFX=100)
        template = Path(base) / 'templates/soh-common.json'
        if template.is_file():
            try:
                volumes = json.loads(template.read_text()).get('CVars', {}).get('gSettings', {}).get('Volume', {})
                self.template_volumes.update({key: value for key, value in volumes.items()
                                              if key in self.template_volumes and type(value) is int and 0 <= value <= 100})
            except (OSError, ValueError, AttributeError):
                pass
        self.sm64_template_volumes = dict(SM64_VOLUMES)
        try:
            for line in (Path(base)/'templates/sm64coopdx-common.txt').read_text().splitlines():
                parts = line.split()
                if len(parts)==2 and parts[0] in SM64_VOLUMES and parts[1].isdigit() and 0 <= int(parts[1]) <= 127:
                    self.sm64_template_volumes[parts[0]] = round(int(parts[1])*100/127)
        except OSError:
            pass
        self.pads = Pads(pg)
        self.input_mode = self.pads.family if self.pads.devices else 'keyboard'
        self.library = 0
        self.tab, self.row, self.pane = 0, 0, 'settings' if rom else 'library'
        self.running, self.accepted = True, False
        self.launch_requested = False
        self.single = False
        self.keyboard = None
        self.modal = None
        self.notice, self.notice_until = '', 0
        self.browser = None
        self.browser_rows = []
        self.pending = None
        self.missing = None
        self.removal = None
        self.pending_common = None
        self.desktop_open = False
        self.desktop_row = 0
        self.desktop_config = None
        self.desktop_outputs = []
        self.storage_open = False
        self.storage_row = self.storage_page = 0
        self.storage_result = None
        self.storage_future = self.storage_pool = None
        self.storage_task = None
        self.launch_pending = False
        self.launch_error = None
        self.storage_config = None
        self.logo = None
        logo = Path(base) / 'assets/windows-party.png'
        if logo.exists():
            self.logo = pg.image.load(str(logo)).convert_alpha()
        if rom is None and self.model.rows:
            self.model.select(self.model.rows[0])
        if self.model.rom in self.model.rows:
            self.library = self.model.rows.index(self.model.rom)

    def toast(self, text):
        self.notice, self.notice_until = text, time.monotonic() + 5

    def available_tabs(self):
        if self.model.data and self.model.data.get("adapter") == "hollowknight-hkmp":return (0,1,2)
        if self.model.data and self.model.data.get('adapter') == 'nfsmw-lan':return (0,1)
        if self.model.data and self.model.data.get('adapter') == 'l4d2-goldberg':
            return (0,1,2)
        if self.model.data and self.model.data.get('adapter') == 'sm64coopdx':
            return (0,1,2,3,4)
        if self.model.data and self.model.data.get('adapter') == 'borderlands2':
            return (0,1,2)
        return (0,1,2,3) if self.model.data and self.model.data.get('adapter') == 'soh-anchor' else (0,)

    def current_fields(self):
        rows=fields(self.tab,self.model.data.get('adapter','standard') if self.model.data else 'standard')
        if self.model.data and self.model.data.get('adapter')=='nfsmw-lan' and self.model.data.get('nfsmw',{}).get('private_lan',True):
            rows=[row for row in rows if row[0]!='nfsmw.host']
        return rows

    def text(self, value, x, y, size=24, color=(228, 234, 247), width=1000):
        font = self.fonts[size]
        value = str(value)
        while value and font.size(value)[0] > width:
            value = value[:-2] + '…' if len(value) > 2 else ''
        self.canvas.blit(font.render(value, True, color), (x, y))

    def box(self, rect, color, border=None):
        x, y, w, h = rect
        key = (w, h, color)
        if key not in self.panels:
            panel = self.pg.Surface((w,h), self.pg.SRCALPHA)
            for row in range(h):
                t = row / max(1, h-1)
                shine = 1.22 - .4*t + .16*math.exp(-((t-.16)/.07)**2)
                shade = tuple(min(255, int(v*shine)) for v in color)
                self.pg.draw.line(panel, shade, (0,row), (w,row))
            mask = self.pg.Surface((w,h), self.pg.SRCALPHA)
            self.pg.draw.rect(mask, (255,255,255), (0,0,w,h), border_radius=12)
            panel.blit(mask, (0,0), special_flags=self.pg.BLEND_RGBA_MULT)
            self.pg.draw.rect(panel, (83,98,124,90), (0,0,w,h), 1, border_radius=12)
            self.pg.draw.line(panel, (123,142,172,90), (14,1), (w-15,1))
            self.panels[key] = panel
        self.canvas.blit(self.panels[key], (x,y))
        if border:
            self.pg.draw.rect(self.canvas, border, rect, 2, border_radius=12)

    def hint(self, action, label, x, y, width=220):
        draw = self.pg.draw
        ps = self.input_mode == 'ps'
        colors = {'ok':(95,216,164), 'back':(255,121,126), 'save':(111,177,255), 'search':(242,208,109)}
        color = colors.get(action, (167,187,219))
        center = (x+16, y+16)
        if self.input_mode == 'keyboard':
            badge = control_label(action, 'keyboard')
            badge_width = self.fonts[16].size(badge)[0]+18
            self.box((x-3,y,badge_width,32), (38,47,65), (107,128,157))
            self.text(badge, x+5, y+5, 16, color, badge_width-10)
        elif action in colors:
            draw.circle(self.canvas, (15,22,35), center, 17)
            draw.circle(self.canvas, color, center, 16, 2)
            if ps:
                if action == 'ok':
                    draw.line(self.canvas, color, (x+10,y+10), (x+22,y+22), 3)
                    draw.line(self.canvas, color, (x+22,y+10), (x+10,y+22), 3)
                elif action == 'back':
                    draw.circle(self.canvas, color, center, 8, 2)
                elif action == 'save':
                    draw.rect(self.canvas, color, (x+8,y+8,16,16), 2)
                else:
                    draw.polygon(self.canvas, color, [(x+16,y+6),(x+25,y+23),(x+7,y+23)], 2)
            else:
                self.text({'ok':'A','back':'B','save':'X','search':'Y'}[action], x+9, y+3, 20, color, 25)
        else:
            badge = control_label(action, self.input_mode)
            badge_width = 64 if action == 'tabs' else 90 if ps else 72
            self.box((x-3,y,badge_width,32), (38,47,65), (107,128,157))
            self.text(badge, x+2, y+5, 16, color, badge_width-8)
        label_offset = 45 if action in colors and self.input_mode != 'keyboard' else badge_width+8
        self.text(label, x+label_offset, y+3, 20, width=max(0,width-label_offset))

    def help_context(self):
        return ('remove' if self.removal else 'storage-error' if self.launch_error else 'confirm' if self.modal else 'missing' if self.missing is not None else
                'keyboard' if self.keyboard else 'browser' if self.browser is not None else
                'desktop' if self.desktop_open else 'storage' if self.storage_open else 'main')

    def open_desktop(self):
        try:
            self.desktop_config=desktop_settings(self.model.base)
            self.desktop_outputs=discover_outputs()
            self.desktop_open=True
            self.desktop_row=0
        except (OSError,ValueError) as error:self.toast(str(error))

    def desktop_action(self,action):
        if action=='back':
            self.desktop_open=False
        elif action in ('up','down'):
            self.desktop_row=(self.desktop_row+(1 if action=='down' else -1))%3
        elif action in ('ok','left','right'):
            if self.desktop_row==2:
                self.desktop_outputs=discover_outputs()
                return
            key='output' if self.desktop_row==0 else 'gpu'
            values=output_choices(self.desktop_outputs,self.desktop_config[key]) if key=='output' else ['auto','system','nvidia']
            value=values[(values.index(self.desktop_config[key])+(-1 if action=='left' else 1))%len(values)]
            candidate=dict(self.desktop_config,**{key:value})
            try:
                save_desktop_settings(self.model.base,candidate)
                self.desktop_config=candidate
            except (OSError,ValueError) as error:self.toast(str(error))

    def draw_desktop(self):
        self.text(tr('PARAMÈTRES WINDOWS PARTY'),416,161,28,width=960)
        self.text(tr('Réglages globaux · enregistrés automatiquement'),418,215,20,width=950)
        for index,title in enumerate((tr('Écran des jeux'),tr('GPU par défaut'),tr('ACTUALISER LES ÉCRANS'))):
            y=285+index*105
            focused=self.desktop_row==index
            self.box((410,y-12,986,90),(38,64,86) if focused else (25,33,50),(90,210,229) if focused else None)
            self.text(title,430,y,24,width=925)
            if index<2:
                value=(output_label(self.desktop_outputs,self.desktop_config['output']) if index==0
                       else label_value('gpu',self.desktop_config['gpu']))
                self.text('‹ '+value+' ›',445,y+39,20,(144,223,234),910)
        self.text(tr('Écran indisponible : repli sur un écran actif, choix conservé.'),418,630,20,width=950)
        self.text(tr('Reconnexion : placement des jeux réajusté automatiquement.'),418,672,20,width=950)
        self.text(tr('GPU appliqué au prochain lancement. Le GPU du jeu peut remplacer ce choix.'),418,714,16,width=950)
        self.text(tr('GPU du jeu sur Automatique : utiliser ce réglage global.'),418,750,16,width=950)

    def storage_job(self, task='scan'):
        if self.storage_future is not None:
            self.toast(tr('Analyse / nettoyage en cours…'))
            return
        if self.storage_pool is None:
            self.storage_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='party-storage')
        self.storage_task = task
        if task == 'launch':
            self.storage_future = self.storage_pool.submit(prepare_launch, self.model.base)
        elif task == 'scan':
            self.storage_future = self.storage_pool.submit(storage_snapshot, self.model.base)
        else:
            self.storage_future = self.storage_pool.submit(clean_storage, self.model.base, task == 'purge')

    def poll_storage(self):
        if self.storage_future is None or not self.storage_future.done():
            return
        future, task = self.storage_future, self.storage_task
        self.storage_future = None
        try:
            result = future.result()
            if task == 'launch':
                if self.launch_pending:
                    self.accepted = True
                    self.launch_requested = not self.single
                    self.running = False
                self.launch_pending = False
            elif task == 'scan':
                self.storage_result = result
            else:
                self.toast(tr('{p0} libérés · {p1} erreurs · sauvegardes conservées', p0=human(result['freed']), p1=len(result['errors'])))
                self.storage_job()
        except (OSError, ValueError, RuntimeError) as error:
            self.launch_pending = False
            if task == 'launch':
                self.launch_error = str(error)
            else:
                self.toast(str(error))

    def open_storage(self):
        try:
            self.storage_config = storage_settings(self.model.base)
        except (OSError, ValueError) as error:
            self.toast(str(error))
            return
        self.storage_open, self.storage_row, self.storage_page = True, 0, 0
        self.storage_job()

    def storage_action(self, action):
        if action == 'back':
            self.storage_open = False
            return
        if action in ('prev', 'next'):
            count = len(self.storage_result['games']) if self.storage_result else 0
            pages = max(1, (count + 2) // 3)
            self.storage_page = (self.storage_page + (1 if action == 'next' else -1)) % pages
        elif action in ('up', 'down'):
            self.storage_row = (self.storage_row + (1 if action == 'down' else -1)) % 8
        elif action in ('left', 'right', 'ok'):
            if self.storage_row >= 5:
                if action == 'ok':
                    self.storage_job(('clean', 'purge', 'scan')[self.storage_row-5])
                return
            key = ('auto_clean', 'cache_mib', 'logs_mib', 'reserve_mib', 'diagnostic')[self.storage_row]
            value = self.storage_config[key]
            def apply(value):
                candidate = dict(self.storage_config, **{key: value})
                save_storage_settings(self.model.base, candidate)
                self.storage_config = candidate
            try:
                if type(value) is bool:
                    apply(not value)
                elif action == 'ok':
                    def entered(text):
                        apply(int(text))
                    self.edit(tr('Valeur en Mio (0 = ') + (tr('seuil désactivé') if key == 'reserve_mib' else tr('aucune rétention')) + ')', value, entered)
                else:
                    step = {'cache_mib':256, 'logs_mib':32, 'reserve_mib':512}[key]
                    apply(max(0, min(1048576, value + (-step if action == 'left' else step))))
            except (OSError, ValueError) as error:
                self.toast(str(error))

    def draw_storage(self):
        self.text(tr('STOCKAGE WINDOWS PARTY'), 416, 161, 28, width=960)
        result = self.storage_result
        if result:
            self.text(tr('Occupé : ') + human(result['total']) + tr(' · hors jeux Windows d’origine'), 418, 204, 20, width=960)
            self.text(' · '.join(human(d['free']) + tr(' libres sur ') + d['path'] for d in result['disks']),
                      418, 237, 16, (159,213,227), 955)
            c = result['categories']
            self.text(tr('Persistant {p0} · Runtime {p1} · Installation {p2}', p0=human(c['persistent']), p1=human(c['runtime']), p2=human(c['installation'])),
                      418, 266, 16, width=955)
            self.text(tr('Caches {p0} · Journaux {p1}', p0=human(c['cache']), p1=human(c['logs'])), 418, 290, 16, width=955)
        else:
            self.text(tr('Analyse du disque en cours…'), 418, 221, 20, width=955)
        rows = [('auto_clean',tr('Entretien automatique')), ('cache_mib',tr('Caches cumulés (Mio)')),
                ('logs_mib',tr('Journaux cumulés (Mio)')), ('reserve_mib',tr('Espace libre avant lancement (Mio)')),
                ('diagnostic',tr('Diagnostic Proton détaillé'))]
        for index, (key, title) in enumerate(rows):
            y = 331+index*38
            focused = self.storage_row == index
            self.box((410,y-5,986,35), (38,64,86) if focused else (25,33,50), (90,210,229) if focused else None)
            self.text(title,430,y,20,width=640)
            value = self.storage_config[key]
            self.text('‹ ' + ((tr('Activé') if value else tr('Désactivé')) if type(value) is bool else str(value)) + ' ›',
                      1130,y,20,(144,223,234),240)
        for index, title in enumerate((tr('NETTOYER'), tr('VIDER LES CACHES'), tr('ACTUALISER'))):
            focused = self.storage_row == index+5
            self.box((416+index*327,533,314,40),(35,75,92), (134,236,238) if focused else None)
            self.text(title,430+index*327,543,16,width=290)
        self.text(tr('Sauvegardes, préfixes et réglages conservés. Limites appliquées hors jeu.'),418,588,16,width=960)
        if self.storage_future is not None:
            self.text(tr('Analyse en cours…') if self.storage_task == 'scan' else tr('Nettoyage en cours…'),418,614,16,(141,220,234),950)
        else:
            self.text(tr('JEUX PAR TAILLE · progression et réglages inclus dans « persistant »'),418,614,16,width=950)
        if result:
            for index, game in enumerate(result['games'][self.storage_page*3:self.storage_page*3+3]):
                y = 648+index*45
                self.text(game['name'],430,y,20,width=730)
                self.text(human(game['total']),1200,y,20,width=180)
                self.text(tr('Persistant {p0} · Runtime {p1} · Caches {p2} · Logs {p3}', p0=human(game['persistent']), p1=human(game['runtime']), p2=human(game['cache']), p3=human(game['logs'])),
                          430,y+25,16,(148,169,191),945)

    def volume(self, key):
        value = get(self.model.data, key)
        source = self.sm64_template_volumes if key.startswith('sm64coopdx.') else self.template_volumes
        return source[key.rsplit('.', 1)[-1]] if value == '' else value

    def slider(self, key, x, y, selected):
        value = self.volume(key)
        inherited = get(self.model.data, key) == ''
        draw = self.pg.draw
        draw.rect(self.canvas, (9,15,26), (x,y+15,260,10), border_radius=5)
        if value:
            draw.rect(self.canvas, (72,200,225) if selected else (78,124,153), (x,y+15,max(5,int(260*value/100)),10), border_radius=5)
        knob = x + int(260*value/100)
        draw.circle(self.canvas, (15,25,39), (knob,y+20), 12)
        draw.circle(self.canvas, (190,236,247) if selected else (136,164,192), (knob,y+20), 9, 2 if inherited else 0)
        self.text(f'{value} %', x+280, y+4, 20, (174,224,236), 95)
        if inherited:
            self.text('BASE' if key.startswith('sm64coopdx.') else 'JSON', x+365, y+8, 16, (129,153,182), 50)

    def edit(self, title, value, callback):
        self.keyboard = dict(title=title, value=str(value), row=0, col=0, shift=False, done=callback)
        self.pg.key.start_text_input()

    def finish_text(self):
        keyboard = self.keyboard
        try:
            keyboard['done'](keyboard['value'])
        except (ValueError, OSError) as error:
            self.toast(str(error))
            return
        self.keyboard = None
        self.pg.key.stop_text_input()

    def keyboard_action(self, action):
        k = self.keyboard
        if action == 'back':
            self.keyboard = None
            self.pg.key.stop_text_input()
            return
        if action == 'save':
            self.finish_text()
            return
        if action in ('up', 'down'):
            k['row'] = (k['row'] + (1 if action == 'down' else -1)) % len(self.keys)
            k['col'] = min(k['col'], len(self.keys[k['row']]) - 1)
        if action in ('left', 'right'):
            k['col'] = (k['col'] + (1 if action == 'right' else -1)) % len(self.keys[k['row']])
        if action == 'ok':
            key = self.keys[k['row']][k['col']]
            if key == 'Valider':
                self.finish_text()
            elif key == 'Maj':
                k['shift'] = not k['shift']
            elif key == 'Effacer':
                k['value'] = k['value'][:-1]
            elif key == 'Vider':
                k['value'] = ''
            else:
                k['value'] += ' ' if key == 'Espace' else key.upper() if k['shift'] else key

    def switch(self, callback):
        if self.model.data and self.model.dirty():
            self.pending = callback
            self.modal = tr('Modifications non enregistrées. Enregistrer avant de continuer ?')
        else:
            callback()

    def save(self):
        try:
            if self.model.data:
                self.model.save()
                self.library = self.model.rows.index(self.model.rom) if self.model.rom in self.model.rows else 0
                self.toast(tr('Profil enregistré · prêt pour le prochain lancement'))
                return True
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            self.toast(tr('Enregistrement impossible : ') + str(error))
        return False

    def launch(self):
        if self.storage_future is not None:
            self.toast(tr('Attendez la fin de l’analyse / du nettoyage.'))
            return
        if self.save():
            self.launch_pending = True
            self.storage_job('launch')

    def request_remove(self):
        recipe = recipe_for(self.model.rom,self.model.data.get('adapter'))
        self.removal = dict(name=self.model.rom.stem, common=recipe is not None)

    def confirm_remove(self):
        try:
            self.model.remove()
            self.library = self.model.rows.index(self.model.selected) if self.model.selected in self.model.rows else 0
            self.pane,self.tab,self.row = 'library',0,0
            self.removal = None
            if self.single:
                self.accepted,self.running = False,False
            self.toast(tr('Jeu retiré / dissocié. ROM et sauvegardes conservées. Actualisez les listes EmulationStation.'))
        except (OSError,ValueError,RuntimeError) as error:
            self.toast(str(error))

    def browse(self, directory=Path('/userdata/roms/windows')):
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError as error:
            self.toast(tr('Dossier inaccessible : ') + str(error))
            return
        self.browser = directory
        self.browser_rows = [directory.parent] + [p for p in children if p.is_dir() or p.suffix.lower() == '.wsquashfs']
        self.row = 0

    def select_game(self, rom):
        if not is_rom(rom):
            self.toast(tr('Choisissez un dossier .wine/.pc ou un fichier .wsquashfs existant.'))
            return
        self.model.select(rom, self.pending_common)
        self.pending_common = None
        self.pane, self.tab, self.row = 'settings', 0, 0

    def action(self, action):
        if self.launch_pending and action in ('back','quit'):
            self.launch_pending = False
            if action == 'back':
                self.poll_storage()
                self.toast(tr('Lancement annulé.'))
                return
        self.poll_storage()
        if self.launch_pending and action != 'quit':
            if action == 'back':
                self.launch_pending = False
                self.toast(tr('Lancement annulé.'))
            return
        if action == 'quit':
            self.launch_pending = False
            self.accepted = False
            self.keyboard = None
            self.pg.key.stop_text_input()
            self.browser, self.missing = None, None
            self.removal = None
            self.launch_requested = False
            self.switch(lambda: setattr(self, 'running', False))
            return
        if self.removal:
            if action == 'back':
                self.removal = None
            elif action == 'ok':
                self.confirm_remove()
            return
        if self.launch_error:
            if action in ('ok', 'back'):
                self.launch_error = None
            return
        if self.missing is not None:
            if action == 'ok':
                self.pending_common = self.missing
                self.missing = None
                self.browse(self.model.windows)
            elif action == 'back':
                self.missing = None
                self.toast(tr('Vous devez disposer du jeu avant d’utiliser ce profil commun.'))
            return
        if self.keyboard:
            self.keyboard_action(action)
            return
        if self.modal:
            if action == 'ok':
                if self.save():
                    self.modal = None
                    self.pending()
            elif action == 'search':
                self.modal = None
                self.pending()
            elif action == 'back':
                self.modal = None
            return
        if self.desktop_open:
            self.desktop_action(action)
            return
        if self.storage_open:
            self.storage_action(action)
            return
        if self.browser is not None:
            if action == 'back':
                self.browser = None
                self.row = 0
                if self.pending_common is not None:
                    self.pending_common = None
                    self.toast(tr('Ajout annulé : vous devez d’abord disposer du jeu.'))
            elif action in ('prev', 'next'):
                self.row = max(0, min(len(self.browser_rows)-1, self.row + (-9 if action == 'prev' else 9)))
            elif action in ('up', 'down'):
                self.row = (self.row + (1 if action == 'down' else -1)) % len(self.browser_rows)
            elif action == 'ok':
                path = self.browser_rows[self.row]
                if is_rom(path):
                    self.browser = None
                    self.select_game(path)
                else:
                    self.browse(path)
            return
        if action == 'add':
            self.switch(self.browse)
        elif action == 'save':
            if self.save() and self.model.rom and self.single:
                self.accepted, self.running = True, False
        elif action == 'search':
            self.edit('Rechercher un jeu', self.model.filter, self.search)
        elif action == 'back':
            if self.pane == 'settings' and not self.single:
                self.pane = 'library'
            else:
                self.switch(lambda: setattr(self, 'running', False))
        elif action in ('prev', 'next') and self.model.data:
            available = self.available_tabs()
            current = available.index(self.tab) if self.tab in available else 0
            self.tab = available[(current + (1 if action == 'next' else -1)) % len(available)]
            self.row, self.pane = 0, 'settings'
        elif self.pane == 'library':
            if action in ('up', 'down'):
                index = (self.library + (1 if action == 'down' else -1)) % (len(self.model.rows)+2)
                def select():
                    self.library = index
                    if index < len(self.model.rows):
                        self.model.select(self.model.rows[index])
                select() if index >= len(self.model.rows) else self.switch(select)
            elif action in ('ok', 'right'):
                if self.library == len(self.model.rows):
                    self.open_storage()
                elif self.library == len(self.model.rows)+1:
                    self.open_desktop()
                elif isinstance(self.model.selected, CommonGame):
                    self.missing = self.model.selected
                elif self.model.data:
                    if not is_rom(self.model.rom):
                        recipe = recipe_for(self.model.rom,self.model.data.get('adapter')) or recipe_for(self.model.rom)
                        if recipe:
                            self.missing = recipe
                        else:
                            self.toast(tr('Jeu introuvable : vous devez d’abord disposer du jeu. Start permet de choisir un autre jeu.'))
                    else:
                        self.pane, self.row = 'settings', 0
        elif self.model.data:
            rows = self.current_fields()
            if action in ('up', 'down'):
                self.row = (self.row + (1 if action == 'down' else -1)) % (len(rows)+3)
            elif action in ('left', 'right', 'ok'):
                if self.row >= len(rows):
                    if action == 'ok':
                        if self.row == len(rows):
                            self.launch()
                        elif self.row == len(rows)+1:
                            self.save()
                        else:
                            self.request_remove()
                    elif action in ('left','right'):
                        self.row = len(rows)+(self.row-len(rows)+(-1 if action=='left' else 1))%3
                    return
                key, title, choices = rows[self.row]
                value = get(self.model.data, key)
                if key == 'input' and not self.model.data.get('keyboard_player', True):
                    self.toast(tr('Clavier/souris réservé aux menus ; joueurs attribués aux manettes.'))
                    return
                if '.volumes.' in key:
                    if action == 'ok':
                        put(self.model.data, key, '')
                        self.toast(tr('Volume repris depuis la configuration commune') if key.startswith('sm64coopdx.') else tr('Volume repris depuis le JSON commun'))
                    else:
                        put(self.model.data, key, max(0, min(100, self.volume(key) + (-5 if action == 'left' else 5))))
                elif choices:
                    index = choices.index(value) if value in choices else 0
                    put(self.model.data, key, choices[(index + (-1 if action == 'left' else 1)) % len(choices)])
                    if key == 'keyboard_player' and not self.model.data[key]:
                        self.model.data['input'] = 'auto'
                        self.toast(tr('Joueurs sur manettes ; clavier/souris disponible dans la fenêtre active pour les menus.'))
                elif action == 'ok':
                    def update(text):
                        result = int(text) if (key in ('anchor.port','hkmp.port') or ('.volumes.' in key and text.strip())) else text
                        if '.volumes.' in key and text.strip() and not 0 <= result <= 100:
                            raise ValueError(tr('Volume : de 0 à 100 %, ou vide pour le JSON commun.'))
                        if key == 'anchor.port' and not 1024 < result < 65535:
                            raise ValueError(tr('Port : de 1025 à 65534.'))
                        if key == 'hkmp.port' and not 1024 <= result <= 65535:
                            raise ValueError(tr('Réglages Hollow Knight HKMP invalides.'))
                        put(self.model.data, key, result)
                    self.edit(title, value, update)

    def search(self, text):
        self.model.filter = text
        self.model.reload()
        self.library, self.pane = 0, 'library'

    def draw(self):
        self.poll_storage()
        if self.tab not in self.available_tabs():
            self.tab, self.row = 0, 0
        self.canvas.blit(self.background, (0,0))
        self.box((24, 22, 1392, 100), (23, 29, 46))
        self.text('WINDOWS PARTY', 52, 37, 36)
        self.text(tr('Votre bibliothèque · vos règles · votre partie'), 54, 84, 16, (152, 167, 191))
        if self.logo is not None:
            factor = min(260/self.logo.get_width(), 76/self.logo.get_height())
            self.canvas.blit(self.pg.transform.smoothscale(self.logo,
                             (int(self.logo.get_width()*factor), int(self.logo.get_height()*factor))), (1110, 35))
        else:
            self.text(tr('CONFIGURATEUR'), 1100, 60, 20, (117, 213, 230), 280)
        self.box((24, 142, 340, 652), (20, 25, 40), (76, 197, 219) if self.pane == 'library' and not self.storage_open and not self.desktop_open else None)
        self.text(tr('BIBLIOTHÈQUE'), 46, 163, 20, (122, 209, 229))
        start_label = control_label('add', self.input_mode)
        self.text(tr('{p0} jeux · {p1} : ajouter', p0=len(self.model.rows), p1=start_label), 46, 201, 16, (160, 174, 199))
        offset = max(0, min(self.library, len(self.model.rows)-1) - 7)
        for i, rom in enumerate(self.model.rows[offset:offset+9], offset):
            y = 246 + (i-offset)*50
            selected = self.model.selected == rom and self.library < len(self.model.rows)
            if selected:
                self.box((38, y-7, 312, 45), (35, 75, 94), (72, 202, 222))
            self.text(rom.stem, 50, y, 20, width=284)
        self.box((38,750,312,36), (35,75,94) if self.library == len(self.model.rows) else (29,39,55),
                 (72,202,222) if self.library == len(self.model.rows) else None)
        self.text(tr('STOCKAGE'),50,758,16,width=284)
        selected=self.library==len(self.model.rows)+1
        self.box((38,708,312,36),(35,75,94) if selected else (29,39,55),(72,202,222) if selected else None)
        self.text(tr('PARAMÈTRES'),50,716,16,width=284)
        self.box((386, 142, 1030, 652), (20, 25, 40), (76,197,219) if self.storage_open or self.desktop_open else None)
        if self.desktop_open:
            self.draw_desktop()
        elif self.storage_open:
            self.draw_storage()
        elif self.model.data:
            self.text(self.model.rom.stem, 416, 161, 28, width=950)
            self.text((tr('MODIFIÉ · non enregistré') if self.model.dirty() else tr('Profil prêt')) + '  ·  ' + self.model.rom.suffix,
                      418, 208, 16, (144, 160, 186))
            tab_width = min(241,970//len(self.available_tabs()))
            for position, i in enumerate(self.available_tabs()):
                if self.model.data.get('adapter') == 'sm64coopdx':
                    title = tr(('Session','Graphismes','Gameplay','Options','Son')[i])
                elif self.model.data.get('adapter') == 'hollowknight-hkmp':
                    title=tr(('Session','Réseau','Coop')[i])
                elif self.model.data.get('adapter') == 'nfsmw-lan':
                    title=tr(('Session','Réseau')[i])
                elif self.model.data.get('adapter') == 'l4d2-goldberg':
                    title = tr(('Session','Joueurs','Options')[i])
                else:
                    title = tr('Image') if i == 1 and self.model.data.get('adapter') == 'borderlands2' else tr(TABS[i])
                self.box((416+position*tab_width, 248, tab_width-13, 45), (41, 102, 127) if i == self.tab else (29, 36, 54))
                if i == self.tab:
                    self.pg.draw.line(self.canvas, (100,222,237), (430+position*tab_width,291), (416+(position+1)*tab_width-27,291), 3)
                self.text(title, 434+position*tab_width, 258, 20,width=tab_width-40)
            if self.tab:
                subtitle = (tr('Borderlands 2 · affichage automatique · VSync et PhysX indépendants') if self.model.data['adapter'] == 'borderlands2' else
                            tr('SoH / Anchor · réglages communs aux joueurs de cette session') if self.model.data['adapter'] == 'soh-anchor'
                            else tr('SoH / Anchor · activer ce profil dans Session pour appliquer ces réglages'))
                if self.model.data['adapter'] == 'borderlands2' and self.tab == 2:
                    subtitle = tr('Borderlands 2 · nom privé par joueur · vide : conserver le nom actuel')
                if self.model.data['adapter'] == 'sm64coopdx':
                    subtitle = tr('SM64CoopDX · configuration commune · réglages privés pour chaque joueur')
                if self.model.data['adapter'] == 'l4d2-goldberg':
                    subtitle = (tr('Sans bordure et résolution automatiques · langue : fichiers du jeu requis') if self.tab==2
                                else tr('Left 4 Dead 2 · Steam ID distincts et persistants · noms personnalisables'))
                if self.model.data['adapter']=='hollowknight-hkmp':
                    subtitle=tr('HKMP · écran automatique · chargez une partie, le réseau se connecte seul')
                if self.model.data['adapter']=='nfsmw-lan':
                    subtitle=(tr('LAN privé : J1 crée le serveur et le salon, J2 le rejoint · sans Internet')
                              if self.model.data.get('nfsmw',{}).get('private_lan',True) else
                              tr('Réseau partagé : connexion au LAN du PC'))
                self.text(subtitle, 418, 310, 16, (150, 169, 193), 950)
            rows = self.current_fields()
            offset = max(0, min(self.row, len(rows)-1) - 6)
            for i, (key, title, choices) in enumerate(rows[offset:offset+7], offset):
                y = 348+(i-offset)*57
                if i == self.row and self.pane == 'settings':
                    self.box((410, y-6, 986, 51), (41, 65, 91), (90, 210, 229))
                    self.pg.draw.rect(self.canvas, (118,224,241), (412,y+3,4,33), border_radius=2)
                self.text(title, 430, y+5, 20, width=500)
                if '.volumes.' in key:
                    self.slider(key, 958, y, i == self.row and self.pane == 'settings')
                else:
                    value = label_value(key, get(self.model.data, key))
                    if key == 'input' and not self.model.data.get('keyboard_player', True):
                        value = tr('Manettes uniquement')
                    if choices:
                        self.text('‹ ' + value + ' ›', 958, y+5, 20, (144, 223, 234), 416)
                    else:
                        focused = i == self.row and self.pane == 'settings'
                        self.box((946, y-1, 433, 42), (34, 47, 65),
                                 (99, 203, 219) if focused else (63, 83, 107))
                        self.text(value, 961, y+6, 20, (221, 236, 243), 400)
            remove_label = tr('DISSOCIER LE JEU') if recipe_for(self.model.rom,self.model.data.get('adapter')) else tr('RETIRER LE JEU')
            for i, label in enumerate((tr('LANCER LA PARTIE'), tr('ENREGISTRER'), remove_label)):
                active = self.pane == 'settings' and self.row == len(rows)+i
                self.box((416+i*327, 750, 314, 36), (35,93,108) if i == 0 else (39,46,66),
                         (134,236,238) if active else None)
                self.text(label, 430+i*327, 757, 16, width=290)
        else:
            if isinstance(self.model.selected, CommonGame):
                self.text(tr(self.model.selected.name), 430, 365, 28, width=900)
                self.text(tr('Profil prêt · le jeu doit être présent sur votre Batocera.'), 430, 420, 20, width=900)
                self.text(tr('Choisissez le jeu pour préparer votre session.'), 430, 470, 20, width=900)
            else:
                self.text(tr('Préparez votre première partie'), 430, 365, 36, width=900)
                self.text(start_label + tr(' : choisir un jeu .wine, .pc ou .wsquashfs'), 430, 430, 24, width=900)
        self.box((24,805,1392,80), (20,27,43))
        context = self.help_context()
        hints = context_hints(context, self.input_mode, len(self.available_tabs()) > 1)
        spacing = min(380, 1350 // len(hints))
        for i, (action, label) in enumerate(hints):
            self.hint(action, label, 45+i*spacing, 815, width=spacing-12)
        volume_selected = (self.model.data and self.browser is None and self.pane == 'settings'
                           and self.row < len(self.current_fields()) and '.volumes.' in self.current_fields()[self.row][0])
        navigation = tr('Flèches : naviguer') if self.input_mode == 'keyboard' else tr('Croix directionnelle / stick : naviguer')
        quit_hint = tr('Échap : retour / quitter') if self.input_mode == 'keyboard' else 'HK + ' + control_label('add', self.input_mode) + tr(' : quitter')
        subtitle = (tr('Gauche / droite : volume par pas de 5 % · ') + control_label('ok', self.input_mode) + tr(' : valeur JSON commun') if volume_selected and context == 'main'
                    else navigation + ' · ' + quit_hint)
        if volume_selected and context == 'main' and self.model.data.get('adapter') == 'sm64coopdx':
            subtitle = tr('Gauche / droite : volume par pas de 5 % · ') + control_label('ok',self.input_mode) + tr(' : valeur de la configuration commune')
        if context in ('confirm','missing','remove'):
            subtitle = ''
        elif context == 'browser':
            subtitle = navigation
        elif context == 'desktop':
            subtitle=tr('Gauche / droite : choisir · réglages enregistrés automatiquement')
        elif context == 'storage':
            subtitle = tr('Gauche / droite : ajuster · ') + control_label('ok', self.input_mode) + tr(' : saisir / exécuter · réglages enregistrés automatiquement')
        if context == 'keyboard':
            subtitle = tr('Saisie directe au clavier · Retour arrière : effacer') if self.input_mode == 'keyboard' else tr('Maj, espace, effacement et caractères spéciaux sur le clavier virtuel')
        self.text(subtitle,
                  45,858,16,(151,171,195),1320)
        if self.browser is not None:
            self.box((160, 150, 1120, 640), (25, 34, 52), (91, 207, 228))
            self.text(tr('CHOISIR UN JEU'), 195, 175, 28)
            self.text(self.browser, 195, 225, 16, width=1040)
            self.text(f'{self.row+1} / {len(self.browser_rows)}', 195, 250, 16, width=1040)
            offset = max(0, self.row-8)
            for i, path in enumerate(self.browser_rows[offset:offset+9], offset):
                y = 278+(i-offset)*50
                if i == self.row:
                    self.box((180, y-4, 1080, 45), (39, 80, 103))
                self.text(tr('.. / retour au dossier parent') if i == 0 else path.name + (' /' if path.is_dir() else ''), 200, y, 20, width=1030)
        if self.keyboard:
            k = self.keyboard
            self.box((200, 180, 1040, 600), (25, 34, 52), (91, 207, 228))
            self.text(k['title'], 230, 198, 28, width=980)
            self.box((224, 250, 992, 60), (12, 19, 33))
            self.text(k['value'][-55:] + '│', 240, 263, 24, width=950)
            for r, keys in enumerate(self.keys):
                cell = 970 // len(keys)
                row_height = 360 // len(self.keys)
                for c, key in enumerate(keys):
                    rect = (235+c*cell, 334+r*row_height, cell-7, row_height-6)
                    self.box(rect, (47, 118, 144) if (r,c) == (k['row'],k['col']) else (38, 47, 66))
                    self.text(key.upper() if k['shift'] and len(key)==1 else tr(key), rect[0]+9, rect[1]+14, 20, width=cell-17)
        if self.modal:
            self.box((230, 340, 980, 210), (36, 45, 65), (100, 213, 230))
            self.text(self.modal, 255, 368, 24, width=920)
        if self.missing is not None:
            self.box((210,310,1020,250), (36,45,65), (100,213,230))
            self.text(tr('Plusieurs versions détectées') if len(self.missing.matches)>1 else tr('Choisir le fichier du jeu') if self.missing.matches else tr('Jeu non détecté dans Windows'), 240,340,28,width=950)
            self.text(tr('Vous devez disposer du jeu pour utiliser ce profil commun.'),240,395,20,width=950)
        if self.removal:
            self.box((190,295,1060,305), (36,45,65), (244,164,128))
            self.text(tr('DISSOCIER CE JEU ?') if self.removal['common'] else tr('RETIRER CE JEU DE WINDOWS PARTY ?'),220,325,28,width=1000)
            self.text(self.removal['name'],220,380,24,width=1000)
            self.text(tr('Le profil commun et vos options resteront disponibles.') if self.removal['common'] else tr('Le lanceur et ses options Windows Party seront retirés.'),220,445,20,width=1000)
            self.text(tr('Le jeu d’origine et toutes ses sauvegardes seront conservés.'),220,495,20,width=1000)
        if self.launch_pending:
            self.box((230,340,980,210), (36,45,65), (100,213,230))
            self.text(tr('PRÉPARATION DE LA PARTIE'),255,368,28,width=920)
            self.text(tr('Vérification de l’espace libre et entretien du stockage…'),255,425,20,width=920)
            self.text(control_label('back',self.input_mode) + tr(' : annuler'),255,480,16,width=920)
        if self.launch_error:
            self.box((190,280,1060,360), (36,45,65), (244,164,128))
            self.text(tr('LANCEMENT INTERROMPU'),220,308,28,width=1000)
            for index, line in enumerate(textwrap.wrap(self.launch_error, width=85)[:6]):
                self.text(line,220,365+index*34,20,width=1000)
        if time.monotonic() < self.notice_until:
            self.box((100, 743, 1240, 57), (48, 73, 91))
            self.text(self.notice, 120, 759, 20, width=1200)
        target = self.screen.get_rect()
        size = self.canvas.get_size()
        scale = min(target.width/size[0], target.height/size[1])
        surface = self.pg.transform.smoothscale(self.canvas, (int(size[0]*scale), int(size[1]*scale)))
        self.screen.fill((8, 10, 18))
        self.screen.blit(surface, surface.get_rect(center=target.center))
        self.pg.display.flip()

    def run(self, single=False):
        self.single = single
        keymap = {self.pg.K_UP:'up', self.pg.K_DOWN:'down', self.pg.K_LEFT:'left', self.pg.K_RIGHT:'right',
                  self.pg.K_RETURN:'ok', self.pg.K_ESCAPE:'back', self.pg.K_F2:'save', self.pg.K_F3:'search',
                  self.pg.K_INSERT:'add', self.pg.K_PAGEUP:'prev', self.pg.K_PAGEDOWN:'next'}
        try:
            while self.running:
                for event in self.pg.event.get():
                    if event.type == self.pg.QUIT:
                        self.action('back')
                    elif event.type in (self.pg.JOYDEVICEADDED, self.pg.JOYDEVICEREMOVED):
                        self.pads.refresh()
                        if not self.pads.devices:
                            self.input_mode = 'keyboard'
                    elif event.type == self.pg.TEXTINPUT and self.keyboard:
                        self.input_mode = 'keyboard'
                        self.keyboard['value'] += event.text
                    elif event.type == self.pg.KEYDOWN:
                        self.input_mode = 'keyboard'
                        if self.keyboard and event.key == self.pg.K_BACKSPACE:
                            self.keyboard['value'] = self.keyboard['value'][:-1]
                        elif self.keyboard and event.key == self.pg.K_RETURN:
                            self.finish_text()
                        elif event.key in keymap:
                            self.action(keymap[event.key])
                for action in self.pads.poll(repeat_pages=self.help_context()=='browser'):
                    self.input_mode = self.pads.family
                    self.action(action)
                self.draw()
                self.clock.tick(60)
        finally:
            self.pg.quit()
            if self.storage_pool is not None:
                self.storage_pool.shutdown(wait=False, cancel_futures=True)
        return self.accepted


def configure(base, rom=None, single=False):
    try:
        app = App(base, rom)
        accepted = app.run(single)
        if app.launch_requested:
            data = app.model.data
            launcher = str(Path(base) / 'windows-party')
            os.execv(launcher, [launcher, 'party', str(app.model.rom), data['players'], data['split'], data['input']])
        return accepted
    except ImportError as error:
        raise RuntimeError(tr('Pygame 2 est requis pour le configurateur à la manette. '
                           'Ancienne interface : PARTYDECK_UI=legacy windows-party configurer')) from error
