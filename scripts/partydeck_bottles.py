"""Private writable bottles over deduplicated, immutable Windows file layers.

Only byte-identical regular files below drive_c/windows are shared. Registry,
users, game directories, whiteouts and unknown entries stay player-private.
Run migration/compaction on the host under the session/storage locks, never
against live mounts. OverlayFS supplies copy-on-write, even on ext4/mergerfs.
"""
import filecmp
from functools import lru_cache
from glob import escape as glob_escape
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import uuid

from partydeck_i18n import tr

def atomic_json(path, data):
    from partydeck_profiles import atomic_write
    atomic_write(path, json.dumps(data) + "\n")
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


ROOT = Path('/userdata/system/wine-bottles/windows-party')


def location(player, root=None):
    player = Path(player)
    if player.name not in ('j1', 'j2', 'j3', 'j4') or not re.fullmatch('[0-9a-f]{16}', player.parent.name):
        raise ValueError(tr('Identité de bottle Windows Party invalide.'))
    return (ROOT if root is None else Path(root)) / 'players' / player.parent.name / player.name


def regular_directory(path):
    path = Path(path).absolute()
    if path.resolve() != path:
        raise RuntimeError(tr('Dossier technique redirigé : {p0}', p0=path))
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate(player, saves):
    """Same-filesystem renames; a crash never leaves an incomplete directory copy.

    Retain old absolute paths as links for existing Wine registries/recovery.
    New players do not get these compatibility links in their save directory.
    """
    area = regular_directory(location(player))
    from partydeck_storage import mounted_paths
    mounts = mounted_paths()
    pairs = [(Path(saves)/'prefixes', area/'prefixes'),
             (Path(saves)/'content', area/'content')]
    for source, target in pairs:
        # Recover a rename interrupted before compatibility-link creation.
        marker = area / ('.migrate-' + source.name + '.json')
        if marker.exists():
            if json.loads(marker.read_text()) != str(source.absolute()):
                raise RuntimeError(tr('Migration de bottle incohérente : {p0}', p0=source))
            if not source.exists() and not source.is_symlink() and target.is_dir():
                source.symlink_to(target, target_is_directory=True)
                marker.unlink()
        if source.is_symlink():
            if source.resolve() != target.resolve():
                raise RuntimeError(tr('Ancien dossier de bottle redirigé : {p0}', p0=source))
            if not target.is_dir():
                raise RuntimeError(tr('Bottle migrée absente : {p0}', p0=target))
            marker.unlink(missing_ok=True)
        elif source.exists():
            if source.resolve() != source.absolute() or not source.is_dir():
                raise RuntimeError(tr('Dossier de bottle invalide : {p0}', p0=source))
            if any(m == source or source in m.parents for m in mounts):
                raise RuntimeError(tr('Bottle encore montée : {p0}', p0=source))
            if target.exists():
                raise RuntimeError(tr('Deux dossiers de bottle existent ; fusion automatique refusée : {p0}', p0=source))
            atomic_json(marker, str(source.absolute()))
            try:
                source.rename(target)
            except OSError as error:
                raise RuntimeError(tr('Déplacement de bottle impossible ; données conservées : {p0}', p0=source)) from error
            source.symlink_to(target, target_is_directory=True)
            marker.unlink()
        # Do not precreate content/upper: the existing overlay helper does it.
    regular_directory(area/'prefixes')
    regular_directory(area/'prefixes-lower')
    return area


OVERLAY_PREFIXES = ('trusted.overlay.', 'user.overlay.')
OVERLAY_ORIGINS = tuple(prefix + 'origin' for prefix in OVERLAY_PREFIXES)


def _attributes(path, *, ignore_origin=False, rejected=None):
    attrs = {key: os.getxattr(path, key, follow_symlinks=False)
             for key in os.listxattr(path, follow_symlinks=False)}
    if ignore_origin:
        for key in OVERLAY_ORIGINS:
            attrs.pop(key, None)
    overlay = {key for key in attrs if key.startswith(OVERLAY_PREFIXES)}
    if overlay:
        if rejected is not None:
            rejected.update(overlay)
        return None
    return attrs


