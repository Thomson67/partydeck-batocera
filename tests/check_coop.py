import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

path = Path(__file__).resolve().parents[1] / "scripts/partydeck-batocera-coop.py"
sys.path.insert(0, str(path.parent))
from partydeck_profiles import defaults, save_profile
spec = importlib.util.spec_from_file_location("coop", path)
coop = importlib.util.module_from_spec(spec)
sys.modules["coop"] = coop
spec.loader.exec_module(coop)

# A low inherited ES limit is raised only in the exec child. Respect a lower
# hard limit, preserve higher/unlimited limits, and tolerate denied changes.
for soft,hard,expected in ((1024,1048576,65536),(1024,4096,4096),
                           (131072,1048576,131072),(-1,-1,-1),(1024,-1,65536)):
    with patch.object(coop.resource,'getrlimit',side_effect=[(soft,hard),(expected,hard)]), \
         patch.object(coop.resource,'setrlimit') as change, \
         patch.object(coop.os,'execv') as execute:
        coop.run_compositor(['/bin/compositor','argument with spaces'])
        if expected!=soft:
            change.assert_called_once_with(coop.resource.RLIMIT_NOFILE,(expected,hard))
        else:change.assert_not_called()
        execute.assert_called_once_with('/bin/compositor',['/bin/compositor','argument with spaces'])
with patch.object(coop.resource,'getrlimit',return_value=(1024,65536)), \
     patch.object(coop.resource,'setrlimit',side_effect=PermissionError('denied')), \
     patch.object(coop.os,'execv') as execute:
    coop.run_compositor(['/bin/compositor'])
    execute.assert_called_once()

# Exercise actual fork/exec inheritance without changing this test's limits.
import json
import subprocess
before=coop.resource.getrlimit(coop.resource.RLIMIT_NOFILE)
for hard in (4096,65536):
    if before[1]!=coop.resource.RLIM_INFINITY and before[1]<hard:continue
    bootstrap=('import os,resource,sys; '
               f'resource.setrlimit(resource.RLIMIT_NOFILE,(1024,{hard})); '
               'os.execv(sys.executable,[sys.executable,*sys.argv[1:]])')
    probe='import json,resource; print(json.dumps(resource.getrlimit(resource.RLIMIT_NOFILE)))'
    result=subprocess.run([sys.executable,'-c',bootstrap,str(path),'_gamescope',
                           sys.executable,'-c',probe],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout.splitlines()[-1])==[hard,hard],result.stdout
assert coop.resource.getrlimit(coop.resource.RLIMIT_NOFILE)==before

pad, another, keyboard, mouse = [
    coop.Device(Path(f"/dev/input/event{i}"), category, "", Path(f"/sys/mock/{i}"))
    for i, category in enumerate((coop.GAMEPADS, coop.GAMEPADS, coop.KEYBOARDS, coop.MICE))
]
assert coop.assign_players([pad, keyboard, mouse], "auto", "auto") == [[pad], [keyboard, mouse]]
assert coop.assign_players([pad], "auto", "auto") == [[pad]]
assert coop.assign_players([keyboard, mouse], "auto", "auto") == [[keyboard, mouse]]
assert coop.assign_players([pad, another, keyboard, mouse], "auto", "auto") == [[pad], [another]]
assert coop.assign_players([pad, keyboard, mouse], "1", "auto") == [[pad]]
assert coop.assign_players([pad, keyboard, mouse], "2", "clavier-j1") == [[keyboard, mouse], [pad]]
assert coop.assign_players([pad, keyboard, mouse], "auto", "auto", False) == [[pad]]
assert coop.assign_players([pad, another, keyboard, mouse], "auto", "auto", False) == [[pad], [another]]
assert coop.assign_players([pad, another, keyboard, mouse], "2", "clavier-j2", False) == [[pad], [another]]
for devices, count in (([keyboard, mouse], "auto"), ([pad, keyboard, mouse], "2")):
    try:
        coop.assign_players(devices, count, "auto", False)
        raise AssertionError("Keyboard assigned despite disabled option")
    except ValueError:
        pass

with patch.object(coop.subprocess, "run") as run:
    run.return_value.stdout = "321\n"
    run.return_value.returncode = 0
    assert coop.top_window("partydeck-coop-123-j1") == "321"
    assert run.call_args.args[0] == ["xdotool", "search", "--onlyvisible", "--class",
                                    "^partydeck-coop-123-j1$"]

# Hidden windows are discovered by the same exact player class; ambiguity
# never activates a possibly unrelated window.
with patch.object(coop.subprocess, "run") as run:
    run.side_effect = [Mock(stdout="", returncode=1), Mock(stdout="322\n", returncode=0)]
    assert coop.top_window("partydeck-coop-123-j2") == "322"
    assert run.call_args.args[0] == ["xdotool", "search", "--class", "^partydeck-coop-123-j2$"]
