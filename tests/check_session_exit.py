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
    processes[0].poll.return_value=-6
    assert coop.session_result(processes,states,False)==134  # Abort survivor cleanup follows in finally.
    processes[0].poll.return_value=None
    state(states[0],7)
    assert coop.session_result(processes,states,False)==7  # Native failure also cannot wait forever.
    state(states[0],0)
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
    state = root / 'session-umu.json'
    state.with_suffix('.umu-ready').touch()
    code = """
import json, sys, time
from pathlib import Path
state = Path(sys.argv[1])
while not state.with_suffix('.stop').exists():
    time.sleep(.02)
time.sleep(.15)
state.write_text(json.dumps(dict(version=1, wine_exit=0)))
time.sleep(60)
"""
    player = subprocess.Popen([sys.executable, '-c', code, str(state)], start_new_session=True)
    compositor = subprocess.Popen(['/bin/true'], start_new_session=True)
    compositor.wine_sandbox = player
    try:
        assert compositor.wait(timeout=2) == 0
        coop.stop_players([compositor], timeout=.3, states=[state], sync_timeout=2)
        assert coop.read_wine_exit(state) == 0
        assert player.returncode == -signal.SIGTERM
    finally:
        if player.poll() is None:
            coop.stop_players([player], timeout=0)

    state = root / 'session-display.json'
    command = [sys.executable, '-c',
               'import os; assert os.environ["DISPLAY"] == ":21"; assert "XAUTHORITY" not in os.environ']
    environment = dict(os.environ, DISPLAY=':0', XAUTHORITY='/outer-authority')
    state.with_suffix('.display').write_text(json.dumps({'DISPLAY': ':21'}))
    subprocess.run([sys.executable, coop.__file__, '_await-display', str(state), *command],
                   env=environment, check=True, timeout=3)

    with patch.dict(os.environ, DISPLAY=':0', XAUTHORITY='/outer-authority'), \
         patch.object(coop.subprocess, 'run') as run:
        run.return_value = subprocess.CompletedProcess([], 1, '', '')
        assert coop.story_window(state) is False
        assert '--onlyvisible' in run.call_args.args[0]
        assert run.call_args.kwargs['env']['DISPLAY'] == ':21'
        assert 'XAUTHORITY' not in run.call_args.kwargs['env']
        run.return_value = subprocess.CompletedProcess([], 1, '', 'cannot open display')
        assert coop.story_window(state) is None
        run.side_effect = [subprocess.CompletedProcess([], 0, '137\n', ''),
                           subprocess.CompletedProcess([], 0, '', '')]
        assert coop.story_window(state, reveal=True) is True
        assert '--onlyvisible' not in run.call_args_list[-2].args[0]
        assert run.call_args.args[0] == ['xdotool', 'windowmap', '137', 'windowraise', '137']

    states = [root / 'j1' / 'startup.json', root / 'j2' / 'startup.json']
    startup = coop.StoryStartup(states, 0)
    with patch.object(coop, 'story_window', side_effect=lambda path, reveal=False: reveal or path == states[1]):
        assert startup.check(states, 59) is None
        assert startup.check(states, 60) is None  # Restore the existing game window first.
        assert startup.check(states, 63) is None
        assert startup.check(states, 64) == 0
        startup.restarted(0, 64)
    with patch.object(coop, 'story_window', return_value=False):
        assert startup.check(states, 124) is None  # A single restart.
        assert not startup.pending
    with patch.object(coop, 'story_window', return_value=None):
        startup = coop.StoryStartup(states, 0)
        assert startup.check(states, 60) is None  # Probe errors cannot cause a restart.
    startup = coop.StoryStartup(states, 0)
    with patch.object(coop, 'story_window', side_effect=[False, True, True, True]):
        assert startup.check(states, 60) is None
        assert startup.check(states, 62) is None  # Restoring the existing window is enough.
        assert not startup.pending and not startup.retried

    context = root/'hotkeygen.state'
    previous = ('ports', {'exit': 'native-exit', 'screenshot': 'take-shot'}, True)
    context.write_text(json.dumps({'context': {'name': previous[0], 'keys': previous[1]},
                                   'include_common': previous[2]}))
    def set_context(_binary, current):
        context.write_text(json.dumps({'context': {'name': current[0], 'keys': current[1]},
                                       'include_common': current[2]}))
    with patch.object(coop, 'HOTKEY_STATE', (context,)), \
         patch.object(coop.shutil, 'which', return_value='/usr/bin/hotkeygen'), \
         patch.object(coop, 'set_hotkey_context', side_effect=set_context) as set_context_mock:
        hotkey = coop.SessionHotkey()
        hotkey.start()
        name, keys, common = coop.hotkey_context()
        assert name == 'windows-party' and common
        assert keys['screenshot'] == 'take-shot' and '_stop-session' in keys['exit']
        hotkey.close()
        assert coop.hotkey_context() == previous
        hotkey.start()
        set_context('/usr/bin/hotkeygen', ('another-emulator', {}, True))
        calls = set_context_mock.call_count
        hotkey.close()
        assert set_context_mock.call_count == calls
    with patch.object(coop, 'process_start_time', return_value='live'), \
         patch.object(coop.os, 'kill') as kill:
        coop.stop_session_from_hotkey(1234, 'stale')
        kill.assert_not_called()
        coop.stop_session_from_hotkey(1234, 'live')
        kill.assert_called_once_with(1234, signal.SIGTERM)

    from partydeck_profiles import track_squashfs_runner
    script = """play_squashfs() {
    SAVEPOINT=/runner/prefix
    if [[ -n "${FAIL:-}" ]]; then false; else true; fi
    waitWineServer 0
}
waitWineServer() { return 0; }
play_squashfs
"""
    updated, count = track_squashfs_runner(script)
    assert count == 1
    target = root/'runner-check.json'
    marker = target.with_suffix('.runner')
    for failure in (True, False):
        env = dict(os.environ, PARTYDECK_EXIT_STATE=str(target), FAIL='1' if failure else '')
        subprocess.run(['bash', '-c', updated], env=env, check=True)
        assert marker.exists() is not failure
    assert marker.read_text().strip() == '/runner/prefix'

print('Fermeture : suivi Wine indépendant, fin globale Wayland, Xorg conservé, codes réels, groupes isolés et nettoyage vérifiés.')
