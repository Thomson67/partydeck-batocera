"""Player-local copy-on-write Proton distributions for nested Steam Runtime.

The distribution is read-only to the native UMU wrapper's protection pass.
UMU receives a separate writable alias before it builds Steam Runtime mounts.
No shared runner files are made writable or copied in full.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from partydeck_i18n import tr


STEAM_RUNTIMES = ('steamrt2', 'steamrt3', 'steamrt4', 'steamrt4-arm64',
                  'soldier', 'sniper')
STEAM_RUNTIME_HOME = Path('home/.local/share/umu')
STEAM_RUNTIME_APPIDS = {'1391110': ('steamrt2', 'soldier'),
                        '1628350': ('steamrt3', 'sniper'),
                        '4183110': ('steamrt4',), '4185400': ('steamrt4-arm64',)}


def installed_steam_runtimes(home):
    root = home / STEAM_RUNTIME_HOME
    if root.resolve() != root:
        return ()
    return tuple(name for name in STEAM_RUNTIMES
                 if (root / name).is_dir() and not (root / name).is_symlink()
                 and all((root / name / entry).is_file()
                         for entry in ('_v2-entry-point', 'VERSIONS.txt', 'mtree.txt.gz'))
                 and (root / name / 'pressure-vessel').is_dir()
                 and any(path.is_dir() for path in (root / name).glob('*_platform_*')))


def use_shared_steam_runtime(proton, available):
    import re
    try:
        manifest = (Path(proton) / 'toolmanifest.vdf').read_text()
    except (OSError, UnicodeError):
        return False
    appid = re.search(r'"require_tool_appid"\s*"?(\d+)"?', manifest)
    return bool(appid and set(STEAM_RUNTIME_APPIDS.get(appid[1], ())).intersection(available))


def prepare_shared_steam_runtimes(home, game, runners=Path('/userdata/system/wine/custom')):
    """Bootstrap only runtimes already needed by this game's private cache."""
    available = installed_steam_runtimes(home)
    requested = {name for name in STEAM_RUNTIMES if name not in available
                 and any(game.glob(f'j*/umu/upper/{STEAM_RUNTIME_HOME}/{name}'))}
    runtime_root = home / STEAM_RUNTIME_HOME
    if not requested:
        return available
    if runtime_root.resolve() != runtime_root or not (home / 'umu-run').is_file():
        print(f"UMU Steam Runtime: shared bootstrap unavailable at {runtime_root}", flush=True)
        return available
    for runner in sorted(runners.glob('*-UMU')):
        bridge = runner / 'umu-batocera/umu-root-runner.py'
        matches = {name for name in requested if use_shared_steam_runtime(runner, (name,))}
        if not matches or not bridge.is_file():
            continue
        requested.difference_update(matches)
        environment = dict(os.environ, HOME=str(home / 'home'), XDG_CACHE_HOME=str(home / 'cache'),
                           PROTONPATH=str(runner))
        environment.pop('XDG_DATA_HOME', None)
        try:
            subprocess.run(['python3', str(bridge), str(home / 'umu-run'), '--prepare-runtime'],
                           env=environment, check=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as error:
            print(f"UMU Steam Runtime: {error}", flush=True)
        if not requested:
            break
    available = installed_steam_runtimes(home)
    print(f"UMU Steam Runtime: host variants = {', '.join(available) or 'none'}", flush=True)
    return available


def clean_shared_steam_runtimes(player, available):
    """Remove only private copies of runtime variants installed on the host."""
    from partydeck_storage import mounted_paths
    area = player / 'umu'
    scratch = area / 'runtime-cache' / 'upper'
    mounts = mounted_paths()
    for root in (area / 'upper' / STEAM_RUNTIME_HOME,
                 area / 'shared' / STEAM_RUNTIME_HOME, scratch):
        if root.resolve() != root:
            continue
        for name in available:
            path = root / name
            if path.is_dir() and not path.is_symlink() and not any(
                    mount == path or path in mount.parents for mount in mounts):
                shutil.rmtree(path)
    # Missing host variants can still use their existing private installation.
    legacy = area / 'upper' / STEAM_RUNTIME_HOME
    if legacy.resolve() == legacy and available:
        from partydeck_bottles import regular_directory
        for name in set(STEAM_RUNTIMES).difference(available):
            old, new = legacy / name, scratch / name
            if old.is_dir() and not old.is_symlink() and not (new.exists() or new.is_symlink()):
                if not any(mount == old or old in mount.parents for mount in mounts):
                    regular_directory(scratch)
                    old.rename(new)


def compact_steam_runtime(player):
    """Share large Steam Runtime files, keeping the rest of UMU's home private."""
    from functools import lru_cache
    from partydeck_bottles import ROOT, compact_tree

    area = player / 'umu'
    upper, shared = area / 'upper', area / 'shared'
    relative = Path('home/.local/share/umu')

    @lru_cache(maxsize=None)
    def visible_lower(directory):
        # After an upper file is removed its lower copy must be visible.
        # A previous Steam Runtime update may have hidden or redirected a
        # parent directory in OverlayFS. Leave that generation alone.
        if any(key in ('trusted.overlay.opaque', 'trusted.overlay.redirect',
                       'user.overlay.opaque', 'user.overlay.redirect')
               for key in os.listxattr(directory, follow_symlinks=False)):
            return False
        return directory == upper or visible_lower(directory.parent)

    def eligible(path, info):
        return info.st_size >= 256 * 1024 and visible_lower(path.parent)

    size = 0
    for name in STEAM_RUNTIMES:
        path = relative / name
        source = upper / path
        if source.is_dir() and source.resolve() == source:
            result = compact_tree(source, shared / path, ROOT / 'objects', eligible=eligible)
            size += result['shared']
    if size:
        print(f"UMU {player.name.upper()}: Steam Runtime shared bytes={size}", flush=True)


@contextmanager
def runner_views(player,runners=Path('/userdata/system/wine/custom'),
                 umu=Path('/userdata/system/umu/umu-run'), shared_runtimes=()):
    candidates=sorted(path.resolve() for path in runners.glob('*-UMU')
                      if path.is_dir() and (path/'proton').is_file())
    candidates=list(dict.fromkeys(candidates))
    if not candidates:
        yield []
        return
    player=player.resolve()
    if os.environ.get('PARTYDECK_PRIVATE_PLAYER')!=str(player):
        raise RuntimeError(tr('Contexte privé UMU absent.'))
    # OverlayFS path separators cannot be escaped by string interpolation.
    if any(any(c in str(path) for c in ',:\\\n\r') for path in [player,*candidates]):
        raise RuntimeError(tr('Chemin incompatible avec la vue privée UMU.'))
    area=Path(tempfile.mkdtemp(prefix='.proton-',dir=player))
    mounted=[]
    aliases={}
    try:
        for index,runner in enumerate(candidates):
            slot=area/str(index)
            upper,work=(slot/name for name in ('upper','work'))
            # Proton may persist links into its distribution in the prefix.
            # Recreate a stable alias each launch, independent of runner order
            # and temporary upper names; never persist random .proton-* paths.
            view=player/'proton-runners'/runner.name
            for path in (upper,work,view):path.mkdir(parents=True,exist_ok=True)
            options=f'lowerdir={runner},upperdir={upper},workdir={work},redirect_dir=on'
            subprocess.run(['mount','-t','overlay','-o',options,'overlay',str(view)],check=True)
            mounted.append(view)
            aliases[str(runner)]=str(view)
            subprocess.run(['mount','--bind',str(view),str(runner)],check=True)
            mounted.append(runner)
            # Existing UMU protection refuses writable runner mountpoints.
            # Its integrity check sees the unmodified lower distribution.
            subprocess.run(['mount','-o','remount,bind,ro',str(runner)],check=True)
        # A RW export does not clear a source bind's read-only flag. Preserve
        # that bind for the wrapper but pass the writable alias to UMU itself.
        # This runs inside the player's mount namespace and private UMU home.
        if umu.is_file():
            original=area/'umu-original.pyz'
            original.touch()
            subprocess.run(['mount','--bind',str(umu),str(original)],check=True)
            mounted.append(original)
            relay=area/'umu-relay.py'
            relay.write_text(launcher_relay(original, aliases, player, shared_runtimes))
            subprocess.run(['mount','--bind',str(relay),str(umu)],check=True)
            mounted.append(umu)
        print(tr('UMU : vues privées temporaires des runners préparées ({p0}).',p0=len(candidates)),flush=True)
        yield list(aliases.values())
    finally:
        clean=True
        for path in reversed(mounted):
            try:
                result=subprocess.run(['umount','--',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                if result.returncode:
                    # A lazy detach can still be held by a descendant. Retain
                    # its upper layer instead of deleting in-use files.
                    clean=False
                    subprocess.run(['umount','-l','--',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:clean=False
        if clean:shutil.rmtree(area)
        else:print(tr('UMU : nettoyage différé de {p0}.',p0=area),flush=True)


def pressure_vessel_environment(paths, environ=None, *, writable=True):
    env=dict(os.environ if environ is None else environ)
    key = 'PRESSURE_VESSEL_FILESYSTEMS_RW' if writable else 'PRESSURE_VESSEL_FILESYSTEMS_RO'
    entries=[entry for entry in env.get(key, '').split(':') if entry]
    entries.extend(str(path) for path in paths if str(path) not in entries)
    if paths:env[key]=':'.join(entries)
    return env


def launcher_relay(original, aliases, player=None, shared_runtimes=()):
    """Prepare the selected private runner, then run the original UMU launcher.

    The original zipapp is pinned by a private bind before covering its normal
    path. Neither the installed runner nor the host UMU launcher is rewritten.
    """
    hook = ''
    if player is not None:
        base = Path(__file__).resolve().parent
        if shared_runtimes:
            hook = (
                f"    sys.path.insert(0,{str(base)!r})\n"
                "    from partydeck_umu import use_shared_steam_runtime\n"
                f"    if use_shared_steam_runtime(selected,{tuple(shared_runtimes)!r}):\n"
                "        os.environ['UMU_RUNTIME_UPDATE']='0'\n"
                "        print('Windows Party: using the host Steam Runtime',flush=True)\n"
                "    sys.path.pop(0)\n"
            )
        hook += (
            "    if os.environ.get('PARTYDECK_CELESTENET') == '1':\n"
            "        from pathlib import Path\n"
            f"        sys.path.insert(0,{str(base)!r})\n"
            "        from partydeck_celestenet import prepare_umu_viewport,unmount_variant\n"
            f"        mounted=prepare_umu_viewport(Path({str(player)!r}))\n"
            "        sys.path.pop(0)\n"
            "    if os.environ.get('PARTYDECK_DST') == '1':\n"
            "        from pathlib import Path\n"
            f"        sys.path.insert(0,{str(base)!r})\n"
            "        from partydeck_celestenet import unmount_variant\n"
            "        from partydeck_dst import prepare_umu\n"
            f"        mounted=prepare_umu(Path({str(player)!r}))\n"
            "        sys.path.pop(0)\n"
        )
    return ("import os,runpy,sys\n"
            f"aliases={aliases!r}\n"
            "mounted=()\n"
            "selected=os.path.realpath(os.environ.get('PROTONPATH',''))\n"
            "if selected in aliases:\n"
            "    os.environ['PROTONPATH']=aliases[selected]\n"
            "    print('Windows Party UMU PROTONPATH='+aliases[selected],flush=True)\n"
            + hook +
            f"sys.argv[0]={str(original)!r}\n"
            "try:\n"
            "    runpy.run_path(sys.argv[0],run_name='__main__')\n"
            "finally:\n"
            "    if mounted:\n"
            "        unmount_variant(mounted)\n")
