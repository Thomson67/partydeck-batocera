"""Bound disposable Windows Party data; never infer that Wine data is disposable."""
from partydeck_i18n import tr, get_language
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import time

MIB = 1024**2
SAVES = Path('/userdata/saves/windows-party')
DEFAULTS = dict(auto_clean=True, cache_mib=2048, logs_mib=128,
                log_file_mib=8, log_keep=20, reserve_mib=2048, diagnostic=False)


def settings(base):
    path = Path(base) / 'storage.json'
    values = dict(DEFAULTS)
    if path.exists():
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError(tr('storage.json doit contenir un objet JSON.'))
        values.update({k: v for k, v in data.items() if k in DEFAULTS})
    for key, default in DEFAULTS.items():
        value = values[key]
        if type(value) is not type(default) or (type(value) is int and not 0 <= value <= 1048576):
            raise ValueError(tr('Réglage stockage invalide : {p0}', p0=key))
    if not values['log_keep'] or not values['log_file_mib']:
        raise ValueError(tr('Conserver au moins un journal et 1 Mio par journal.'))
    return values


def save_settings(base, values):
    # Validate before replacing an existing configuration.
    data = {k: values[k] for k in DEFAULTS}
    for key, default in DEFAULTS.items():
        if type(data[key]) is not type(default) or (type(default) is int and not 0 <= data[key] <= 1048576):
            raise ValueError(tr('Réglage stockage invalide : {p0}', p0=key))
    if not data['log_keep'] or not data['log_file_mib']:
        raise ValueError(tr('Conserver au moins un journal et 1 Mio par journal.'))
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.storage-', dir=base)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2)
            stream.write('\n')
        os.replace(name, base / 'storage.json')
    finally:
        Path(name).unlink(missing_ok=True)


def human(size):
    units = ('o','Kio','Mio','Gio','Tio') if get_language() == 'fr' else ('B','KiB','MiB','GiB','TiB')
    for index,unit in enumerate(units):
        if abs(size) < 1024 or index == len(units)-1:
            return f'{size:.1f} {unit}' if index else f'{size} {unit}'
        size /= 1024


def identity(rom):
    digest = hashlib.sha256(os.fsencode(rom)).hexdigest()[:16]
    return digest, f'{rom.stem[:90]} [{digest[:10]}]'


def mounted_paths():
    try:
        return {Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), line.split()[4]))
                for line in Path('/proc/self/mountinfo').read_text().splitlines()}
    except OSError:
        # No cleanup if mount boundaries cannot be checked.
        raise RuntimeError(tr('Impossible de vérifier les montages ; nettoyage refusé.'))


def umu_mounts():
    """Check foreign namespaces too, including surviving Proton containers."""
    namespaces, mounts = set(), set()
    for process in Path('/proc').glob('[0-9]*'):
        try:
            namespace = (process/'ns/mnt').stat().st_ino
            if namespace in namespaces:
                continue
            entries = (process/'mountinfo').read_text().splitlines()
        except (FileNotFoundError, ProcessLookupError):
            continue
        namespaces.add(namespace)
        for line in entries:
            for field in line.split()[3:5]:
                mounts.add(Path(re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), field)))
    return mounts


def files(root, mounts=None):
    """No symlink traversal, including ancestors, and no nested mount traversal."""
    root = Path(root).absolute()
    mounts = mounted_paths() if mounts is None else mounts
    if root.resolve() != root or root in mounts or not root.is_dir():
        return
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if path in mounts or entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        yield path, entry.stat(follow_symlinks=False)
        except FileNotFoundError:
            continue


def players(base):
    for mode in ('runtime', 'coop'):
        for game in sorted((Path(base) / mode).glob('*')):
            if re.fullmatch(r'[a-f0-9]{16}', game.name) and not game.is_symlink():
                for index in range(1, 5):
                    path = game / f'j{index}'
                    if path.is_dir() and not path.is_symlink():
                        yield path


def disposable_roots(base):
    yield 'cache', Path(base) / 'cache'
    yield 'logs', Path(base) / 'logs'
    for player in players(base):
        yield 'cache', player / 'cache'
        for name in ('logs', 'umu-logs', 'proton-logs'):
            yield 'logs', player / name


