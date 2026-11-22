"""Persistent private Goldberg IDs, minimal edits and L4D2 controller profile."""
import os
os.environ['PARTYDECK_LANGUAGE']='fr'
os.environ['SDL_VIDEODRIVER']='dummy'
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_l4d2 as l4d2
from partydeck_profiles import defaults,save_profile,read_profile,profile_path
from partydeck_catalog import discover,recipe_for,COMMON
from partydeck_couch import App,Model,fields
from partydeck_anchor import instrument_native
from partydeck_i18n import set_language

SEED=str(l4d2.STEAM64_BASE+2000)
ORIGINAL=('# private example\r\n[user::general]\r\naccount_name=Player\r\n'
          'language=french\r\naccount_steamid='+SEED+'\r\n[user::saves]\r\nlocal_save_path=./saves\r\n').encode()

for name in ('Left 4 Dead 2','Left4Dead2','L4D2','Left_4_Dead_II [runner]'):
    for suffix in ('.wine','.pc','.wsquashfs'):assert l4d2.matches(Path(name+suffix))
assert not l4d2.matches(Path('Left 4 Dead.wine'))
assert not l4d2.matches(Path('Left 4 Dead 20.pc'))
assert len({l4d2.player_id(SEED,i) for i in range(4)})==4
assert l4d2.player_id(SEED,0)==SEED
for seed in (str(l4d2.STEAM64_BASE+1),str(l4d2.STEAM64_BASE+l4d2.ACCOUNT_MAX)):
    assert all(l4d2.valid_id(l4d2.player_id(seed,i)) for i in range(4))
    assert len({l4d2.player_id(seed,i) for i in range(4)})==4
for name in ('','A\nB','A#B','A;B','é'*32):
    try:l4d2.validate(dict(names=[name,'B','C','D']));raise AssertionError('invalid name accepted')
    except ValueError:pass

assert l4d2.validate(dict(names=['A','B','C','D']))['language']=='keep'
assert l4d2.validate(dict(names=['A','B','C','D']))['gamepad'] is True
assert l4d2.validate(dict(names=['A','B','C','D']))['campaign_mode']=='coop'
assert l4d2.validate(dict(l4d2.defaults(),campaign_mode='versus'))['campaign_mode']=='versus'
for mode in l4d2.SOURCE_MODES:
    map_id=l4d2.mode_maps(mode)[0]
    assert l4d2.launch_options(dict(campaign_mode=mode,campaign=map_id))['campaign']==map_id
for invalid in (dict(campaign_mode='survival',campaign='c1m1_hotel'),
                dict(campaign_mode='coop',campaign='c1m4_atrium'),
                dict(campaign_mode='mutation',campaign='c1m1_hotel')):
    try:l4d2.launch_options(invalid);raise AssertionError('incompatible mode or map accepted')
    except ValueError:pass
for mode in ('unknown',[],1):
    try:l4d2.validate(dict(l4d2.defaults(),campaign_mode=mode));raise AssertionError('invalid campaign mode accepted')
    except ValueError:pass
for changes in (dict(language='bogus'),dict(language=[]),dict(gamepad=1)):
    try:l4d2.validate(dict(l4d2.defaults(),**changes));raise AssertionError('invalid options accepted')
    except ValueError:pass
for size in ((0,540),(1920,0),(True,540),(1920,'540'),(20000,1)):
    try:l4d2.dimensions(dict(width=size[0],height=size[1]));raise AssertionError('invalid size accepted')
    except ValueError:pass
# Comments, duplicated keys and malformed quotes are handled without guessing.
text='"VideoConfig" { "setting.defaultres" "1" "setting.defaultres" "2" "note" "{keep}" }'
assert l4d2.patch_video(text,960,1080).count('"setting.defaultres" "960"')==2
try:l4d2.patch_video('"VideoConfig" { "broken }',960,540);raise AssertionError('bad quote accepted')
except ValueError:pass

# Valve root spelling, comments, nested objects and EOF markers are preserved.
for root_name in ('VideoConfig','video.cfg','video.txt'):
    source='"'+root_name+'"\r\n{ /* comment */ "setting.defaultres" "1280" [$WIN32] "quality" { "setting.defaultres" "7" } }\x00\x1a'
    result=l4d2.patch_video(source,960,1080)
    assert '"setting.defaultres" "960" [$WIN32]' in result
    assert '"quality" { "setting.defaultres" "7" }' in result
    assert result.endswith('\x00\x1a') and '/* comment */' in result
    assert l4d2.patch_video(result,960,1080)==result

