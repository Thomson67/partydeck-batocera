"""SM64CoopDX template, private views, audio, discovery, controller UI and hook."""
import os
os.environ['PARTYDECK_LANGUAGE']='fr'
os.environ['SDL_VIDEODRIVER']='dummy'
from pathlib import Path
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_sm64coopdx as sm64
from partydeck_profiles import defaults,save_profile,read_profile
from partydeck_catalog import COMMON,CommonGame,recipe_for,discover
from partydeck_couch import Model,App,fields,label_value,get
from partydeck_i18n import set_language
from partydeck_anchor import instrument_native

TEMPLATE=Path(__file__).resolve().parents[1]/'templates/sm64coopdx-common.txt'
common=TEMPLATE.read_bytes().decode('utf-8')


def values(text):
    return dict(line.split(None,1) for line in text.splitlines() if len(line.split(None,1))==2)


for name in ('sm64coopdx','SM64 Coop DX','Super Mario 64 Coop Deluxe v1.5.1','Super_Mario_64_CoopDX'):
    for suffix in ('.wine','.pc','.wsquashfs'):
        assert sm64.matches(Path(name+suffix))
for name in ('sm64ex-coop','Super Mario 64','SM64 Randomizer','Borderlands 2'):
    assert not sm64.matches(Path(name+'.wsquashfs'))
assert recipe_for(Path('sm64coopdx.wsquashfs'))==COMMON[2]
assert recipe_for(Path('Custom title.pc'),'sm64coopdx')==COMMON[2]
options=sm64.defaults()
assert options['names']==['Joueur1','Joueur2','Joueur3','Joueur4']
for index in range(4):
    text=sm64.configured_template(common,options,index,960,540)
    got=values(text)
    assert got['coop_player_name']==f'Joueur{index+1}' and got['language']=='French'
    assert got['music_volume']==('127' if index==0 else '0')
    assert got['master_volume']=='80' and got['sfx_volume']=='127' and got['env_volume']=='127'
    assert got['window_w']=='960' and got['window_h']=='540' and got['fullscreen']=='true'
    assert got['bettercam_xsens']=='20' and got['bettercam_invertx']=='true'
    assert got['msaa']=='8' and got['coop_draw_distance']=='6'
    for prefix in ('enable-mod:','dynos-pack:','save-name:','key_'):
        assert [line for line in text.splitlines() if line.startswith(prefix)]==[line for line in common.splitlines() if line.startswith(prefix)]
    assert ('\r\n' in text)==('\r\n' in common)
assert sm64.patch_config('vsync true\r\nmsaa 8\r\n',{'vsync':False})=='vsync false\r\nmsaa 8\r\n'
changed=dict(options,vsync=False,msaa=16,texture_filtering=0,coop_draw_distance=0,
             free_camera=False,sensitivity_x=1,sensitivity_y=100,invert_x=False,invert_y=False,
             language='English',names=['Alice','Benoît','Charlie','David'],
             volumes={'master_volume':50,'music_volume':25,'sfx_volume':0,'env_volume':100})
