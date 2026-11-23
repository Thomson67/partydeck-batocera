"""Data-preserving root migration, generated launchers and legacy isolation."""
import os,sys,tempfile,shlex,subprocess
from pathlib import Path
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_migrate import LIBRARY_NAME, migrate_root,finalize

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
 windows=roms.parent/'windows';windows.mkdir()
 (windows/'cover.png').write_bytes(b'COVER')
 (roms/'cover.png').symlink_to('../windows/cover.png')
 gamelist=ET.Element('gameList');game=ET.SubElement(gamelist,'game')
 ET.SubElement(game,'path').text=str(launcher)
 ET.SubElement(game,'image').text='../windows/cover.png'
 ET.SubElement(game,'video').text='./preview.mp4'
 ET.SubElement(game,'favorite').text='true'
 ET.ElementTree(gamelist).write(roms/'gamelist.xml')
 test=roms/'Test LAN NFS.sh';test.write_text('#!/bin/bash\nexport PARTYDECK_NFSMW_PRIVATE_LAN=1\n'+shlex.join(['exec',str(old/'partydeck-test'),'party','/roms/windows/NFS.wsquashfs','2','horizontal','auto'])+'\n')
 gui=ports/'PartyDeck - Test.sh';gui.write_text('#!/bin/bash\n# Entrée gérée par partydeck-test\n'+shlex.join(['exec',str(old/'partydeck-test'),'jouer','Game.exe'])+'\n')
 assert migrate_root(old,new)==new
 assert old.is_symlink() and (old/'profiles/game.json').read_bytes()==b'OPTIONS'
 (new/'windows-party').write_bytes(b'NEW PROGRAM')
 finalize(new,old,roms,ports)
 library=new.parent/LIBRARY_NAME
 migrated=ET.parse(library/'gamelist.xml')
 assert migrated.findtext('.//path')==str(library/launcher.name)
 assert migrated.findtext('.//image')==str(windows/'cover.png')
 assert migrated.findtext('.//video')=='./preview.mp4'
 assert migrated.findtext('.//favorite')=='true'
 assert (library/'cover.png').read_bytes()==b'COVER'
 assert ET.parse(roms/'gamelist.xml').findtext('.//path')==str(launcher)
 assert (new/'runtime/game/j1/state').read_bytes()==b'PLAYER'
 assert (old/'party/game/j1/state').read_bytes()==b'PLAYER'  # Absolute prefix paths remain usable.
 assert (new/'partydeck-test').resolve()==new/'windows-party'
 assert (new/'partydeck').resolve()==new/'windows-party'
 assert (new/'test.lock').resolve()==new/'session.lock'
 assert (new/'archive/legacy/jeux/Original.exe').read_bytes()==b'GAME'
 assert (new/'archive/legacy/coop/saved').read_bytes()==b'LEGACY DATA'
 assert (saves/'save.dat').read_bytes()==b'SAVE' and (library/custom.name).read_bytes()==custom_before
 assert test.exists() and not (library/test.name).exists() and (new/'archive/legacy/Test LAN NFS.sh').is_file()
 assert not gui.exists() and (new/'archive/legacy/PartyDeck - Test.sh').is_file()
 assert shlex.split((library/launcher.name).read_text().splitlines()[2])[1]==str(new/'windows-party')
 assert shlex.split(launcher.read_text().splitlines()[2])[1]==str(old/'partydeck-test')
 # Execute the installer's actual finalization command with its session lock
 # held. The migrator borrows fd 9; closing it here makes it lock itself out.
 scripts=Path(__file__).resolve().parents[1]/'scripts'
 for module in ('partydeck_migrate.py','partydeck_i18n.py'):
  (new/module).write_bytes((scripts/module).read_bytes())
 install_line=next(line.strip() for line in (scripts/'install-windows-party.sh').read_text().splitlines()
                   if line.strip().startswith('python3 "$base/partydeck_migrate.py" finalize'))
 install_line=install_line.replace('/userdata/system/partydeck-test','"$legacy"').replace('/userdata/roms/windows-party','"$roms"')
 subprocess.run(['bash','-c',
                 'base=$1; legacy=$2; roms=$3; ports_dir=$4; exec 9>"$base/session.lock"; flock -n 9 || exit 1; '+install_line,
                 'migration',str(new),str(old),str(roms),str(ports)],check=True,timeout=10,capture_output=True)
 (library/custom.name).write_bytes(b'EDITED AFTER MIGRATION')
 finalize(new,old,roms,ports);migrate_root(old,new)  # Re-running cannot clobber archives or data.
 assert (library/custom.name).read_bytes()==b'EDITED AFTER MIGRATION'
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