def open_files():
    opened = set()
    for directory in Path('/proc').glob('[0-9]*/fd'):
        try:
            for fd in directory.iterdir():
                try:
                    info = fd.stat()
                    opened.add((info.st_dev, info.st_ino))
                except OSError:
                    pass
        except OSError:
            pass
    return opened


def ensure_idle(base):
    # A launcher killed by itself can leave a compositor behind after its flock
    # was released. Do not treat these orphaned sessions as abandoned data.
    prefix = str(Path(base).absolute()) + '/'
    for process in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args = [os.fsdecode(arg) for arg in process.read_bytes().split(b'\0') if arg]
            compositor = bool(args) and Path(args[0]).name == 'gamescope-kbm'
            child = any(Path(arg).name == 'partydeck-batocera-coop.py' for arg in args) and any(arg in ('_wine', '_sandbox') for arg in args)
            if (compositor or child) and any(arg.startswith(prefix) for arg in args):
                raise RuntimeError(tr('Une instance Windows Party est encore active. Fermez-la avant de nettoyer ou relancer.'))
        except (OSError, ProcessLookupError):
            pass


def occupied(info):
    return info.st_blocks * 512


def _trim(path, info, limit):
    """Keep the end of closed logs; replacement does not affect linked originals."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    tmp = None
    try:
        with os.fdopen(fd, 'rb') as source:
            if (os.fstat(source.fileno()).st_ino, os.fstat(source.fileno()).st_dev) != (info.st_ino, info.st_dev):
                return
            source.seek(-limit, os.SEEK_END)
            out, tmp = tempfile.mkstemp(prefix='.log-tail-', dir=path.parent)
            with os.fdopen(out, 'wb') as target:
                shutil.copyfileobj(source, target)
        os.utime(tmp, ns=(info.st_atime_ns, info.st_mtime_ns))
        os.replace(tmp, path)
    finally:
        if tmp:
            Path(tmp).unlink(missing_ok=True)


@contextmanager
def storage_lock(base):
    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)
    with (base / 'storage.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(tr('Une session ou un nettoyage Windows Party est déjà en cours.')) from None
        yield


def _clean(base, config, purge=False):
    ensure_idle(base)
    mounts, opened = mounted_paths(), open_files()
    now = time.time()
    removed, trimmed, errors = 0, 0, []
    groups = {'cache': [], 'logs': []}
    for kind, root in disposable_roots(base):
        groups[kind].extend(files(root, mounts))
    for kind, entries in groups.items():
        entries.sort(key=lambda item: item[1].st_mtime)
        total = sum(occupied(info) for _, info in entries)
        ceiling = (0 if purge else config['cache_mib']) * MIB if kind == 'cache' else config['logs_mib'] * MIB
        remaining = len(entries)
        for path, info in entries:
            # A recently closed file may still belong to a child. Never touch open
            # logs, hardlinks, active cache files, or symlinked game/save content.
            if ((info.st_dev, info.st_ino) in opened or info.st_nlink != 1
                    or now - info.st_mtime < 60):
                continue
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino, current.st_mtime_ns) != (info.st_dev, info.st_ino, info.st_mtime_ns):
                    continue
                if kind == 'logs' and info.st_size > config['log_file_mib'] * MIB:
                    _trim(path, info, config['log_file_mib'] * MIB)
                    current = path.stat()
                    freed = max(0, occupied(info) - occupied(current))
                    removed += freed
                    total -= freed
                    trimmed += 1
                    info = current
                if total > ceiling or (kind == 'logs' and remaining > config['log_keep']):
                    path.unlink()
                    removed += occupied(info)
                    total -= occupied(info)
                    remaining -= 1
            except OSError as error:
                errors.append(f'{path}: {error}')
    # Only abandoned installer staging, never wine-run, UMU prefixes, overlays,
    # content/upper, user data, or guessed Temp directories inside prefixes.
    for pattern in ('.coop-*', '.launcher-*', '.storage-*', 'releases/.partydeck-*', 'releases/.xwayland-*'):
        for path in Path(base).glob(pattern):
            try:
                if path.is_symlink() or path.resolve() != path.absolute() or now - path.stat().st_mtime < 86400:
                    continue
                if any(m == path or path in m.parents for m in mounts):
                    continue
                entries = list(files(path, mounts)) if path.is_dir() else [(path, path.stat())]
                if any((info.st_dev, info.st_ino) in opened or now - info.st_mtime < 86400 for _, info in entries):
                    continue
                size = sum(occupied(info) for _, info in entries)
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                removed += size
            except OSError as error:
                errors.append(f'{path}: {error}')
    return dict(freed=removed, trimmed=trimmed, errors=errors)


@contextmanager
def maintenance_lock(base):
    """Serialize user-requested cleanup with both the installer and game sessions."""
    base = Path(base)
    with (base / 'session.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(tr('Fermez la session ou attendez la fin de l’installation avant de nettoyer.')) from None
        with storage_lock(base):
            yield


def clean(base, purge=False):
    with maintenance_lock(base):
        return _clean(base, settings(base), purge)


def clean_umu_work(game, *, discard_recovery=False):
    """Under the session lock, collect closed materialized prefixes for this game."""
    if game.resolve() != game or not re.fullmatch('[0-9a-f]{16}', game.name):
        raise ValueError(f'Invalid UMU game directory: {game}')
    players = [(game/f'j{i}') for i in range(1, 5)]
    if not any((player/'umu-private/materialized-prefixes').is_dir() for player in players):
        return {'removed': 0, 'retained': 0}
    mounts = umu_mounts()
    result = {'removed': 0, 'retained': 0}
    for player in players:
        root = player/'umu-private/materialized-prefixes'
        upper = player/'umu/upper'
        records = upper/'runtime-prefix-state'
        if not root.is_dir() or root.resolve() != root or records.resolve() != records:
            continue
        lock = upper/'.materialized-prefix.lock'
        if upper.resolve() != upper:
            continue
        # Match Btrfs mount roots even when mountinfo omits /userdata.
        suffix = root.parts[-5:]
        if any(any(parent.parts[-5:] == suffix for parent in (mount, *mount.parents))
               for mount in mounts):
            result['retained'] += sum(path.is_dir() for path in root.iterdir())
            continue
        upper.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                result['retained'] += sum(path.is_dir() for path in root.iterdir())
                continue
            for prefix in root.iterdir():
                if prefix.is_symlink() or not prefix.is_dir():
                    continue
                journal = records/(hashlib.sha256(os.fsencode(prefix.name)).hexdigest() + '.json')
                disposable = False
                if journal.is_file() and not journal.is_symlink():
                    try:
                        record = json.loads(journal.read_text())
                        disposable = (isinstance(record, dict) and record.get('version') == 1
                                      and record.get('prefix') ==
                                      f'/userdata/system/umu/materialized-prefixes/{prefix.name}'
                                      and record.get('phase') == 'disposable' and record.get('pid') == 0)
                    except (OSError, ValueError):
                        pass
                if disposable or discard_recovery:
                    shutil.rmtree(prefix)
                    journal.unlink(missing_ok=True)
                    result['removed'] += 1
                else:
                    result['retained'] += 1
    return result


def clean_game(base, rom, *, include_saves=False):
    """Remove this game's PartyDeck bottles and optionally its external saves."""
    from partydeck_bottles import ROOT as bottles_root

    base, rom = Path(base).absolute(), Path(rom)
    if not rom.is_absolute() or rom.suffix.lower() not in ('.wine', '.pc', '.wsquashfs'):
        raise ValueError(tr('Chemin de jeu Windows Party invalide.'))
    digest, name = identity(rom)
    bottles = bottles_root / 'players' / digest
    saves = SAVES / name
    runtime = base / 'runtime' / digest

    with maintenance_lock(base):
        ensure_idle(base)
        mounts = mounted_paths()
        targets = []

        def check(path, game_root, compatibility_target=None):
            if path.parent.resolve() != path.parent:
                raise RuntimeError(tr('Dossier technique redirigé : {p0}', p0=path.parent))
            if any(mount == path or path in mount.parents
                   or (mount in path.parents and mount.is_relative_to(game_root))
                   for mount in mounts):
                raise RuntimeError(tr('Bottle encore montée : {p0}', p0=path))
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                return
            if stat.S_ISDIR(mode):
                targets.append((path, False))
            elif compatibility_target is not None and stat.S_ISLNK(mode) and Path(
                    os.path.normpath(path.parent / os.readlink(path))) == compatibility_target:
                targets.append((path, True))
            else:
                raise RuntimeError(tr('Dossier technique redirigé : {p0}', p0=path))

        if include_saves:
            check(saves, saves)
        for index in range(1, 5):
            player = f'j{index}'
            if not include_saves:
                # Older installations put these directories under saves. Remove
                # migration links before their targets so relaunch can rebuild.
                for folder in ('prefixes', 'content'):
                    check(saves / player / folder, saves, bottles / player / folder)
            for folder in ('bottles', 'umu', 'umu-private'):
                check(runtime / player / folder, runtime)
        check(bottles, bottles)

        for path, link in targets:
            if link:
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path)
        return bool(targets)


