"""Companion loaded by Willow2 SDK in the private game overlay, never solo."""
from pathlib import Path
from ipaddress import IPv4Address
import json
import os
import re
import time

TRAVEL_ABSOLUTE = 0
NATIVE_LAN_CALLS = (
    'WillowGame.LANServerBrowserGFxMovie:FindGames',
    'IpDrv.OnlineGameInterfaceImpl:FindOnlineGames',
    'WillowGame.LANServerBrowserGFxMovie:OnFindGamesComplete',
    'WillowGame.LANServerBrowserGFxMovie:JoinMatchmakingSession',
    'IpDrv.OnlineGameInterfaceImpl:JoinOnlineGame',
    'WillowGame.LANServerBrowserGFxMovie:OnJoinMatchComplete',
    'OnlineSubsystemSteamworks.OnlineGameInterfaceSteamworks:GetResolvedConnectString',
    'Engine.PlayerController:ClientTravel',
)


def describe_params(params, depth=1):
    """Read reflected values without interpreting native session pointers."""
    fields={}
    for prop in params._type._properties():
        name=str(prop.Name)
        if name.casefold() in {'platformdata','returnvalue'}:continue
        try:
            value=getattr(params,name)
            if isinstance(value,str):
                fields[name]=value.split('?',1)[0][:120]
            elif value is None or isinstance(value,(bool,int,float)):
                fields[name]=value
            elif depth and hasattr(value,'_type'):
                fields[name]=describe_params(value,depth-1)
            else:
                fields[name]=type(value).__name__
        except Exception as error:
            fields[name]=type(error).__name__
    return fields


def native_argument_hooks(register, post, record):
    hooks=[]
    for name in NATIVE_LAN_CALLS:
        def capture(obj,args,ret,func,*,name=name):
            try:
                data=dict(call=name,params=describe_params(args),
                          result=ret if isinstance(ret,(bool,int,float)) else None)
                if name.endswith((':OnFindGamesComplete',':JoinMatchmakingSession')):
                    data['browser_members']=[field for field in dir(obj) if
                        re.search(r'find|search|server|selected|results|session',field,re.I)][:50]
                record(data)
            except Exception as error:
                record(dict(call=name,error=type(error).__name__))
        hooks.append(register(name,post)(capture))
    return hooks


class NativeTrace:
    """Record one explicitly requested pass through the native LAN menus."""
    def __init__(self, trigger, toggle, log, now=time.monotonic):
        self.trigger=trigger
        self.toggle=toggle
        self.log=log
        self.now=now
        self.deadline=None
        self.done=False

    def tick(self):
        if self.done:return
        if self.deadline is None:
            if not self.trigger.exists():return
            self.trigger.unlink()
            self.toggle(True)
            self.deadline=self.now()+15
            self.log('Native LAN trace started (15 seconds).')
        elif self.now()>=self.deadline:
            self.toggle(False)
            self.done=True
            self.log('Native LAN trace finished.')


class Session:
    def __init__(self, config, now=time.monotonic, log=lambda message: None):
        self.config=config
        self.now=now
        self.log=log
        self.next_tick=0
        self.attempts=0
        self.joined=False
        self.client_mode=False
        self.deadline=None
        self.expired=False

    def tick(self, pc, world):
        c=self.config
        if not c.get('automatic') or pc is None or world is None:return
        if c['index']+1==c['host_player']:return
        # Notice a connection even during the retry delay. A short visit to
        # NM_Client is enough to stop automatic retries after a disconnect.
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
        path=Path(c['host_marker'])
        try:ready=json.loads(path.read_text())
        except (OSError,ValueError):return
        if (not isinstance(ready,dict) or ready.get('token')!=c['token']
                or not ready.get('ready') or ready.get('port')!=c['port']):return
        try:host_address=IPv4Address(ready.get('address'))
        except (ValueError,TypeError):return
        if host_address.is_loopback or host_address.is_unspecified or host_address.is_multicast:return
        if self.deadline is None:
            self.deadline=now+120
            self.log(f'Host UDP endpoint verified: {host_address}:{c["port"]}.')
        if now>=self.deadline or self.attempts>=6:
            if not self.expired:
                self.log('Automatic join attempts ended without entering client mode.')
                self.expired=True
            return
        self.next_tick=now+20
        self.attempts+=1
        address=f'{host_address}:{c["port"]}'
        self.log(f'Automatic join attempt {self.attempts}: ClientTravel {address}.')
        # Invoke the local player's network travel directly from the menu.
        pc.ClientTravel(address,TRAVEL_ABSOLUTE,False)


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

    native_trace=None
    argument_hooks=[]
    if trace is not None and trace.with_name('bl2-native-trace.mode').is_file():
        from unrealsdk.hooks import Type, log_all_calls
        trigger=trace.with_name('bl2-native-trace.start')
        trigger.unlink(missing_ok=True)
        native_log=config_path.parent.parent/'Binaries'/'Win32'/'Plugins'/'unrealsdk.calls.tsv'
        summary=trace.with_name('bl2-native-lan.log')
        summary.unlink(missing_ok=True)
        arguments=trace.with_name('bl2-native-args.log')
        arguments.unlink(missing_ok=True)

        def record_args(data):
            try:
                with arguments.open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(data)+'\n')
            except OSError as error:
                logging.error(f'Windows Party LAN argument trace: {error}')

        argument_hooks=native_argument_hooks(hook,Type.POST_UNCONDITIONAL,record_args)

        def record(enabled):
            log_all_calls(enabled)
            if enabled:return
            relevant=re.compile(r'find.*(game|session)|join|matchmak|lanbeacon|connect|travel',re.I)
            with native_log.open(errors='replace') as source, summary.open('w',encoding='utf-8') as out:
                seen=set()
                for line in source:
                    fields=line.split('\t',2)
                    if len(fields)<2 or not relevant.search(fields[1]) or fields[1] in seen:continue
                    seen.add(fields[1])
                    print(fields[1],file=out)

        native_trace=NativeTrace(trigger,record,log)
    session=Session(config,log=log)
    next_error=0

    @hook('Engine.PlayerController:PlayerTick')
    def tick(obj,args,ret,func):
        nonlocal next_error
        try:
            if native_trace is not None:
                native_trace.tick()
                return
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

    mod=build_mod(name='Windows Party LAN',version='0.3',author='Windows Party',
                  hooks=[tick,*argument_hooks],auto_enable=False)
    # The SDK's auto_enable only restores an earlier enabled state. The
    # PartyDeck session plan, rather than an SDK preference, owns activation.
    if config.get('automatic'):
        log(f'J{config["index"]+1}; host J{config["host_player"]}; port {config["port"]}.',reset=True)
        mod.enable()
        log('LAN module enabled.')
        if native_trace is not None:
            log('Native LAN trace armed. Automatic join disabled for this launch.')
            log('Recording native LAN parameters without a trigger.')
        logging.info(f'Windows Party LAN: J{config["index"]+1}, host J{config["host_player"]}')
    return mod


if os.name=='nt':
    mod=load()
