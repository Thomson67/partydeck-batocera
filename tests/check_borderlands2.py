"""Private BL2 INI application, dimensions, presets, backups and launcher ordering."""
import codecs
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_borderlands2 as bl2
from partydeck_anchor import instrument_native
from partydeck_profiles import defaults, save_profile, read_profile

ORIGINAL = ('; Exemple privé\r\n[SystemSettings]\r\nFullscreen=True\r\nWindowedFullscreen=False\r\n'
            'ResX=1920\r\nResY=1080\r\nTextureQuality=1\r\nPhysXLevel=0\r\n'
            'UseVsync=True\r\nShadowSplit=0.1\r\nShadowSplit=0.5\r\n'
            '[SystemSettingsMobile]\r\nFullscreen=True\r\nResX=800\r\n'
            '[Core.System]\r\nSuppress=DevOne\r\nSuppress=DevTwo\r\n')

assert bl2.matches(Path('Borderlands 2 [GE-Proton].wsquashfs'))
assert bl2.matches(Path('Borderlands_II.wine'))
assert not bl2.matches(Path('Borderlands 3.pc'))
assert not bl2.matches(Path('Borderlands 2 VR.wsquashfs'))
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder)
    rom=root/'Borderlands 2.wsquashfs'
    profile=defaults(rom)
    assert profile['adapter']=='borderlands2'
    save_profile(root,rom,profile)
    assert read_profile(root,rom)['borderlands2']==bl2.defaults()
    for index,(width,height) in enumerate(((1920,540),(960,1080),(960,540),(1280,720)),1):
        player=root/f'j{index}'
        prefix=player/'prefix'
        path=prefix/'drive_c/users/steamuser/Documents/My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini'
        path.parent.mkdir(parents=True)
        path.write_bytes(ORIGINAL.encode())
        saves=path.parent.parent/'SaveData/slot.sav'
        saves.parent.mkdir()
        saves.write_bytes(b'PROGRESSION')
        payload=dict(player=str(player),settings=bl2.defaults(),width=width,height=height)
        bl2.apply_config(prefix,payload,private_binds=())
        text=path.read_bytes().decode()
        assert 'Fullscreen=False\r\nWindowedFullscreen=True' in text
        assert 'bPauseLostFocusWindowed=False' in text
        assert f'ResX={width}\r\nResY={height}' in text
        assert 'TextureQuality=1\r\nPhysXLevel=0\r\nUseVsync=True' in text
        assert '[SystemSettingsMobile]\r\nFullscreen=True\r\nResX=800' in text
        assert text.count('ShadowSplit=')==2 and text.count('Suppress=')==2
        assert '\n' not in text.replace('\r\n','')
        assert list((player/'borderlands2-before').glob('*.ini'))[0].read_bytes()==ORIGINAL.encode()
        for preset in bl2.PRESETS[1:]:
            payload['settings']['preset']=preset
            bl2.apply_config(prefix,payload,private_binds=())
        assert 'MaxShadowResolution=4096' in path.read_text()
        assert 'MaxAnisotropy=16' in path.read_text() and 'ViewDistance=3' in path.read_text()
        assert saves.read_bytes()==b'PROGRESSION'
        assert len(list((player/'borderlands2-before').glob('*.ini')))==1
        assert list((player/'borderlands2-before').glob('*.ini'))[0].read_bytes()==ORIGINAL.encode()
    # Legitimate Documents redirection into the player's private save bind works.
    player=root/'linked'; prefix=player/'prefix with spaces'
    user=prefix/'drive_c/users/root'; user.mkdir(parents=True)
    private_saves=player/'private-saves';private_saves.mkdir()
    (user/'Documents').symlink_to(private_saves,target_is_directory=True)
    payload=dict(player=str(player),settings=bl2.defaults(),width=1920,height=540)
    bl2.apply_config(prefix,payload,private_binds=())
    assert (private_saves/'My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini').is_file()
    (user/'Documents').unlink()
    solo=root/'solo';solo.mkdir()
    untouched=solo/'precious';untouched.write_bytes(b'SOLO')
    (user/'Documents').symlink_to(solo,target_is_directory=True)
    try:
        bl2.apply_config(prefix,payload,private_binds=())
        raise AssertionError('wrote through a solo symlink')
    except ValueError:
        assert list(solo.iterdir())==[untouched] and untouched.read_bytes()==b'SOLO'
    (user/'Documents').unlink()
    # Existing UMU private prefixes reused after interruption get the same options.
    reused=player/'umu-private/materialized-prefixes/game'
    reused_ini=reused/'drive_c/users/steamuser/Documents/My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini'
    reused_ini.parent.mkdir(parents=True);reused_ini.write_text(ORIGINAL)
    bl2.apply_config(prefix,payload,private_binds=())
    assert 'WindowedFullscreen=True' in reused_ini.read_text()
    # UTF-16 configs and case-insensitive existing Windows paths stay usable.
    explicit=prefix/'Custom'/'WILLOWENGINE.INI';explicit.parent.mkdir()
    explicit.write_bytes(codecs.BOM_UTF16_LE+ORIGINAL.encode('utf-16-le'))
    payload['settings']['config']='custom/willowengine.ini'
    # Test explicit path separately from the unrelated cached prefixes.
    shutil_path=player/'umu-private'
    import shutil
    shutil.rmtree(shutil_path)
    bl2.apply_config(prefix,payload,private_binds=())
    assert explicit.read_bytes().startswith(codecs.BOM_UTF16_LE)
    assert 'WindowedFullscreen=True' in explicit.read_bytes().decode('utf-16')
    for key,value in (('preset','ultra-invalid'),('config','../solo.ini'),('config','/tmp/a.ini')):
        try:
            bl2.validate(dict(bl2.defaults(),**{key:value}))
            raise AssertionError('invalid options accepted')
        except ValueError:
            pass
    # Execute a native-shaped launcher: apply only after mounting/setup, before Wine.
    payload_file=player/'payload.json';payload_file.write_text(json.dumps(payload))
    explicit.write_bytes(ORIGINAL.encode())
    source='#!/bin/bash\nset -e\n'
    for name in ('play_wine','play_pc','play_squashfs'):
        source+=name+'() {\n if [[ -n "${WINE_LANG:-}" ]]; then\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q WindowedFullscreen=True Custom/WILLOWENGINE.INI)\n else\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q WindowedFullscreen=True Custom/WILLOWENGINE.INI)\n fi\n}\n'
    source+=f'WINEPOINT={shlex.quote(str(prefix))}\nWINE_DIR=.\nplay_squashfs\n'
    native=player/'native.sh'
    hook=[sys.executable,str(Path(bl2.__file__)),str(payload_file)]
    native.write_text(instrument_native(source,hook,prefix_argument=True))
    subprocess.run(['bash',str(native)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),check=True)
    # Real hook installation preserves the host launcher and uses private replacement.
    native.write_text(source)
    with patch.object(bl2.shutil,'which',return_value=str(native)),patch.object(bl2.subprocess,'run') as run, \
         patch.dict(os.environ,dict(PARTYDECK_PLAYER_WIDTH='960',PARTYDECK_PLAYER_HEIGHT='540')):
        bl2.install_hook(root,rom,player)
        assert run.call_args_list[-1].args[0]==['mount','--bind',str(player/'batocera-wine-borderlands2'),str(native)]
    assert native.read_text()==source
    spec=importlib.util.spec_from_file_location('bl2_coop',Path(bl2.__file__).parent/'partydeck-batocera-coop.py')
    coop=importlib.util.module_from_spec(spec);sys.modules[spec.name]=coop;spec.loader.exec_module(coop)
    with patch('partydeck_profiles.profile_path',return_value=root/'profiles'/'exists'), \
         patch('partydeck_profiles.read_profile',return_value=profile), \
         patch.object(coop,'sandbox_arguments',return_value=[]),patch.object(coop.subprocess,'Popen') as launch:
        (root/'profiles'/'exists').touch()
        coop.start_player(root,player,rom,rom,[],(0,0,1920,540),'test',saves=root/'saves')
        args=launch.call_args.args[0]
        assert args[args.index('-w')+1]=='1920' and args[args.index('-h')+1]=='540'
        assert launch.call_args.kwargs['env']['PARTYDECK_PLAYER_HEIGHT']=='540'

print('Borderlands 2 : INI, préréglages, dimensions J1–J4, sauvegardes, liens privés, UMU et application avant Wine vérifiés.')
