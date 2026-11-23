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
import partydeck_umu as umu
from check_bottles import fixture
import importlib
coop = importlib.import_module('partydeck-batocera-coop')

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
test_disk = os.environ.get('TMPDIR', Path(__file__).resolve().parents[2])
with tempfile.TemporaryDirectory(dir=test_disk) as folder:
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

with tempfile.TemporaryDirectory(dir=test_disk) as folder:
    root = Path(folder)
    runtime = Path('home/.local/share/umu/steamrt4')
    content = b'Steam Runtime' * 25600
    host = root / 'umu-host'
    host.mkdir()
    with patch.object(b, 'ROOT', root / 'bottles'):
        for number in (1, 2):
            player = root / f'j{number}'
            area = player / 'umu'
            source = area / 'upper' / runtime
            source.mkdir(parents=True)
            library = source / 'library.so'
            library.write_bytes(content)
            os.utime(library, (1, 1))
            (source / 'small').write_text('private')
            (area / 'upper/home/save').write_bytes(content)
            umu.compact_steam_runtime(player)
            assert not library.exists() and (source / 'small').is_file()
            assert (area / 'upper/home/save').is_file()
        a, c = [root / f'j{number}/umu/shared' / runtime / 'library.so' for number in (1, 2)]
        assert a.samefile(c)
        for number in (1, 2):
            area = root / f'j{number}/umu'
            coop.mount_overlay(host, area, shared=area / 'shared')
            library = host / runtime / 'library.so'
            assert library.read_bytes() == content
            if number == 1:
                library.write_bytes(b'J1 override')
                try:
                    a.write_bytes(b'write through shared path')
                    raise AssertionError('shared layer writable')
                except OSError:
                    pass
            for target in (host, area / 'view', area / 'shared'):
                subprocess.run(['umount', str(target)], check=True)
        assert a.read_bytes() == c.read_bytes() == content
print('Steam Runtime files have one shared inode and isolated OverlayFS writes.')

with tempfile.TemporaryDirectory(dir=test_disk) as folder:
    root = Path(folder)
    host = root / 'umu-system'
    runtime = host / umu.STEAM_RUNTIME_HOME / 'steamrt4'
    for name in ('pressure-vessel', 'steamrt4_platform_test'):
        (runtime / name).mkdir(parents=True)
    for name in ('_v2-entry-point', 'VERSIONS.txt', 'mtree.txt.gz', 'library.so'):
        (runtime / name).write_text('host')
    assert umu.installed_steam_runtimes(host) == ('steamrt4',)
    for index in (1, 2):
        player = root / f'j{index}'
        area = player / 'umu'
        old = area / 'upper' / umu.STEAM_RUNTIME_HOME / 'steamrt4'
        old.mkdir(parents=True)
        (old / 'library.so').write_text('private legacy copy')
        unrelated = area / 'upper' / 'home' / 'unrelated'
        unrelated.write_text('keep')
        umu.clean_shared_steam_runtimes(player, ('steamrt4',))
        assert not old.exists()
        assert coop.mount_umu_home(host, area) == ('steamrt4',)
        assert (runtime / 'library.so').read_text() == 'host'
        (runtime / 'library.so').write_text(f'player {index}')
        for target in (host / umu.STEAM_RUNTIME_HOME, host, area / 'view', area / 'runtime-cache/source'):
            subprocess.run(['umount', str(target)], check=True)
        assert (runtime / 'library.so').read_text() == 'host'
        umu.clean_shared_steam_runtimes(player, ('steamrt4',))
        assert not (area / 'runtime-cache/upper/steamrt4').exists()
        assert unrelated.read_text() == 'keep'
print('Host Steam Runtime mounted and reused by both players; private caches reclaimed.')
