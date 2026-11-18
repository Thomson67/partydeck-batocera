"""Common recipes, missing/ambiguous ROMs, generic tabs, paging and HK+Start."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
os.environ['SDL_VIDEODRIVER'] = 'dummy'
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_catalog import CommonGame, discover, matches_soh
from partydeck_couch import App, Model, fields
from partydeck_profiles import profile_path

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    windows = root/'windows'; windows.mkdir()
    base = root/'install'
    model = Model(base, windows=windows)
    assert len(model.rows) == 4 and isinstance(model.rows[0], CommonGame)
    model.select(model.rows[0]); assert model.rom is None and model.data is None
    assert not (base/'profiles').exists()
    assert not matches_soh(Path('Ocarina of Time 3D.wsquashfs'))
    for suffix in ('.wine','.pc','.wsquashfs'):
        rom = windows/('The Legend of Zelda (SoH)'+suffix)
        rom.touch() if suffix == '.wsquashfs' else rom.mkdir()
        assert discover(windows) == (rom,)
        model = Model(base, windows=windows)
        assert [p for p in model.rows if not isinstance(p,CommonGame)] == [rom]
        model.select(rom); assert model.data['adapter'] == 'soh-anchor'
        rom.unlink() if rom.is_file() else rom.rmdir()
    a=windows/'SoH.wsquashfs'; b=windows/'Ship of Harkinian.pc'; a.touch();b.mkdir()
    model=Model(base, windows=windows)
    assert isinstance(model.rows[0],CommonGame) and len(model.rows[0].matches)==2
    a.unlink();b.rmdir()
    def create_app():
        with patch('partydeck_couch.Model',side_effect=lambda base,rom=None:Model(base,rom,windows=windows)):
            return App(base,windowed=True)
    app=create_app()
    app.action('ok'); assert app.missing is not None
    app.action('back'); assert app.missing is None and 'disposer du jeu' in app.notice
    assert not (base/'profiles').exists()
    app.action('ok'); app.action('ok')
    assert app.browser==windows and app.pending_common is not None
    app.action('back'); assert app.browser is None and app.pending_common is None
    # Manual linking works for every supported format, without writing any game data.
    for suffix in ('.wine','.pc','.wsquashfs'):
        rom=windows/('My custom title'+suffix)
        rom.touch() if suffix=='.wsquashfs' else rom.mkdir()
        app.action('ok'); app.action('ok')
        app.row=app.browser_rows.index(rom); app.action('ok')
        assert app.model.rom==rom and app.model.data['adapter']=='soh-anchor'
        assert not profile_path(base,rom).exists()
        app.model.select(CommonGame('soh','SoH','soh-anchor'));app.pane='library'
        rom.unlink() if rom.is_file() else rom.rmdir()
    for i in range(25): (windows/f'Directory {i:02}').mkdir()
    app.browse(windows); app.action('next'); assert app.row==9
    app.action('next'); assert app.row==18
    app.action('prev'); assert app.row==9
    # Holding either shoulder pages continuously in the picker, with the same
    # delay/rate as directional navigation. SDL and ES fallback both support it.
    for kind in ('sdl','es'):
        fake=Mock();fake.name='DualSense';fake.get_name.return_value='8BitDo'
        fake.get_axis.return_value=0
        buttons=set()
        fake.get_button.side_effect=lambda n:n in buttons
        app.pads.devices=[(kind,fake,{} if kind=='sdl' else {
            'pageup':dict(type='button',id='4',value='1'),
            'pagedown':dict(type='button',id='5',value='1')})]
        app.pads.raw=[];app.pads.previous.clear();app.row=0
        def held(at):
            with patch('partydeck_couch.time.monotonic',return_value=at):
                actions=app.pads.poll(repeat_pages=app.help_context()=='browser')
                for action in actions:app.action(action)
                return actions
        buttons.add(10 if kind=='sdl' else 5)
        assert held(10)==['next'] and app.row==9
        assert held(10.34)==[] and app.row==9
        assert held(10.351)==['next'] and app.row==18
        assert held(10.46)==[]
        assert held(10.472)==['next'] and app.row==min(27,len(app.browser_rows)-1)
        assert held(10.60)==['next'] and app.row==len(app.browser_rows)-1
        buttons.clear();assert held(11)==[]
        buttons.add(9 if kind=='sdl' else 4)
        assert held(12)==['prev']
        old=app.row;assert held(12.351)==['prev'] and app.row==max(0,old-9)
        assert held(12.48)==['prev'] and app.row==0
        # Modal text entry and regular tabs never repeat shoulder actions.
        app.edit('Search','',lambda value:None)
        assert held(14)==[]
        app.action('back');app.action('back');assert app.browser is None
        assert held(15)==[]
        app.browse(windows);buttons.clear();held(16)
    app.action('back')
    generic=windows/'Other game.wsquashfs';generic.touch();app.select_game(generic)
    assert app.available_tabs()==(0,)
    app.action('next'); assert app.tab==0
    with patch('partydeck_couch.subprocess.run',return_value=Mock(returncode=0)):
        assert app.save()
    assert '"anchor"' not in profile_path(base,generic).read_text()
    # The raw ES hotkey can be any button, not only Guide.
    pad=Mock(); buttons={8,9};pad.get_button.side_effect=lambda n:n in buttons
    app.pads.devices=[]; app.pads.raw=[(pad,{'hotkeyenable':dict(type='button',id='8',value='1'),
                                         'start':dict(type='button',id='9',value='1')})]
    app.pads.previous.clear()
    assert app.pads.poll()==['quit']
    assert app.pads.poll()==[]
    app.action('quit');assert not app.running
    app.running=True;app.model.data['players']='2'
    app.edit('Pending text','abc',lambda value:None)
    app.action('quit');assert app.modal and app.keyboard is None and app.running
    app.action('back');assert app.running and app.modal is None
    app.action('quit');app.action('search');assert not app.running
    app.pg.quit()
print('Catalogue : détection, liaison manuelle, annulation, profils génériques, pages LB/RB et HK+Start vérifiés.')
