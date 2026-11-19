"""Private HKMP state, addons, command preservation and viewport configuration."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['PARTYDECK_LANGUAGE']='fr'
import json,sys,tempfile,subprocess,uuid
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_hkmp as h
from partydeck_profiles import defaults,save_profile,read_profile
from partydeck_catalog import recipe_for
from partydeck_couch import Model,fields
from partydeck_anchor import instrument_native

assert h.matches(Path('Hollow Knight[GE-Proton].wsquashfs'))
assert h.matches(Path('Hollow_Knight.pc'))
assert not h.matches(Path('Hollow Knight Silksong.wine'))
for value in (True,0,65536,'7777'):
    try:h.validate(dict(port=value));raise AssertionError('invalid port')
    except ValueError:pass
for names in (['A','a','B','C'],['A B','J2','J3','J4'],['x'*21,'B','C','D']):
    try:h.validate(dict(names=names));raise AssertionError('invalid names')
    except ValueError:pass

# Exercise real shell command construction, preserving bat autoruns and other
# DLL overrides in every native Wine launch path.
native='#!/bin/bash\ngetWine_var() { printf "%s" "$COMMAND"; }\n'
for name in ('play_wine','play_pc','play_squashfs'):
    native+=name+'() {\n WINE_CMD=$(getWine_var "${WINEPOINT}" "CMD" "explorer")\n printf "%s\\n%s\\n" "$WINE_CMD" "$WINEDLLOVERRIDES"\n (cd "${WINEPOINT}/${WINE_DIR}" && true)\n (cd "${GAMENAME}/${WINE_DIR}" && true)\n}\n'
native+='play_wine\nplay_pc\nplay_squashfs\n'
for command in ('hollow_knight.exe -keep','"hollow_knight.exe" -keep','start.bat','explorer /desktop=test start.bat'):
    configured=h.instrument_display(native,1920,540)
    subprocess.run(['bash','-n'],input=instrument_native(configured,['true'],True),text=True,check=True)
    done=subprocess.run(['bash','-c',configured],env=dict(os.environ,COMMAND=command,WINEDLLOVERRIDES='dinput8=n,b',WINEPOINT='/',GAMENAME='/',WINE_DIR=''),text=True,capture_output=True,check=True)
    lines=done.stdout.splitlines()
    if 'hollow_knight.exe' in command:
        assert lines[0].startswith(command) and '-screen-width 1920 -screen-height 540' in lines[0]
    else:assert lines[0]==command
    assert all('dinput8=n,b' in lines[i] and lines[i].endswith('winhttp=n,b') for i in (1,3,5))
try:h.instrument_display(native.replace('WINE_CMD=$(', 'OTHER=$('),1920,540);raise AssertionError('unsafe native hook')
except RuntimeError:pass

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);base=root/'system';base.mkdir();rom=root/'Hollow Knight.wine';rom.mkdir()
    profile=defaults(rom);assert profile['adapter']=='hollowknight-hkmp'
    assert recipe_for(rom).id=='hkmp'
    save_profile(base,rom,profile)
    assert read_profile(base,rom)['hkmp']['pvp'] is False
    assert len(fields(1,'hollowknight-hkmp'))==6
    assert len(fields(2,'hollowknight-hkmp'))==7
    fake=base/'plugins/WindowsParty.HKMP.dll';fake.parent.mkdir();fake.write_bytes(b'OUR PLUGIN')
    auth=[]
    for index in range(4):
        player=base/f'j{index+1}';prefix=player/'prefix';game=prefix/'drive_c/game'
        managed=game/'hollow_knight_Data/Managed';mods=managed/'Mods'
        (mods/'HKMP').mkdir(parents=True);(mods/'HKMP/HKMP.dll').write_bytes(b'USER HKMP')
        (game/'hollow_knight.exe').write_bytes(b'USER GAME');(game/'winhttp.dll').write_bytes(b'USER WINHTTP')
        (game/'BepInEx/core').mkdir(parents=True);(game/'BepInEx/core/BepInEx.dll').write_bytes(b'USER BEPINEX')
        (game/'doorstop_config.ini').write_bytes(b'[General]\r\nenabled=true\r\n[UnityMono]\r\ndll_search_path_override=\r\ndebug_enabled=false\r\n')
        savedir=prefix/'drive_c/users/steamuser/AppData/LocalLow/Team Cherry/Hollow Knight'
        savedir.mkdir(parents=True)
        settings=savedir/'HKMP.GlobalSettings.json';settings.write_text(json.dumps(dict(AuthKey='x'*56,ServerSettings=dict(NailDamage=7),Other='keep')))
        save=savedir/'user1.dat';save.write_bytes(b'SAVE UNCHANGED')
        data=dict(player=str(player),index=index,width=1920 if index<2 else 960,height=540,
                  settings=h.defaults(),plugin=str(fake))
        h.apply_config(game,prefix,data,private_binds=())
        state=json.loads(settings.read_text());key=state['AuthKey'];auth.append(key)
        assert len(key)==56 and key!='x'*56 and state['Username']==f'J{index+1}'
        assert state['Other']=='keep' and state['ServerSettings']['NailDamage']==7
        assert state['ServerSettings']['AlwaysShowMapIcons'] and not state['ServerSettings']['IsPvpEnabled']
        assert save.read_bytes()==b'SAVE UNCHANGED'
        cfg=game/'BepInEx/config/windows.party.hkmp.cfg'
        assert f'Player = {index+1}' in cfg.read_text() and 'Automatic = true' in cfg.read_text()
        assert f'Width = {data["width"]}' in cfg.read_text()
        assert b'BepInEx\\core' in (game/'doorstop_config.ini').read_bytes()
        h.apply_config(game,prefix,data,private_binds=())
        assert json.loads(settings.read_text())['AuthKey']==key
        # Opt-in addon changes only rename selected private DLLs. Dependency
        # DLLs, user saves, game binaries and unrelated mod settings survive.
        for name in ('ESoulLink','GhostHunter','HkmpPouch','Satchel'):
            (mods/name).mkdir();(mods/name/(name+'.dll')).write_bytes(name.encode())
        data['settings'].update(enemy_health='off',enemy_ghosts='off',automatic=False)
        h.apply_config(game,prefix,data,private_binds=())
        assert (mods/'ESoulLink/ESoulLink.dll.windows-party-disabled').read_bytes()==b'ESoulLink'
        assert not (mods/'GhostHunter/GhostHunter.dll').exists()
        assert 'Automatic = false' in cfg.read_text()
        data['settings'].update(enemy_health='on',enemy_ghosts='on')
        h.apply_config(game,prefix,data,private_binds=())
        assert (mods/'GhostHunter/GhostHunter.dll').read_bytes()==b'GhostHunter'
        assert (mods/'HkmpPouch/HkmpPouch.dll').read_bytes()==b'HkmpPouch'
        # CLI result reporting catches native launchers that swallow failures.
        result=player/f'hkmp-result-{uuid.uuid4().hex}.json';data['result']=str(result)
        payload=player/'payload.json';payload.write_text(json.dumps(data))
        env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player))
        run=lambda:subprocess.run([sys.executable,h.__file__,str(payload),str(game),str(prefix)],env=env,text=True,capture_output=True)
        assert run().returncode==0 and h.finish_launch(result,0)==0
        (mods/'Satchel/Satchel.dll').unlink()
        assert run().returncode!=0 and h.finish_launch(result,0)==1
        # Reject escape symlinks before changing files.
        settings.unlink();external=root/f'outside-{index}.json';external.write_text('{}')
        settings.symlink_to(external)
        try:h.apply_config(game,prefix,data,private_binds=());raise AssertionError('escaped settings')
        except ValueError:pass
        assert external.read_text()=='{}'
    assert len(set(auth))==4
print('HKMP: private identities, viewports, autoruns, addon controls and CLI outcomes verified.')

# Existing Standard profiles can opt into HKMP without losing saved options.
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);windows=root/'windows';windows.mkdir();base=root/'system'
    rom=windows/'Hollow Knight.wsquashfs';rom.write_bytes(b'ROM')
    profile=defaults(rom);profile['adapter']='standard';profile['players']='2';profile.pop('hkmp')
    save_profile(base,rom,profile)
    model=Model(base,rom,windows=windows)
    from partydeck_catalog import COMMON
    model.select(rom,common=next(r for r in COMMON if r.id=='hkmp'))
    assert model.data['adapter']=='hollowknight-hkmp' and model.data['players']=='2'
    assert model.data['hkmp']['names']==['J1','J2','J3','J4']
