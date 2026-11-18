"""Private BL2 INI application, dimensions, presets, backups and launcher ordering."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import codecs
import importlib.util
import json
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
    legacy=dict(windowed_fullscreen=False,fit_resolution=False,config='../old.ini',preset='keep',physx='keep')
    assert bl2.validate(legacy)==bl2.defaults()
    old=defaults(rom);old['borderlands2']=legacy
    save_profile(root,rom,old)
    assert read_profile(root,rom)['borderlands2']==bl2.defaults()
    forced=bl2.overrides(legacy,960,1080)
    assert forced['SystemSettings']['WindowedFullscreen']=='True' and forced['SystemSettings']['ResX']==960
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
        for mode,expected in (('on','True'),('off','False'),('keep','False')):
            payload['settings']['vsync']=mode
            bl2.apply_config(prefix,payload,private_binds=())
            assert 'UseVsync='+expected in path.read_text()
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
    original_ini=user/'Documents/My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini'
    explicit=original_ini.with_name('WILLOWENGINE.INI');original_ini.rename(explicit)
    explicit.write_bytes(codecs.BOM_UTF16_LE+ORIGINAL.encode('utf-16-le'))
    # Test automatic discovery separately from the unrelated cached prefixes.
    shutil_path=player/'umu-private'
    import shutil
    shutil.rmtree(shutil_path)
    bl2.apply_config(prefix,payload,private_binds=())
    assert explicit.read_bytes().startswith(codecs.BOM_UTF16_LE)
    assert 'WindowedFullscreen=True' in explicit.read_bytes().decode('utf-16')
    for key,value in (('preset','ultra-invalid'),('vsync','invalid'),('physx','invalid'),
                      ('language','invalid'),('names',['one']),('names',['bad\nLanguage=foo','','','']),
                      ('names',['bad;name','','','']),('names',[' ']*4),('names',['x'*65]*4)):
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
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q WindowedFullscreen=True "drive_c/users/root/Documents/My Games/Borderlands 2/WillowGame/Config/WILLOWENGINE.INI")\n else\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q WindowedFullscreen=True "drive_c/users/root/Documents/My Games/Borderlands 2/WillowGame/Config/WILLOWENGINE.INI")\n fi\n}\n'
    source+=f'WINEPOINT={shlex.quote(str(prefix))}\nWINE_DIR=.\nplay_squashfs\n'
    native=player/'native.sh'
    hook=[sys.executable,str(Path(bl2.__file__)),str(payload_file)]
    native.write_text(instrument_native(source,hook,prefix_argument=True))
    subprocess.run(['bash',str(native)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),check=True)
    # Real hook installation preserves the host launcher and uses private replacement.
    native.write_text(source)
    with patch.object(bl2.shutil,'which',return_value=str(native)),patch.object(bl2.subprocess,'run') as run, \
         patch.dict(os.environ,dict(PARTYDECK_PLAYER_WIDTH='960',PARTYDECK_PLAYER_HEIGHT='540')):
        bl2.install_hook(root,rom,root/'j1')
        assert run.call_args_list[-1].args[0]==['mount','--bind',str(root/'j1/batocera-wine-borderlands2'),str(native)]
        assert json.loads((root/'j1/borderlands2-launch.json').read_text())['index']==0
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

    # Persona/language are taken from the supplied INI, never from Willow Name.
    original=(b'### legacy header \xdc\xb2\r\n[Settings]\r\nAppId=49520\r\nUserName=CODEX\r\n'
              b'Language=french\r\nOffline=0\r\nLobbyEnabled=1\r\n#AccountId=0\r\n'
              b'[DLC]\r\nDLCUnlockall=0\r\n[Interfaces]\r\nSteamFriends=SteamFriends013\r\n')
    names=['Alice','Benoît','Charlie','David']
    configs=[]
    for index in range(4):
        player=root/f'persona/j{index+1}'
        prefix=player/'prefix';game=prefix/'drive_c/game'
        ini=game/'binaries/WIN32/STEAM_EMU.INI'
        ini.parent.mkdir(parents=True);ini.write_bytes(original)
        (prefix/'drive_c/users/steamuser').mkdir(parents=True)
        payload=dict(player=str(player),index=index,width=960,height=540,
                     settings=dict(bl2.defaults(),language='english',names=names))
        bl2.apply_config(prefix,payload,private_binds=(),directory=game)
        after=ini.read_bytes()
        assert after==original.replace(b'UserName=CODEX',('UserName='+names[index]).encode()).replace(b'Language=french',b'Language=english')
        assert any(p.read_bytes()==original for p in (player/'borderlands2-before').glob('*.ini'))
        configs.append(ini)
        payload['settings']=bl2.defaults()
        bl2.apply_config(prefix,payload,private_binds=(),directory=game)
        assert ini.read_bytes()==after  # Keep leaves the current player values intact.
    assert b'UserName=Alice' in configs[0].read_bytes() and b'UserName=David' in configs[3].read_bytes()
    payload['settings']=dict(bl2.defaults(),language='french')
    bl2.apply_config(prefix,payload,private_binds=(),directory=game)
    assert b'Language=french' in ini.read_bytes() and b'UserName=David' in ini.read_bytes()
    # Refuse another game's config, external links or missing configurations,
    # validating everything before any of the Willow display edits are written.
    willow=prefix/'drive_c/users/steamuser/Documents/My Games/Borderlands 2/WillowGame/Config/WillowEngine.ini'
    unchanged=willow.read_bytes()
    for kind in ('appid','symlink','missing','directory-link'):
        ini.unlink(missing_ok=True)
        if kind=='appid':ini.write_bytes(original.replace(b'AppId=49520',b'AppId=123'))
        if kind=='symlink':ini.symlink_to(configs[0])
        if kind=='directory-link':
            ini.parent.rmdir();ini.parent.symlink_to(configs[0].parent,target_is_directory=True)
        try:
            bl2.apply_config(prefix,payload,private_binds=(),directory=game)
            raise AssertionError('invalid Steam config accepted: '+kind)
        except ValueError:
            assert willow.read_bytes()==unchanged
            assert b'UserName=Alice' in configs[0].read_bytes()

print('Borderlands 2 : INI, préréglages, dimensions J1–J4, sauvegardes, liens privés, UMU et application avant Wine vérifiés.')
