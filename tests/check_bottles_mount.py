"""Run with: unshare -Urnm python3 tests/check_bottles_mount.py.

Real Linux OverlayFS: isolated writes/deletions, native-style cp -a, stable
symlinks across materialization/return, compaction and remount persistence.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_bottles as b
from check_bottles import fixture

if os.geteuid()!=0:raise SystemExit('Run inside unshare -Urnm (private user and mount namespaces).')
subprocess.run(['mount','--make-rprivate','/'],check=True)
# Rootless OverlayFS requires userxattr and forbids redirect_dir=on. Batocera
# runs as real root and uses trusted overlay attributes instead.
real_run=subprocess.run
def rootless_run(command,**kwargs):
    if command[:3]==['mount','-t','overlay']:
        command=list(command)
        index=command.index('-o')+1
        command[index]=command[index].replace('redirect_dir=on','redirect_dir=off')+',userxattr'
    return real_run(command,**kwargs)
b.subprocess.run=rootless_run
with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as folder:
    root=Path(folder)
    with patch.object(b,'ROOT',root/'bottles'):
        original,players=fixture(root)
        views=[];slots=[]
        for player,saves in players:
            b.prepare(player,saves,original,original)
            view,=b.mount_windows(player)
            views.append(view);slots.append(view.parent)
            prefix=b.location(player)/'prefixes/Runner/Game.wine'
            materialized=root/('materialized-'+player.name)
            subprocess.run(['cp','-a',str(prefix),str(materialized)],check=True)
            assert (materialized/'drive_c/windows').is_symlink()
            assert os.readlink(materialized/'drive_c/windows')==str(view)
            assert (materialized/'drive_c/windows/system32/shared.dll').read_bytes()==(original/'drive_c/windows/system32/shared.dll').read_bytes()
        # All prefix access, including a materialized copy, uses the right view.
        first=root/'materialized-j1/drive_c/windows'
        (first/'system32/shared.dll').write_bytes(b'J1 DLL override')
        (first/'inherited.txt').unlink()
        assert (views[1]/'system32/shared.dll').read_bytes().startswith(b'Windows runtime')
        assert (views[1]/'inherited.txt').exists()
        assert (original/'drive_c/windows/inherited.txt').exists()
        # Lower paths are read-only even when reached outside the overlay view.
        try:
            (slots[0]/'lower/system32/shared.dll').write_bytes(b'bad')
            raise AssertionError('lower writable')
        except OSError:pass
        for slot in slots:
            subprocess.run(['umount',str(slot/'view')],check=True)
            subprocess.run(['umount',str(slot/'lower')],check=True)
            subprocess.run(['umount',str(original/'drive_c/windows')],check=True)
        # Recompact the modified private file, remount: whiteout still masks
        # both the old manifest entry and the seed file for J1 only.
        for player,saves in players:
            b.prepare(player,saves,original,original)
            b.mount_windows(player)
        assert (views[0]/'system32/shared.dll').read_bytes()==b'J1 DLL override'
        assert not (views[0]/'inherited.txt').exists()
        assert (views[1]/'inherited.txt').exists()
        for slot in slots:
            subprocess.run(['umount',str(slot/'view')],check=True)
            subprocess.run(['umount',str(slot/'lower')],check=True)
            subprocess.run(['umount',str(original/'drive_c/windows')],check=True)
print('Real OverlayFS: J1/J2 writes, deletions, materialized prefix copies, read-only lowers and restart persistence verified.')
