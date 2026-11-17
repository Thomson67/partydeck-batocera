"""Windows Party's controller-first configurator. Original Pygame implementation."""
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

from partydeck_profiles import (defaults, read_profile, save_profile, profile_path,
                               validate, ROM_TYPES)
from partydeck_anchor import defaults as anchor_defaults, graphics_defaults, VOLUME_FIELDS

TABS = ['Session', 'Réseau', 'Joueurs', 'Image & son']
KEYS = [list('azertyuiop'), list('qsdfghjklm'), list('wxcvbn0123'),
        list('456789 .-_'), list('@:/\\!?éèàç'), list('[]()#&+=$%'),
        list("'\";<>^~{}|"), ['Maj', 'Espace', 'Effacer', 'Vider', 'Valider']]


def fields(tab):
    if tab == 0:
        return [('players', 'Joueurs', ['auto', '1', '2', '3', '4']),
                ('split', 'Partage de l’écran', ['horizontal', 'vertical']),
                ('input', 'Attribution des contrôles', ['auto', 'clavier-j1', 'clavier-j2']),
                ('configure_before_launch', 'Configurer avant chaque lancement', [False, True]),
                ('adapter', 'Profil du jeu', ['standard', 'soh-anchor'])]
    if tab == 1:
        return [('anchor.enabled', 'Connexion automatique Anchor', [False, True]),
                ('anchor.room', 'Room ID commun', None), ('anchor.host', 'Serveur', None),
                ('anchor.port', 'Port', None), ('anchor.config', 'Chemin du JSON SoH', None),
                ('anchor.pvp', 'PvP', [0, 1, 2]), ('anchor.locations', 'Positions visibles', [0, 1, 2]),
                ('anchor.teleport', 'Téléportation', [0, 1, 2]), ('anchor.sync', 'Objets et progression partagés', [False, True])]
    if tab == 2:
        return [(f'anchor.{key}.{i}', f'J{i+1} · {label}', None)
                for i in range(4) for key, label in [('names', 'Nom'), ('teams', 'Équipe')]]
    return [('anchor.graphics.internal_resolution', 'Résolution interne', [.5, .75, 1., 1.25, 1.5, 1.75, 2.]),
            ('anchor.graphics.msaa', 'Anti-aliasing MSAA', list(range(1, 9))),
            ('anchor.graphics.vsync', 'VSync', [False, True]),
            ('anchor.graphics.texture_filter', 'Filtre des textures', [0, 1, 2]),
            ('anchor.graphics.music_j1_only', 'Musique uniquement pour J1', [False, True]),
            *[(f'anchor.graphics.volumes.{key}', label + ' (%)', None) for key, label in VOLUME_FIELDS]]


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
    if type(value) is bool:
        return 'Activé' if value else 'Désactivé'
    if key == 'adapter':
        return {'standard': 'Standard', 'soh-anchor': 'SoH / Anchor'}.get(value, value)
    if key in ('anchor.locations', 'anchor.teleport'):
        return ['Personne', 'Même équipe', 'Tous'][value]
    if key == 'anchor.pvp':
        return ['Désactivé', 'Activé', 'Avec tirs alliés'][value]
    if key.endswith('texture_filter'):
        return ['Trois points N64', 'Linéaire', 'Aucun'][value]
    return str(value) if value != '' else 'JSON commun'


