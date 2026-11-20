"""Real-file migration, Windows deduplication and interrupted transition recovery."""
import errno
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_bottles as b
from partydeck_storage import snapshot,identity


def fixture(root, count=2):
    original=root/'Game.wine'
    windows=original/'drive_c/windows'
    windows.mkdir(parents=True)
    (windows/'system32').mkdir()
    (windows/'system32/shared.dll').write_bytes(b'Windows runtime'*8192)
    (windows/'inherited.txt').write_text('original Windows file')
    players=[]
    digest,name=identity(original)
    for i in range(1,count+1):
        player=root/'app/runtime'/digest/f'j{i}';player.mkdir(parents=True)
        saves=root/'saves'/name/f'j{i}';saves.mkdir(parents=True)
        prefix=saves/'prefixes/Runner/Game.wine'
        (prefix/'drive_c').mkdir(parents=True)
        shutil.copytree(windows,prefix/'drive_c/windows')
        users=prefix/'drive_c/users/root/AppData'
        users.mkdir(parents=True)
        (users/'progress.dat').write_text(f'private save J{i}')
        (prefix/'user.reg').write_text(f'private registry J{i}')
        (saves/'windows').mkdir();(saves/'windows/slot.sav').write_text(f'external J{i}')
        players.append((player,saves))
    return original,players


def run():
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        with patch.object(b,'ROOT',root/'bottles'):
            original,players=fixture(root)
            before={}
            for player,saves in players:
                before[player.name]=(saves/'prefixes/Runner/Game.wine/drive_c/users/root/AppData/progress.dat').read_bytes()
                b.prepare(player,saves,original,original)
                area=b.location(player)
                assert saves.joinpath('prefixes').is_symlink()
                assert (area/'prefixes/Runner/Game.wine').is_dir()
                assert not (area/'prefixes/Runner/Game.wine').is_symlink()
                assert (area/'prefixes/Runner/Game.wine/drive_c/users/root/AppData/progress.dat').read_bytes()==before[player.name]
                assert (area/'prefixes/Runner/Game.wine/user.reg').read_text()==f'private registry {player.name.upper()}'
                assert (saves/'windows/slot.sav').read_text()==f'external {player.name.upper()}'
                slot=next((area/'windows').iterdir())
                assert not (slot/'upper/system32/shared.dll').exists()
                assert (slot/'lower/system32/shared.dll').read_bytes()==(original/'drive_c/windows/system32/shared.dll').read_bytes()
            objects=list((b.ROOT/'objects').glob('[a-f0-9][a-f0-9]/'+'[a-f0-9]'*64))
            assert len(objects)==2
            assert all(p.stat().st_nlink==3 for p in objects) # one store + two private manifests
            # Repeated preparation is idempotent and retains all private files.
            for player,saves in players:b.prepare(player,saves,original,original)
            # A newly created player gets no technical compatibility entry in saves.
            fresh=root/'app/runtime'/players[0][0].parent.name/'j3';fresh.mkdir()
            save3=players[0][1].parent/'j3';save3.mkdir()
            b.prepare(fresh,save3,original,original)
            assert not (save3/'prefixes').exists()
            assert not (save3/'content').exists()
            # Recover rename interrupted before creation of the old absolute alias.
            player,saves=players[0];area=b.location(player)
            (saves/'prefixes').unlink()
            b.atomic_json(area/'.migrate-prefixes.json',str((saves/'prefixes').absolute()))
            b.migrate(player,saves)
            assert (saves/'prefixes').resolve()==area/'prefixes'
            # Conflicting source and destination must never be merged or deleted.
            (saves/'prefixes').unlink();(saves/'prefixes').mkdir()
            (saves/'prefixes/precious').write_text('keep')
            try:b.migrate(player,saves);raise AssertionError('conflict accepted')
            except RuntimeError:pass
            assert (saves/'prefixes/precious').read_text()=='keep'
            # Global report counts shared inode allocations only once.
            report=snapshot(root/'app',root/'saves')
            assert report['categories']['bottles']>0
            assert report['total']==sum(report['categories'].values())
            # Garbage collection never removes any referenced object or unknown file.
            assert b.collect_objects()==0
            loose=b.ROOT/'objects/aa'/('a'*64);loose.parent.mkdir(exist_ok=True);loose.write_text('unreferenced')
            unknown=loose.parent/'do-not-delete';unknown.write_text('user')
            assert b.collect_objects()>0 and not loose.exists() and unknown.exists()
    # Failure to hardlink/cross-device compaction leaves the private data intact.
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder);upper=root/'upper';upper.mkdir();(upper/'data.dll').write_bytes(b'keep')
        with patch.object(b.os,'link',side_effect=OSError(errno.EXDEV,'cross-device')):
            assert b.compact_tree(upper,root/'lower',root/'objects')['files']==0
        assert (upper/'data.dll').read_bytes()==b'keep'

    # Compressed Windows extraction is cached per archive generation. The
    # extraction process is stubbed here; actual OverlayFS is tested separately.
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        original,players=fixture(root)
        archive=root/'Game.wsquashfs';archive.write_bytes(b'archive generation 1')
        real_run=b.subprocess.run
        extractions=[]
        def extract(command,**kwargs):
            if command[0]=='unsquashfs':
                destination=Path(command[command.index('-d')+1])
                shutil.copytree(original/'drive_c/windows',destination/'drive_c/windows',symlinks=True)
                extractions.append(command)
                return type('Result',(),dict(returncode=0,stderr=''))()
            return real_run(command,**kwargs)
        with patch.object(b,'ROOT',root/'bottles'),patch.object(b.subprocess,'run',side_effect=extract):
            seed=b.seed_windows(archive,archive)
            assert (seed/'system32/shared.dll').read_bytes()==(original/'drive_c/windows/system32/shared.dll').read_bytes()
            assert b.seed_windows(archive,archive)==seed and len(extractions)==1
            archive.write_bytes(b'archive generation 2 changed')
            assert b.seed_windows(archive,archive)!=seed and len(extractions)==2
    print('Bottles: private saves/registries, shared Windows inodes, migration recovery/conflicts, safe hardlink fallback and accounting verified.')