def inherits_lower(root):
    """Check that moving a file to the lower layer leaves it visible."""
    @lru_cache(maxsize=None)
    def inherits(directory):
        attrs = os.listxattr(directory, follow_symlinks=False)
        for prefix in OVERLAY_PREFIXES:
            if prefix + 'redirect' in attrs:
                return False
            # 'x' speeds up whiteout lookup without hiding the lower directory.
            if prefix + 'opaque' in attrs and os.getxattr(directory, prefix + 'opaque',
                                                         follow_symlinks=False) != b'x':
                return False
        return directory == root or inherits(directory.parent)
    return inherits


def _key(path, info, attrs):
    key = hashlib.sha256()
    key.update(json.dumps([stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid,
                           info.st_size, info.st_mtime_ns,
                           [(k, v.hex()) for k, v in sorted(attrs.items())]], separators=(',', ':')).encode())
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            key.update(chunk)
    return key.hexdigest()


def compact_tree(upper, lower, objects, *, eligible=None, retained=None,
                 copy_up_origin=False, rejected_attributes=None):
    """Publish a lower hardlink BEFORE unlinking its identical private upper.

    Objects are never writable through a bottle: only OverlayFS can expose
    them, and every write copies up. Never hardlink two writable prefixes.
    """
    upper, lower, objects = map(Path, (upper, lower, objects))
    if not upper.is_dir():
        return dict(shared=0, files=0)
    regular_directory(lower)
    regular_directory(objects)
    # Hardlinks need one filesystem. Disable compaction, not player isolation,
    # on an unsuitable placement (including different mergerfs branches).
    from partydeck_storage import mounted_paths
    mounts = mounted_paths()
    if any(m == upper or upper in m.parents for m in mounts):
        raise RuntimeError(tr('Bottle encore montée : {p0}', p0=upper))
    result = dict(shared=0, files=0)
    measured = set()
    inherits = inherits_lower(upper) if copy_up_origin else None

    def account(reason, info):
        inode = (info.st_dev, info.st_ino)
        if retained is not None and inode not in measured:
            measured.add(inode)
            retained[reason] = retained.get(reason, 0) + info.st_blocks*512

    from partydeck_storage import files
    for path, info in files(upper):
        if not info.st_size:
            continue
        if eligible is not None and not eligible(path, info):
            account('filtered', info)
            continue
        if info.st_nlink != 1:
            account('hardlinked', info)
            continue
        if info.st_size > 512*1024**2:
            account('large', info)
            continue
        if inherits is not None and not inherits(path.parent):
            account('filtered', info)
            continue
        # A regular copy-up with origin alone has complete local data. Other
        # OverlayFS metadata may encode hidden data or link/redirect semantics.
        attrs = _attributes(path, ignore_origin=copy_up_origin, rejected=rejected_attributes)
        if attrs is None:
            account('overlay', info)
            continue
        digest = _key(path, info, attrs)
        obj = objects/digest[:2]/digest
        obj.parent.mkdir(exist_ok=True)
        if not obj.exists():
            fd, name = tempfile.mkstemp(prefix='.object-', dir=obj.parent)
            os.close(fd)
            tmp = Path(name)
            try:
                subprocess.run(['cp', '--preserve=all', '--reflink=auto', '--sparse=always', '--', str(path), str(tmp)], check=True)
                if copy_up_origin:
                    for key in set(os.listxattr(tmp, follow_symlinks=False)).intersection(OVERLAY_ORIGINS):
                        os.removexattr(tmp, key, follow_symlinks=False)
                os.chown(tmp, info.st_uid, info.st_gid)
                # Publish only complete, verified bytes and metadata.
                copied_attrs = _attributes(tmp)
                if copied_attrs is None or _key(tmp, tmp.stat(), copied_attrs) != digest:
                    raise RuntimeError(tr('Vérification de bottle échouée : {p0}', p0=path))
                with tmp.open('rb') as stream:
                    os.fsync(stream.fileno())
                tmp.replace(obj)
            finally:
                tmp.unlink(missing_ok=True)
        elif obj.is_symlink() or not obj.is_file() or _key(obj, obj.stat(), _attributes(obj)) != digest:
            raise RuntimeError(tr('Fichier commun de bottle altéré : {p0}', p0=obj))
        dest = lower/path.relative_to(upper)
        regular_directory(dest.parent)
        # A whiteout or opaque parent in the upper always takes precedence.
        # The manifest only represents this player's own compacted entries.
        candidate = dest.with_name('.link-' + uuid.uuid4().hex)
        try:
            os.link(obj, candidate)
            os.replace(candidate, dest)
        except OSError:
            candidate.unlink(missing_ok=True)
            # No original removed if hardlinking is unsupported/cross-device.
            account('link_error', info)
            continue
        current = path.lstat()
        if (current.st_ino, current.st_dev, current.st_size, current.st_mtime_ns, current.st_ctime_ns) != (info.st_ino, info.st_dev, info.st_size, info.st_mtime_ns, info.st_ctime_ns):
            raise RuntimeError(tr('Bottle modifiée pendant la mutualisation : {p0}', p0=path))
        # Ensure the lower directory entry survives an interrupted operation.
        fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        path.unlink()
        result['shared'] += info.st_blocks*512
        result['files'] += 1
    return result