with patch.object(coop.subprocess, "run") as run:
    run.return_value = Mock(stdout="321\n322\n", returncode=0)
    assert coop.top_window("partydeck-coop-123-j1") is None
    assert run.call_count == 1

with tempfile.TemporaryDirectory() as temp, \
     patch.object(coop, "sandbox_arguments", return_value=[]), \
     patch.object(coop.subprocess,"Popen") as popen, \
     patch.dict(os.environ, PARTYDECK_PRIVATE_LAN_IP='192.168.247.99'):
    base = Path(temp)
    game = base / "Game.wsquashfs"
    coop.start_player(base, base / "j2", game, game, [], (960, 0, 960, 1080), "test-j2")
    assert popen.call_args.kwargs["env"]["SDL_VIDEO_X11_WMCLASS"] == "test-j2"
    assert 'PARTYDECK_PRIVATE_LAN_IP' not in popen.call_args.kwargs['env']
    assert 'PARTYDECK_PRIVATE_LAN_IP' not in popen.call_args.args[0]
    assert popen.call_args.kwargs['stdin']==coop.subprocess.DEVNULL
    assert "test-j2" not in popen.call_args.args[0]
    assert "-W" in popen.call_args.args[0]
    assert "--backend-disable-keyboard" not in popen.call_args.args[0]
    assert "--backend-disable-mouse" not in popen.call_args.args[0]
    assert "--grab" not in popen.call_args.args[0]
    coop.start_player(base, base / "j2", game, game, [keyboard, mouse],
                      (960, 0, 960, 1080), "test-j2", shared_keyboard_mouse=False)
    exclusive = popen.call_args.args[0]
    assert "--backend-disable-keyboard" in exclusive
    assert "--backend-disable-mouse" in exclusive
    assert "--grab" in exclusive
    assert "--libinput-hold-dev=/dev/input/event2,/dev/input/event3," in exclusive
    network=Mock(fds=[200]);network.prefix.return_value=['python3','partydeck_private_lan.py','_enter','200','1','2','--']
    network.child_prefix.return_value=['python3','partydeck_private_lan.py','_enter-path','/proc/123/ns/net','1','2','1','3','--']
    network.address.return_value='192.168.247.11'
    coop.start_player(base,base/'j1',game,game,[pad],(0,0,1920,540),'private-j1',network=network)
    command=popen.call_args.args[0]
    assert command[:3]==[sys.executable,str(path),'_gamescope']
    assert command[3:5]==[str(base/'AppRun'),'gamescope-kbm']
    child=network.child_prefix.return_value
    assert command[command.index('sh')+1:command.index('sh')+1+len(child)]==child
    assert 'pass_fds' not in popen.call_args.kwargs
    assert command[command.index('PARTYDECK_PRIVATE_LAN_IP')+1]=='192.168.247.11'

