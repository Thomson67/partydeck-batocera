"""Batocera locale precedence, English UI/options, and unchanged profile values."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_i18n as lang
from partydeck_couch import App,control_label,context_hints,fields,label_value
from partydeck_profiles import defaults,save_profile,read_profile,profile_path,edit_profile_legacy,edit_anchor,edit_soh_graphics
from partydeck_anchor import defaults as anchor_defaults, graphics_defaults
from partydeck_storage import DEFAULTS,human,preflight
from partydeck_catalog import COMMON

for locale in ('fr','fr_FR','fr-FR','FR_ca.UTF-8','fr_BE@euro',"'fr_FR'"):
    assert lang.locale_language(locale)=='fr'
for locale in ('en_US','de_DE','es_ES','zh_CN','C.UTF-8','','frr_FR','france'):
    assert lang.locale_language(locale)=='en'

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);conf=root/'batocera.conf';es=root/'es_settings.cfg'
    env={'LANG':'fr_FR.UTF-8'}
    def detect(environment=env):
        return lang.detect_language(environment,conf,es)
    with patch.object(lang.shutil,'which',return_value='/bin/batocera-settings-get'):
        for selected,expected in (('fr_FR\n','fr'),('de_DE\n','en'),('es_ES\n','en'),('en_US\n','en')):
            with patch.object(lang.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=selected)) as run:
                assert detect()==expected
                assert run.call_args.args[0]==['/bin/batocera-settings-get','system.language']
                assert run.call_args.kwargs['timeout']==2
        conf.write_text('#system.language=en_US\nsystem.language=de_DE\nsystem.language=fr_CA\n')
        with patch.object(lang.subprocess,'run',side_effect=subprocess.TimeoutExpired('settings',2)):
            assert detect()== 'fr'
    with patch.object(lang.shutil,'which',return_value=None):
        conf.write_text('system.language=de_DE\n')
        assert detect()=='en'  # Batocera wins over a French SSH environment.
        conf.write_text('system.language=fr_FR\n')
        assert detect({'LANG':'en_US'})=='fr'
        conf.unlink();es.write_text('<config><string name="Language" value="it_IT"/></config>')
        assert detect()=='en'
        es.write_text('<config><string name="Language" value="fr_FR"/></config>')
        assert detect({'LANG':'en_US'})=='fr'
        es.write_text('<invalid')
        assert detect({'LC_ALL':'de_DE','LANG':'fr_FR'})=='en'
        assert detect({'LANGUAGE':'fr_FR:en_US'})=='fr'
        assert detect({})=='en'
        assert detect({'PARTYDECK_LANGUAGE':'en','LANG':'fr_FR'})=='en'
    # Every translation keeps the same format placeholders.
    import string
    for source,target in lang.EN.items():
        names=lambda s: {f[1] for f in string.Formatter().parse(s) if f[1] is not None}
        assert names(source)==names(target),source
    lang.set_language('en')
    assert lang.tr('--field=Joueurs:CB')=='--field=Players:CB'
    assert lang.tr('--button=Annuler:1')=='--button=Cancel:1'
    assert lang.tr('--field=J{p0} — nom',p0=2)=='--field=Player 2 — name'
    assert control_label('ok','keyboard')=='Enter'
    assert control_label('back','keyboard')=='Esc'
    assert control_label('add','keyboard')=='Ins'
    assert control_label('ok','ps')=='Cross'
    assert ('save','Save') in context_hints('main','ps')
    assert label_value('input','clavier-j1')=='Keyboard/mouse · P1'
    assert label_value('borderlands2.preset','medium')=='Medium'
    assert label_value('borderlands2.vsync','on')=='Enabled'
    assert label_value('borderlands2.vsync','off')=='Disabled'
    assert label_value('borderlands2.vsync','keep')=='Keep current'
    assert [key for key,_,_ in fields(1,'borderlands2')]==['borderlands2.preset','borderlands2.vsync','borderlands2.physx','borderlands2.language']
    assert label_value('borderlands2.language','keep')=='Keep current'
    assert label_value('borderlands2.language','french')=='French'
    assert label_value('borderlands2.language','english')=='English'
    assert label_value('borderlands2.names.0','')=='Keep current'
    assert label_value('borderlands2.names.0','Joueur français')=='Joueur français'
    assert fields(2,'borderlands2')[0][1]=='Player 1 · Name'
    assert label_value('anchor.locations',1)=='Team only'
    assert label_value('anchor.graphics.texture_filter',0)=='N64 three-point'
    assert label_value('anchor.names.0','Enregistrer')=='Enregistrer'
    assert human(1024**3)=='1.0 GiB'
    assert 'shared profile' in COMMON[0].stem
    # Create French-named user data before switching the configurator to English.
    lang.set_language('fr')
    assert label_value('borderlands2.language','english')=='Anglais'
    assert fields(2,'borderlands2')[0][1]=='J1 · Nom'
    rom=root/'Enregistrer.wsquashfs';rom.touch()
    data=defaults(rom);data.update(adapter='soh-anchor',anchor=anchor_defaults())
    data['anchor'].update(room='Annuler',names=['Enregistrer','Équipe','Moyen','Joueur4'])
    save_profile(root,rom,data)
    original=profile_path(root,rom).read_bytes()
    with patch('partydeck_couch.detect_language',return_value='en'):
        app=App(root,rom,windowed=True)
    assert lang.get_language()=='en' and ''.join(app.keys[0])=='qwertyuiop'
    rendered=[]
    original_text=app.text
    def record(value,*args,**kwargs):
        rendered.append(str(value));return original_text(value,*args,**kwargs)
    with patch.object(app,'text',side_effect=record):
        for tab in range(4):
            app.tab=tab;app.row=0;app.draw()
        app.tab=2;app.draw()
        assert 'Player 1 · Name' in rendered and 'Enregistrer' in rendered
        assert 'Network' in rendered and 'Graphics & audio' in rendered
        assert 'Master volume (%)' in [title for _,title,_ in fields(3)]
        app.edit('Player name','Enregistrer',lambda value:None);app.draw()
        assert {'Shift','Space','Backspace','Clear','Done'} <= set(rendered)
        app.action('back');app.request_remove();app.draw()
        assert 'UNLINK THIS GAME?' in rendered
        app.action('back')
        app.storage_open=True;app.storage_config=dict(DEFAULTS);app.draw()
        assert 'WINDOWS PARTY STORAGE' in rendered and 'Total caches (MiB)' in rendered
        app.storage_open=False
    assert profile_path(root,rom).read_bytes()==original
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    after=read_profile(root,rom)
    assert after['anchor']['names']==data['anchor']['names'] and after['anchor']['room']=='Annuler'
    assert after['input']=='auto' and after['split']=='horizontal'
    # QWERTY uses translated command labels, but inserts literal characters.
    typed=[];app.edit('Player name','',typed.append);app.action('ok')
    assert app.keyboard['value']=='q'
    app.action('save');assert typed==['q']
    # Legacy editor choices translate back to stable, existing schema tokens.
    with patch('partydeck_profiles.yad',return_value=Mock(returncode=0,stdout='Automatic\x1fVertical\x1fKeyboard/mouse · P1\x1fFALSE\x1f\n')):
        assert edit_profile_legacy(root,rom)
    after=read_profile(root,rom)
    assert after['players']=='auto' and after['split']=='vertical' and after['input']=='clavier-j1'
    values=['TRUE','TRUE','Annuler','anchor.hm64.org','43383','shipofharkinian.json',
            'Enabled + friendly fire','Everyone','Nobody','FALSE',
            'Enregistrer','default','Équipe','default','Moyen','default','Joueur4','default']
    with patch('partydeck_profiles.yad',return_value=Mock(returncode=0,stdout='\x1f'.join(values)+'\x1f\n')):
        assert edit_anchor(after)
    assert after['anchor']['pvp']==2 and after['anchor']['names'][0]=='Enregistrer'
    with patch('partydeck_profiles.yad',return_value=Mock(returncode=0,stdout='1.25\x1f4\x1fTRUE\x1fLinear\x1fTRUE'+'\x1f'*6+'\n')):
        assert edit_soh_graphics(after['anchor'])
    assert after['anchor']['graphics']['texture_filter']==1
    with patch('partydeck_storage.disks',return_value=[dict(path='/userdata',free=0,total=1024**3)]):
        try:
            preflight(root,root,dict(DEFAULTS,auto_clean=False))
            raise AssertionError('ignored disk threshold')
        except RuntimeError as error:
            assert str(error).startswith('Not enough disk space')
    app.pg.quit()
    with patch('partydeck_couch.detect_language',return_value='fr'):
        app=App(root,rom,windowed=True)
    assert ''.join(app.keys[0])=='azertyuiop' and control_label('ok','keyboard')=='Entrée'
    assert read_profile(root,rom)['anchor']['names']==data['anchor']['names']
    app.pg.quit()

print('Langues : priorité Batocera/SSH, FR sinon EN, options de jeux, clavier, stockage et données conservées vérifiés.')