def _safe_path(path):
    if any(c in str(path) for c in ',:\\\n\r'):
        raise RuntimeError(tr('Chemin incompatible avec la bottle privée.'))


def seed_windows(original, target):
    """One immutable Windows seed per source generation, never a player's data."""
    info = target.stat()
    identity = [str(target), info.st_dev, info.st_ino, info.st_mtime_ns,
                info.st_ctime_ns, info.st_size]
    if target.is_dir():
        # A directory mtime alone cannot identify edits to nested files. Use
        # the existing read-only ROM as the seed instead of caching a copy.
        windows = target/'drive_c/windows'
        return windows if windows.is_dir() and not windows.is_symlink() else None
    if original.suffix.lower() != '.wsquashfs':
        return None
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    seed = ROOT/'seeds'/key
    if (seed/'complete.json').is_file():
        if json.loads((seed/'complete.json').read_text()) != identity:
            raise RuntimeError(tr('Base Windows incohérente : {p0}', p0=seed))
        return seed/'windows'
    regular_directory(seed.parent)
    staging = Path(tempfile.mkdtemp(prefix='.seed-', dir=seed.parent))
    try:
        result = subprocess.run(['unsquashfs', '-no-progress', '-d', str(staging/'extract'),
                                 str(target), 'drive_c/windows'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        extracted = staging/'extract/drive_c/windows'
        if result.returncode or extracted.is_symlink() or (extracted.exists() and not extracted.is_dir()):
            raise RuntimeError(tr('Extraction de la base Windows impossible : {p0}', p0=target))
        # A valid archive may contain only the game's files. Wine boots the
        # Windows tree into each player's writable prefix on the first run.
        if not extracted.exists():
            return None
        # A seed is a complete original tree. Keep links/empty files/directories
        # in it, while deduplicating its regular files through the same objects.
        # Build directory metadata first; do not duplicate the full seed on a
        # nearly full userdata disk. Only the current object needs a temporary
        # copy. Non-eligible files/links remain intact via the final pass.
        shutil.copytree(extracted, staging/'windows', symlinks=True,
                        ignore=lambda directory,names: [name for name in names
                            if (Path(directory)/name).is_symlink() or not (Path(directory)/name).is_dir()])
        compact_tree(extracted, staging/'windows', ROOT/'objects')
        shutil.copytree(extracted, staging/'windows', symlinks=True,
                        dirs_exist_ok=True, copy_function=os.link)
        # compact_tree leaves empty directory scaffolding in extract.
        shutil.rmtree(staging/'extract')
        atomic_json(staging/'complete.json', identity)
        current = target.stat()
        if [str(target),current.st_dev,current.st_ino,current.st_mtime_ns,current.st_ctime_ns,current.st_size] != identity:
            raise RuntimeError(tr('Archive modifiée pendant la préparation : {p0}',p0=target))
        staging.rename(seed)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return seed/'windows'


def window_directories(root):
    """Physical prefix trees only. Never inspect mounted views or user links."""
    if not root.is_dir() or root.is_symlink():
        return
    for directory, names, _ in os.walk(root, followlinks=False):
        names[:] = [name for name in names if not (Path(directory)/name).is_symlink()]
        parent = Path(directory)
        if parent.name == 'drive_c' and 'windows' in names:
            yield parent/'windows'
            names.remove('windows')


def prepare_windows(player, original, target):
    """Host-only, idle: relocate existing Windows uppers and compact them.

    Only the Windows subtree becomes a link to a stable private COW view.
    Bottle roots remain real directories: Batocera needs physical upperdirs
    when constructing its own wsquashfs overlay.
    """
    area = location(player)
    roots = (area/'prefixes', area/'content/upper')
    candidates = [p for root in roots for p in window_directories(root)]
    records = regular_directory(area/'windows')
    # Do not extract a seed until a prefix actually exists.
    existing = list(records.glob('*/state.json'))
    if not candidates and not existing:
        return
    seed = seed_windows(original, target)
    if seed is None:
        # Unknown source layout: preserve the physical private prefix.
        return
    for path in candidates:
        relative = path.relative_to(area)
        key = hashlib.sha256(os.fsencode(relative)).hexdigest()[:24]
        slot = regular_directory(records/key)
        state = slot/'state.json'
        data = dict(version=1, path=str(relative), seed=str(seed))
        if state.exists() and json.loads(state.read_text())['path'] != str(relative):
            raise RuntimeError(tr('Vue Windows incohérente : {p0}', p0=path))
        if (slot/'upper').exists():
            raise RuntimeError(tr('Deux dossiers Windows existent ; données conservées : {p0}', p0=path))
        # State precedes rename: interruption is recoverable on next launch.
        atomic_json(state, data)
        path.rename(slot/'upper')
        path.symlink_to(slot/'view', target_is_directory=True)
    for state in records.glob('*/state.json'):
        data = json.loads(state.read_text())
        relative = Path(data['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[-2:] != ('drive_c', 'windows'):
            raise RuntimeError(tr('Vue Windows incohérente : {p0}', p0=state))
        slot = state.parent
        path = area/relative
        # Finish an interrupted rename/link operation. Refuse divergent trees.
        if not (slot/'upper').is_dir():
            if path.is_dir() and not path.is_symlink():
                path.rename(slot/'upper')
            else:
                raise RuntimeError(tr('Dossier Windows privé absent : {p0}', p0=path))
        if not path.exists() and not path.is_symlink():
            path.symlink_to(slot/'view', target_is_directory=True)
        if not path.is_symlink() or os.readlink(path) != str(slot/'view'):
            raise RuntimeError(tr('Vue Windows incohérente : {p0}', p0=path))
        # Keep this player's previous Windows changes above the new ROM
        # generation, exactly as a normal persistent WSquashFS upper would.
        if data['seed'] != str(seed):
            data['seed']=str(seed)
            atomic_json(state,data)
        for name in ('lower', 'work', 'view'):
            regular_directory(slot/name)
        retained, rejected = {}, set()
        result = compact_tree(slot/'upper', slot/'lower', ROOT/'objects', retained=retained,
                              copy_up_origin=True, rejected_attributes=rejected)
        if retained or result['shared']:
            sizes = ' '.join(f'{key}={size}' for key, size in sorted(retained.items()) if size)
            if rejected:
                sizes += ' overlay_attributes=' + ','.join(sorted(rejected))
            print(f"Windows Party {player.name.upper()}: Windows layer {relative} "
                  f"shared={result['shared']} {sizes}".rstrip(), flush=True)


def mount_windows(player):
    """Inside bwrap; expose private views to Wine/Pressure Vessel as RW paths."""
    area = location(player)
    views = []
    for state in sorted((area/'windows').glob('*/state.json')):
        slot = state.parent
        data = json.loads(state.read_text())
        seed = Path(data['seed'])
        if not seed.is_dir():
            raise RuntimeError(tr('Base Windows absente : {p0}', p0=seed))
        lower, upper, work, view = (slot/name for name in ('lower', 'upper', 'work', 'view'))
        for path in (lower, upper, work, view):
            path.mkdir(exist_ok=True)
            _safe_path(path)
        _safe_path(seed)
        for path in (lower, seed):
            subprocess.run(['mount', '--bind', str(path), str(path)], check=True)
            subprocess.run(['mount', '-o', 'remount,bind,ro', str(path)], check=True)
        options = f'lowerdir={lower}:{seed},upperdir={upper},workdir={work},index=off,redirect_dir=on'
        subprocess.run(['mount', '-t', 'overlay', '-o', options, 'overlay', str(view)], check=True)
        views.append(view)
    return views


def private_windows_paths(player):
    """Authorize only mounted COW Windows views owned by this player.

    Native game hooks normally permit prefix-contained paths only. A Windows
    view lives outside the materialized prefix, without granting access to
    another player's bottle or to the global shared object store.
    """
    try:
        area=location(player)
    except ValueError:
        return ()
    from partydeck_storage import mounted_paths
    mounts=mounted_paths()
    return tuple(state.parent/'view' for state in sorted((area/'windows').glob('*/state.json'))
                 if state.parent/'view' in mounts)


def collect_objects():
    """Only unreferenced content objects, never prefixes, manifests or seeds."""
    removed = 0
    root = ROOT/'objects'
    if root.resolve() != root.absolute():
        raise RuntimeError(tr('Dossier technique redirigé : {p0}', p0=root))
    for directory in root.glob('*'):
        if directory.is_symlink() or not re.fullmatch('[a-f0-9]{2}', directory.name):
            continue
        for path in directory.iterdir():
            if path.is_symlink() or not re.fullmatch('[a-f0-9]{64}', path.name):
                continue
            info = path.stat()
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                removed += info.st_blocks*512
                path.unlink()
    return removed


def retire_runner_bottles(player, original, report):
    """Retire only archive prefixes for this game after a verified replacement."""
    from partydeck_storage import umu_mounts
    expected = Path('/userdata/system/wine-bottles/windows')
    active = Path(report)
    name = original.name + '.wine'
    if (original.suffix.lower() != '.wsquashfs' or active.parent.parent != expected
            or active.name != name or active.parent.name in ('', '.', '..')):
        return 0
    area = location(player)
    prefixes = area/'prefixes'
    current = prefixes/active.parent.name/name
    if current.resolve() != current or not current.is_dir():
        return 0
    mounts = umu_mounts()
    if any(area.parts[-3:] == parent.parts[-3:] for mount in mounts
           for parent in (mount, *mount.parents)):
        return 0
    previous = [candidate for candidate in prefixes.glob(f'*/{glob_escape(name)}')
                if candidate != current and candidate.is_dir() and candidate.resolve() == candidate]
    if not previous:
        return 0
    stage = regular_directory(area/'.retired-runner-bottles')
    for candidate in previous:
        relative = candidate.relative_to(area)/'drive_c/windows'
        slot = area/'windows'/hashlib.sha256(os.fsencode(relative)).hexdigest()[:24]
        if slot.resolve() == slot and slot.is_dir():
            slot.rename(stage/uuid.uuid4().hex)
        candidate.rename(stage/uuid.uuid4().hex)
    shutil.rmtree(stage)
    return len(previous)


def prune_inherited_dependencies(area, target):
    """Drop legacy copy-up files when the original .wine already supplies them."""
    from partydeck_storage import files, mounted_paths

    if target.suffix.lower() != '.wine' or not target.is_dir():
        return 0
    upper = area/'content/upper'
    mounts = mounted_paths()
    if upper.resolve() != upper or any(m == upper or upper in m.parents for m in mounts):
        return 0

    inherits = inherits_lower(upper)

    def metadata(info):
        return info.st_mode, info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns

    def identity(info):
        return info.st_dev, info.st_ino, info.st_ctime_ns

    freed = 0
    for relative in ('Program Files/dotnet', 'Program Files (x86)/dotnet', 'ProgramData/Package Cache'):
        directory = upper/'drive_c'/relative
        if not (target/'drive_c'/relative).is_dir():
            continue
        for path, info in files(directory, mounts):
            original = target/path.relative_to(upper)
            if info.st_nlink != 1 or original.resolve() != original or not inherits(path.parent):
                continue
            try:
                original_info = original.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(original_info.st_mode) or metadata(info) != metadata(original_info):
                continue
            attrs = _attributes(path)
            if attrs is None or attrs != _attributes(original) or not filecmp.cmp(path, original, shallow=False):
                continue
            if identity(path.lstat()) == identity(info) and identity(original.lstat()) == identity(original_info):
                path.unlink()
                freed += info.st_blocks*512
    return freed


def prepare(player, saves, original, target):
    area = migrate(player, saves)
    retired = area/'.retired-runner-bottles'
    if retired.is_dir() and retired.resolve() == retired:
        from partydeck_storage import mounted_paths
        if not any(m == retired or retired in m.parents for m in mounted_paths()):
            shutil.rmtree(retired)
    prepare_windows(player, original, target)
    return area


def probe_filesystem():
    """Called in a throwaway bwrap mount namespace BEFORE any migration."""
    regular_directory(ROOT)
    with tempfile.TemporaryDirectory(prefix='.bottles-probe-', dir=ROOT) as folder:
        area=Path(folder)
        for name in ('lower','upper','work','view'):
            (area/name).mkdir()
        (area/'lower/check').write_text('lower')
        options=f'lowerdir={area}/lower,upperdir={area}/upper,workdir={area}/work,index=off,redirect_dir=on'
        mounted=False
        try:
            subprocess.run(['mount','-t','overlay','-o',options,'overlay',str(area/'view')],check=True)
            mounted=True
            (area/'view/check').write_text('private')
            if (area/'lower/check').read_text()!='lower':
                raise RuntimeError(tr('La copie privée des bottles n’est pas isolée.'))
        finally:
            if mounted:
                subprocess.run(['umount','--',str(area/'view')],check=True)


def adapt_prefix_isolation(runners, windows):
    """Authorize only this player's mounted Windows views in private runners.

    Keep the real UMU distribution untouched. Its usual escape rejection is
    retained for every other directory; runner DLL link repair is unchanged.
    OverlayFS lower hardlinks are already isolated by copy-up.
    """
    if not windows:
        return
    allowed=repr(tuple(str(Path(path).resolve()) for path in windows))
    guard='    if not windows.resolve().is_relative_to(prefix):'
    shared='shared = not path.is_symlink() and path.stat().st_nlink > 1'
    for runner in runners:
        runner=Path(runner)
        path=runner/'umu-batocera/prefix-isolation.py'
        if not path.exists():
            continue
        if path.is_symlink() or path.resolve()!=path.absolute():
            raise RuntimeError(tr('Protection de préfixe redirigée : {p0}',p0=path))
        source=path.read_text()
        if source.count(guard)!=1 or source.count(shared)!=1:
            raise RuntimeError(tr('Version de protection UMU non reconnue : {p0}',p0=path))
        updated=source.replace(guard,
            f'    private_windows = str(windows.resolve()) in {allowed}\n'
            '    if not private_windows and not windows.resolve().is_relative_to(prefix):')
        updated=updated.replace(shared,'shared = not private_windows and not path.is_symlink() and path.stat().st_nlink > 1')
        manifest=runner/'umu-batocera/integrity.sha256'
        manifest_text=None
        if manifest.exists():
            old=hashlib.sha256(source.encode()).hexdigest()
            manifest_text=manifest.read_text()
            pattern=re.compile(r'(?m)^([a-fA-F0-9]{64})([ \t]+[* ]?(?:\./)?umu-batocera/prefix-isolation\.py)$')
            matches=list(pattern.finditer(manifest_text))
            if len(matches)!=1 or matches[0][1].lower()!=old:
                raise RuntimeError(tr('Intégrité de la protection UMU invalide : {p0}',p0=path))
            manifest_text=pattern.sub(lambda m:hashlib.sha256(updated.encode()).hexdigest()+m[2],manifest_text)
        from partydeck_profiles import atomic_write
        atomic_write(path,updated,stat.S_IMODE(path.stat().st_mode))
        if manifest_text is not None:
            atomic_write(manifest,manifest_text,stat.S_IMODE(manifest.stat().st_mode))

if __name__=='__main__':
    import sys
    if sys.argv[1:]==['_probe']:
        probe_filesystem()
    else:
        raise SystemExit('Private helper: _probe')
