"""Session-scoped adapter for the installed UWT virtual keyboard and mouse.

Runs on the host display, never inside a player's Gamescope/PID namespace.
The toolbox remains responsible for settings, shortcuts, UI and uinput.
"""
from pathlib import Path
import json,os,re,signal,subprocess,sys,tempfile
from partydeck_i18n import tr

HOME=Path('/userdata/system/ultimate-wine-toolbox')


def identity(pid):
    try:
        fields=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split()
        return fields[19] if fields[0] not in ('Z','X') else ''
    except (OSError,IndexError):return ''


def load_toolbox(home):
    helpers=home/'toolbox/helpers'
    if not (helpers/'virtual_keyboard.py').is_file():raise RuntimeError('UWT virtual input unavailable')
    sys.path.insert(0,str(helpers))
    import virtual_keyboard as policy
    import virtual_keyboard_runtime as runtime
    import virtual_keyboard_antimicrox as amx
    import antimicrox_focus as focus
    return policy,runtime,amx,focus


def probe(rom,home=HOME):
    if not (home/'toolbox/helpers/virtual_keyboard.py').is_file():return False
    try:
        result=subprocess.run([sys.executable,__file__,'probe',str(home),str(rom)],
                              stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=5)
        data=json.loads(result.stdout)
        if isinstance(data,dict) and data.get('busy'):
            print(tr('Contrôles virtuels toolbox : un autre service est actif ; session conservée.'),flush=True)
        return result.returncode==0 and isinstance(data,dict) and data.get('enabled') is True
    except (OSError,ValueError,subprocess.TimeoutExpired):
        print(tr('Contrôles virtuels toolbox indisponibles ; consulter le diagnostic toolbox.'),flush=True)
        return False


