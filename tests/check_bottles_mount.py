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
        views=[];slots=[];identities=[]
        import partydeck_hkmultiplayer as multi
        companion=root/'WindowsParty.HKMultiplayer.dll';companion.write_bytes(b'BRIDGE')
        wide=root/'WindowsParty.NativeWide.dll';wide.write_bytes(b'WIDE')
        for player,saves in players:
            b.prepare(player,saves,original,original)
            view,=b.mount_windows(player)
            views.append(view);slots.append(view.parent)
            prefix=b.location(player)/'prefixes/Runner/Game.wine'
            # The native handler must recognize only its own Windows COW view.
            assert b.private_windows_paths(player)==(view,)
            game=prefix/'drive_c/game'
            mods=game/'hollow_knight_Data/Managed/Mods/HKMultiplayer'
            mods.mkdir(parents=True)
            (mods/'HKMultiplayer.dll').write_bytes(b'USER MOD')
            (game/'hollow_knight.exe').write_bytes(b'GAME')
            payload=dict(player=str(player),index=int(player.name[1:])-1,width=1920,height=540,
                settings=multi.defaults(),code='ABCDEFGH',plugin=str(companion),wide_plugin=str(wide))
            multi.apply_config(game,prefix,payload,private_binds=())
            identity=view/'windows-party-hkmultiplayer-identity.json'
            saved=json.loads(identity.read_text())
            identities.append(saved)
            multi.apply_config(game,prefix,payload,private_binds=())
            assert json.loads(identity.read_text())==saved
            materialized=root/('materialized-'+player.name)
            subprocess.run(['cp','-a',str(prefix),str(materialized)],check=True)
            assert (materialized/'drive_c/windows').is_symlink()
            assert os.readlink(materialized/'drive_c/windows')==str(view)
            assert (materialized/'drive_c/windows/system32/shared.dll').read_bytes()==(original/'drive_c/windows/system32/shared.dll').read_bytes()
        assert identities[0]['key']!=identities[1]['key']
        assert identities[0]['player']==0 and identities[1]['player']==1
        # Even when both views exist in this test namespace, the J1 handler
        # cannot follow a redirected identity path into J2's Windows view.
        player,saves=players[0]
        prefix=b.location(player)/'prefixes/Runner/Game.wine'
        link=prefix/'drive_c/windows'
        link.unlink();link.symlink_to(views[1])
        payload=dict(player=str(player),index=0,width=1920,height=540,
            settings=multi.defaults(),code='ABCDEFGH',plugin=str(companion),wide_plugin=str(wide))
        try:
            multi.apply_config(prefix/'drive_c/game',prefix,payload,private_binds=())
            raise AssertionError('J1 handler accepted J2 Windows view')
        except ValueError:pass
        finally:
            link.unlink();link.symlink_to(views[0])
        assert json.loads((views[1]/'windows-party-hkmultiplayer-identity.json').read_text())==identities[1]
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
        assert all(json.loads((view/'windows-party-hkmultiplayer-identity.json').read_text())==saved for view,saved in zip(views,identities))
        assert (views[0]/'system32/shared.dll').read_bytes()==b'J1 DLL override'
        assert not (views[0]/'inherited.txt').exists()
        assert (views[1]/'inherited.txt').exists()
        for slot in slots:
            subprocess.run(['umount',str(slot/'view')],check=True)
            subprocess.run(['umount',str(slot/'lower')],check=True)
            subprocess.run(['umount',str(original/'drive_c/windows')],check=True)
print('Real OverlayFS: J1/J2 writes, deletions, materialized prefix copies, read-only lowers, HKMultiplayer private identities and restart persistence verified.')
