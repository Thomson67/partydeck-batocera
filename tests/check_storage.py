"""Real temporary files: eviction, protected data, locks and low disk refusal."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import hashlib
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_storage as storage
import partydeck_bottles as bottles


with tempfile.TemporaryDirectory() as directory:
    game = Path(directory)/'runtime'/'c762298afdf53e67'
    player = game/'j1'
    work = player/'umu-private/materialized-prefixes'
    records = player/'umu/upper/runtime-prefix-state'
    records.mkdir(parents=True)
    for phase in ('disposable', 'recovery', 'running', 'unknown'):
        (work/phase).mkdir(parents=True)
        (work/phase/'user.reg').write_text(phase)
        if phase != 'unknown':
            key = hashlib.sha256(phase.encode()).hexdigest()
            (records/f'{key}.json').write_text(json.dumps(dict(
                version=1, prefix=f'/userdata/system/umu/materialized-prefixes/{phase}',
                phase=phase, pid=42 if phase == 'running' else 0)))
    other = player/'umu-private/compatdata'
    other.mkdir()
    with patch.object(storage, 'umu_mounts', return_value=set()):
        assert storage.clean_umu_work(game) == {'removed': 1, 'retained': 3}
        assert {p.name for p in work.iterdir()} == {'recovery', 'running', 'unknown'}
    bind = Path('/system').joinpath(*work.parts[-5:], 'running')
    with patch.object(storage, 'umu_mounts', return_value={bind}):
        assert storage.clean_umu_work(game, discard_recovery=True) == {'removed': 0, 'retained': 3}
    with patch.object(storage, 'umu_mounts', return_value=set()):
        assert storage.clean_umu_work(game, discard_recovery=True) == {'removed': 3, 'retained': 0}
        assert storage.clean_umu_work(game, discard_recovery=True) == {'removed': 0, 'retained': 0}
    assert other.is_dir() and not list(records.iterdir())


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
    player = base/'runtime'/digest/'j1'
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
    script = Path(__file__).resolve().parents[1]/'scripts'/'install-windows-party.sh'
    launcher = root/'launcher.sh'
    launcher.write_text(script.read_text().replace("base='/userdata/system/windows-party'", f"base='{base}'"))
    (base/'partydeck_storage.py').write_text(Path(storage.__file__).read_text())
    (base/'partydeck_i18n.py').write_text((Path(storage.__file__).parent/'partydeck_i18n.py').read_text())
    (base/'partydeck_bottles.py').write_text((Path(storage.__file__).parent/'partydeck_bottles.py').read_text())
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

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    base, saves, bottle_root = root/'system', root/'saves', root/'bottles'
    rom = file(root/'Game.wsquashfs')
    digest, name = storage.identity(rom)
    slot = saves/name
    bottle = bottle_root/'players'/digest
    prefix = file(bottle/'j1/prefixes/user.reg')
    (slot/'j1').mkdir(parents=True)
    migration_link = slot/'j1/prefixes'
    migration_link.symlink_to(prefix.parent)
    legacy = file(slot/'j2/content/upper/legacy.dat')
    externalized = file(slot/'j1/windows/slot.sav')
    runtime_prefix = file(base/'runtime'/digest/'j1/umu-private/materialized-prefixes/game/user.reg')
    private_overlay = file(bottle/'j2/content/upper/NFS Most Wanted 2005.bak/game.exe')
    solo_save = file(root/'solo/slot.sav')
    (prefix.parent/'dosdevices').symlink_to(solo_save.parent)
    (externalized.parent/'linked.sav').symlink_to(solo_save)
    kept = [rom, solo_save, file(bottle_root/'players'/'0000000000000000/j1/prefixes/user.reg'),
            file(bottle_root/'seeds/shared'), file(base/'profiles'/f'{digest}.json')]
    base.mkdir(exist_ok=True)
    with patch.object(storage, 'SAVES', saves), patch.object(bottles, 'ROOT', bottle_root):
        def expect_refusal():
            try:
                storage.clean_game(base, rom)
            except RuntimeError:
                pass
            else:
                raise AssertionError('unsafe game cleanup allowed')
            assert all(path.exists() for path in (prefix, legacy, externalized, runtime_prefix, private_overlay))

        with storage.storage_lock(base):
            expect_refusal()
        with patch.object(storage, 'mounted_paths', return_value={prefix.parent/'mounted-view'}):
            expect_refusal()
        with patch.object(storage, 'mounted_paths', return_value={legacy.parents[2]}):
            expect_refusal()
        redirected = slot/'j3'
        redirected.symlink_to(solo_save.parent)
        expect_refusal()
        redirected.unlink()
        assert storage.clean_game(base, rom)
        assert not bottle.exists() and not legacy.exists() and not runtime_prefix.exists()
        assert not private_overlay.exists()
        assert not migration_link.is_symlink() and externalized.exists()
        # Restarting a migrated game must not encounter a dangling migration link.
        bottles.migrate(base/'runtime'/digest/'j1', slot/'j1')
        assert prefix.parent.is_dir()
        assert storage.clean_game(base, rom, include_saves=True)
        assert not slot.exists() and not bottle.exists()
        assert not storage.clean_game(base, rom, include_saves=True)
        assert all(path.exists() for path in kept)

with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    rom = file(root/'Left 4 Dead 2.wsquashfs')
    digest, name = storage.identity(rom)
    private = root/'bottles/players'/digest
    config = file(private/'j1/prefixes/TKG/game.wine/drive_c/game/left4dead2/cfg/config.cfg')
    config.write_bytes(b'name2 "unnamed"\r\n')
    legacy = file(root/'saves'/name/'j2/content/upper/game/Left4Dead2/CFG/CONFIG.CFG')
    protected = [file(config.with_name('config_default.cfg')),file(config.with_name('autoexec.cfg')),
                 file(root/'saves'/name/'j1/windows/550/remote/left4dead2/cfg/config.cfg'),
                 file(root/'solo/left4dead2/cfg/config.cfg')]
    (private/'j3').symlink_to(protected[-1].parents[2],target_is_directory=True)
    with patch.object(storage,'SAVES',root/'saves'),patch.object(bottles,'ROOT',root/'bottles'):
        assert storage.reset_l4d2_config(root,rom)==2
        assert storage.reset_l4d2_config(root,rom)==0
    assert not config.exists() and not legacy.exists()
    assert next(config.parent.glob('config.cfg.partydeck-*/config.cfg')).read_bytes()==b'name2 "unnamed"\r\n'
    assert all(path.exists() for path in protected)

print('Stockage : budgets, préservation, verrous et nettoyage ciblé des bottles et sauvegardes vérifiés.')