class Routing:
    def __init__(self,assignments,windows):
        self.assignments=assignments;self.windows=windows;self.owner=None
        self.known={}

    def allowed(self,window):
        group=self.known.get(window)
        if not group:return False
        try:
            pid=self.windows.cardinal(window,'_NET_WM_PID')
            return pid>1 and os.getpgid(pid)==group
        except OSError:return False

    def refresh(self):
        found={}
        for row in self.assignments:
            result=subprocess.run(['xdotool','search','--class','^'+re.escape(row['class'])+'$'],
                                  capture_output=True,text=True,timeout=2)
            ids=result.stdout.split() if result.returncode==0 else []
            if len(ids)==1 and ids[0].isdigit():found[int(ids[0])]=row['group']
        self.known=found

    def select(self,controller):
        if (self.owner is not None and self.owner is not controller
                and getattr(self.owner,'captured',False)):return False
        row=next((r for r in self.assignments if controller.device.path in r['devices']),None)
        if row is None:return False
        window=next((w for w,g in self.known.items() if g==row['group'] and self.allowed(w)),None)
        if window is None:return False
        # Activate the initiating controller's outer window before sending any
        # uinput. Keep all other controllers available to their games.
        subprocess.run(['xdotool','windowactivate',str(window)],check=False,timeout=2,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['xdotool','windowraise',str(window),'windowfocus',str(window)],
                       check=False,timeout=2,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        self.owner=controller
        return True

    def wrap(self,controller):
        poll,grab,released=controller.poll,controller.grab,controller.released
        def routed_poll():
            keys=poll()
            if any(k in ('toggle','mouse-toggle') for k in keys):
                if not self.select(controller):return []
            # Controller state is still drained on every tick. Non-owners keep
            # controlling their game, but cannot type into another player's UI.
            return keys if self.owner is controller else []
        controller.poll=routed_poll
        controller.grab=lambda:grab() if self.owner is controller else None
        controller.released=lambda:released() if self.owner is controller else True
        return controller


def run(data):
    home=Path(data['home']);private=Path(data['private']);rom=data['rom']
    policy,runtime,amx,focus=load_toolbox(home)
    parent=data['parent'];stamp=data['parent_identity']
    if not stamp or identity(parent)!=stamp:return
    # Private lifecycle/locks prevent touching the solo toolbox watcher. Settings
    # are shared read-only via a symlink; no ROM or config is rewritten.
    state=private/'state/virtual-keyboard';state.mkdir(parents=True,exist_ok=True)
    (private/'config').symlink_to(home/'config',target_is_directory=True)
    (state/'session.json').write_text(json.dumps(dict(rom=rom,pid=os.getpid(),token=policy.process_identity(os.getpid()))))
    windows=focus.XWindows();routing=Routing(data['assignments'],windows)
    original_current=focus.XWindows.current
    def current(self,editor):
        kind,window=original_current(self,editor)
        return ('game',window) if routing.allowed(window) else ('other',window)
    focus.XWindows.current=current
    original_controllers=runtime.controllers
    def controllers(*args,**kwargs):
        allowed={node for row in data['assignments'] for node in row['devices']}
        result=[]
        for controller in original_controllers(*args,**kwargs):
            if controller.device.path in allowed:result.append(routing.wrap(controller))
            else:controller.close()
        return result
    runtime.controllers=controllers
    def running_game():
        if identity(parent)!=stamp:return ''
        routing.refresh()
        return rom
    runtime.running_game=running_game
    # AMX was not started by this session. Do not stop, replace or restore a
    # solo mapping while showing the virtual controls.
    amx.priority=lambda *args,**kwargs:None
    # HK+Start while the overlay has grabbed the pad must reach our supervisor,
    # not Batocera's global Wine stop command.
    real_popen=runtime.subprocess.Popen
    def popen(command,*args,**kwargs):
        if command in (['hotkeygen','--send','exit'],['batocera-wine','windows','stop']):
            if identity(parent)==stamp:os.kill(parent,signal.SIGTERM)
            command=['/bin/true']
        return real_popen(command,*args,**kwargs)
    runtime.subprocess.Popen=popen
    try:runtime.run(private,rom)
    finally:windows.close()


class Watcher:
    def __init__(self,base,rom,processes,players,classes,home=HOME):
        self.process=None;self.directory=None
        self.base=base;self.rom=rom;self.home=home
        self.processes=processes;self.players=players;self.classes=classes

    def start(self):
        self.directory=tempfile.TemporaryDirectory(prefix='.virtual-input-',dir=self.base)
        private=Path(self.directory.name)
        rows=[dict(group=p.pid,devices=[str(d.node) for d in devices if d.category=='ID_INPUT_JOYSTICK'],
                   **{'class':name}) for p,devices,name in zip(self.processes,self.players,self.classes)]
        payload=private/'launch.json'
        payload.write_text(json.dumps(dict(home=str(self.home),private=str(private),rom=str(self.rom),
            parent=os.getpid(),parent_identity=identity(os.getpid()),assignments=rows)))
        log=self.base/'logs/virtual-input.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('wb',buffering=0) as output:
            self.process=subprocess.Popen([sys.executable,__file__,'run',str(payload)],stdin=subprocess.DEVNULL,
                stdout=output,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
        print(tr('Contrôles virtuels toolbox : service démarré ; journal {p0}.',p0=log),flush=True)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        if self.directory is not None:self.directory.cleanup()


if __name__=='__main__':
    try:
        if sys.argv[1]=='probe':
            home,rom=Path(sys.argv[2]),sys.argv[3]
            policy,*_=load_toolbox(home)
            enabled=policy.Settings(home).enabled(rom) or policy.Settings(home,'mouse').enabled(rom)
            busy=False
            session=home/'state/virtual-keyboard/session.json'
            if enabled and session.is_file():
                data=json.loads(session.read_text());pid=data.get('pid');token=data.get('token')
                busy=type(pid) is int and pid>1 and bool(token) and policy.process_identity(pid)==token
            print(json.dumps(dict(enabled=enabled and not busy,busy=busy)))
        elif sys.argv[1]=='run':run(json.loads(Path(sys.argv[2]).read_text()))
        else:raise ValueError('Unknown virtual input action')
    except (OSError,ValueError,RuntimeError,ImportError,subprocess.SubprocessError) as error:
        print(tr('Contrôles virtuels toolbox : {p0}',p0=str(error)),file=sys.stderr);raise SystemExit(1)
