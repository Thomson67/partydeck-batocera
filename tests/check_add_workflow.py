"""Explicit personal library, catalogue/manual add, localization and cover lookup."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['PARTYDECK_LANGUAGE']='fr'
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_couch import App,Model
from partydeck_i18n import set_language
from partydeck_profiles import profile_path

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);windows=root/'windows';windows.mkdir();base=root/'app'
    rom=windows/'Hollow Knight Multiplayer.wsquashfs';rom.touch()
    # Even recognized games on disk do not populate a fresh personal library.
    assert Model(base,windows=windows).rows==[]
    with patch('partydeck_couch.Model',side_effect=lambda base,rom=None:Model(base,rom,windows=windows)):
        app=App(base,windowed=True)
    app.action('add');assert app.add_menu==0 and app.help_context()=='add'
    app.draw();app.action('back');assert app.add_menu is None and not app.model.rows
    app.action('add');app.action('down');app.action('ok')
    assert app.browser==windows and app.add_mode=='manual'
    app.draw();app.row=app.browser_rows.index(rom);app.action('ok')
    assert app.model.data['adapter']=='standard'
    assert not profile_path(base,rom).exists()
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    assert app.model.rows==[rom]
    # The catalogue is separate and explicitly activates its predefined adapter.
    app.action('add');app.action('ok')
    assert app.catalog_picker is not None and app.help_context()=='catalog'
    app.catalog_index=next(i for i,r in enumerate(app.catalog_picker) if r.id=='hkmultiplayer')
    app.draw();app.action('ok')
    assert app.model.data['adapter']=='hollowknight-hkmultiplayer'
    assert app.available_tabs()==(0,1,2,3)
    assert app.model.rows==[rom] # no duplicate while selecting another adapter
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    assert app.model.rows==[rom]
    # A manual re-selection of an existing game preserves its saved settings.
    app.action('add');app.action('down');app.action('ok')
    app.row=app.browser_rows.index(rom);app.action('ok')
    assert app.model.data['adapter']=='hollowknight-hkmultiplayer'
    # Standard Batocera metadata supplies a real portrait cover, read-only.
    cover=windows/'media/cover.png';cover.parent.mkdir()
    surface=app.pg.Surface((200,300));surface.fill((120,60,180));app.pg.image.save(surface,str(cover))
    logo=windows/'media/title.png'
    surface=app.pg.Surface((400,120),app.pg.SRCALPHA);surface.fill((20,210,160,255));app.pg.image.save(surface,str(logo))
    gamelist=windows/'gamelist.xml'
    gamelist.write_text('<gameList><game><path>./'+rom.name+'</path><image>./media/cover.png</image><marquee>./media/title.png</marquee></game></gameList>')
    before=gamelist.read_bytes();app.cover_key=None;app.game_logo_key=None
    image=app.selected_cover()
    assert image.get_size()==(200,300) and gamelist.read_bytes()==before
    assert app.selected_game_logo().get_size()==(400,120)
    app.screen=app.pg.display.set_mode((1920,1080))
    for language,expected in (('fr','Depuis le catalogue'),('en','From the catalogue')):
        set_language(language);app.action('add')
        rendered=[];real_text=app.text
        def record(value,*args,**kwargs):
            rendered.append(str(value));return real_text(value,*args,**kwargs)
        with patch.object(app,'text',side_effect=record):app.draw()
        assert expected in rendered
        app.action('ok');app.draw();app.action('back');app.action('back')
    # Broken media never prevents configuration or modifies the source file.
    cover.write_bytes(b'bad image');app.cover_key=None
    assert app.selected_cover() is None
    app.draw();assert gamelist.read_bytes()==before
    # A broken marquee falls back to a conventional wheel; a game with no
    # logo leaves the cover usable and does not borrow another game's image.
    logo.write_bytes(b'bad image');app.game_logo_key=None
    wheel=windows/'media/wheel'/(rom.stem+'.png');wheel.parent.mkdir()
    surface=app.pg.Surface((240,90));app.pg.image.save(surface,str(wheel))
    assert app.selected_game_logo().get_size()==(240,90)
    wheel.unlink();app.game_logo_key=None
    assert app.selected_game_logo() is None
    app.draw();assert gamelist.read_bytes()==before
    app.pg.quit()
print('Add workflow: empty library, catalogue vs manual, adapter persistence, no duplicates, French/English and read-only cover fallback verified.')
