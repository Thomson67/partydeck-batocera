"""Wine completion vs SDL compositor lifetime; coordinated Wayland-only exit."""
import os
os.environ['PARTYDECK_LANGUAGE']='fr'
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import Mock,patch

path=Path(__file__).resolve().parents[1]/'scripts/partydeck-batocera-coop.py'
sys.path.insert(0,str(path.parent))
spec=importlib.util.spec_from_file_location('session_exit',path)
coop=importlib.util.module_from_spec(spec);sys.modules[spec.name]=coop;spec.loader.exec_module(coop)


def state(path,code):
    path.write_text(json.dumps(dict(version=1,wine_exit=code)))


with tempfile.TemporaryDirectory() as folder,contextlib.redirect_stdout(io.StringIO()):
    root=Path(folder);states=[root/'first.json',root/'second.json']
    processes=[Mock(**{'poll.return_value':None}),Mock(**{'poll.return_value':None})]
    assert coop.session_result(processes,states,True) is None
    state(states[0],0)
    assert coop.session_result(processes,states,True)==0  # Wine exited, SDL keeps running.
    assert coop.session_result(processes,states,False) is None  # Preserve Xorg lifetime.
    for native,outer,want in ((0,-11,0),(0,245,0),(0,139,0),(0,7,7),(8,0,8),(139,-11,139)):
        state(states[0],native);processes[0].poll.return_value=outer
        assert coop.session_result(processes,states,True)==want
    states[0].unlink();processes[0].poll.return_value=-11
    assert coop.session_result(processes,states,True)==139  # An unproven crash is not hidden as 0/245.
    processes[0].poll.return_value=0;state(states[0],0);state(states[1],9)
    assert coop.session_result(processes,states,True)==9  # Preserve the other player's observed failure.
    processes[1].poll.return_value=0
    assert coop.session_result(processes,states,False)==9
    for file in states:state(file,0)
    assert coop.session_result(processes,states,False)==0
    processes[0].poll.return_value=-11
    assert coop.session_result(processes,states,False)==139  # No Xorg-specific error suppression.
    states[0].write_text('{broken')
    assert coop.read_wine_exit(states[0]) is None
    for code in (True,-1,256,'0'):
        state(states[0],code);assert coop.read_wine_exit(states[0]) is None

    # The child records native exit only after batocera-wine returns, including
    # pre-launch exceptions. A future launch cannot inherit an old state path.
    player=root/'j1';player.mkdir();report=player/('session-'+'a'*32+'.json')
    with patch.dict(os.environ,PARTYDECK_EXIT_STATE=str(report)),patch.object(coop,'_run_wine',return_value=0):
        assert coop.run_wine(root/'game',root/'game',player)==0
        assert coop.read_wine_exit(report)==0
    with patch.dict(os.environ,PARTYDECK_EXIT_STATE=str(report)),patch.object(coop,'_run_wine',side_effect=ValueError('early failure')):
        try:coop.run_wine(root/'game',root/'game',player);raise AssertionError('exception lost')
        except ValueError:pass
        assert coop.read_wine_exit(report)==1
    with patch.dict(os.environ,PARTYDECK_EXIT_STATE=str(root/('session-'+'b'*32+'.json'))),patch.object(coop,'_run_wine',return_value=0):
        try:coop.run_wine(root/'game',root/'game',player);raise AssertionError('external state accepted')
        except ValueError:pass
        assert not (root/('session-'+'b'*32+'.json')).exists()
    with patch.dict(os.environ,PARTYDECK_EXIT_STATE=str(report)),patch.object(coop,'sandbox_arguments',return_value=[]),patch.object(coop.subprocess,'Popen') as launch:
        coop.start_player(root,player,root/'game',root/'game',[],(0,0,960,540),'test')
        assert 'PARTYDECK_EXIT_STATE' not in launch.call_args.kwargs['env']
        coop.start_player(root,player,root/'game',root/'game',[],(0,0,960,540),'test',exit_state=report)
        assert launch.call_args.kwargs['env']['PARTYDECK_EXIT_STATE']==str(report)
    # Real lingering compositors: one Wine completion closes the two owned
    # groups without requiring either window's close button. An unrelated
    # process must survive (no global Gamescope/Wine process-name killing).
    created=[]
    sentinel=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True)
    def start(app,player,*args,exit_state=None,**kwargs):
        if player.name=='j1':
            code='from pathlib import Path; import sys,json,time; Path(sys.argv[1]).write_text(json.dumps(dict(version=1,wine_exit=0))); time.sleep(60)'
        else:
            code='import time; time.sleep(60)'
        proc=subprocess.Popen([sys.executable,'-c',code,str(exit_state)],start_new_session=True)
        created.append(proc);return proc
    pad=coop.Device(Path('/dev/input/event0'),coop.GAMEPADS,'',root)
    original_handlers={sig:signal.getsignal(sig) for sig in coop.SIGNALS}
    try:
        with patch.dict(os.environ,WAYLAND_DISPLAY='wayland-0'),patch.object(coop.shutil,'which',return_value='/ok'),\
             patch.object(coop,'read_input_devices',return_value=[pad,pad]),patch.object(coop,'primary_monitor',return_value=(0,0,1920,1080)),\
             patch.object(coop.subprocess,'run',return_value=Mock(returncode=0)),patch.object(coop,'start_player',side_effect=start),\
             patch.object(coop,'top_window',return_value='123'),patch.object(coop,'place_window',return_value=True):
            assert coop._run_session(root,root,root/'game.wsquashfs',root/'game.wsquashfs','2','horizontal','auto')==0
        assert all(proc.poll() is not None for proc in created)
        assert sentinel.poll() is None
        assert not list(root.glob('coop/**/session-*.json'))
        assert all(signal.getsignal(sig)==previous for sig,previous in original_handlers.items())
        with patch.dict(os.environ,WAYLAND_DISPLAY='wayland-0'),patch.object(coop.shutil,'which',return_value='/ok'),\
             patch.object(coop,'read_input_devices',return_value=[pad]),patch.object(coop,'primary_monitor',return_value=(0,0,1920,1080)),\
             patch.object(coop.subprocess,'run',return_value=Mock(returncode=0)),patch.object(coop,'start_player',side_effect=coop.SessionStopped(signal.SIGTERM)):
            assert coop._run_session(root,root,root/'game.wsquashfs',root/'game.wsquashfs','1','horizontal','auto')==0
        assert all(signal.getsignal(sig)==previous for sig,previous in original_handlers.items())
    finally:
        coop.stop_players(created+[sentinel])
    # One common grace deadline, followed by a targeted SIGKILL for an ignored TERM.
    stubborn=subprocess.Popen([sys.executable,'-u','-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print("ready",flush=True); time.sleep(60)'],
                              stdout=subprocess.PIPE,text=True,start_new_session=True)
    try:
        assert stubborn.stdout.readline().strip()=='ready'
        before=time.monotonic();coop.stop_players([stubborn],timeout=.1)
        assert stubborn.returncode==-signal.SIGKILL and time.monotonic()-before<2
    finally:
        if stubborn.poll() is None:coop.stop_players([stubborn],timeout=0)
        stubborn.stdout.close()
    with patch.object(coop.os,'killpg') as kill:
        coop.stop_players([Mock(pid=999999,**{'poll.return_value':0,'wait.return_value':0})])
        kill.assert_not_called()  # Do not signal a PID that was reaped long ago.

print('Fermeture : suivi Wine indépendant, fin globale Wayland, Xorg conservé, codes réels, groupes isolés et nettoyage vérifiés.')
