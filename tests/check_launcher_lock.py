"""Exercise the real shell lock across helper/background process lifetimes."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

script = Path(__file__).resolve().parents[1]/'scripts/install-windows-party.sh'
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    base, binary = root/'base', root/'bin'
    base.mkdir()
    binary.mkdir()
    (binary/'batocera-version').write_text('#!/bin/sh\necho 44-test\n')
    (binary/'batocera-version').chmod(0o755)
    launcher = base/'windows-party'
    launcher.write_text(script.read_text().replace("base='/userdata/system/windows-party'",f"base='{base}'"))
    launcher.chmod(0o755)
    records, wait = base/'records', base/'wait'
    (base/'partydeck-batocera-coop.py').write_text('''import json,os,subprocess,sys,time
from pathlib import Path
base=Path(__file__).parent
try:
    os.fstat(9)
    inherited=True
except OSError:
    inherited=False
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],
    close_fds=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
with (base/'records').open('a') as output:
    output.write(json.dumps(dict(pid=child.pid,inherited=inherited))+'\\n')
while (base/'wait').exists():time.sleep(.01)
''')
    env = dict(os.environ,PATH=str(binary)+os.pathsep+os.environ['PATH'])
    command = [str(launcher),'ajouter',str(root/'Hollow Knight.wine'),'auto','horizontal','auto']
    active = None
    try:
        # Surviving descendants no longer prevent a subsequent addition.
        for _ in range(2):
            result = subprocess.run(command,env=env,capture_output=True,text=True,timeout=5)
            assert result.returncode==0,(result.stdout,result.stderr)
        data = [json.loads(line) for line in records.read_text().splitlines()]
        assert len(data)==2 and not any(row['inherited'] for row in data)
        assert all(Path(f"/proc/{row['pid']}").exists() for row in data)

        # The shell still excludes another invocation while its helper runs.
        wait.touch()
        active = subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        deadline = time.monotonic()+5
        while len(records.read_text().splitlines())<3:
            assert time.monotonic()<deadline,'helper did not start'
            time.sleep(.01)
        refused = subprocess.run(command,env=env,capture_output=True,text=True,timeout=5)
        assert refused.returncode!=0 and 'session Windows Party' in refused.stderr
        wait.unlink()
        active.communicate(timeout=5)
        assert active.returncode==0
        again = subprocess.run(command,env=env,capture_output=True,text=True,timeout=5)
        assert again.returncode==0,again.stderr
    finally:
        wait.unlink(missing_ok=True)
        if active is not None:
            active.communicate(timeout=5)
        if records.exists():
            for line in records.read_text().splitlines():
                try:os.kill(json.loads(line)['pid'],signal.SIGTERM)
                except ProcessLookupError:pass

print('Launcher lock: background descendants released; active helper still protected.')