if __name__=='__main__':run()

# UMU authorization remains confined to this player's known Windows views.
with tempfile.TemporaryDirectory() as folder:
    import hashlib
    root=Path(folder);runner=root/'Runner-UMU'
    helper=runner/'umu-batocera/prefix-isolation.py';helper.parent.mkdir(parents=True)
    source='''from pathlib import Path

def isolate(prefix, windows, path):
    if not windows.resolve().is_relative_to(prefix):
        raise ValueError('Windows directory escapes the prefix')
    shared = not path.is_symlink() and path.stat().st_nlink > 1
    return shared
'''
    helper.write_text(source)
    manifest=helper.with_name('integrity.sha256')
    manifest.write_text(hashlib.sha256(source.encode()).hexdigest()+'  umu-batocera/prefix-isolation.py\n')
    windows=root/'private-view';windows.mkdir();file=windows/'file';file.write_bytes(b'Windows')
    os.link(file,windows/'other-link')
    b.adapt_prefix_isolation([runner],[windows])
    assert manifest.read_text().split()[0]==hashlib.sha256(helper.read_bytes()).hexdigest()
    scope={};exec(helper.read_text(),scope)
    assert scope['isolate'](root/'prefix',windows,file) is False
    try:scope['isolate'](root/'prefix',root/'other-player',file);raise AssertionError('other player accepted')
    except ValueError:pass
    helper.write_text(source)
    manifest.write_text('0'*64+'  umu-batocera/prefix-isolation.py\n')
    try:b.adapt_prefix_isolation([runner],[windows]);raise AssertionError('invalid integrity accepted')
    except RuntimeError:pass
    assert helper.read_text()==source
print('Private UMU adapter: exact view authorization, other-player rejection and original integrity verification pass.')
