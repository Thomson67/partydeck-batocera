"""Player-local copy-on-write Proton distributions for nested Steam Runtime.

The distribution is read-only to the native UMU wrapper's protection pass.
Pressure Vessel can bind the private overlay writable inside Steam Runtime.
No shared runner files are made writable or copied in full.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from partydeck_i18n import tr


@contextmanager
def runner_views(player,runners=Path('/userdata/system/wine/custom')):
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
    try:
        for index,runner in enumerate(candidates):
            slot=area/str(index)
            upper,work,view=(slot/name for name in ('upper','work','view'))
            for path in (upper,work,view):path.mkdir(parents=True)
            options=f'lowerdir={runner},upperdir={upper},workdir={work},redirect_dir=on'
            subprocess.run(['mount','-t','overlay','-o',options,'overlay',str(view)],check=True)
            mounted.append(view)
            subprocess.run(['mount','--bind',str(view),str(runner)],check=True)
            mounted.append(runner)
            # Existing UMU protection refuses writable runner mountpoints.
            # Its integrity check sees the unmodified lower distribution.
            subprocess.run(['mount','-o','remount,bind,ro',str(runner)],check=True)
        print(tr('UMU : vues privées temporaires des runners préparées ({p0}).',p0=len(candidates)),flush=True)
        yield candidates
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


def pressure_vessel_environment(paths,environ=None):
    env=dict(os.environ if environ is None else environ)
    entries=[entry for entry in env.get('PRESSURE_VESSEL_FILESYSTEMS_RW','').split(':') if entry]
    entries.extend(str(path) for path in paths if str(path) not in entries)
    if paths:env['PRESSURE_VESSEL_FILESYSTEMS_RW']=':'.join(entries)
    return env
