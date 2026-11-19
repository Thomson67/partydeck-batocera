"""Data-preserving root migration, generated launchers and legacy isolation."""
import os,sys,tempfile,shlex,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_migrate import migrate_root,finalize

with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);old=root/'partydeck-test';new=root/'windows-party';old.mkdir()
 roms=root/'roms/windows-party';ports=root/'roms/ports';roms.mkdir(parents=True);ports.mkdir(parents=True)
 (old/'profiles').mkdir();(old/'profiles/game.json').write_bytes(b'OPTIONS')
 (old/'party/game/j1').mkdir(parents=True);(old/'party/game/j1/state').write_bytes(b'PLAYER')
 (old/'partydeck-test').write_bytes(b'OLD PROGRAM');(old/'partydeck').symlink_to('partydeck-test')
 (old/'jeux').mkdir();(old/'jeux/Original.exe').write_bytes(b'GAME')
 (old/'coop').mkdir();(old/'coop/saved').write_bytes(b'LEGACY DATA')
 saves=root/'saves';saves.mkdir();(saves/'save.dat').write_bytes(b'SAVE')
 launcher=roms/'Game.sh';launcher.write_text('#!/bin/bash\n# Entrée gérée par PartyDeck Wine\n'+shlex.join(['exec',str(old/'partydeck-test'),'profil','/roms/windows/Game.wsquashfs'])+'\n')
 custom=roms/'User.sh';custom.write_text('#!/bin/bash\necho custom\n');custom_before=custom.read_bytes()
 test=roms/'Test LAN NFS.sh';test.write_text('#!/bin/bash\nexport PARTYDECK_NFSMW_PRIVATE_LAN=1\n'+shlex.join(['exec',str(old/'partydeck-test'),'party','/roms/windows/NFS.wsquashfs','2','horizontal','auto'])+'\n')
 gui=ports/'PartyDeck - Test.sh';gui.write_text('#!/bin/bash\n# Entrée gérée par partydeck-test\n'+shlex.join(['exec',str(old/'partydeck-test'),'jouer','Game.exe'])+'\n')
 assert migrate_root(old,new)==new
 assert old.is_symlink() and (old/'profiles/game.json').read_bytes()==b'OPTIONS'
 (new/'windows-party').write_bytes(b'NEW PROGRAM')
 finalize(new,old,roms,ports)
 assert (new/'runtime/game/j1/state').read_bytes()==b'PLAYER'
 assert (old/'party/game/j1/state').read_bytes()==b'PLAYER'  # Absolute prefix paths remain usable.
 assert (new/'partydeck-test').resolve()==new/'windows-party'
 assert (new/'partydeck').resolve()==new/'windows-party'
 assert (new/'test.lock').resolve()==new/'session.lock'
 assert (new/'archive/legacy/jeux/Original.exe').read_bytes()==b'GAME'
 assert (new/'archive/legacy/coop/saved').read_bytes()==b'LEGACY DATA'
 assert (saves/'save.dat').read_bytes()==b'SAVE' and custom.read_bytes()==custom_before
 assert not test.exists() and (new/'archive/legacy/Test LAN NFS.sh').is_file()
 assert not gui.exists() and (new/'archive/legacy/PartyDeck - Test.sh').is_file()
 assert shlex.split(launcher.read_text().splitlines()[2])[1]==str(new/'windows-party')
 subprocess.run(['bash','-c','exec 9>"$1/session.lock"; flock -n 9; "$2" "$3" finalize "$1" "$4" "$5" "$6"',
                 'migration',str(new),sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/partydeck_migrate.py'),
                 str(old),str(roms),str(ports)],check=True,timeout=10,capture_output=True)
 finalize(new,old,roms,ports);migrate_root(old,new)  # Re-running cannot clobber archives or data.
 assert (new/'archive/legacy/partydeck-test').read_bytes()==b'OLD PROGRAM'
 # Refuse merges instead of picking one of two existing installations.
 other=root/'other';other.mkdir()
 try:migrate_root(other,new);raise AssertionError('conflicting roots merged')
 except ValueError:pass
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);old=root/'old';old.mkdir();new=root/'new'
 # A live legacy session blocks the move before any directory is renamed.
 import fcntl
 with (old/'test.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  try:migrate_root(old,new);raise AssertionError('live migration accepted')
  except RuntimeError:pass
 assert old.is_dir() and not old.is_symlink() and not new.exists()
print('Migration : profils/saves conservés, liens des préfixes compatibles, runtime, lanceurs reconnus, archives, refus en cours de jeu et idempotence vérifiés.')