for command in ('"C:\\game folder\\left4dead2.exe" -novid +sv_lan 1',
                'left4dead2.exe -language english -novid +sv_lan 1',
                'left4dead2.exe "-language" "german" -novid +sv_lan 1',
                'left4dead2.exe -language english -language german -novid +sv_lan 1'):
    updated=l4d2.language_arguments(command,'french')
    assert updated.count('-language french')==1 and '-language english' not in updated
    assert '-novid +sv_lan 1' in updated
    assert l4d2.language_arguments(updated,'french')==updated
    assert '-language english' in l4d2.language_arguments(updated,'english')
    assert l4d2.language_arguments(command,'keep')==command

native_locale='#!/bin/bash\ngetWine_var() { if [[ $2 == LANG ]]; then printf \'%s\' "${TEST_AUTORUN_LANG:-}"; else printf \'%s\' "${TEST_AUTORUN_CMD:-left4dead2.exe}"; fi; }\n'
for name in ('play_wine','play_pc','play_squashfs'):
    native_locale+=name+'() {\n WINE_CMD=$(getWine_var "${WINEPOINT}" "CMD" "explorer")\n WINE_LANG=$(getWine_var "${WINEPOINT}" "LANG" "")\n LC_ALL=${WINE_LANG} '+shlex.quote(sys.executable)+' -c \'import os,sys; print(os.environ["LC_ALL"]); print(sys.argv[1])\' "${WINE_CMD}"\n}\n'
native_locale+='play_wine\nplay_pc\nplay_squashfs\n'
assert l4d2.instrument_locale(native_locale,'keep')==native_locale
for language in ('french','english','keep'):
    done=subprocess.run(['bash','-c',l4d2.instrument_locale(native_locale,language)],
        env=dict(os.environ,TEST_AUTORUN_LANG='de_DE.UTF-8'),text=True,capture_output=True,check=True)
    assert done.stdout.splitlines()==[l4d2.WINE_LOCALES.get(language,'de_DE.UTF-8'),
        l4d2.language_arguments('left4dead2.exe',language)]*3
