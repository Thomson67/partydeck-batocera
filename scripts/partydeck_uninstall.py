"""Uninstall owned Windows Party files; retain saves and private Wine state."""
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET
from partydeck_i18n import tr
from partydeck_storage import ensure_idle, mounted_paths


@dataclass(frozen=True)
class Layout:
    userdata: Path = Path('/userdata')

    @property
    def base(self): return self.userdata / 'system/windows-party'
    @property
    def legacy(self): return self.userdata / 'system/partydeck-test'
    @property
    def saves(self): return self.userdata / 'saves/windows-party'
    @property
    def bottles(self): return self.userdata / 'system/wine-bottles/windows-party'
    @property
    def roms(self): return self.userdata / 'roms/windows-party'
    @property
    def ports(self): return self.userdata / 'roms/ports'
    @property
    def config(self): return self.userdata / 'system/configs/emulationstation'
    @property
    def backup(self): return self.saves / '.uninstall-preserved'


def _plain(path):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise RuntimeError(tr('Désinstallation refusée : chemin redirigé ({p0}).', p0=path))
    return path


def _owned_launcher(path, layout):
    if path.is_symlink() or not path.is_file(): return False
    lines = path.read_text(errors='replace').splitlines()
    if len(lines) != 3 or lines[0] not in ('#!/bin/bash', '#!/usr/bin/env bash'): return False
    if lines[1] not in ('# Entrée gérée par PartyDeck Wine', '# Configuration gérée par Windows Party',
                        '# Entrée gérée par partydeck-test', 'export PARTYDECK_NFSMW_PRIVATE_LAN=1'):
        return False
    try: command = shlex.split(lines[2])
    except ValueError: return False
    commands = {str(root / name) for root in (layout.base, layout.legacy)
                for name in ('windows-party', 'partydeck', 'partydeck-test')}
    return (len(command) >= 3 and command[0] == 'exec' and command[1] in commands
            and command[2] in ('configurer', 'profil', 'party', 'coop', 'jouer'))


