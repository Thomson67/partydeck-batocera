"""Owned window targeting and per-controller isolation without GTK/uinput."""
import os,sys,json,tempfile,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_virtual_input as v

assert v.identity(os.getpid()) and not v.identity(99999999)
class Controller:
    def __init__(self,node):
        self.device=SimpleNamespace(path=node);self.events=[];self.captured=False
        self.grabs=0;self.polls=0
    def poll(self):self.polls+=1;return self.events
    def grab(self):self.captured=True;self.grabs+=1
    def released(self):return False
    def close(self):self.closed=True

rows=[{'group':101,'devices':['/dev/input/event1'],'class':'partydeck-test-j1'},
      {'group':102,'devices':['/dev/input/event2'],'class':'partydeck-test-j2'}]
windows=Mock();windows.cardinal.side_effect=lambda w,k:{42:201,43:202,99:999}.get(w,0)
route=v.Routing(rows,windows)
with patch.object(v.subprocess,'run',side_effect=[Mock(returncode=0,stdout='42\n'),Mock(returncode=0,stdout='43\n')]):
    route.refresh()
assert route.known=={42:101,43:102}
with patch.object(v.os,'getpgid',side_effect=lambda pid:{201:101,202:102,999:999}.get(pid,0)):
    assert route.allowed(42) and route.allowed(43) and not route.allowed(99)
    with patch.object(v.subprocess,'run') as run:
        j1,j2=route.wrap(Controller('/dev/input/event1')),route.wrap(Controller('/dev/input/event2'))
        j1.events=['toggle'];assert j1.poll()==['toggle']
        assert run.call_args.args[0]==['xdotool','windowraise','42','windowfocus','42']
        j1.grab();j2.grab()
        assert j1.grabs==1 and j2.grabs==0
        assert j2.released() and not j1.released()
        # The other pad keeps playing: events are drained but don't navigate
        # the keyboard, and its evdev device has not been grabbed.
        j2.events=['down'];assert j2.poll()==[] and j2.polls==1
        j2.events=['mouse-toggle'];assert j2.poll()==[] and route.owner is j1
        j1.captured=False
        assert j2.poll()==['mouse-toggle'] and route.owner is j2
        assert run.call_args.args[0][-1]=='43'
    # A recycled/non-owned process cannot receive any synthetic input.
    route.known[99]=101
    assert not route.allowed(99)

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);home=root/'toolbox';private=root/'private';private.mkdir()
    (home/'config').mkdir(parents=True)
    settings=home/'config/virtual-keyboard.json';settings.write_text('{"global":true,"games":{}}')
    class Windows:
        def current(self,editor):return ('other',42)
        def cardinal(self,window,key):return 201
        def close(self):pass
    policy=SimpleNamespace(process_identity=lambda pid:'token')
    assigned=Controller('/dev/input/event1');unassigned=Controller('/dev/input/event9')
    runtime=SimpleNamespace(controllers=lambda **kwargs:[assigned,unassigned],
                            subprocess=SimpleNamespace(Popen=Mock()))
    amx=SimpleNamespace(priority=Mock())
    focus=SimpleNamespace(XWindows=Windows)
    def launch(path,rom):
        assert path==private and rom=='/userdata/roms/windows/Game.wsquashfs'
        assert runtime.running_game()==rom
        assert runtime.controllers()==[assigned] and unassigned.closed
        assert Windows().current(0)==('game',42)
        assert json.loads((private/'state/virtual-keyboard/session.json').read_text())['token']=='token'
        assert (private/'config/virtual-keyboard.json').read_bytes()==settings.read_bytes()
        amx.priority(home,rom,True)
        # Exit from captured virtual controls only signals the session owner.
        runtime.subprocess.Popen(['hotkeygen','--send','exit'])
    runtime.run=launch
    data=dict(home=str(home),private=str(private),rom='/userdata/roms/windows/Game.wsquashfs',
              parent=os.getpid(),parent_identity=v.identity(os.getpid()),assignments=rows[:1])
    with patch.object(v,'load_toolbox',return_value=(policy,runtime,amx,focus)),\
         patch.object(v.subprocess,'run',return_value=Mock(returncode=0,stdout='42\n')),\
         patch.object(v.os,'getpgid',return_value=101),patch.object(v.os,'kill') as kill:
        v.run(data)
        kill.assert_called_once_with(os.getpid(),v.signal.SIGTERM)
    assert settings.read_text()=='{"global":true,"games":{}}'

with tempfile.TemporaryDirectory() as temp:
    home=Path(temp);rom=home/'Game.wsquashfs'
    assert not v.probe(rom,home)
    helper=home/'toolbox/helpers/virtual_keyboard.py';helper.parent.mkdir(parents=True);helper.write_text('# installed')
    for output,want in (('{"enabled":true}',True),('{"enabled":false}',False),('[]',False),('invalid',False)):
        with patch.object(v.subprocess,'run',return_value=Mock(returncode=0,stdout=output)):
            assert v.probe(rom,home)==want
    # One host watcher per session; a private config link never changes solo
    # lifecycle files. It is detached from inherited pipes and stopped by PID.
    watcher=v.Watcher(home,rom,[SimpleNamespace(pid=101)],
        [[SimpleNamespace(node=Path('/dev/input/event1'),category='ID_INPUT_JOYSTICK')]],['partydeck-test-j1'],home)
    process=Mock(pid=321);process.poll.return_value=None
    with patch.object(v.subprocess,'Popen',return_value=process) as spawn:
        watcher.start()
        kwargs=spawn.call_args.kwargs
        assert kwargs['stdin']==subprocess.DEVNULL and kwargs['start_new_session'] and kwargs['close_fds']
        payload=Path(spawn.call_args.args[0][-1]);data=json.loads(payload.read_text())
        assert data['parent']==os.getpid() and data['rom']==str(rom)
        assert data['assignments'][0]['devices']==['/dev/input/event1']
        directory=payload.parent
        watcher.close();process.terminate.assert_called_once()
        assert not directory.exists()
print('Contrôles virtuels : options héritées, un service hôte, fenêtre propriétaire, capture limitée au joueur et arrêt isolé vérifiés.')