for split, second_position, inputs, shared, party, virtual in [
    ("horizontal", (0, 540, 1920, 540), [pad, keyboard, mouse], False, False,False),
    ("vertical", (960, 0, 960, 1080), [pad, keyboard, mouse], False, False,False),
    ("horizontal", (0, 540, 1920, 540), [pad, another], True, False,False),
    ("vertical", (960, 0, 960, 1080), [pad, another], True, False,False),
    ("horizontal", (0, 540, 1920, 540), [pad, another, keyboard, mouse], True, True,False),
    ("horizontal", (0, 540, 1920, 540), [pad, keyboard, mouse], False, True,True),
]:
    with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
        def mock(obj, attr, **kwargs):
            return stack.enter_context(patch.object(obj, attr, **kwargs))
        base = Path(temp)
        stack.enter_context(patch("partydeck_bottles.ROOT",base/"bottles"))
        game = base / "Game.wsquashfs"
        if party:
            profile = defaults(game)
            profile['keyboard_player'] = virtual
            save_profile(base, game, profile)
            mock(coop, "PARTY_SAVES", new=base / "party-saves")
        mock(coop.shutil, "which", return_value="/path")
        mock(coop, "read_input_devices", return_value=inputs)
        monitor_call=mock(coop, "primary_monitor", return_value=(0, 0, 1920, 1080))
        graphics_call=mock(coop, "graphics_environment", return_value={})
        if party and not virtual:
            from partydeck_display import save_settings as save_desktop
            save_desktop(base,dict(gpu="system",output="DP-7"))
        mock(coop.subprocess, "run", return_value=Mock(returncode=0))
        mock(coop.signal, "signal")
        mock(coop, "stop_players")
        import partydeck_virtual_input as virtual_module
        mock(virtual_module,'probe',return_value=virtual)
        watcher=mock(virtual_module,'Watcher')
        processes = [Mock(pid=123, **{"poll.return_value": None, "wait.return_value": 0}),
                     Mock(pid=456, **{"poll.return_value": None, "wait.return_value": 0})]
        starts = mock(coop, "start_player", side_effect=processes)
        classes = [f"partydeck-coop-{os.getpid()}-j1", f"partydeck-coop-{os.getpid()}-j2"]
        windows = mock(coop, "top_window", side_effect={classes[0]:"810", classes[1]:"811"}.get)
        place = mock(coop, "place_window", return_value=True)
        for process in processes:
            process.poll.side_effect = lambda: 0 if place.call_count==2 else None
        output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        assert coop.run_session(base, base, game, game, "auto", split, "auto", party=party) == 0
        if party and not virtual:
            assert graphics_call.call_args.args[1]=="system"
            assert monitor_call.call_args.args==("DP-7",)
        assert [call.args[0] for call in windows.call_args_list] == classes
        assert [call.args[-1] for call in starts.call_args_list] == classes
        assert all(call.kwargs["shared_keyboard_mouse"] is (shared or virtual)
                   for call in starts.call_args_list)
        if party and not virtual:
            assert all(d.category == coop.GAMEPADS for call in starts.call_args_list for d in call.args[4])
        if virtual:
            watcher.return_value.start.assert_called_once()
            watcher.return_value.close.assert_called_once()
            assert starts.call_args_list[1].args[4]==[keyboard,mouse]
        assert place.call_args_list[1].args == ("811", second_position)
        assert "Joueurs : 2" in output.getvalue() and "Fenêtre J2 placée : 811" in output.getvalue()
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    def gpu(name,vendor,driver):
        path=root/name;path.mkdir()
        (path/'class').write_text('0x030200')
        (path/'vendor').write_text(vendor)
        (path/'driver').symlink_to(root/'drivers'/driver)
        return path
    intel=gpu('intel','0x8086','i915')
    assert not coop.hybrid_nvidia(root)
    nvidia=gpu('nvidia','0x10de','nvidia')
    assert coop.hybrid_nvidia(root)
    with patch.object(coop,'hybrid_nvidia',return_value=True):
        env=coop.graphics_environment({'__GLX_VENDOR_LIBRARY_NAME':'nvidia'})
        assert env['VK_LOADER_DRIVERS_SELECT']=='*nvidia*'
        for key,value in (('DRI_PRIME','0'),('VK_DRIVER_FILES','custom.json'),
                          ('__NV_PRIME_RENDER_OFFLOAD','0'),('MESA_VK_DEVICE_SELECT','8086:1234')):
            assert coop.graphics_environment({key:value})=={}
        assert coop.graphics_environment({},'system')=={}
        assert coop.graphics_environment({'DRI_PRIME':'0'},'nvidia')==env
        with patch.dict(os.environ,env,clear=True),patch.object(coop,'player_paths',return_value=[]),patch.object(coop,'UMU_HOME',root/'absent'):
            arguments=coop.sandbox_arguments(root/'j1',[])
            assert arguments[arguments.index('__VK_LAYER_NV_optimus')+1]=='NVIDIA_only'
    (nvidia/'driver').unlink();(nvidia/'driver').symlink_to(root/'drivers/nouveau')
    assert not coop.hybrid_nvidia(root)
    (nvidia/'driver').unlink();(nvidia/'driver').symlink_to(root/'drivers/nvidia')
    (intel/'vendor').write_text('0x1002')
    assert coop.hybrid_nvidia(root)  # AMD + NVIDIA also uses the guarded path.
    for file in intel.iterdir():file.unlink()
    intel.rmdir()
    assert not coop.hybrid_nvidia(root)  # Single NVIDIA keeps system selection.
with patch.object(coop.subprocess,'run') as run:
    coop.focus_window('810')
    assert [call.args[0] for call in run.call_args_list] == [
        ['xdotool','windowmap','810'], ['xdotool','windowactivate','810'],
        ['xdotool','windowraise','810','windowfocus','810']]
with patch.object(coop.subprocess,'run') as run:
    run.side_effect = [None, OSError('activation unavailable'), None]
    coop.focus_window('810')
    assert run.call_count == 3  # Xorg fallback survives WM activation failure.
print("Attribution auto, classes J1/J2, placement, GPU hybride, focus et entrée standard détachée vérifiés.")

# Match the XWayland mode to the Celeste viewport in 32:9 sessions.
with patch.object(coop.subprocess, 'Popen') as popen:
    coop.start_player(base, base/'j2', game, game, [], (0, 540, 1920, 540), 'celeste-j2',
                      celestenet=True, celeste_options={'language': 'french'})
    args = popen.call_args.args[0]
    for option, size in (('-w', '1920'), ('-h', '540'), ('-W', '1920'), ('-H', '540')):
        assert args[args.index(option) + 1] == size
    assert popen.call_args.kwargs['env']['PARTYDECK_CELESTE_OPTIONS'] == '{"language": "french"}'
    coop.start_player(base, base/'j2', game, game, [], (960, 0, 960, 1080), 'celeste-j2', celestenet=True)
    assert '-w' not in popen.call_args.args[0]
    coop.start_player(base, base/'j1', game, game, [], (0, 0, 1920, 1080), 'celeste-j1',
                      celeste_options={'language': 'french'})
    assert '-w' not in popen.call_args.args[0]
