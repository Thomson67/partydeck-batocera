"""Bound disposable Windows Party data; never infer that Wine data is disposable."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
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
            raise ValueError('storage.json doit contenir un objet JSON.')
        values.update({k: v for k, v in data.items() if k in DEFAULTS})
    for key, default in DEFAULTS.items():
        value = values[key]
        if type(value) is not type(default) or (type(value) is int and not 0 <= value <= 1048576):
            raise ValueError(f'Réglage stockage invalide : {key}')
    if not values['log_keep'] or not values['log_file_mib']:
        raise ValueError('Conserver au moins un journal et 1 Mio par journal.')
    return values


def save_settings(base, values):
    # Validate before replacing an existing configuration.
    data = {k: values[k] for k in DEFAULTS}
    for key, default in DEFAULTS.items():
        if type(data[key]) is not type(default) or (type(default) is int and not 0 <= data[key] <= 1048576):
            raise ValueError(f'Réglage stockage invalide : {key}')
    if not data['log_keep'] or not data['log_file_mib']:
        raise ValueError('Conserver au moins un journal et 1 Mio par journal.')
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
    for unit in ('o', 'Kio', 'Mio', 'Gio', 'Tio'):
        if abs(size) < 1024 or unit == 'Tio':
            return f'{size:.1f} {unit}' if unit != 'o' else f'{size} o'
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
        raise RuntimeError('Impossible de vérifier les montages ; nettoyage refusé.')


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
    for mode in ('party', 'coop'):
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
                raise RuntimeError('Une instance Windows Party est encore active. Fermez-la avant de nettoyer ou relancer.')
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
            raise RuntimeError('Une session ou un nettoyage Windows Party est déjà en cours.') from None
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


def clean(base, purge=False):
    """User requested maintenance; also respect the existing installer/GUI lock."""
    base = Path(base)
    with (base / 'test.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Fermez la session ou attendez la fin de l’installation avant de nettoyer.') from None
        with storage_lock(base):
            return _clean(base, settings(base), purge)


def prepare_launch(base):
    """UI preflight stays responsive and reports refusal before leaving SDL."""
    base = Path(base)
    with (base / 'test.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Une session ou une installation est déjà en cours.') from None
        with storage_lock(base):
            preflight(base, SAVES, settings(base))


def disks(base, saves):
    seen = set()
    for root in (Path(base), Path(saves)):
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
            detail = ', '.join(f"{d['path']} : {human(d['free'])} libres" for d in lacking)
            raise RuntimeError(f'Espace insuffisant ({detail}). Seuil de lancement : {human(reserve)}. '
                               'Libérez de l’espace ou ajustez Stockage. Aucune sauvegarde supprimée.')


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
                    print(f"Stockage : {human(result['freed'])} libérés ; {len(result['errors'])} erreurs de nettoyage.", flush=True)
                except (OSError, RuntimeError) as error:
                    print(f'Nettoyage différé : {error}', flush=True)


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

    categories = dict(cache=0, logs=0, persistent=0, runtime=0, installation=0)
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
                player = base / 'party' / digest / f'j{index}'
                cache += size(player / 'cache')
                logs += sum(size(player / item) for item in ('logs', 'umu-logs', 'proton-logs'))
            persistent = size(saves / name)
            runtime = size(base / 'party' / digest)
            row = dict(name=rom.stem, cache=cache, logs=logs, persistent=persistent, runtime=runtime)
            row['total'] = cache + logs + persistent + runtime
            games.append(row)
            for key in ('cache', 'logs', 'persistent', 'runtime'):
                categories[key] += row[key]
        except (OSError, ValueError, KeyError, TypeError):
            continue
    for kind, root in disposable_roots(base):
        categories[kind] += size(root)
    categories['persistent'] += size(saves)
    for mode in ('party', 'coop'):
        categories['runtime'] += size(base / mode)
    categories['installation'] = size(base)
    return dict(categories=categories, total=sum(categories.values()),
                games=sorted(games, key=lambda g: g['total'], reverse=True),
                disks=list(disks(base, saves)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('bilan', 'nettoyer', 'purger-caches', 'reglages', '_maintenance'))
    parser.add_argument('base', type=Path)
    args = parser.parse_args()
    if args.action == 'bilan':
        result = snapshot(args.base)
    elif args.action == 'reglages':
        result = settings(args.base)
    elif args.action == '_maintenance':
        # Only the installed shell launcher uses this while holding test.lock.
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
