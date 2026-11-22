"""Companion loaded by Willow2 SDK in the private game overlay, never solo."""
from pathlib import Path
import json
import os
import time


class Session:
    def __init__(self, config, now=time.monotonic, log=lambda message: None):
        self.config=config
        self.now=now
        self.log=log
        self.lan=False
        self.next_tick=0
        self.attempts=0
        self.joined=False
        self.client_mode=False
        self.deadline=None
        self.expired=False

    def tick(self, pc, world):
        c=self.config
        if not c.get('automatic') or pc is None or world is None:return
        host=c['index']+1==c['host_player']
        # Notice a connection even during the retry delay. A short visit to
        # NM_Client is enough to stop automatic retries after a disconnect.
        if not host:
            client_mode=int(world.NetMode)==3
            if client_mode!=self.client_mode:
                self.log('Entered client mode.' if client_mode else 'Left client mode.')
                self.client_mode=client_mode
            if self.joined or client_mode:
                self.joined=True
                return
        now=self.now()
        if now<self.next_tick:return
        self.next_tick=now+1
        if not self.lan:
            pc.AttemptNetworkTransition(1,2,False)
            self.lan=True
            self.log('LAN transition requested.')
        path=Path(c['host_marker'])
        if host:
            if int(world.NetMode)==2:
                # A listen server is the readiness signal; startup/menu timing
                # is not enough to let the other players connect.
                data=json.dumps(dict(token=c['token'],ready=True))
                if not path.exists() or path.read_text()!=data:
                    temporary=path.with_suffix('.tmp')
                    temporary.write_text(data);os.replace(temporary,path)
                    self.log('Host ready.')
            elif path.exists():
                try:
                    if json.loads(path.read_text()).get('token')==c['token']:
                        path.unlink()
                        self.log('Host no longer ready.')
                except (OSError,ValueError):pass
            return
        try:ready=json.loads(path.read_text())
        except (OSError,ValueError):return
        if ready.get('token')!=c['token'] or not ready.get('ready'):return
        if self.deadline is None:
            self.deadline=now+120
            self.log('Host ready signal received.')
        if now>=self.deadline or self.attempts>=6:
            if not self.expired:
                self.log('Automatic join attempts ended without entering client mode.')
                self.expired=True
            return
        self.next_tick=now+20
        self.attempts+=1
        self.log(f'Automatic join attempt {self.attempts}: 127.0.0.1:{c["port"]}.')
        pc.ConsoleCommand('open 127.0.0.1:'+str(c['port']),False)


def load():
    from mods_base import build_mod, get_pc, hook
    from unrealsdk import logging
    config_path=Path(__file__).parent.parent/'partydeck_session.json'
    try:config=json.loads(config_path.read_text())
    except (OSError,ValueError):config={}
    trace=None
    if os.name=='nt' and config.get('automatic'):
        trace=Path('Z:'+config['player'].replace('/','\\'))/'bl2-lan.log'

    def log(message, *, reset=False):
        if trace is None:return
        try:
            with trace.open('w' if reset else 'a',encoding='utf-8') as stream:
                stream.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {message}\n')
        except OSError as error:
            logging.error(f'Windows Party LAN log: {error}')

    session=Session(config,log=log)
    next_error=0

    @hook('Engine.PlayerController:PlayerTick')
    def tick(obj,args,ret,func):
        nonlocal next_error
        try:
            pc=get_pc()
            if pc is not None and pc==obj:
                session.tick(pc,pc.WorldInfo)
        except IndexError:
            # The SDK's player list can still be empty on the first frames.
            pass
        except Exception as error:
            # SDK failures must never abort the game or spin on every frame.
            now=session.now()
            if now>=next_error:
                next_error=now+10
                log(f'{type(error).__name__}: {error}')

    mod=build_mod(name='Windows Party LAN',version='0.2',author='Windows Party',
                  hooks=[tick],auto_enable=False)
    # The SDK's auto_enable only restores an earlier enabled state. The
    # PartyDeck session plan, rather than an SDK preference, owns activation.
    if config.get('automatic'):
        log(f'J{config["index"]+1}; host J{config["host_player"]}; port {config["port"]}.',reset=True)
        mod.enable()
        log('LAN module enabled.')
        logging.info(f'Windows Party LAN: J{config["index"]+1}, host J{config["host_player"]}')
    return mod


if os.name=='nt':
    mod=load()
