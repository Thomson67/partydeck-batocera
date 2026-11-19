"""A fresh launcher must prepare its dependency and log before a game runs."""
from pathlib import Path
import os,subprocess,tempfile
script=Path(__file__).resolve().parents[1]/'scripts/install-windows-party.sh'
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);base=root/'windows-party';bin_dir=root/'bin';bin_dir.mkdir()
 version=bin_dir/'batocera-version';version.write_text('#!/bin/sh\nprintf "44-bootstrap\\n"\n');version.chmod(0o755)
 # Fail a dependency download deliberately; this exercises the actual clean
 # startup path with no network, installed Gamescope, Wine or graphic session.
 curl=bin_dir/'curl';curl.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$BOOTSTRAP_DOWNLOAD_ARGS"\nexit 44\n');curl.chmod(0o755)
 launcher=root/'launcher';launcher.write_text(script.read_text().replace("base='/userdata/system/windows-party'",f"base='{base}'"));launcher.chmod(0o755)
 env=dict(os.environ,PATH=str(bin_dir)+':'+os.environ['PATH'],BOOTSTRAP_DOWNLOAD_ARGS=str(root/'download.args'))
 result=subprocess.run(['bash',str(launcher),'verifier'],env=env,capture_output=True,text=True,timeout=10)
 assert result.returncode==44,(result.returncode,result.stdout,result.stderr)
 assert 'partydeck/partydeck/releases/download/' in (root/'download.args').read_text()
 logs=list((base/'logs').glob('partydeck-*'))
 assert len(logs)==1 and 'Batocera 44-bootstrap' in logs[0].read_text()
 assert 'Journal :' in result.stdout
 assert not list((base/'releases').glob('.partydeck-*'))  # Failed staging cleaned.
print('Bootstrap : téléchargement requis sur installation neuve, journal principal et nettoyage après échec vérifiés sans réseau.')