got=values(sm64.configured_template(common,changed,0,1920,1080))
assert got['vsync']=='false' and got['msaa']=='16' and got['coop_draw_distance']=='0'
assert got['bettercam_enable']=='false' and got['bettercam_xsens']=='1' and got['bettercam_ysens']=='100'
assert got['bettercam_invertx']=='false' and got['language']=='English'
assert got['master_volume']=='64' and got['music_volume']=='32' and got['sfx_volume']=='0'
assert values(sm64.configured_template(common,changed,3,1920,540))['music_volume']=='0'
assert values(sm64.configured_template(common,dict(changed,music_j1_only=False),3,1920,540))['music_volume']=='32'
for key,value in (('msaa',3),('vsync',1),('sensitivity_x',0),('sensitivity_y',101),
                  ('texture_filtering',3),('coop_draw_distance',7),('language','invalid'),
                  ('names',['A']*4),('names',['é'*32,'B','C','D']),('names',['A\nvsync true','B','C','D']),
                  ('names',['Alice Bob','B','C','D']),
                  ('volumes',{'music_volume':101}),('volumes',{'unknown':50}),('volumes',{'music_volume':True})):
    try:
        sm64.validate(dict(options,**{key:value}));raise AssertionError('accepted invalid '+key)
    except ValueError:pass

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);base=root/'install';windows=root/'windows';windows.mkdir();base.mkdir()
    (base/'templates').mkdir();shutil.copyfile(TEMPLATE,base/'templates/sm64coopdx-common.txt')
    rom=windows/'sm64coopdx.wsquashfs';rom.write_bytes(b'SOLO ROM')
    assert discover(windows,sm64.matches)==(rom,)
    data=defaults(rom);assert data['adapter']=='sm64coopdx'
    data['sm64coopdx']=changed;save_profile(base,rom,data)
    assert read_profile(base,rom)['sm64coopdx']==changed
    model=Model(base,rom,windows)
    assert model.data['adapter']=='sm64coopdx' and rom in model.rows
    for index in range(4):
        player=base/'party'/f'j{index+1}';prefix=player/'prefix';game=prefix/'drive_c/game'
        game.mkdir(parents=True);portable=game/'sm64config.txt';portable.write_text('SOLO CONFIG')
        appdata=prefix/'drive_c/users/steamuser/AppData/Roaming/sm64coopdx';appdata.mkdir(parents=True)
        ini=appdata/'sm64config.txt';ini.write_text('OLD PRIVATE')
        save=appdata/'sm64_save_file.bin';save.write_bytes(b'PROGRESSION')
        reused=player/'umu-private/compatdata/entry/pfx'
        cached=reused/'drive_c/users/root/AppData/Roaming/sm64coopdx/sm64config.txt'
        cached.parent.mkdir(parents=True);cached.write_text('CACHED')
        payload=dict(player=str(player),settings=changed,index=index,template=common,width=960,height=540)
        sm64.apply_config(game,prefix,payload,private_binds=())
        expected=sm64.configured_template(common,changed,index,960,540).encode()
        assert portable.read_bytes()==expected and ini.read_bytes()==expected and cached.read_bytes()==expected
        assert save.read_bytes()==b'PROGRESSION' and rom.read_bytes()==b'SOLO ROM'
        backups=list((player/'sm64coopdx-before').glob('*.txt'));assert len(backups)==3
        assert {p.read_bytes() for p in backups}=={b'SOLO CONFIG',b'OLD PRIVATE',b'CACHED'}
        # Edits made during play are allowed, then the common base is reapplied.
        ini.write_text('vsync true\nshow_fps true\n')
        sm64.apply_config(game,prefix,payload,private_binds=())
        assert ini.read_bytes()==expected and len(list((player/'sm64coopdx-before').glob('*.txt')))==3
    # The game's legacy directory choice must not be changed by our bootstrap.
    player=base/'legacy/j1';prefix=player/'prefix';game=prefix/'drive_c/game';game.mkdir(parents=True)
    legacy=prefix/'drive_c/users/root/AppData/Roaming/sm64ex-coop';legacy.mkdir(parents=True)
    (legacy.parent/'sm64coopdx').mkdir()  # Empty canonical folder must not steal old saves.
    (legacy/'sm64_save_file.bin').write_bytes(b'OLD SAVE')
    payload=dict(player=str(player),settings=options,index=0,template=common,width=1920,height=540)
    sm64.apply_config(game,prefix,payload,private_binds=())
    assert (legacy/'sm64config.txt').exists() and not list((legacy.parent/'sm64coopdx').iterdir())
    assert (legacy/'sm64_save_file.bin').read_bytes()==b'OLD SAVE'
    # Validate all redirects before touching files, including already-existing game config.
    old=(game/'sm64config.txt').read_bytes();external=root/'solo';external.mkdir()
    (external/'important').write_bytes(b'KEEP')
    roaming=legacy.parent;shutil.rmtree(roaming);roaming.symlink_to(external,target_is_directory=True)
    try:
        sm64.apply_config(game,prefix,payload,private_binds=());raise AssertionError('external write allowed')
    except ValueError:
        assert (game/'sm64config.txt').read_bytes()==old and list(external.iterdir())==[external/'important']
    # Instrument every supported native launch path, before Wine starts.
    player=base/'hook/j1';prefix=player/'prefix';game=prefix/'drive_c/game';game.mkdir(parents=True)
    (prefix/'drive_c/users/root').mkdir(parents=True)
    payload=dict(player=str(player),settings=options,index=0,template=common,width=960,height=1080)
    player.joinpath('payload.json').write_text(json.dumps(payload))
    source='#!/bin/bash\nset -e\n'
    for name in ('play_wine','play_pc','play_squashfs'):
        source+=name+'() {\n if [[ -n "${WINE_LANG:-}" ]]; then\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q "coop_player_name Joueur1" sm64config.txt)\n else\n'
        source+=' (cd "${WINEPOINT}/${WINE_DIR}" && grep -q "coop_player_name Joueur1" sm64config.txt)\n fi\n}\n'
    source+=f'WINEPOINT={shlex.quote(str(prefix))}\nWINE_DIR=drive_c/game\nplay_wine\nplay_pc\nplay_squashfs\n'
    native=player/'batocera-wine';native.write_text(source)
    hook=[sys.executable,str(Path(sm64.__file__)),str(player/'payload.json')]
    replacement=instrument_native(source,hook,prefix_argument=True)
    script=player/'test.sh';script.write_text(replacement)
    subprocess.run(['bash',str(script)],env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player)),check=True,capture_output=True)
    rejected=subprocess.run([sys.executable,str(Path(sm64.__file__)),str(player/'payload.json'),str(game),str(prefix)],
                            env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER='wrong'),capture_output=True)
    assert rejected.returncode==1
    with patch.object(sm64.shutil,'which',return_value=str(native)),patch.object(sm64.subprocess,'run') as run,\
         patch.dict(os.environ,PARTYDECK_PLAYER_WIDTH='960',PARTYDECK_PLAYER_HEIGHT='540'):
        sm64.install_hook(base,rom,player)
        assert run.call_args_list[-1].args[0]==['mount','--bind',str(player/'batocera-wine-sm64coopdx'),str(native)]
        assert native.read_text()==source
        assert json.loads((player/'sm64coopdx-launch.json').read_text())['index']==0
    # Controller editing, virtual keyboard, percent sliders and persisted profile.
    app=App(base,rom,windowed=True)
    assert app.available_tabs()==(0,1,2,3,4)
    for tab in app.available_tabs():app.tab=tab;app.draw()
    app.pane='settings';app.tab=4;app.row=1
    app.action('right');assert get(app.model.data,'sm64coopdx.volumes.master_volume')==55
    app.action('ok');assert get(app.model.data,'sm64coopdx.volumes.master_volume')==''
    assert app.volume('sm64coopdx.volumes.master_volume')==63
    app.tab=3;app.row=1;app.action('ok');assert app.keyboard is not None
    app.keyboard['value']='Testeur';app.keyboard_action('save')
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    assert read_profile(base,rom)['sm64coopdx']['names'][0]=='Testeur'
    saved=json.loads(next((base/'profiles').glob('*.json')).read_text())
    assert 'anchor' not in saved and 'borderlands2' not in saved
    for language in ('fr','en'):
        set_language(language)
        for tab in app.available_tabs():app.tab=tab;app.draw()
    app.pg.quit()
    assert TEMPLATE.read_bytes().decode('utf-8')==common

print('SM64CoopDX : base commune, musique J1, volumes, options, J1–J4, préfixes privés, UMU, catalogue et UI manette vérifiés.')