class Model:
    def __init__(self, base, rom=None):
        self.base, self.rom = Path(base), rom
        self.data = None
        self.saved = None
        self.rows = []
        self.filter = ''
        self.reload()
        if rom is not None:
            self.select(Path(rom))

    def reload(self):
        self.rows = []
        for path in sorted((self.base / 'profiles').glob('*.json')):
            data = json.loads(path.read_text())
            rom = Path(data['rom'])
            validate(data, rom)
            if self.filter.casefold() in rom.stem.casefold():
                self.rows.append(rom)
        self.rows.sort(key=lambda p: p.stem.casefold())

    def select(self, rom):
        self.rom = rom
        self.data = read_profile(self.base, rom) if profile_path(self.base, rom).exists() else defaults(rom)
        self.data.setdefault('adapter', 'standard')
        self.data.setdefault('anchor', anchor_defaults())
        self.data['anchor'].setdefault('graphics', graphics_defaults())
        self.saved = copy.deepcopy(self.data)

    def dirty(self):
        # Defaults displayed by the UI do not by themselves count as an edit.
        return self.saved != self.data

    def save(self):
        validate(self.data, self.rom)
        old = profile_path(self.base, self.rom)
        previous = old.read_bytes() if old.exists() else None
        save_profile(self.base, self.rom, self.data)
        try:
            subprocess.run([str(self.base / 'partydeck-test'), 'ajouter', str(self.rom),
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


class Pads:
    """SDL standardized mappings, with ES mappings for unrecognized devices."""
    def __init__(self, pg):
        self.pg, self.devices = pg, []
        self.previous = set()
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
        cfg = Path('/userdata/system/configs/emulationstation/es_input.cfg')
        try:
            configs = ET.parse(cfg).findall('inputConfig') if cfg.exists() else []
        except ET.ParseError:
            configs = []
        for i in range(self.pg.joystick.get_count()):
            if self.controllers and self.controllers.is_controller(i):
                self.devices.append(('sdl', self.controllers.Controller(i), {}))
            else:
                stick = self.pg.joystick.Joystick(i)
                stick.init()
                profile = next((c for c in configs if c.get('deviceGUID', '').lower() == stick.get_guid().lower()), None)
                mapping = {n.get('name'): n.attrib for n in profile} if profile is not None else {}
                self.devices.append(('es', stick, mapping))
        self.previous.clear()

    def poll(self):
        held = set()
        for kind, pad, mapping in self.devices:
            try:
                if kind == 'sdl':
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
            except (self.pg.error, IndexError):
                continue
        now = time.monotonic()
        actions = []
        for action in held:
            if action not in self.previous:
                actions.append(action)
                self.timers[action] = now + .35
            elif action in ('up', 'down', 'left', 'right') and now >= self.timers.get(action, now):
                actions.append(action)
                self.timers[action] = now + .12
        self.previous = held
        return actions


class App:
    def __init__(self, base, rom=None, windowed=False):
        import pygame as pg
        self.pg = pg
        pg.display.init()
        pg.font.init()
        pg.joystick.init()
        self.screen = pg.display.set_mode((1280, 800) if windowed else (0, 0), 0 if windowed else pg.FULLSCREEN)
        pg.display.set_caption('Windows Party · Configurateur')
        pg.mouse.set_visible(False)
        self.canvas = pg.Surface((1440, 900))
        self.fonts = {s: pg.font.SysFont('DejaVu Sans', s) for s in (16, 20, 24, 28, 36)}
        self.clock = pg.time.Clock()
        self.model = Model(base, rom)
        self.pads = Pads(pg)
        self.library = 0
        self.tab, self.row, self.pane = 0, 0, 'settings' if rom else 'library'
        self.running, self.accepted = True, False
        self.single = False
        self.keyboard = None
        self.modal = None
        self.notice, self.notice_until = '', 0
        self.browser = None
        self.browser_rows = []
        self.pending = None
        self.logo = None
        logo = Path(base) / 'assets/windows-party.png'
        if logo.exists():
            self.logo = pg.image.load(str(logo)).convert_alpha()
        if rom is None and self.model.rows:
            self.model.select(self.model.rows[0])

    def toast(self, text):
        self.notice, self.notice_until = text, time.monotonic() + 5

    def text(self, value, x, y, size=24, color=(228, 234, 247), width=1000):
        font = self.fonts[size]
        value = str(value)
        while value and font.size(value)[0] > width:
            value = value[:-2] + '…' if len(value) > 2 else ''
        self.canvas.blit(font.render(value, True, color), (x, y))

    def box(self, rect, color, border=None):
        self.pg.draw.rect(self.canvas, color, rect, border_radius=12)
        if border:
            self.pg.draw.rect(self.canvas, border, rect, 2, border_radius=12)

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
            k['row'] = (k['row'] + (1 if action == 'down' else -1)) % len(KEYS)
            k['col'] = min(k['col'], len(KEYS[k['row']]) - 1)
        if action in ('left', 'right'):
            k['col'] = (k['col'] + (1 if action == 'right' else -1)) % len(KEYS[k['row']])
        if action == 'ok':
            key = KEYS[k['row']][k['col']]
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
            self.modal = 'Modifications non enregistrées. Enregistrer avant de continuer ?'
        else:
            callback()

    def save(self):
        try:
            if self.model.data:
                self.model.save()
                self.toast('Profil enregistré · prêt pour le prochain lancement')
                return True
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            self.toast('Enregistrement impossible : ' + str(error))
        return False

    def browse(self, directory=Path('/userdata/roms/windows')):
        try:
            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
        except OSError as error:
            self.toast('Dossier inaccessible : ' + str(error))
            return
        self.browser = directory
        self.browser_rows = [directory.parent] + [p for p in children if p.is_dir() or p.suffix.lower() == '.wsquashfs']
        self.row = 0

    def select_game(self, rom):
        self.model.select(rom)
        self.pane, self.tab, self.row = 'settings', 0, 0

    def action(self, action):
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
        if self.browser is not None:
            if action == 'back':
                self.browser = None
                self.row = 0
            elif action in ('up', 'down'):
                self.row = (self.row + (1 if action == 'down' else -1)) % len(self.browser_rows)
            elif action == 'ok':
                path = self.browser_rows[self.row]
                if path.suffix.lower() in ROM_TYPES and ((path.is_dir() and path.suffix.lower() != '.wsquashfs') or path.is_file()):
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
            self.tab = (self.tab + (1 if action == 'next' else -1)) % len(TABS)
            self.row, self.pane = 0, 'settings'
        elif self.pane == 'library':
            if action in ('up', 'down') and self.model.rows:
                index = (self.library + (1 if action == 'down' else -1)) % len(self.model.rows)
                def select():
                    self.library = index
                    self.model.select(self.model.rows[index])
                self.switch(select)
            elif action in ('ok', 'right') and self.model.data:
                self.pane, self.row = 'settings', 0
        elif self.model.data:
            rows = fields(self.tab)
            if action in ('up', 'down'):
                self.row = (self.row + (1 if action == 'down' else -1)) % len(rows)
            elif action in ('left', 'right', 'ok'):
                key, title, choices = rows[self.row]
                value = get(self.model.data, key)
                if choices:
                    index = choices.index(value) if value in choices else 0
                    put(self.model.data, key, choices[(index + (-1 if action == 'left' else 1)) % len(choices)])
                elif action == 'ok':
                    def update(text):
                        result = int(text) if (key == 'anchor.port' or ('.volumes.' in key and text.strip())) else text
                        if '.volumes.' in key and text.strip() and not 0 <= result <= 100:
                            raise ValueError('Volume : de 0 à 100 %, ou vide pour le JSON commun.')
                        if key == 'anchor.port' and not 1024 < result < 65535:
                            raise ValueError('Port : de 1025 à 65534.')
                        put(self.model.data, key, result)
                    self.edit(title, value, update)

    def search(self, text):
        self.model.filter = text
        self.model.reload()
        self.library, self.pane = 0, 'library'

    def draw(self):
        self.canvas.fill((12, 16, 27))
        self.box((24, 22, 1392, 100), (23, 29, 46))
        self.text('WINDOWS PARTY', 52, 37, 36)
        self.text('Votre bibliothèque · vos règles · votre partie', 54, 84, 16, (152, 167, 191))
        if self.logo is not None:
            factor = min(260/self.logo.get_width(), 76/self.logo.get_height())
            self.canvas.blit(self.pg.transform.smoothscale(self.logo,
                             (int(self.logo.get_width()*factor), int(self.logo.get_height()*factor))), (1110, 35))
        else:
            self.text('CONFIGURATEUR', 1100, 60, 20, (117, 213, 230), 280)
        self.box((24, 142, 340, 652), (20, 25, 40), (76, 197, 219) if self.pane == 'library' else None)
        self.text('BIBLIOTHÈQUE', 46, 163, 20, (122, 209, 229))
        self.text(f'{len(self.model.rows)} jeux · Start : ajouter', 46, 201, 16, (160, 174, 199))
        offset = max(0, self.library - 8)
        for i, rom in enumerate(self.model.rows[offset:offset+10], offset):
            y = 246 + (i-offset)*50
            selected = self.model.rom == rom
            if selected:
                self.box((38, y-7, 312, 45), (35, 75, 94), (72, 202, 222))
            self.text(rom.stem, 50, y, 20, width=284)
        self.box((386, 142, 1030, 652), (20, 25, 40))
        if self.model.data:
            self.text(self.model.rom.stem, 416, 161, 28, width=950)
            self.text(('MODIFIÉ · non enregistré' if self.model.dirty() else 'Profil prêt') + '  ·  ' + self.model.rom.suffix,
                      418, 208, 16, (144, 160, 186))
            for i, title in enumerate(TABS):
                self.box((416+i*241, 248, 228, 45), (41, 102, 127) if i == self.tab else (29, 36, 54))
                self.text(title, 434+i*241, 258, 20)
            if self.tab:
                self.text('SoH / Anchor · activer ce profil dans Session pour appliquer ces réglages', 418, 310, 16, (150, 169, 193), 950)
            rows = fields(self.tab)
            offset = max(0, self.row - 6)
            for i, (key, title, choices) in enumerate(rows[offset:offset+7], offset):
                y = 348+(i-offset)*57
                if i == self.row and self.pane == 'settings':
                    self.box((410, y-6, 986, 51), (41, 65, 91), (90, 210, 229))
                self.text(title, 430, y+5, 20, width=500)
                value = label_value(key, get(self.model.data, key))
                self.text(('‹ ' + value + ' ›') if choices else value + '  ✎', 958, y+5, 20, (144, 223, 234), 416)
        else:
            self.text('Préparez votre première partie', 430, 365, 36, width=900)
            self.text('Start : choisir un jeu .wine, .pc ou .wsquashfs', 430, 430, 24, width=900)
        self.text('Croix/A : choisir   Cercle/B : retour   Carré/X : enregistrer   Triangle/Y : rechercher', 40, 817, 20, width=1370)
        self.text('LB/RB : onglet   Start : ajouter   Croix directionnelle / stick : naviguer', 40, 855, 20, (137, 158, 185), 1370)
        if self.browser is not None:
            self.box((160, 150, 1120, 640), (25, 34, 52), (91, 207, 228))
            self.text('CHOISIR UN JEU', 195, 175, 28)
            self.text(self.browser, 195, 225, 16, width=1040)
            offset = max(0, self.row-8)
            for i, path in enumerate(self.browser_rows[offset:offset+9], offset):
                y = 278+(i-offset)*50
                if i == self.row:
                    self.box((180, y-4, 1080, 45), (39, 80, 103))
                self.text('.. / retour au dossier parent' if i == 0 else path.name + (' /' if path.is_dir() else ''), 200, y, 20, width=1030)
        if self.keyboard:
            k = self.keyboard
            self.box((200, 180, 1040, 600), (25, 34, 52), (91, 207, 228))
            self.text(k['title'], 230, 198, 28, width=980)
            self.box((224, 250, 992, 60), (12, 19, 33))
            self.text(k['value'][-55:] + '│', 240, 263, 24, width=950)
            for r, keys in enumerate(KEYS):
                cell = 970 // len(keys)
                row_height = 360 // len(KEYS)
                for c, key in enumerate(keys):
                    rect = (235+c*cell, 334+r*row_height, cell-7, row_height-6)
                    self.box(rect, (47, 118, 144) if (r,c) == (k['row'],k['col']) else (38, 47, 66))
                    self.text(key.upper() if k['shift'] and len(key)==1 else key, rect[0]+9, rect[1]+14, 20, width=cell-17)
            self.text('A/Croix : saisir · X/Carré : valider · B/Cercle : annuler', 240, 719, 20, width=950)
        if self.modal:
            self.box((230, 340, 980, 210), (36, 45, 65), (100, 213, 230))
            self.text(self.modal, 255, 368, 24, width=920)
            self.text('A : enregistrer   Y : abandonner les modifications   B : annuler', 255, 455, 20, width=920)
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
                    elif event.type == self.pg.TEXTINPUT and self.keyboard:
                        self.keyboard['value'] += event.text
                    elif event.type == self.pg.KEYDOWN:
                        if self.keyboard and event.key == self.pg.K_BACKSPACE:
                            self.keyboard['value'] = self.keyboard['value'][:-1]
                        elif self.keyboard and event.key == self.pg.K_RETURN:
                            self.finish_text()
                        elif event.key in keymap:
                            self.action(keymap[event.key])
                for action in self.pads.poll():
                    self.action(action)
                self.draw()
                self.clock.tick(60)
        finally:
            self.pg.quit()
        return self.accepted


def configure(base, rom=None, single=False):
    try:
        return App(base, rom).run(single)
    except ImportError as error:
        raise RuntimeError('Pygame 2 est requis pour le configurateur à la manette. '
                           'Ancienne interface : PARTYDECK_UI=legacy partydeck-test configurer') from error
