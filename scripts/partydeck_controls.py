"""Most Wanted confirmation chord, restricted to one player's input/display.

Read key state without grabbing or remapping the controller. Send X11 events
directly to that player's game window, including on hosts without XTEST.
"""
from pathlib import Path
import fcntl,os,subprocess,threading
from partydeck_i18n import tr

BTN_TL=310
BTN_TR=311
KEY_BYTES=96
EVIOCGKEY=0x80000000 | (KEY_BYTES<<16) | (ord('E')<<8) | 0x18


def held(fd):
    keys=bytearray(KEY_BYTES)
    fcntl.ioctl(fd,EVIOCGKEY,keys,True)
    return all(keys[code//8] & (1<<(code%8)) for code in (BTN_TL,BTN_TR))


def send_enter(player):
    if player not in ('j1','j2','j3','j4'):raise ValueError('Invalid player for Most Wanted naming')
    result=subprocess.run(['xdotool','search','--onlyvisible','--name',
                           '^Need for Speed.*Most Wanted.*$'],
                          capture_output=True,text=True,timeout=2)
    ids=result.stdout.split()
    if result.returncode or len(ids)!=1 or not ids[0].isdigit():return False
    # --window uses XSendEvent, not global XTEST/uinput. DISPLAY is the inner
    # Gamescope X server inherited by this Wine child, never the ES display.
    # The game's custom field need not implement Ctrl+A. Clear on both sides
    # of the caret instead; enough for the full name field, without clipboard
    # access or keyboard-layout-dependent punctuation.
    commands=[(['xdotool','key','--window',ids[0],'--delay','0',
                'End',*(['BackSpace']*64),*(['Delete']*64)],3),
              (['xdotool','type','--window',ids[0],'--delay','0','--',player.upper()],2),
              (['xdotool','key','--window',ids[0],'--delay','40','Return'],2)]
    for command,timeout in commands:
        result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=timeout)
        if result.returncode:return False
    return True


class Confirmation:
    def __init__(self,enabled,inputs=Path('/dev/input'),player='j1'):
        if player not in ('j1','j2','j3','j4'):raise ValueError('Invalid Most Wanted player')
        self.player=player
        self.enabled=enabled;self.inputs=inputs;self.stop=threading.Event();self.thread=None

    def __enter__(self):
        if self.enabled:
            self.thread=threading.Thread(target=self.run,daemon=True)
            self.thread.start()
            print(tr('Most Wanted : LB + RB / L1 + R1 remplace le champ par {p0} puis valide.',p0=self.player.upper()),flush=True)
        return self

    def __exit__(self,*args):
        self.stop.set()
        if self.thread:self.thread.join(timeout=8)

    def run(self):
        # Only this player's devices exist under /dev/input in the sandbox.
        devices={}
        try:
            while not self.stop.is_set():
                for path in self.inputs.glob('event[0-9]*'):
                    if path in devices:continue
                    try:
                        fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
                        try:previous=held(fd)
                        except OSError:os.close(fd);continue
                        devices[path]=(fd,previous)
                    except OSError:continue
                for path,(fd,previous) in list(devices.items()):
                    try:
                        current=held(fd)
                        # One Enter per chord, rearmed only after release.
                        if current and not previous:
                            try:send_enter(self.player)
                            except (OSError,subprocess.SubprocessError):pass
                        devices[path]=(fd,current)
                    except OSError:
                        os.close(fd);del devices[path]
                self.stop.wait(.05)
        finally:
            for fd,_ in devices.values():os.close(fd)
