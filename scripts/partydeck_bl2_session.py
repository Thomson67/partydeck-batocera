"""Companion loaded by Willow2 SDK in the private game overlay, never solo."""
from pathlib import Path
import json
import os
import time


class Session:
    def __init__(self, config, now=time.monotonic):
        self.config=config
        self.now=now
        self.lan=False
        self.next_tick=0
        self.attempts=0
        self.joined=False
        self.deadline=None

    def tick(self, pc, world):
        c=self.config
        if not c.get('automatic') or pc is None or world is None:return
        now=self.now()
        if now<self.next_tick:return
        self.next_tick=now+1
        if not self.lan:
            pc.AttemptNetworkTransition(1,2,False)
            self.lan=True
        host=c['index']+1==c['host_player']
        netmode=int(world.NetMode)
        path=Path(c['host_marker'])
        if host:
            if netmode==2:
                # A listen server is the readiness signal; startup/menu timing
                # is not enough to let the other players connect.
                data=json.dumps(dict(token=c['token'],ready=True))
                if not path.exists() or path.read_text()!=data:
                    temporary=path.with_suffix('.tmp')
                    temporary.write_text(data);os.replace(temporary,path)
            elif path.exists():
                try:
                    if json.loads(path.read_text()).get('token')==c['token']:path.unlink()
                except (OSError,ValueError):pass
            return
        if netmode==3:
            self.joined=True
            return
        # Do not pull a player back into a party after an intentional leave.
        if self.joined:return
        try:ready=json.loads(path.read_text())
        except (OSError,ValueError):return
        if ready.get('token')!=c['token'] or not ready.get('ready'):return
        if self.deadline is None:self.deadline=now+120
        if now>=self.deadline or self.attempts>=6:return
        self.next_tick=now+20
        pc.ConsoleCommand('open 127.0.0.1:'+str(c['port']),False)
        self.attempts+=1


def load():
    from mods_base import ENGINE, build_mod, hook
    config_path=Path(__file__).parent.parent/'partydeck_session.json'
    try:config=json.loads(config_path.read_text())
    except (OSError,ValueError):config={}
    session=Session(config)

    def update():
        try:
            players=ENGINE.GamePlayers
            if players and players[0].Actor:
                pc=players[0].Actor
                session.tick(pc,pc.WorldInfo)
        except Exception as error:
            # SDK failures must never abort the game or spin on every frame.
            session.next_tick=session.now()+10
            print('Windows Party / Borderlands 2:',error)

    @hook('WillowGame.WillowPlayerController.PlayerTick')
    def tick(obj,args,ret,func):
        update()

    @hook('WillowGame.WillowGFxMoviePressStart.BeginStartupProcess')
    def startup(obj,args,ret,func):
        update()

    return build_mod(name='Windows Party LAN',version='0.1',author='Windows Party',
                     hooks=[startup,tick],auto_enable=True)


if os.name=='nt':
    mod=load()
