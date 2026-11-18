"""Real temporary files: eviction, protected data, locks and low disk refusal."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_storage as storage


def file(path, size=4096, age=3600):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'x' * size)
    os.utime(path, (time.time()-age, time.time()-age))
    return path


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    base, saves = root/'system', root/'saves'
    base.mkdir()
    rom = root/'Game.wsquashfs'
    digest, name = storage.identity(rom)
    player = base/'party'/digest/'j1'
    config = dict(storage.DEFAULTS, cache_mib=2, logs_mib=4, log_file_mib=1, log_keep=3)
    storage.save_settings(base, config)
    assert storage.settings(base) == config
    prior = (base/'storage.json').read_bytes()
    try:
        storage.save_settings(base, dict(config, cache_mib=-1))
    except ValueError:
        pass
    else:
        raise AssertionError('accepted invalid configuration')
    assert (base/'storage.json').read_bytes() == prior
    # The budget is global, not multiplied by players/games. Oldest files go first.
    oldest = file(base/'cache'/'older', 2*storage.MIB, 7200)
    latest = file(player/'cache'/'newer', storage.MIB)
    persistent = [file(saves/name/'j1'/'windows'/'save.dat'),
                  file(saves/name/'j1'/'prefixes'/'user.reg'),
                  file(saves/name/'j1'/'content'/'upper'/'slot.dat'),
                  file(player/'wine-run'/'slot.sav'),
                  file(player/'umu-private'/'materialized-prefixes'/'game'/'save.dat'),
                  file(player/'umu'/'upper'/'user.reg')]
    backups = {p: p.read_bytes() for p in persistent}
    outside = file(root/'external'/'precious')
    (base/'cache'/'outside').symlink_to(outside.parent, target_is_directory=True)
    (player/'cache'/'linked-file').symlink_to(outside)
    os.link(outside, base/'cache'/'hardlink')
    # Mounted cache subtrees and open files cannot be deleted, even during purge.
    mounted = file(base/'cache'/'mounted'/'keep')
    opened = file(base/'cache'/'opened')
    with opened.open('rb') as stream, patch.object(storage, 'mounted_paths', return_value={mounted.parent}):
        result = storage.clean(base)
        assert not oldest.exists() and latest.exists()
        assert opened.exists() and mounted.exists() and outside.exists()
        assert result['freed'] >= storage.MIB
        storage.clean(base, purge=True)
        assert not latest.exists() and opened.exists() and mounted.exists()
    assert (base/'cache'/'hardlink').exists()
    assert all(p.read_bytes() == content for p, content in backups.items())
    # Per-file log tails, global count, open-log and fresh-file exemptions.
    for path in (base/'cache').glob('*'):
        if path.is_file() and not path.is_symlink():
            path.unlink()
    log = file(player/'proton-logs'/'large.log', 5*storage.MIB)
    with log.open('ab') as stream:
        stream.write(b'END')
    os.utime(log, (time.time()-3600,)*2)
    storage.clean(base)
    assert log.stat().st_size == storage.MIB and log.read_bytes().endswith(b'END')
    for i in range(5):
        file(base/'logs'/f'old-{i}', age=3600+i)
    active = file(base/'logs'/'active', age=10000)
    with active.open('rb'):
        storage.clean(base)
        assert active.exists()
    assert sum(1 for _ in storage.files(base/'logs')) <= 3
    # Interrupted installer staging is reclaimable; prefix data is never guessed.
    stale = file(base/'releases'/'.partydeck-aborted'/'AppImage', age=90000)
    os.utime(stale.parent, (time.time()-90000,)*2)
    fresh = file(base/'.coop-fresh'/'data', age=0)
    storage.clean(base)
    assert not stale.parent.exists() and fresh.exists()
    with storage.storage_lock(base):
        try:
            storage.clean(base)
        except RuntimeError:
            pass
        else:
            raise AssertionError('cleaned during a session')
    # An OS-released lock after a killed process does not permanently block cleanup.
    code = ('import fcntl,sys; f=open(sys.argv[1],"a"); '
            'fcntl.flock(f,fcntl.LOCK_EX); print("locked",flush=True); sys.stdin.read()')
    process = subprocess.Popen([sys.executable,'-c',code,str(base/'storage.lock')],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    assert process.stdout.readline().strip() == 'locked'
    try:
        storage.clean(base)
    except RuntimeError:
        pass
    else:
        raise AssertionError('ignored another process lock')
    process.terminate()
    process.wait(timeout=5)
    storage.clean(base)
    # Detect an orphan compositor even after the original lock owner died.
    process = subprocess.Popen([str(base/'releases'/'test'/'gamescope-kbm'),'-c',
                                'import sys; print("ready",flush=True); sys.stdin.read()'],
                               executable=sys.executable,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    assert process.stdout.readline().strip() == 'ready'
    try:
        try:
            storage.clean(base)
        except RuntimeError as error:
            assert 'encore active' in str(error)
        else:
            raise AssertionError('ignored an orphan compositor')
    finally:
        process.terminate()
        process.wait(timeout=5)
    # Low free space refuses before any game process can start. 0 disables guard.
    low = [dict(path=str(base), free=storage.MIB, total=100*storage.MIB)]
    with patch.object(storage, 'disks', return_value=low):
        try:
            with storage.session(base, saves):
                raise AssertionError('started on full disk')
        except RuntimeError as error:
            assert 'Espace insuffisant' in str(error)
        storage.preflight(base, saves, dict(config, reserve_mib=0))
    # Reporting includes leftovers and per-game allocations, without link inflation.
    file(base/'profiles'/'game.json', 1)
    (base/'profiles'/'game.json').write_text(json.dumps({'rom':str(rom)}))
    report = storage.snapshot(base, saves)
    assert report['categories']['persistent'] > 0 and report['categories']['runtime'] > 0
    assert report['games'][0]['name'] == 'Game'
    assert report['total'] == sum(report['categories'].values())
    assert all(p.read_bytes() == content for p, content in backups.items())
    # A renamed/symlinked cache root must never expose external save data to purge.
    linked = base/'coop'/'aaaaaaaaaaaaaaaa'/'j1'
    linked.mkdir(parents=True)
    (linked/'cache').symlink_to(outside.parent, target_is_directory=True)
    storage.clean(base, purge=True)
    assert outside.exists()
    # The installed shell entry point must dispatch storage without graphical
    # initialization/network access or recursively taking its own flock.
    script = Path(__file__).resolve().parents[1]/'scripts'/'install-partydeck-test.sh'
    launcher = root/'launcher.sh'
    launcher.write_text(script.read_text().replace("base='/userdata/system/partydeck-test'", f"base='{base}'"))
    (base/'partydeck_storage.py').write_text(Path(storage.__file__).read_text())
    bin_dir = root/'bin'
    bin_dir.mkdir()
    batocera = bin_dir/'batocera-version'
    batocera.write_text('#!/bin/sh\necho 44-test\n')
    batocera.chmod(0o755)
    env = dict(os.environ, PATH=str(bin_dir)+os.pathsep+os.environ['PATH'])
    for action in ('reglages','bilan','nettoyer'):
        result = subprocess.run(['bash',str(launcher),'stockage',action],env=env,
                                capture_output=True,text=True,check=True,timeout=10)
        assert isinstance(json.loads(result.stdout),dict)
    spec = importlib.util.spec_from_file_location('storage_coop', script.parent/'partydeck-batocera-coop.py')
    coop = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = coop
    spec.loader.exec_module(coop)
    # Detailed Proton output defaults off; UI diagnostics and explicit overrides work.
    umu = base/'umu-host'
    umu.mkdir()
    with patch.object(coop,'UMU_HOME',umu), patch.object(coop,'UMU_LOGS',base/'host-logs'), \
         patch.object(coop,'UMU_SESSION_STATE',base/'session-state'), patch.object(coop,'WRITABLE',{}), \
         patch.dict(os.environ,{},clear=True):
        args = coop.sandbox_arguments(player,[],hidraw=root/'no-hidraw')
        index = args.index('PROTON_LOG')
        assert args[index+1] == '0'
        storage.save_settings(base,dict(config,diagnostic=True))
        args = coop.sandbox_arguments(player,[],hidraw=root/'no-hidraw')
        assert args[args.index('PROTON_LOG')+1] == '1'
        with patch.dict(os.environ,{'PROTON_LOG':'0'}):
            args = coop.sandbox_arguments(player,[],hidraw=root/'no-hidraw')
            assert args[args.index('PROTON_LOG')+1] == '0'
    with patch.object(storage,'disks',return_value=low), patch.object(coop,'start_player') as start:
        try:
            coop.run_session(base,base,rom,rom,'2','horizontal','auto',party=True)
        except RuntimeError as error:
            assert 'Espace insuffisant' in str(error)
        else:
            raise AssertionError('started despite full disk')
        start.assert_not_called()

print('Stockage : budgets globaux, préservation, liens, montages, fichiers ouverts, verrous et manque d’espace vérifiés.')