def reset_l4d2_config(base, rom):
    """Move private L4D2 config files aside so the game can load defaults."""
    from partydeck_bottles import ROOT as bottles_root
    from partydeck_l4d2 import matches

    base, rom = Path(base).absolute(), Path(rom)
    if not rom.is_absolute() or rom.suffix.lower() not in ('.wine', '.pc', '.wsquashfs') or not matches(rom):
        raise ValueError(tr('Chemin de jeu Windows Party invalide.'))
    digest, name = identity(rom)
    with maintenance_lock(base):
        ensure_idle(base)
        mounts = mounted_paths()
        count = 0
        for index in range(1, 5):
            player = f'j{index}'
            private = bottles_root/'players'/digest/player
            legacy = SAVES/name/player
            umu = base/'runtime'/digest/player/'umu-private'
            roots = (private/'prefixes', private/'content/upper', legacy/'prefixes',
                     legacy/'content/upper', umu/'materialized-prefixes', umu/'compatdata')
            for root in roots:
                for path, _ in files(root, mounts):
                    parts = tuple(part.casefold() for part in path.relative_to(root).parts)
                    if parts[-3:] != ('left4dead2', 'cfg', 'config.cfg') or any(
                            part.endswith('.bak') for part in parts[:-3]):
                        continue
                    backup = Path(tempfile.mkdtemp(prefix='config.cfg.partydeck-', dir=path.parent))
                    path.rename(backup/'config.cfg')
                    print(tr('Configuration Left 4 Dead 2 sauvegardée dans {p0}.',p0=backup),flush=True)
                    count += 1
        return count