try:l4d2.instrument_locale(native_locale.replace('WINE_LANG=$(', 'OTHER=$('),'french');raise AssertionError('missing native locale hook accepted')
except RuntimeError:pass

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);base=root/'system';base.mkdir();windows=root/'windows';windows.mkdir()
    rom=windows/'Left 4 Dead 2.wsquashfs';rom.write_bytes(b'SOLO ROM')
    profile=defaults(rom);assert profile['adapter']=='l4d2-goldberg'
    profile['l4d2']['names']=['Alice','Benoît','Charlie','David']
    save_profile(base,rom,profile)
    assert recipe_for(rom)==COMMON[3] and discover(windows,l4d2.matches)==(rom,)
    model=Model(base,rom,windows);assert model.data['adapter']=='l4d2-goldberg'
    assert [key for key,_,_ in fields(1,'l4d2-goldberg')]==[f'l4d2.names.{i}' for i in range(4)]
    ids=[]
    for index in range(4):
        player=base/'runtime'/f'j{index+1}';prefix=player/'prefix';game=prefix/'drive_c/game'
        user_configs=[]
        other_files=[]
        game.mkdir(parents=True)
        (game/'left4dead2/cfg').mkdir(parents=True)
        (game/'start.bat').write_bytes(b'@echo off\r\nstart /wait left4dead2.exe -novid +sv_lan 1\r\n')
        root_appid=game/'steam_appid.txt';root_appid.write_bytes(b'999\n')
        other_files.append((root_appid,b'999\n'))  # Goldberg's local 550 takes precedence.
        for rel in ('steam_settings','BIN/x64/STEAM_SETTINGS'):
            settings=game/rel;settings.mkdir(parents=True)
            user=settings/'configs.user.ini';user.write_bytes(ORIGINAL);user_configs.append(user)
            for filename,data in (('steam_appid.txt',b'550'),('configs.main.ini',b'[main::connectivity]\nlisten_port=47584\n'),
                                  ('supported_languages.txt',b'english'),('configs.app.ini',b'# untouched\n'),
                                  ('configs.overlay.ini',b'[overlay::general]\nenable_experimental_overlay=1\n'),
                                  ('stats.txt',b'stat int 42\n'),('steam_interfaces.txt',b'SteamFriends017\n')):
                path=settings/filename;path.write_bytes(data);other_files.append((path,data))
        global_ini=prefix/'drive_c/users/root/AppData/Roaming/GSE Saves/settings/configs.user.ini'
        global_ini.parent.mkdir(parents=True);global_ini.write_bytes(b'GLOBAL IDENTITY')
        payload=dict(player=str(player),index=index,settings=profile['l4d2'],width=1920,height=540)
        l4d2.apply_config(game,prefix,payload,private_binds=())
        identity=player/'l4d2-goldberg-identity.json'
        data=json.loads(identity.read_text());ids.append(data['steamid'])
        expected=ORIGINAL.replace(b'account_name=Player',('account_name='+profile['l4d2']['names'][index]).encode())
        expected=expected.replace(('account_steamid='+SEED).encode(),('account_steamid='+data['steamid']).encode())
        assert all(user.read_bytes()==expected for user in user_configs)
        assert global_ini.read_bytes()==b'GLOBAL IDENTITY' and rom.read_bytes()==b'SOLO ROM'
        assert all(path.read_bytes()==original for path,original in other_files)
        backups=list((player/'l4d2-goldberg-before').glob('*.ini'))
        assert len(backups)==2 and all(path.read_bytes()==ORIGINAL for path in backups)
        # Reapplying/renaming after a partial update never increments the ID again.
        user_configs[1].write_bytes(ORIGINAL)
        before_identity=identity.read_bytes()
        payload['settings']=dict(names=['One','Two','Three','Four'])
        l4d2.apply_config(game,prefix,payload,private_binds=())
        assert identity.read_bytes()==before_identity
        for user in user_configs:
            got=user.read_text();assert 'account_steamid='+data['steamid'] in got
            assert 'account_name='+payload['settings']['names'][index] in got
        assert all(path.read_bytes()==ORIGINAL for path in backups)
    assert ids[0]==SEED and len(set(ids))==4
    # Source settings preserve quality, user binds and host commands. Changing
    # layout/language/controller is idempotent; it never regenerates identities.
    cfg=game/'left4dead2/cfg'
    video=cfg/'video.txt'
    source_video='"VideoConfig"\r\n{\r\n "setting.defaultres" "1280" // old\r\n "setting.fullscreen" "1"\r\n "setting.mat_antialias" "8"\r\n}\r\n'
    video.write_bytes(source_video.encode())
    config=cfg/'config.cfg';config.write_bytes(b'bind "w" "+forward"\r\njoystick "0"\r\n')
    auto=cfg/'autoexec.cfg';auto.write_text('sv_lan 1\n// custom host command\n')
    payload['settings']=dict(names=['One','Two','Three','Four'],language='french',gamepad=True)
    payload.update(width=960,height=1080)
    identity_before=(player/'l4d2-goldberg-identity.json').read_bytes()
    l4d2.apply_config(game,prefix,payload,private_binds=())
    assert (player/'l4d2-goldberg-identity.json').read_bytes()==identity_before
    assert '"setting.mat_antialias" "8"' in video.read_text()
    assert '"setting.defaultres" "960"' in video.read_text()
    assert '"setting.fullscreen" "0"' in video.read_text()
    assert '"setting.nowindowborder"\t"1"' in video.read_text()
    assert 'bind "w" "+forward"' in config.read_text()
    assert 'sv_lan 1\n// custom host command' in auto.read_text()
    assert 'mat_setvideomode 960 1080 1' in auto.read_text() and 'joystick "1"' in auto.read_text()
    for user in user_configs:
        assert 'language=french' in user.read_text()
        assert (user.parent/'supported_languages.txt').read_text().splitlines()==['english','french']
    snapshots={p:p.read_bytes() for p in (video,config,auto,*user_configs)}
    l4d2.apply_config(game,prefix,payload,private_binds=())
    assert all(p.read_bytes()==data for p,data in snapshots.items())
    payload['settings'].update(language='english',gamepad=False)
    payload.update(width=1920,height=540)
    l4d2.apply_config(game,prefix,payload,private_binds=())
    assert 'joystick "0"' in auto.read_text() and '+jlook' not in auto.read_text()
    assert auto.read_text().count(l4d2.BEGIN)==1 and 'mat_setvideomode 1920 540 1' in auto.read_text()
    assert all('language=english' in user.read_text() for user in user_configs)
    assert (player/'l4d2-goldberg-identity.json').read_bytes()==identity_before
    batch=game/'start.bat'
    original_batch=b'@echo off\r\nstart /wait left4dead2.exe -novid +sv_lan 1\r\n'
    assert batch.read_bytes()==original_batch
    # Replacing the private language preamble preserves the original batch,
    # including the exact body and line endings; missing batches
    # no longer prevent a native launch from selecting its own entrypoint.
    for language in ('keep','french','english'):
        old='@rem Windows Party language begin\r\n@reg add "HKCU\\Software\\Valve\\Steam" /v Language /t REG_SZ /d french /f >nul\r\n@rem Windows Party language end\r\n'
        batch.write_bytes(old.encode()+original_batch)
        payload['settings']['language']=language
        l4d2.apply_config(game,prefix,payload,private_binds=())
        expected=original_batch
        assert batch.read_bytes()==expected
        assert batch.read_bytes().endswith(original_batch)
        l4d2.apply_config(game,prefix,payload,private_binds=())
        assert batch.read_bytes()==expected
    batch.unlink()
    l4d2.apply_config(game,prefix,payload,private_binds=())
    assert not batch.exists()
    batch.write_bytes(original_batch)
    # A symlink to the solo launcher is refused before touching any config.
    batch.unlink();solo_batch=root/'solo-start.bat';solo_batch.write_bytes(original_batch);batch.symlink_to(solo_batch)
    before_users=[user.read_bytes() for user in user_configs]
    try:l4d2.apply_config(game,prefix,payload,private_binds=());raise AssertionError('external batch accepted')
    except ValueError:pass
    assert solo_batch.read_bytes()==original_batch and [user.read_bytes() for user in user_configs]==before_users
    batch.unlink();batch.write_bytes(original_batch)
    # Reproduce the reported pre-Wine failure: an unfamiliar video format
    # must survive byte-for-byte and let the adapter report successful launch.
    payload['settings']['language']='french'
    video.write_text('broken "VideoConfig"')
    l4d2.apply_config(game,prefix,payload,private_binds=())
    assert video.read_bytes()==b'broken "VideoConfig"'
    assert 'mat_setvideomode 1920 540 1' in auto.read_text()
    snapshots=[user.read_bytes() for user in user_configs]
    # External configs remain forbidden; recovery must not bypass confinement.
    video.unlink();outside=root/'solo-video.txt';outside.write_text(source_video);video.symlink_to(outside)
    try:l4d2.apply_config(game,prefix,payload,private_binds=());raise AssertionError('external video config accepted')
    except ValueError:pass
    assert outside.read_bytes()==source_video.encode() and [user.read_bytes() for user in user_configs]==snapshots
    video.unlink();video.write_text(source_video)
    # Zero/missing local AppIDs fall back to the root; numeric prefixes tolerate
    # Windows text terminators as std::stoul does, without rewriting the file.
    local_appid=user_configs[0].parent/'steam_appid.txt'
    local_appid.write_bytes(b'550\x00\r\n')
    assert user_configs[0] in l4d2.config_files(game,(prefix,player))
    local_appid.write_text('0');root_appid.write_text('550')
    assert user_configs[0] in l4d2.config_files(game,(prefix,player))
    local_appid.write_text('550')
    # Wrong AppIDs and out-of-view configs fail before modifying the identity/files.
    first=user_configs[0];before=first.read_bytes();identity_before=identity.read_bytes()
    appid=first.parent/'steam_appid.txt';appid.write_text('999')
    try:l4d2.apply_config(game,prefix,payload,private_binds=());raise AssertionError('wrong app accepted')
    except ValueError:pass
    assert first.read_bytes()==before and identity.read_bytes()==identity_before
    appid.write_text('550')
    outside=root/'solo.ini';outside.write_bytes(ORIGINAL)
    first.unlink();first.symlink_to(outside)
    try:l4d2.apply_config(game,prefix,payload,private_binds=());raise AssertionError('external config accepted')
    except ValueError:pass
    assert outside.read_bytes()==ORIGINAL and identity.read_bytes()==identity_before
    first.unlink();first.write_bytes(before)
    identity.write_text('invalid JSON')
    try:l4d2.apply_config(game,prefix,payload,private_binds=());raise AssertionError('corrupt identity regenerated')
    except ValueError:pass
    assert identity.read_text()=='invalid JSON' and first.read_bytes()==before
    # No first-run partial edits if DLL copies disagree on their source identity.
    identity.unlink();user_configs[1].write_bytes(ORIGINAL.replace(SEED.encode(),str(l4d2.STEAM64_BASE+9999).encode()))
    snapshots=[path.read_bytes() for path in user_configs]
    try:l4d2.apply_config(game,prefix,payload,private_binds=());raise AssertionError('ambiguous seed accepted')
    except ValueError:pass
    assert not identity.exists() and [p.read_bytes() for p in user_configs]==snapshots
    # Native launcher hook runs after mounting the game and before Wine in all formats.
    player=base/'hook/j1';prefix=player/'prefix';game=prefix/'drive_c/game'
    settings=game/'steam_settings';settings.mkdir(parents=True)
    (settings/'configs.user.ini').write_bytes(ORIGINAL)
    (game/'left4dead2/cfg').mkdir(parents=True)
    payload=dict(player=str(player),index=0,settings=profile['l4d2'],width=1920,height=540)
    payload_file=player/'payload.json';payload_file.write_text(json.dumps(payload))
    source='#!/bin/bash\nset -e\ngetWine_var() { if [[ $2 == LANG ]]; then printf \'%s\' "${TEST_AUTORUN_LANG:-}"; else printf \'%s\' "${TEST_AUTORUN_CMD:-left4dead2.exe}"; fi; }\n'
    for name in ('play_wine','play_pc','play_squashfs'):
        source+=name+'() {\n WINE_CMD=$(getWine_var "${WINEPOINT}" "CMD" "explorer")\n WINE_LANG=$(getWine_var "${WINEPOINT}" "LANG" "")\n if [[ -n "${WINE_LANG:-}" ]]; then\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q account_name=Alice steam_settings/configs.user.ini)\n else\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q account_name=Alice steam_settings/configs.user.ini)\n fi\n}\n'
    source+=f'WINEPOINT={shlex.quote(str(prefix))}\nWINE_DIR=drive_c/game\nplay_wine\nplay_pc\nplay_squashfs\n'
    script=player/'test.sh';script.write_text(instrument_native(source,[sys.executable,str(Path(l4d2.__file__)),str(payload_file)],prefix_argument=True))
    subprocess.run(['bash',str(script)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),check=True,capture_output=True)
    native=player/'native';native.write_text(source)
    profile['l4d2']['language']='french';save_profile(base,rom,profile)
    with patch.dict(os.environ,PARTYDECK_PLAYER_WIDTH='1920',PARTYDECK_PLAYER_HEIGHT='540'),\
         patch.object(l4d2.shutil,'which',return_value=str(native)),patch.object(l4d2.subprocess,'run') as run:
        result=l4d2.install_hook(base,rom,player)
        assert run.call_args_list[-1].args[0]==['mount','--bind',str(player/'batocera-wine-l4d2'),str(native)]
        assert native.read_text()==source
        assert (player/'batocera-wine-l4d2').read_text().count('WINE_LANG=fr_FR.UTF-8')==3
        assert json.loads(result.read_text())['code']==1
        assert Path(json.loads((player/'l4d2-goldberg-launch.json').read_text())['result'])==result
    rejected=subprocess.run([sys.executable,str(Path(l4d2.__file__)),str(payload_file),str(game),str(prefix)],
                            env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER='wrong'),capture_output=True)
    assert rejected.returncode==1
    # Reproduce Batocera's swallowed hook error: bad config, no game command,
    # then a successful wineserver wait makes the native launcher return zero.
    payload['result']=str(result);payload_file.write_text(json.dumps(payload))
    bad=ORIGINAL.replace(SEED.encode(),b'0')
    (settings/'configs.user.ini').write_bytes(bad)
    swallowed=source.replace('set -e\n','')+'\ntrue\n'
    script.write_text(instrument_native(swallowed,[sys.executable,str(Path(l4d2.__file__)),str(payload_file)],prefix_argument=True))
    done=subprocess.run(['bash',str(script)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),capture_output=True,text=True)
    assert done.returncode==0 and 'Steam ID Goldberg' in done.stderr
    assert json.loads(result.read_text())['code']==1
    assert l4d2.finish_launch(result,0)==1 and not result.exists()
    (settings/'configs.user.ini').write_bytes(ORIGINAL)
    (game/'steam_appid.txt').write_text('999');(settings/'steam_appid.txt').write_text('550')
    done=subprocess.run(['bash',str(script)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),capture_output=True,text=True)
    assert done.returncode==0 and json.loads(result.read_text())['code']==0
    assert l4d2.finish_launch(result,0)==0 and not result.exists()
    video_hook=game/'left4dead2/cfg/video.txt'
    video_hook.write_bytes(b'unsupported video format\x00')
    done=subprocess.run(['bash',str(script)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),capture_output=True,text=True)
    assert done.returncode==0 and json.loads(result.read_text())['code']==0
    assert 'format vidéo non reconnu' in done.stdout
    assert video_hook.read_bytes()==b'unsupported video format\x00'
    assert l4d2.finish_launch(result,0)==0
    bad_result=root/('l4d2-result-'+'a'*32+'.json')
    try:
        l4d2.apply_launch(game,prefix,dict(payload,result=str(bad_result)))
        raise AssertionError('external result path accepted')
    except ValueError:pass
    assert not bad_result.exists()
    for contents in (None,'bad JSON','{"version":1,"code":true}'):
        if contents is not None:result.write_text(contents)
        try:l4d2.finish_launch(result,0);raise AssertionError('missing/bad result treated as success')
        except RuntimeError:pass
        assert not result.exists()
    # The actual parent runner also honors the hook result rather than native 0.
    spec=importlib.util.spec_from_file_location('l4d2_runner',Path(l4d2.__file__).parent/'partydeck-batocera-coop.py')
    runner=importlib.util.module_from_spec(spec);sys.modules[spec.name]=runner;spec.loader.exec_module(runner)
    for hook_code,native_code,expected in ((1,0,1),(0,0,0),(0,9,9),(0,-11,139)):
        result.write_text(json.dumps(dict(version=1,code=hook_code)))
        with patch('partydeck_bottles.mount_windows',return_value=[]),patch.object(runner,'UMU_HOME',root/'missing-umu'),patch.object(l4d2,'install_hook',return_value=result),\
             patch.object(runner.subprocess,'run',return_value=Mock(returncode=native_code)):
            assert runner.run_wine(rom,rom,player,root/'private-saves')==expected
        assert not result.exists()
    app=App(base,rom,windowed=True);assert app.available_tabs()==(0,1,2)
    app.action('next');app.row=0;app.action('ok');assert app.keyboard is not None
    app.keyboard['value']='Joueur test';app.keyboard_action('save')
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):assert app.save()
    assert read_profile(base,rom)['l4d2']['names'][0]=='Joueur test'
    saved=json.loads(profile_path(base,rom).read_text())
    assert all(key not in saved for key in ('anchor','borderlands2','sm64coopdx'))
    for lang in ('fr','en'):
        set_language(lang)
        for tab in (1,2):app.tab=tab;app.draw()
    pg=app.pg
    from partydeck_couch import l4d2_session_screen
    def press(key):
        return [pg.event.Event(pg.KEYDOWN,key=key)]
    for language in ('fr','en'):
        set_language(language)
        with patch.object(pg.event,'get',side_effect=[
            press(pg.K_RIGHT),press(pg.K_DOWN),press(pg.K_RIGHT),
            press(pg.K_DOWN),press(pg.K_RIGHT),press(pg.K_F5),
        ]):
            choices=l4d2_session_screen(pg,app.screen,l4d2.defaults(),2)
        assert choices==dict(campaign='c2m1_highway',campaign_mode='coop',difficulty='hard')
    with patch.object(pg.event,'get',side_effect=[
        press(pg.K_RIGHT),press(pg.K_RIGHT),press(pg.K_DOWN),press(pg.K_RIGHT),press(pg.K_F5),
    ]):
        choices=l4d2_session_screen(pg,app.screen,l4d2.defaults(),2)
    assert choices==dict(campaign='c1m1_hotel',campaign_mode='mutation3',difficulty=None)
    for mode,steps in (('mutation12',5),('survival',6),('mutation15',7),('scavenge',8)):
        with patch.object(pg.event,'get',side_effect=[*[press(pg.K_RIGHT) for _ in range(steps)],press(pg.K_F5)]):
            choices=l4d2_session_screen(pg,app.screen,l4d2.defaults(),2)
        assert choices==dict(campaign=l4d2.mode_maps(mode)[0],campaign_mode=mode,difficulty=None)
    with patch.object(pg.event,'get',return_value=press(pg.K_ESCAPE)):
        assert l4d2_session_screen(pg,app.screen,l4d2.defaults(),2) is None
    pg.quit()

print('Left 4 Dead 2 : identités J1–J4, langue, manette, sans bordure/résolution, fichiers privés, hook et UI vérifiés.')
