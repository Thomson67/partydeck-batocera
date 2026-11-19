"""Conservative migration from the legacy test installation to Windows Party.

Rename, never copy ROMs or delete saves. Compatibility links keep absolute paths
inside existing Wine prefixes valid. Only generated launchers are rewritten.
"""
from pathlib import Path
import fcntl,json,os,re,shlex,sys,time
from partydeck_i18n import tr


def lock_installation(base,inherited_fd=None):
    locks=[];seen=set()
    try:
        for name in ('storage.lock','test.lock','session.lock'):
            path=base/name
            stream=path.open('a')
            stat=os.fstat(stream.fileno());identity=(stat.st_dev,stat.st_ino)
            if identity in seen:
                stream.close();continue
            seen.add(identity)
            if inherited_fd is not None:
                try:
                    parent=os.fstat(inherited_fd)
                    if identity==(parent.st_dev,parent.st_ino):
                        stream.close();stream=os.fdopen(os.dup(inherited_fd),'a')
                except OSError:pass
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:
                stream.close();raise
            locks.append(stream)
        return locks
    except (OSError,BlockingIOError):
        for stream in locks:stream.close()
        raise RuntimeError(tr('Fermez Windows Party avant la migration.')) from None


def migrate_root(legacy,current):
    legacy,current=Path(legacy),Path(current)
    current.parent.mkdir(parents=True,exist_ok=True)
    if current.is_symlink():raise ValueError(tr('Migration refusée : destination inattendue ({p0}).',p0=current))
    if legacy.is_symlink():
        if legacy.resolve()!=current.resolve():raise ValueError(tr('Migration refusée : destination inattendue ({p0}).',p0=legacy))
    elif legacy.exists():
        if current.exists():raise ValueError(tr('Migration refusée : deux installations existent.'))
        locks=lock_installation(legacy)
        try:
            legacy.rename(current)
            try:legacy.symlink_to(current,target_is_directory=True)
            except OSError:
                current.rename(legacy)
                raise
        finally:
            for stream in locks:stream.close()
    current.mkdir(parents=True,exist_ok=True)
    return current


def finalize(base,legacy,roms,ports):
    base,legacy,roms,ports=map(Path,(base,legacy,roms,ports))
    locks=lock_installation(base,inherited_fd=9)
    try:
        archive=base/'archive'/'legacy'
        if not archive.resolve().is_relative_to(base.resolve()):
            raise ValueError(tr('Migration refusée : destination inattendue ({p0}).',p0=archive))
        def aside(source):
            if not source.exists() or source.is_symlink():return
            archive.mkdir(parents=True,exist_ok=True)
            dest=archive/source.name
            if dest.exists():dest=archive/(source.name+'-'+str(time.time_ns()))
            source.rename(dest)
        old=base/'party';runtime=base/'runtime'
        if old.exists() and not old.is_symlink():
            if runtime.exists():raise ValueError(tr('Migration refusée : destination inattendue ({p0}).',p0=runtime))
            old.rename(runtime)
            old.symlink_to('runtime',target_is_directory=True)
        old_lock=base/'test.lock'
        if old_lock.is_symlink():old_lock.unlink()
        elif old_lock.exists():old_lock.unlink()
        old_lock.symlink_to('session.lock')
        # Old exploratory game data is archived, never discarded as cache.
        for name in ('coop','jeux','data'):
            aside(base/name)
        for name in ('partydeck-test','partydeck'):
            path=base/name
            if path.is_symlink():path.unlink()
            elif path.exists():aside(path)
            path.symlink_to('windows-party')
        # Rewrite only a fully recognised generated shell command. User-authored
        # scripts and custom additions remain byte-for-byte intact.
        for folder in (roms,ports):
            if not folder.is_dir():continue
            for entry in folder.glob('*.sh'):
                if entry.is_symlink():continue
                text=entry.read_text(errors='replace');lines=text.splitlines()
                if (entry.name=='Test LAN NFS.sh' and len(lines)==3
                    and lines[0]=='#!/bin/bash' and lines[1]=='export PARTYDECK_NFSMW_PRIVATE_LAN=1'):
                    command=shlex.split(lines[2])
                    if (len(command)==7 and command[0]=='exec' and command[2]=='party'
                        and command[1] in (str(legacy/'partydeck-test'),str(base/'partydeck-test'))
                        and command[4:]==['2','horizontal','auto']):
                        aside(entry)
                        continue
                if folder==ports and len(lines)==3 and lines[1] in ('# Entrée gérée par partydeck-test','# Entrée gérée par PartyDeck Wine'):
                    try:command=shlex.split(lines[2])
                    except ValueError:command=[]
                    if (len(command)>=3 and command[0]=='exec' and command[2] in ('jouer','coop')
                        and command[1] in (str(legacy/'partydeck-test'),str(base/'partydeck-test'))):
                        aside(entry)
                        continue
                if len(lines)!=3 or lines[1] not in ('# Entrée gérée par PartyDeck Wine','# Configuration gérée par Windows Party'):
                    continue
                try:args=shlex.split(lines[2])
                except ValueError:continue
                if len(args)<3 or args[0]!='exec':continue
                old_commands={str(root/name) for root in (base,legacy) for name in ('partydeck-test','partydeck','windows-party')}
                if args[1] not in old_commands:continue
                if args[2] not in ('profil','party','configurer','coop'):continue
                args[1]=str(base/'windows-party')
                after='\n'.join([*lines[:2],shlex.join(args)])+'\n'
                if after!=text:
                    archive.mkdir(parents=True,exist_ok=True)
                    backup=archive/('launchers-'+folder.name);backup.mkdir(exist_ok=True)
                    original=backup/entry.name
                    if not original.exists():original.write_bytes(entry.read_bytes())
                    entry.write_text(after);entry.chmod(0o755)
        print(tr('Migration Windows Party terminée ; anciennes données conservées dans archive.'),flush=True)
    finally:
        for stream in locks:stream.close()


if __name__=='__main__':
    try:
        if sys.argv[1]=='prepare':migrate_root(Path(sys.argv[2]),Path(sys.argv[3]))
        elif sys.argv[1]=='finalize':finalize(*sys.argv[2:6])
        else:raise ValueError('prepare|finalize')
    except (OSError,ValueError,RuntimeError) as error:
        print(str(error),file=sys.stderr);raise SystemExit(1)