def _xml_edit(path, removed_scripts, layout, systems=False):
    if not path.is_file(): return None
    _plain(path)
    before = path.read_bytes()
    root = ET.fromstring(before, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    changed = False
    for node in list(root):
        if systems:
            owned = (node.tag == 'system' and node.findtext('name') in ('windows-party', 'partydeck-test')
                     and node.findtext('path') in (str(layout.roms), str(layout.userdata / 'roms/partydeck-test')))
        else:
            value = node.findtext('path') if node.tag == 'game' else None
            owned = value and Path(os.path.abspath(path.parent / value)) in removed_scripts
        if owned:
            root.remove(node); changed = True
    if not changed: return None
    elements = [n for n in root if isinstance(n.tag, str)]
    # Never remove the user's shared system/Ports configuration file itself.
    dedicated = path.parent == layout.roms or path.name in ('es_systems_windows-party.cfg', 'es_systems_partydeck-test.cfg')
    after = None if not elements and dedicated else ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return dict(path=path, before=before, after=after)


def plan(layout=Layout(), mounts=None):
    mounts = mounted_paths() if mounts is None else mounts
    roots = [p for p in (layout.base, layout.legacy) if p.exists() or p.is_symlink()]
    for path in (layout.saves, layout.bottles, layout.roms, layout.ports, layout.config): _plain(path)
    for root in roots:
        if root.is_symlink():
            if root != layout.legacy or root.resolve() != layout.base.resolve():
                raise RuntimeError(tr('Désinstallation refusée : chemin redirigé ({p0}).', p0=root))
        else: _plain(root)
    for root in (*roots, layout.bottles, layout.roms):
        if any(m == root or root in m.parents for m in mounts):
            raise RuntimeError(tr('Dossier encore monté ; désinstallation refusée : {p0}', p0=root))

    removed = []
    for folder in (layout.roms, layout.ports):
        if folder.is_dir():
            removed.extend(p for p in folder.glob('*.sh') if _owned_launcher(p, layout))
    edits = []
    for folder in (layout.roms, layout.ports):
        edit = _xml_edit(folder / 'gamelist.xml', set(removed), layout)
        if edit: edits.append(edit)
    for name in ('es_systems_windows-party.cfg', 'es_systems_partydeck-test.cfg', 'es_systems.cfg'):
        edit = _xml_edit(layout.config / name, set(), layout, systems=True)
        if edit: edits.append(edit)
    settings = layout.config / 'es_settings.cfg'
    if settings.is_file():
        _plain(settings)
        before = settings.read_bytes()
        root = ET.fromstring(before)
        for node in list(root):
            if node.get('name', '').startswith(('windows-party.', 'partydeck-test.')):
                root.remove(node)
        after = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        if len(ET.fromstring(before)) != len(root): edits.append(dict(path=settings, before=before, after=after))
    theme = layout.roms / 'theme.xml'
    if theme.is_file() and not theme.is_symlink() and 'Logo géré par Windows Party' in theme.read_text(): removed.append(theme)
    # Metadata backups and locks are generated, not the Windows source media.
    for name in ('gamelist.xml.partydeck-before', '.partydeck-metadata.lock'):
        path = layout.roms / name
        if path.is_file() and not path.is_symlink(): removed.append(path)
    for name in ('media', 'images', 'videos', 'manuals'):
        path = layout.roms / name
        if path.exists() or path.is_symlink(): removed.append(path)

    preserve = []
    for root in roots:
        if root.is_symlink(): continue
        # Unknown game data is not classified as cache. This also preserves old
        # test prefixes and identity files inside a game/content overlay.
        technical = {'releases', 'cache', 'logs', 'profiles', 'detached-profiles',
                     'templates', 'assets', 'plugins', '__pycache__'}
        for source in root.iterdir():
            name = source.name
            if name in technical: continue
            if source.is_dir() and not source.is_symlink():
                preserve.append((source, Path('state') / root.name / name))
    players = layout.bottles / 'players'
    if players.is_dir():
        _plain(players)
        preserve.append((players, Path('bottles/players')))
    return dict(roots=roots, remove=removed, edits=edits, preserve=preserve)


def _write_edit(edit):
    path, after = edit['path'], edit['after']
    if path.read_bytes() != edit['before']:
        raise RuntimeError(tr('Configuration modifiée pendant la désinstallation : {p0}', p0=path))
    if after is None: path.unlink(); return
    mode = path.stat().st_mode & 0o777
    fd, temporary = tempfile.mkstemp(prefix='.partydeck-uninstall-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(after); stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, mode); os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def execute(layout=Layout()):
    """No deletion until locks, mounts, XML and preservation destinations pass."""
    with ExitStack() as locks:
        seen = set()
        for root in (layout.base, layout.legacy):
            if not root.is_dir() or root.is_symlink(): continue
            _plain(root)
            for name in ('session.lock', 'storage.lock', 'test.lock'):
                path = root / name
                if path.is_symlink() and path.resolve() != root / 'session.lock': _plain(path)
                stream = locks.enter_context(path.open('a'))
                stat = os.fstat(stream.fileno()); identity = (stat.st_dev, stat.st_ino)
                if identity in seen: continue
                try: fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError(tr('Fermez les jeux et attendez la fin du nettoyage avant de désinstaller.')) from None
                seen.add(identity)
            ensure_idle(root)
        operations = plan(layout)
        _plain(layout.backup)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
        snapshot = layout.backup / stamp
        snapshot.mkdir(parents=True)
        receipt = dict(version=1, complete=False, preserved=[])
        def checkpoint():
            (snapshot / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        checkpoint()
        # shutil.move preserves symlinks and falls back to a complete copy before
        # removing a source on different mergerfs branches/filesystems.
        for source, relative in operations['preserve']:
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            receipt['preserved'].append(str(relative)); checkpoint()
        for edit in operations['edits']: _write_edit(edit)
        for path in operations['remove']:
            if path.is_dir() and not path.is_symlink(): shutil.rmtree(path)
            else: path.unlink(missing_ok=True)
        for root in operations['roots']:
            if root.is_symlink(): root.unlink()
            elif root.exists(): shutil.rmtree(root)
        # Shared Windows seeds/objects are technical data. Private upper/lower
        # files were moved first; hardlinks in the preserved lowers remain valid.
        if layout.bottles.exists(): shutil.rmtree(layout.bottles)
        if layout.roms.is_dir() and not any(layout.roms.iterdir()): layout.roms.rmdir()
        receipt['complete'] = True; checkpoint()
        return dict(snapshot=str(snapshot), leftovers=str(layout.roms) if layout.roms.exists() else None)


def restore_preserved(layout=Layout()):
    """Reinstall restores only persistent player state, never old app/configs."""
    _plain(layout.backup)
    if not layout.backup.is_dir(): return
    for snapshot in sorted(layout.backup.iterdir(), reverse=True):
        if snapshot.is_symlink() or not snapshot.is_dir(): continue
        _plain(snapshot)
        pairs = [(snapshot / 'bottles/players', layout.bottles / 'players'),
                 (snapshot / 'state/windows-party/runtime', layout.base / 'runtime')]
        for source, target in pairs:
            if source.exists() and not target.exists():
                _plain(source); _plain(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))


def preview(base):
    layout = Layout()
    if Path(base).absolute() != layout.base: raise ValueError(tr('Installation Windows Party non reconnue.'))
    plan(layout)


if __name__ == '__main__':
    if sys.argv[1:] == ['restore']: restore_preserved()
    else: raise SystemExit('restore')