def prepare_launch(base):
    """UI preflight stays responsive and reports refusal before leaving SDL."""
    base = Path(base)
    with (base / 'session.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(tr('Une session ou une installation est déjà en cours.')) from None
        with storage_lock(base):
            preflight(base, SAVES, settings(base))


def disks(base, saves):
    seen = set()
    from partydeck_bottles import ROOT as bottles
    for root in (Path(base), Path(saves), bottles):
        while not root.exists():
            root = root.parent
        dev = root.stat().st_dev
        if dev not in seen:
            seen.add(dev)
            usage = shutil.disk_usage(root)
            yield dict(path=str(root), free=usage.free, total=usage.total)


def preflight(base, saves, config):
    ensure_idle(base)
    if config['auto_clean']:
        _clean(base, config)
    reserve = config['reserve_mib'] * MIB
    if reserve and any(d['free'] < reserve for d in disks(base, saves)):
        if config['auto_clean']:
            _clean(base, config, purge=True)
        lacking = [d for d in disks(base, saves) if d['free'] < reserve]
        if lacking:
            detail = ', '.join(tr('{p0} : {p1} libres', p0=d['path'], p1=human(d['free'])) for d in lacking)
            raise RuntimeError(tr('Espace insuffisant ({p0}). Seuil de lancement : {p1}. Libérez de l’espace ou ajustez Stockage. Aucune sauvegarde supprimée.', p0=detail, p1=human(reserve)))


@contextmanager
def session(base, saves):
    with storage_lock(base):
        config = settings(base)
        preflight(base, saves, config)
        try:
            yield config
        finally:
            if config['auto_clean']:
                try:
                    result = _clean(base, config)
                    print(tr('Stockage : {p0} libérés ; {p1} erreurs de nettoyage.', p0=human(result['freed']), p1=len(result['errors'])), flush=True)
                except (OSError, RuntimeError) as error:
                    print(tr('Nettoyage différé : {p0}', p0=error), flush=True)


def snapshot(base, saves=None):
    """Allocated bytes, no following game links or counting shared hardlinks twice."""
    base, saves = Path(base), Path(saves) if saves is not None else SAVES
    mounts, seen = mounted_paths(), set()

    def size(root):
        total = 0
        for _, info in files(root, mounts):
            inode = (info.st_dev, info.st_ino)
            if inode not in seen:
                seen.add(inode)
                total += occupied(info)
        return total

    from partydeck_bottles import ROOT as bottles_root
    categories = dict(cache=0, logs=0, persistent=0, runtime=0, installation=0, bottles=0)
    # Count shared objects before player manifests: one physical allocation,
    # attributed to the global bottle total rather than to the first game.
    categories['bottles'] = size(bottles_root/'objects') + size(bottles_root/'seeds')
    games, mapped = [], set()
    for profile in sorted((base / 'profiles').glob('*.json')):
        try:
            data = json.loads(profile.read_text())
            rom = Path(data['rom'])
            digest, name = identity(rom)
            if digest in mapped:
                continue
            mapped.add(digest)
            cache = logs = 0
            for index in range(1, 5):
                player = base / 'runtime' / digest / f'j{index}'
                cache += size(player / 'cache')
                logs += sum(size(player / item) for item in ('logs', 'umu-logs', 'proton-logs'))
            persistent = size(saves / name)
            runtime = size(base / 'runtime' / digest)
            bottles = size(bottles_root/'players'/digest)
            row = dict(name=rom.stem, rom=str(rom), cache=cache, logs=logs, persistent=persistent, runtime=runtime, bottles=bottles)
            row['total'] = cache + logs + persistent + runtime + bottles
            games.append(row)
            for key in ('cache', 'logs', 'persistent', 'runtime', 'bottles'):
                categories[key] += row[key]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for kind, root in disposable_roots(base):
        categories[kind] += size(root)
    categories['persistent'] += size(saves)
    for mode in ('runtime', 'coop'):
        categories['runtime'] += size(base / mode)
    categories['bottles'] += size(bottles_root)
    categories['installation'] = size(base)
    return dict(categories=categories, total=sum(categories.values()),
                games=sorted(games, key=lambda g: g['total'], reverse=True),
                disks=list(disks(base, saves)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('bilan', 'nettoyer', 'purger-caches', 'reglages',
                                           'purger-travail-umu', '_maintenance'))
    parser.add_argument('base', type=Path)
    parser.add_argument('--jeu', help='Identifiant du jeu / Game ID')
    args = parser.parse_args()
    if args.action == 'bilan':
        result = snapshot(args.base)
    elif args.action == 'reglages':
        result = settings(args.base)
    elif args.action == 'purger-travail-umu':
        if not args.jeu or not re.fullmatch('[0-9a-f]{16}', args.jeu):
            parser.error('--jeu requires a 16-character game ID')
        with maintenance_lock(args.base):
            ensure_idle(args.base)
            result = clean_umu_work(args.base.absolute()/'runtime'/args.jeu, discard_recovery=True)
    elif args.action == '_maintenance':
        # Only the installed shell launcher uses this while holding session.lock.
        with storage_lock(args.base):
            cfg = settings(args.base)
            result = _clean(args.base, cfg) if cfg['auto_clean'] else {'freed': 0}
    else:
        result = clean(args.base, args.action == 'purger-caches')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error))
