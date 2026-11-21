"""Experimental MW LAN configuration, isolation, CLI outcome and FR/EN UI."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['PARTYDECK_LANGUAGE']='fr'
import sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_nfsmw as mw
from partydeck_profiles import defaults,save_profile,read_profile
from partydeck_catalog import recipe_for
from partydeck_couch import App,fields
from partydeck_i18n import set_language

assert mw.matches(Path('Need for Speed Most Wanted 2005.wsquashfs'))
assert not mw.matches(Path('Need for Speed Most Wanted 2012.wsquashfs'))
assert not mw.matches(Path('Need for Speed Underground 2.wine'))
for ip in ('auto','192.168.1.20','10.0.0.2'):mw.validate(dict(host=ip))
for ip in ('0.0.0.0','127.0.0.1','255.255.255.255','224.0.0.1','x','192.168.1.2:9900'):
    try:mw.validate(dict(host=ip));raise AssertionError(ip)
    except ValueError:pass
with patch.object(mw.subprocess,'check_output',return_value='[{"prefsrc":"192.168.1.20"}]'):
    assert mw.host_ip('auto')=='192.168.1.20'
from partydeck_profiles import private_lan_enabled
assert mw.defaults()['private_lan'] is True
assert mw.validate(dict(host='auto'))['private_lan'] is True  # Existing profiles migrate by default.
for adapter in ('standard','soh-anchor','borderlands2','sm64coopdx','l4d2-goldberg'):
    assert not private_lan_enabled(dict(adapter=adapter),2)
for count in (2,3,4):
    assert private_lan_enabled(dict(adapter='nfsmw-lan',nfsmw={}),count)
    assert not private_lan_enabled(dict(adapter='nfsmw-lan',nfsmw=dict(private_lan=False)),count)
assert not private_lan_enabled(dict(adapter='nfsmw-lan'),1)
try:mw.validate(dict(private_lan='yes'));raise AssertionError('non-boolean network mode')
except ValueError:pass
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);base=root/'system';base.mkdir();rom=root/'Most Wanted 2005.wsquashfs';rom.write_bytes(b'SOLO')
    profile=defaults(rom);assert profile['adapter']=='nfsmw-lan' and recipe_for(rom).id=='nfsmw'
    save_profile(base,rom,profile)
    wine=base/'batocera-wine';wine.write_text('#!/bin/bash\n')
    solo=b'# ORIGINAL\r\nLAN_THROTTLE=30\r\nACCOUNT=1\r\nADDR=%%bind("159.153.253.82")\r\n'
    for index in range(4):
        player=base/f'j{index+1}';prefix=player/'prefix';game=prefix/'drive_c/game';scripts=game/'scripts';scripts.mkdir(parents=True)
        # Optional distribution icons must not prevent a selected MW profile
        # from starting; the actual LAN files are still required.
        (game/'server.cfg').write_bytes(solo);(game/'server.dll').write_bytes(b'PRIVATE DLL')
        extra=scripts/'NFSMWExtraOptionsSettings.ini';extra.write_text('[Misc]\nWindowedMode=0\nOther=keep\n')
        wide=scripts/'NFSMostWanted.WidescreenFix.ini';wide.write_text('[MAIN]\nResX=1920\nResY=1080\nFixHUD=1\n')
        data=dict(player=str(player),index=index,settings=mw.defaults(),host='192.168.1.20',width=1920,height=540)
        mw.apply_config(game,prefix,data,private_binds=())
        text=(game/'server.cfg').read_text();assert f'PORT={9900+index}' in text
        assert f'ADDR=%%bind("192.168.1.20:{9900+index}")' in text
        assert 'TRUST_MATCH=%%bind("192.168.1.20")' in text and '[SERVER]' in text
        assert 'LAN_THROTTLE=6' in text and 'ACCOUNT=1' in text
        assert 'Other=keep' in extra.read_text() and f'EnableMusic={int(index==0)}' in extra.read_text()
        assert 'ResY=540' in wide.read_text() and 'FixHUD=1' in wide.read_text()
        snapshots={p:p.read_bytes() for p in (game/'server.cfg',extra,wide)}
        mw.apply_config(game,prefix,data,private_binds=())
        assert all(p.read_bytes()==v for p,v in snapshots.items())
        data['settings']['music_j1_only']=False
        mw.apply_config(game,prefix,data,private_binds=())
        assert 'EnableMusic=1' in extra.read_text()
        data['settings']['music_j1_only']=True
        assert (game/'server.dll').read_bytes()==b'PRIVATE DLL' and rom.read_bytes()==b'SOLO'
        assert any(p.read_bytes()==solo for p in (player/'nfsmw-before').glob('*.bak'))
        private_ip=f'192.168.247.{11+index}'
        with patch.dict(os.environ,PARTYDECK_PRIVATE_LAN_IP=private_ip,
                        PARTYDECK_PLAYER_WIDTH='1920',PARTYDECK_PLAYER_HEIGHT='540'), \
             patch.object(mw.shutil,'which',return_value=str(wine)), \
             patch.object(mw.subprocess,'run'), \
             patch('partydeck_anchor.instrument_native',return_value=wine.read_text()):
            result=mw.install_hook(base,rom,player)
        payload=player/'nfsmw-launch.json'
        # Verify the private IP and common port through the real CLI payload.
        env=dict(os.environ,PARTYDECK_PRIVATE_PLAYER=str(player))
        done=subprocess.run([sys.executable,mw.__file__,str(payload),str(game),str(prefix)],env=env,capture_output=True,text=True)
        assert done.returncode==0 and mw.finish_launch(result,0)==0
        text=(game/'server.cfg').read_text()
        assert 'PORT=9900\n' in text
        assert f'ADDR=%%bind("{private_ip}:9900")' in text
        assert f'TRUST_MATCH=%%bind("{private_ip}")' in text
        mw.apply_config(game,prefix,data,private_binds=())
        assert f'PORT={9900+index}\n' in (game/'server.cfg').read_text()
        (game/'server.dll').unlink()
        done=subprocess.run([sys.executable,mw.__file__,str(payload),str(game),str(prefix)],env=env,capture_output=True,text=True)
        assert done.returncode==1 and mw.finish_launch(result,0)==1
        (game/'server.dll').write_bytes(b'PRIVATE DLL')
        # A game config symlink outside the private player area is never edited.
        cfg=game/'server.cfg';cfg.unlink();external=root/f'solo-{index}.cfg';external.write_bytes(solo);cfg.symlink_to(external)
        try:mw.apply_config(game,prefix,data,private_binds=());raise AssertionError('outside edit')
        except ValueError:pass
        assert external.read_bytes()==solo
    app=App(base,rom,windowed=True);assert app.available_tabs()==(0,1)
    app.tab=1
    assert 'nfsmw.host' not in [row[0] for row in app.current_fields()]
    app.model.data['nfsmw']['private_lan']=False
    assert 'nfsmw.host' in [row[0] for row in app.current_fields()]
    for language in ('fr','en'):
        set_language(language);app.tab=1;app.draw()
        labels=[label for _,label,_ in fields(1,'nfsmw-lan')]
        assert ('PC LAN IP (auto: detect)' if language=='en' else 'IP LAN du PC (auto : détection)') in labels
    app.pg.quit()
    assert read_profile(base,rom)['nfsmw']['host']=='auto'
print('Most Wanted : port 9900 en LAN privé, ports 9900–9903 en réseau partagé, TRUST_MATCH sans port, DLL privée, échec conservé et UI FR/EN vérifiés.')
