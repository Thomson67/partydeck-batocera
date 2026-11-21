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
        auto.configure_bl2(game,player,blplan,(prefix,player))
        assert (game/'Binaries/Win32/ddraw.dll').read_bytes()==b'LOADER'
        assert json.loads((game/'sdk_mods/partydeck_session.json').read_text())['automatic']
        auto.configure_bl2(game,player,dict(blplan,automatic=False),(prefix,player))
        assert not json.loads((game/'sdk_mods/partydeck_session.json').read_text())['automatic']
        (game/'Binaries/Win32/ddraw.dll').write_bytes(b'OTHER LOADER')
        auto.configure_bl2(game,player,blplan,(prefix,player))
        assert (game/'Binaries/Win32/ddraw.dll').read_bytes()==b'OTHER LOADER'
    # BL2 host publishes readiness only after becoming a listen server.
    path=player/'bl2-ready.json';clock=[0]
    cfg=dict(blplan,host_marker=str(path));host=Session(cfg,now=lambda:clock[0]);pc=Mock()
    host.tick(pc,SimpleNamespace(NetMode=0));assert not path.exists()
    clock[0]=1;host.tick(pc,SimpleNamespace(NetMode=2))
    assert json.loads(path.read_text())==dict(token='a'*32,ready=True)
    client=Session(dict(cfg,index=1),now=lambda:clock[0]);client_pc=Mock()
    client.tick(client_pc,SimpleNamespace(NetMode=0))
    client_pc.ConsoleCommand.assert_called_once_with('open 127.0.0.1:7777',False)
    clock[0]=22;client.tick(client_pc,SimpleNamespace(NetMode=3))
    clock[0]=50;client.tick(client_pc,SimpleNamespace(NetMode=0))
    assert client_pc.ConsoleCommand.call_count==1 # No forced rejoin after leaving.
    host.tick(pc,SimpleNamespace(NetMode=0));assert not path.exists()

# Real UDP challenge and response, not a mocked readiness boolean.
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as server:
    server.bind(('127.0.0.1',0));server.settimeout(3)
    def respond():
        request,addr=server.recvfrom(2048)
        server.sendto(b'\xff\xff\xff\xffAabcd',addr)
        request,addr=server.recvfrom(2048)
        assert request.endswith(b'abcd')
        server.sendto(b'\xff\xff\xff\xffI\x11name\0map\0folder\0game\0'+struct.pack('<H',550),addr)
    thread=threading.Thread(target=respond);thread.start()
    assert auto.source_ready(server.getsockname()[1],timeout=2)
    thread.join(timeout=3);assert not thread.is_alive()

print('Autoconnect: launch args, private batches/rollback, session tokens, Source query, SDK conflicts and BL2 readiness verified.')
