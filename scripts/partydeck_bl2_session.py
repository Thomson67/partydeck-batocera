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
        host=c['index']+1==c['host_player']
        # Notice a connection even during the retry delay. A short visit to
        # NM_Client is enough to stop automatic retries after a disconnect.
        if not host and (self.joined or int(world.NetMode)==3):
            self.joined=True
            return
        now=self.now()
        if now<self.next_tick:return
        self.next_tick=now+1
        if not self.lan:
            pc.AttemptNetworkTransition(1,2,False)
            self.lan=True
        path=Path(c['host_marker'])
        if host:
            if int(world.NetMode)==2:
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
        try:ready=json.loads(path.read_text())
        except (OSError,ValueError):return
        if ready.get('token')!=c['token'] or not ready.get('ready'):return
        if self.deadline is None:self.deadline=now+120
        if now>=self.deadline or self.attempts>=6:return
        self.next_tick=now+20
        pc.ConsoleCommand('open 127.0.0.1:'+str(c['port']),False)
        self.attempts+=1


def load():
    from mods_base import build_mod, get_pc, hook
    from unrealsdk import logging
    config_path=Path(__file__).parent.parent/'partydeck_session.json'
    try:config=json.loads(config_path.read_text())
    except (OSError,ValueError):config={}
    session=Session(config)

    @hook('Engine.PlayerController:PlayerTick')
    def tick(obj,args,ret,func):
        try:
            pc=get_pc()
            if pc is not None and pc==obj:
                session.tick(pc,pc.WorldInfo)
        except IndexError:
            # The SDK's player list can still be empty on the first frames.
            pass
        except Exception as error:
            # SDK failures must never abort the game or spin on every frame.
            if session.now()>=session.next_tick:
                session.next_tick=session.now()+10
                logging.error(f'Windows Party / Borderlands 2: {error}')

    mod=build_mod(name='Windows Party LAN',version='0.2',author='Windows Party',
                  hooks=[tick],auto_enable=False)
    # The SDK's auto_enable only restores an earlier enabled state. The
    # PartyDeck session plan, rather than an SDK preference, owns activation.
    if config.get('automatic'):
        mod.enable()
        logging.info(f'Windows Party LAN: J{config["index"]+1}, host J{config["host_player"]}')
    return mod


if os.name=='nt':
    mod=load()
