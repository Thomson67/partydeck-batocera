"""Remove local entries, detach common recipes, re-link and protect user files."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
os.environ['SDL_VIDEODRIVER']='dummy'
from pathlib import Path
import shlex
import sys
import tempfile
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_couch import Model,App
from partydeck_catalog import CommonGame,COMMON,unlinked
import partydeck_profiles as profiles


def launcher(base,rom,roms):
    import hashlib
    path=roms/f'{rom.stem[:90]} [{hashlib.sha256(os.fsencode(rom)).hexdigest()[:10]}].sh'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('#!/bin/bash\n'+profiles.MARKER+'\nexec '+shlex.join([str(base/'partydeck-test'),'profil',str(rom)])+'\n')
    return path


with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);base=root/'system';base.mkdir();windows=root/'windows';windows.mkdir();roms=root/'party-roms'
    solo=windows/'Other.wine';solo.mkdir();(solo/'game.exe').write_bytes(b'ORIGINAL')
    save=root/'saves'/'slot.sav';save.parent.mkdir();save.write_bytes(b'SAVE')
    profiles.save_profile(base,solo,profiles.defaults(solo))
    entry=launcher(base,solo,roms)
    model=Model(base,solo,windows)
    model.remove(roms)
    assert not entry.exists() and not profiles.profile_path(base,solo).exists()
    assert (solo/'game.exe').read_bytes()==b'ORIGINAL' and save.read_bytes()==b'SAVE'
    assert solo not in model.rows
    # A common recipe remains visible and remembers options, without auto-linking.
    for recipe,title in ((COMMON[0],'Ship of Harkinian'),(COMMON[1],'Borderlands 2')):
        game=windows/(title+'.wsquashfs');game.write_bytes(b'ROM')
        model=Model(base,windows=windows);model.select(game,recipe)
        model.data['players']='3'
        if recipe.id=='borderlands2':model.data['borderlands2']['preset']='medium'
        with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
            model.save()
        entry=launcher(base,game,roms)
        model.remove(roms)
        assert game.read_bytes()==b'ROM' and not entry.exists()
        assert recipe.id in unlinked(base)
        assert any(isinstance(p,CommonGame) and p.id==recipe.id for p in model.rows)
        assert game not in model.rows
        again=Model(base,windows=windows)
        assert game not in again.rows  # Detection cannot undo an explicit unlink.
        again.select(game,recipe)
        assert again.data['players']=='3'
        if recipe.id=='borderlands2':assert again.data['borderlands2']['preset']=='medium'
        with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
            again.save()
        assert recipe.id not in unlinked(base)
    # Failed dissociation restores catalogue flags/options and leaves the profile.
    common_game=windows/'Borderlands 2.wsquashfs'
    common_entry=launcher(base,common_game,roms)
    common_entry.write_text('#!/bin/sh\necho customized\n')
    catalogue=(base/'catalog.json').read_bytes()
    retained=(base/'detached-profiles/borderlands2.json').read_bytes()
    model=Model(base,common_game,windows)
    try:
        model.remove(roms)
        raise AssertionError('removed modified common launcher')
    except ValueError:
        assert (base/'catalog.json').read_bytes()==catalogue
        assert (base/'detached-profiles/borderlands2.json').read_bytes()==retained
        assert profiles.profile_path(base,common_game).exists()
    # Modified or linked launchers are refused before deleting settings.
    entry=launcher(base,solo,roms)
    profiles.save_profile(base,solo,profiles.defaults(solo))
    entry.write_text('#!/bin/sh\necho user launcher\n')
    before=profiles.profile_path(base,solo).read_bytes()
    try:
        profiles.remove_profile(base,solo,roms)
        raise AssertionError('removed user launcher')
    except ValueError:
        assert entry.exists() and profiles.profile_path(base,solo).read_bytes()==before
    entry.unlink();external=root/'user-file';external.write_text('KEEP')
    entry.symlink_to(external)
    try:
        profiles.remove_profile(base,solo,roms)
        raise AssertionError('removed symlink')
    except ValueError:
        assert external.read_text()=='KEEP' and entry.is_symlink()
    # Controller/keyboard confirmation can be cancelled; BL2 has only its own tabs.
    game=windows/'Borderlands 2.wsquashfs'
    app=App(base,game,windowed=True)
    assert app.available_tabs()==(0,1,2)
    app.action('next');assert app.tab==1
    assert any(key=='borderlands2.preset' for key,_,_ in app.current_fields())
    app.row=0;app.action('right')
    assert app.model.data['borderlands2']['preset']=='high'  # retained medium -> high
    app.row=1;app.action('right')
    assert app.model.data['borderlands2']['vsync']=='on'
    app.action('right')
    assert app.model.data['borderlands2']['vsync']=='off'
    app.row=3;app.action('right')
    assert app.model.data['borderlands2']['language']=='french'
    app.action('right')
    assert app.model.data['borderlands2']['language']=='english'
    app.action('next');assert app.tab==2
    app.row=0;app.action('ok')
    assert app.keyboard is not None
    app.keyboard['value']='Alice';app.keyboard_action('save')
    assert app.model.data['borderlands2']['names']==['Alice','','','']
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    saved=profiles.read_profile(base,game)['borderlands2']
    assert saved['vsync']=='off' and saved['language']=='english' and saved['names'][0]=='Alice'
    assert set(app.model.data['borderlands2'])=={'preset','vsync','physx','language','names'}
    app.draw()
    app.row=len(app.current_fields())+2;app.action('ok')
    assert app.removal and app.removal['common'] and app.help_context()=='remove'
    app.draw();app.action('back');assert app.removal is None
    app.action('ok')
    with patch.object(profiles,'PARTY_ROMS',roms):
        # Restore a managed entry for this common game before confirmation.
        launcher(base,game,roms)
        app.action('ok')
    assert app.removal is None and app.model.rom is None
    assert game.exists() and save.read_bytes()==b'SAVE'
    assert any(isinstance(p,CommonGame) and p.id=='borderlands2' for p in app.model.rows)
    app.pg.quit()

print('Bibliothèque : retrait, dissociation, options conservées, reliaison, annulation et protection des fichiers utilisateur vérifiés.')
