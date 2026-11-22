"""Real command hooks, private batch rollback, Source readiness and SDK states."""
import os
os.environ['PARTYDECK_LANGUAGE']='fr'
import hashlib
import json
from pathlib import Path
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import Mock,patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_autoconnect as auto
import partydeck_bl2_session as bl2_session
from partydeck_bl2_session import Session
from partydeck_profiles import defaults,save_profile
from partydeck_i18n import EN

for kind in auto.EXECUTABLES:
    config=auto.options({},kind)
    assert config['automatic'] and config['host_player']==1
    for invalid in (dict(automatic=1),dict(port=True),dict(port=65536),dict(host_player=0)):
        try:auto.options(invalid,kind);raise AssertionError(invalid)
        except ValueError:pass

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);player=root/'players/j1';player.mkdir(parents=True)
    prefix=player/'prefix';game=prefix/'drive_c/game';game.mkdir(parents=True)
    plan=dict(player=str(player),token='a'*32,count=2,index=0,host_player=1,
              port=7777,automatic=True,kind='sm64coopdx',base=str(root))
    for command in ('"sm64coopdx.exe"','start "" sm64coopdx.exe -f','"C:\\A B\\sm64coopdx.exe"'):
        out,found=auto.command_arguments(command,plan)
        assert found and out==command+' --server 7777'
    for command in ('sm64coopdx-helper.exe','launcher.exe','sm64coopdx.exe > log','sm64coopdx.exe & exit'):
        assert auto.command_arguments(command,plan)==(command,False)
    try:auto.command_arguments('sm64coopdx.exe --client 1.2.3.4 7777',plan);raise AssertionError('conflicting network')
    except ValueError:pass
    other=dict(plan,index=1)
    assert auto.game_arguments(other)==['--client','127.0.0.1','7777']
    assert '+map' not in auto.game_arguments(dict(plan,kind='l4d2',campaign='menu'))
    assert auto.game_arguments(dict(plan,kind='l4d2',campaign='c1m1_hotel'))[-3:]==['+map','c1m1_hotel','coop']
    startup=dict(plan,kind='l4d2',campaign='c1m1_hotel',difficulty='hard')
    assert auto.game_arguments(startup)[-5:]==['+z_difficulty','hard','+map','c1m1_hotel','coop']
    assert '+z_difficulty' not in auto.game_arguments(dict(startup,campaign_mode='versus'))
    assert '+z_difficulty' not in auto.game_arguments(dict(startup,campaign='menu'))
    for mode in ('realism','versus'):
        campaign=dict(plan,kind='l4d2',campaign='c1m1_hotel',campaign_mode=mode)
        assert auto.game_arguments(campaign)[-3:]==['+map','c1m1_hotel',mode]
        assert '+map' not in auto.game_arguments(dict(campaign,campaign='menu'))
        assert '+map' not in auto.game_arguments(dict(campaign,index=1))
    source_client=dict(plan,kind='l4d2',index=1,direct=True,port=27015)
    cfg=game/'left4dead2/cfg'
    cfg.mkdir(parents=True)
    for address in ('192.168.1.141','192.168.1.162',False):
        client=dict(source_client)
        with patch.object(auto,'wait_host',return_value=address) as wait:
            out=auto.launch_command('left4dead2.exe -novid',client)
        wait.assert_called_once_with(client,timeout=120)
        assert client['direct']
        if address:
            assert out.endswith(f'+connect {address}:27015')
        else:
            assert '+connect' not in out
    source_batch=game/'source.bat'
    source_batch.write_bytes(b'@echo off\r\nstart "" left4dead2.exe -novid\r\n')
    client=dict(source_client)
    with patch.object(auto,'wait_host',return_value='192.168.1.141') as wait:
        assert auto.launch_command('cmd /c source.bat',client)=='cmd /c source.bat'
        auto.prepare_game(game,prefix,client)
    wait.assert_called_once()
    assert b'+connect 192.168.1.141:27015' in source_batch.read_bytes()
    auto.prepare_game(game,prefix,dict(client,automatic=False))
    assert b'+connect' not in source_batch.read_bytes()
    original_host_cfg=cfg/'listenserver.cfg'
    original_host_cfg.write_text('sv_allow_lobby_connect_only 1\n')
    source_host=dict(source_client,index=0)
    for address in ('192.168.1.141','192.168.1.162'):
        with patch.object(auto,'udp_bound',return_value=False), \
             patch.object(auto,'lan_ipv4_address',return_value=address):
            auto.prepare_game(game,prefix,source_host)
        assert json.loads(auto.marker(source_client).read_text())['address']==address
        with patch.object(auto,'source_ready',return_value=True) as probe:
            assert auto.wait_host(source_client,timeout=1)==address
        probe.assert_called_once_with(27015,address=address)
    with patch.object(auto,'source_ready',side_effect=[False,True]) as probe:
        assert auto.wait_host(source_client,timeout=1)=='127.0.0.1'
    assert original_host_cfg.read_text()=='sv_allow_lobby_connect_only 1\n'
    assert (cfg/auto.SOURCE_HOST).read_text().splitlines()[:3]==[
        'exec listenserver.cfg','sv_lan 1','sv_allow_lobby_connect_only 0']
    for native_host_cfg in ('',' +lservercfgfile custom.cfg'):
        out,found=auto.command_arguments('left4dead2.exe'+native_host_cfg,source_host)
        assert found and out.count('+lservercfgfile')==1
        assert ('custom.cfg' if native_host_cfg else auto.SOURCE_HOST) in out
    command='"Borderlands2.exe"'
    for index in (0,1):
        assert auto.command_arguments(command,dict(plan,kind='borderlands2',index=index))==(command,True)
    custom=auto.command_arguments(command,dict(plan,kind='borderlands2',port=7781))
    assert custom==(command+' -port=7781',True)

    # Only the batch actually selected by the native launcher is modified.
    batch=game/'start.bat';original=b'@echo off\r\nrem sm64coopdx.exe\r\nstart "" "sm64coopdx.exe" -f\r\n'
    batch.write_bytes(original)
    unused=game/'other.bat';unused.write_bytes(original)
    plan.update(original_command='cmd /c start.bat',direct=False)
    with patch.object(auto,'udp_bound',return_value=False):auto.prepare_game(game,prefix,plan)
    assert b'--server 7777' in batch.read_bytes() and unused.read_bytes()==original
    # Repeat launches don't accumulate arguments; manual mode restores originals.
    with patch.object(auto,'udp_bound',return_value=False):auto.prepare_game(game,prefix,plan)
    assert batch.read_bytes().count(b'--server')==1
    auto.prepare_game(game,prefix,dict(plan,automatic=False))
    assert batch.read_bytes()==original
    with patch.object(auto,'udp_bound',return_value=False):auto.prepare_game(game,prefix,plan)
    batch.write_bytes(b'USER CHANGED')
    auto.prepare_game(game,prefix,dict(plan,automatic=False))
    assert batch.read_bytes()==b'USER CHANGED'
    # Stale host readiness cannot launch a client in a new session.
    auto.write_bytes(auto.marker(plan),json.dumps(dict(token='b'*32)).encode())
    with patch.object(auto,'udp_bound',return_value=True),patch.object(auto.time,'monotonic',side_effect=[0,0,2]),patch.object(auto.time,'sleep'):
        assert not auto.wait_host(other,timeout=1)

    # Native command parsing runs before the private configuration hook.
    native=root/'batocera-wine'
    source='#!/bin/bash\ngetWine_var() { echo sm64coopdx.exe; }\n'
    for name in ('play_wine','play_pc','play_squashfs'):
        source+=name+'() {\n WINE_CMD=$(getWine_var "${WINEPOINT}" "CMD" "explorer")\n'
        for _ in range(2):source+=' (cd "${WINEPOINT}/${WINE_DIR}" && printf "%s\\n" "$WINE_CMD")\n'
        source+='}\n'
    source+='WINEPOINT='+shlex.quote(str(prefix))+'\nWINE_DIR=drive_c/game\nplay_wine\n'
    native.write_text(source)
    rom=root/'SM64CoopDX.wsquashfs';rom.touch()
    profile=defaults(rom)
    scripts=Path(auto.__file__).parent
    env=dict(PARTYDECK_SESSION_TOKEN='a'*32,PARTYDECK_SESSION_PLAYERS='2',PARTYDECK_PRIVATE_PLAYER=str(player))
    with patch('partydeck_profiles.profile_path',return_value=rom),patch('partydeck_profiles.read_profile',return_value=profile), \
         patch('shutil.which',return_value=str(native)),patch.object(auto.subprocess,'run'),patch.dict(os.environ,env):
        auto.install_hook(scripts,rom,player)
    replacement=player/'batocera-wine-autoconnect'
    # Bind a real local UDP socket only after the host marker is reset, so the
    # hook should refuse hosting into somebody else's occupied port.
    auto.marker(plan).unlink(missing_ok=True)
    result=subprocess.run(['bash',str(replacement)],env=dict(os.environ,**env),capture_output=True,text=True,timeout=10)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert result.stdout.count('sm64coopdx.exe --server 7777')==2,result.stdout
    # Selecting the default adapter restores private batches and disables SDK
    # state left by a previous multiplayer profile, even in a new session.
    with patch('partydeck_profiles.profile_path',return_value=rom),patch('partydeck_profiles.read_profile',return_value=dict(adapter='standard')), \
         patch('shutil.which',return_value=str(native)),patch.object(auto.subprocess,'run'),patch.dict(os.environ,env):
        auto.install_hook(scripts,rom,player)
    cleanup=json.loads((player/'autoconnect-launch.json').read_text())
    assert not cleanup['automatic'] and cleanup['count']==1
    result=subprocess.run(['bash',str(replacement)],env=dict(os.environ,**env),capture_output=True,text=True,timeout=10)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert '--server' not in result.stdout

    rom=root/'Left 4 Dead 2.wsquashfs';rom.touch()
    profile=defaults(rom)
    profile['l4d2'].update(campaign='c1m1_hotel',campaign_mode='versus')
    with patch('partydeck_profiles.profile_path',return_value=rom),patch('partydeck_profiles.read_profile',return_value=profile), \
         patch('shutil.which',return_value=str(native)),patch.object(auto.subprocess,'run'),patch.dict(os.environ,env):
        auto.install_hook(scripts,rom,player)
    assert json.loads((player/'autoconnect-launch.json').read_text())['campaign_mode']=='versus'
    chosen=dict(campaign='c2m1_highway',campaign_mode='realism',difficulty='impossible')
    with patch('partydeck_profiles.profile_path',return_value=rom),patch('partydeck_profiles.read_profile',return_value=profile), \
         patch('shutil.which',return_value=str(native)),patch.object(auto.subprocess,'run'), \
         patch.dict(os.environ,dict(env,PARTYDECK_L4D2_LAUNCH=json.dumps(chosen))):
        auto.install_hook(scripts,rom,player)
    loaded=json.loads((player/'autoconnect-launch.json').read_text())
    assert {key:loaded[key] for key in chosen}==chosen
    assert profile['l4d2']['campaign']=='c1m1_hotel'

    # Pinned SDK fixture: files stay under the player's game view. Never
    # overwrite an existing loader or change the source SDK zip.
    archive=root/'dependencies/willow2-sdk-v3.8.zip';archive.parent.mkdir()
    with zipfile.ZipFile(archive,'w') as sdk:
        sdk.writestr('Binaries/Win32/ddraw.dll',b'LOADER')
        sdk.writestr('Binaries/Win32/Plugins/unrealsdk.dll',b'SDK')
        sdk.writestr('sdk_mods/__main__.py',b'# bootstrap')
    (root/'partydeck_bl2_session.py').write_bytes(b'# companion')
    blplan=dict(plan,kind='borderlands2')
    with patch.object(auto,'SDK_SHA256',hashlib.sha256(archive.read_bytes()).hexdigest()):
        auto.prepare_game(game,prefix,blplan)
        assert not (game/'Binaries/Win32/ddraw.dll').exists()
        auto_lan_marker=player.parent/'bl2-auto-lan.mode'
        auto_lan_marker.touch()
        auto.prepare_game(game,prefix,blplan)
        host_plan=json.loads((game/'sdk_mods/partydeck_session.json').read_text())
        assert host_plan['automatic'] and host_plan['auto_lan']
        assert (player/'autoconnect-sdk-ready').exists()
        auto_lan_marker.unlink()
        auto.prepare_game(game,prefix,dict(blplan,host_player=2))
        assert (player/'autoconnect-sdk-ready').exists()
        assert (game/'Binaries/Win32/ddraw.dll').read_bytes()==b'LOADER'
        assert json.loads((game/'sdk_mods/partydeck_session.json').read_text())['automatic']
        auto.configure_bl2(game,player,dict(blplan,automatic=False),(prefix,player))
        assert not json.loads((game/'sdk_mods/partydeck_session.json').read_text())['automatic']
        (game/'Binaries/Win32/ddraw.dll').write_bytes(b'OTHER LOADER')
        auto.configure_bl2(game,player,blplan,(prefix,player))
        assert (game/'Binaries/Win32/ddraw.dll').read_bytes()==b'OTHER LOADER'
    # A socket held only by P2 cannot publish P1's readiness.
    proc=root/'proc';(proc/'net').mkdir(parents=True)
    (proc/'net/udp').write_text('header\n  0: 00000000:1E61 00000000:0000 07 0 0 0 0 0 42\n')
    sample=proc/'123';(sample/'fd').mkdir(parents=True)
    (sample/'fd/4').symlink_to('socket:[42]')
    environ=sample/'environ'
    environ.write_bytes(b'PARTYDECK_PRIVATE_PLAYER='+os.fsencode(player.with_name('j2'))+b'\0')
    assert not auto.bl2_owns_port(player,'192.168.1.141',7777,proc)
    environ.write_bytes(b'PARTYDECK_PRIVATE_PLAYER='+os.fsencode(player)+b'\0')
    assert auto.bl2_owns_port(player,'192.168.1.141',7777,proc)
    host=auto.BL2Host(player,7777,blplan['token'],'192.168.1.141')
    with patch.object(auto,'bl2_owns_port',return_value=True):
        host.poll()
    path=host.path;clock=[0]
    assert json.loads(path.read_text())==dict(token='a'*32,ready=True,address='192.168.1.141',port=7777)
    cfg=dict(blplan,index=1,host_marker=str(path))

    # Willow2 auto_enable restores saved settings only. A fresh PartyDeck
    # session must explicitly activate the registered local-player hook.
    module_path=game/'sdk_mods/partydeck_session/__init__.py'
    config_path=module_path.parent.parent/'partydeck_session.json'
    config_path.write_text(json.dumps(cfg))
    mod=Mock()
    local_pc=Mock(WorldInfo=SimpleNamespace(NetMode=0))
    hook=Mock(side_effect=lambda path:lambda callback:callback)
    sdk=SimpleNamespace(build_mod=Mock(return_value=mod),get_pc=lambda:local_pc,hook=hook)
    with patch.object(bl2_session,'__file__',str(module_path)),patch.dict(sys.modules,{
            'mods_base':sdk,'unrealsdk':SimpleNamespace(logging=Mock())}):
        bl2_session.load()
        mod.enable.assert_called_once_with()
        hook.assert_called_once_with('Engine.PlayerController:PlayerTick')
        callback,=sdk.build_mod.call_args.kwargs['hooks']
        callback(Mock(),None,None,None)
        local_pc.ClientTravel.assert_not_called()
        callback(local_pc,None,None,None)
        local_pc.ClientTravel.assert_called_once_with('192.168.1.141:7777',0,False)
        local_pc.AttemptNetworkTransition.assert_not_called()
        mod.reset_mock()
        config_path.write_text('{"automatic":false}')
        bl2_session.load()
        mod.enable.assert_not_called()
    clock[0]=1
    events=[]
    client=Session(dict(cfg,index=1),now=lambda:clock[0],log=events.append);client_pc=Mock()
    client.tick(client_pc,SimpleNamespace(NetMode=0))
    client_pc.ClientTravel.assert_called_once_with('192.168.1.141:7777',0,False)
    client_pc.ConsoleCommand.assert_not_called()
    # Joining and leaving can both happen inside the 20-second retry delay.
    # The still-ready host must not pull the client back into the game.
    clock[0]=2;client.tick(client_pc,SimpleNamespace(NetMode=3))
    clock[0]=21;client.tick(client_pc,SimpleNamespace(NetMode=0))
    assert client_pc.ClientTravel.call_count==1 # No forced rejoin after leaving.
    assert events==['Host UDP endpoint verified: 192.168.1.141:7777.',
                    'Automatic join attempt 1: ClientTravel 192.168.1.141:7777.',
                    'Entered client mode.', 'Left client mode.']
    host.close();assert not path.exists()
    trigger=player/'bl2-native-trace.start'
    toggles=[]
    trace=bl2_session.NativeTrace(trigger,toggles.append,events.append,now=lambda:clock[0])
    trace.tick();assert toggles==[]
    trigger.touch()
    trace.tick();assert toggles==[True] and not trigger.exists()
    clock[0]+=14
    trace.tick();assert toggles==[True]
    clock[0]+=1
    trace.tick();assert toggles==[True,False]
    # Native discovery/join calls are observed without changing their arguments.
    args=SimpleNamespace(SessionName='Game',URL='192.168.1.141:7777?Name=Player',
                         PlatformData=123456,UserIndex=0)
    args._type=SimpleNamespace(_properties=lambda: [SimpleNamespace(Name=name)
                                                   for name in ('SessionName','URL','PlatformData','UserIndex')])
    records=[]
    observers=bl2_session.native_argument_hooks(lambda name,post: lambda callback:callback,
                                               'POST',records.append)
    observers[-1](None,args,True,None)
    assert records==[dict(call='Engine.PlayerController:ClientTravel',result=True,
                         params=dict(SessionName='Game',URL='192.168.1.141:7777',UserIndex=0))]
    registered={}
    def register(name,timing):
        def bind(callback):
            registered[name]=(timing,callback)
            return callback
        return bind
    bl2_session.native_argument_hooks(register,'POST',records.append,pre='PRE')
    timing,click=registered[bl2_session.SERVER_BROWSER+'HandleServerBrowserItemClick']
    browser=SimpleNamespace(SortedResults=[SimpleNamespace(
        GameSettings=SimpleNamespace(OwningPlayerName='j1'),PlatformData=123456)])
    click(browser,args,None,None)
    assert timing=='PRE' and records[-1]['result_count']==1
    assert records[-1]['results']==[dict(GameSettings=dict(OwningPlayerName='j1'))]

    # Do not click a different or duplicate host, or trust a previous launch.
    marker=player/'native-ready.json'
    native_config=dict(token=cfg['token'],port=7777,host_marker=str(marker))
    click=Mock(func=object())
    wrapped=object()
    wrap=Mock(return_value=wrapped)
    native=bl2_session.NativeJoin(native_config,'J1',wrap,events.append)
    j1=SimpleNamespace(Name='j1')
    browser=SimpleNamespace(bSearchingForGames=False,SortedResults=[j1],
                            IncompatibleGameVersionsServerIndex=-1,HandleServerBrowserItemClick=click)
    native.select(browser)
    marker.write_text(json.dumps(dict(token='b'*32,ready=True,port=7777)))
    native.select(browser)
    marker.write_text(json.dumps(dict(token=native_config['token'],ready=True,port=7777)))
    for rows in ([SimpleNamespace(Name='other')],[j1,j1]):
        browser.SortedResults=rows
        native.select(browser)
    click.assert_not_called()
    browser.SortedResults=[SimpleNamespace(Name='other'),j1]
    native.select(browser)
    native.select(browser)
    wrap.assert_called_once_with(click.func,ServerIndex=1)
    click.assert_called_once_with(wrapped)
    local_pc=Mock(WorldInfo=SimpleNamespace(NetMode=0))
    menu=Mock()
    boot=bl2_session.LanFrontend(native_config,events.append,now=lambda:clock[0],
                                 weak=lambda obj:lambda:obj)
    boot.tick(local_pc,True)
    local_pc.AttemptNetworkTransition.assert_not_called()
    boot.menu_started(lambda:menu)
    boot.tick(local_pc,True)
    local_pc.AttemptNetworkTransition.assert_not_called()
    clock[0]+=0.5
    local_pc.WorldInfo.NetMode=2
    boot.tick(local_pc,True)
    local_pc.AttemptNetworkTransition.assert_called_once_with(1,2,True)
    assert events[-1]=='Native LAN mode requested from the main menu.'
    menu.ShowLanBrowser.assert_not_called()
    original_world=local_pc.WorldInfo
    local_pc.WorldInfo=SimpleNamespace(NetMode=0)
    clock[0]+=1
    boot.tick(local_pc,True)
    menu.ShowLanBrowser.assert_not_called()
    local_pc.WorldInfo=original_world
    clock[0]+=1
    boot.tick(local_pc,False)
    menu.ShowLanBrowser.assert_not_called()
    clock[0]+=1
    boot.tick(local_pc,True)
    boot.tick(local_pc,True)
    menu.ShowLanBrowser.assert_called_once_with()
    trace.tick();assert toggles==[True,False]

# Real UDP challenge and response, not a mocked readiness boolean.
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as server:
    server.bind(('127.0.0.2',0));server.settimeout(3)
    def respond():
        request,addr=server.recvfrom(2048)
        server.sendto(b'\xff\xff\xff\xffAabcd',addr)
        request,addr=server.recvfrom(2048)
        assert request.endswith(b'abcd')
        server.sendto(b'\xff\xff\xff\xffI\x11name\0map\0folder\0game\0'+struct.pack('<H',550),addr)
    thread=threading.Thread(target=respond);thread.start()
    assert auto.source_ready(server.getsockname()[1],timeout=2,address='127.0.0.2')
    thread.join(timeout=3);assert not thread.is_alive()

print('Autoconnect: launch args, private batches/rollback, session tokens, Source query, SDK conflicts and BL2 readiness verified.')
