"""One source/row across recipes; full-screen layout and readable library titles."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['PARTYDECK_LANGUAGE']='fr'
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_couch import App,Model
from partydeck_profiles import defaults,save_profile,profile_path
from partydeck_hkmultiplayer import defaults as multi_defaults
from partydeck_i18n import set_language

with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);windows=root/'roms';windows.mkdir();base=root/'app'
    rom=windows/'Hollow Knight.wsquashfs';rom.touch()
    data=defaults(rom);data.update(adapter='hollowknight-hkmultiplayer',hkmultiplayer=multi_defaults())
    save_profile(base,rom,data)
    before=profile_path(base,rom).read_bytes()
    model=Model(base,windows=windows)
    # Plain title matches HKMP discovery but was deliberately linked to the
    # newer HKMultiplayer adapter. Do not add that same ROM for both adapters.
    assert model.rows.count(rom)==1
    model.select(rom)
    assert model.data['adapter']=='hollowknight-hkmultiplayer'
    assert model.common_for_rom[rom].adapter=='hollowknight-hkmultiplayer'
    assert profile_path(base,rom).read_bytes()==before
    # Symlink aliases to the same source also appear only once.
    alias=windows/'Hollow Knight alias.wsquashfs';alias.symlink_to(rom)
    save_profile(base,alias,defaults(alias))
    model=Model(base,windows=windows)
    assert len([p for p in model.rows if isinstance(p,Path) and p.resolve()==rom])==1
    for text in ('Hollow','Knight'):
        model.filter=text;model.reload()
        assert len([p for p in model.rows if isinstance(p,Path) and p.resolve()==rom])==1
    # Identically named but genuinely separate ROM files are not collapsed.
    second=windows/'Other/Hollow Knight.wsquashfs';second.parent.mkdir();second.touch()
    save_profile(base,second,data|{'rom':str(second)})
    model=Model(base,windows=windows)
    assert len([p for p in model.rows if isinstance(p,Path)])==2
    with patch('partydeck_couch.Model',side_effect=lambda base,rom=None:Model(base,rom,windows=windows)):
        app=App(base,windowed=True)
    for language in ('fr','en'):
        set_language(language)
        for resolution in ((1920,1080),(2560,1440),(3440,1440),(1280,1024),(1280,800)):
            app.screen=app.pg.display.set_mode(resolution)
            app.draw()
            width,height=app.canvas.get_size()
            assert abs(width/height-resolution[0]/resolution[1])<.002
            assert app.screen.get_at((0,resolution[1]//2))[:3]!=(8,10,18)
            assert app.layout_point(1440,900)==(width,height)
            if resolution[0]/resolution[1]>1.6:
                assert app.layout_rect((24,142,340,652))[2]>340
            rendered=[]
            with patch.object(app,'text',side_effect=lambda value,*a,**k:rendered.append((value,a,k))):
                title='The Legend of Zelda - Ocarina of Time - Ship of Harkinian'
                app.library_title(title,50,246,284)
            assert 1<=len(rendered)<=2
            assert all(call[1][2]==16 for call in rendered)
            assert ' '.join(call[0] for call in rendered)==title
    # The cover sits above the library; the narrower title banner begins at
    # the settings panel rather than covering the portrait at upper left.
    boxes=[];original_box=app.box
    def record_box(rect,color,*args,**kwargs):
        boxes.append((rect,color));return original_box(rect,color,*args,**kwargs)
    with patch.object(app,'box',side_effect=record_box):app.draw()
    cover=next(rect for rect,color in boxes if color==(12,19,31))
    header=next(rect for rect,color in boxes if color==(23,29,46))
    panes=[rect for rect,color in boxes if color==(20,25,40)]
    library=min(panes,key=lambda rect:rect[0]);settings=max(panes,key=lambda rect:rect[0])
    assert cover[1]+cover[3]<=library[1] # cover entirely above the library
    assert cover[0]==library[0] and cover[2]==library[2]
    assert header[0]==settings[0] and header[2]==settings[2]
    assert header[0]>=cover[0]+cover[2] # no title/cover overlap
    # Visual order and controller order are identical below the game list.
    app.pane='library';app.library=len(app.model.rows)-1
    with patch.object(app,'open_desktop') as desktop,patch.object(app,'open_storage') as storage:
        app.action('down');assert app.library==len(app.model.rows)
        app.action('ok');desktop.assert_called_once();storage.assert_not_called()
        app.action('down');assert app.library==len(app.model.rows)+1
        app.action('ok');storage.assert_called_once()
        app.action('up');assert app.library==len(app.model.rows)
        app.action('ok');assert desktop.call_count==2
    app.pg.quit()
print('UI: unique linked sources/aliases, saved adapter preserved, full-screen aspect ratios, French/English and two-line titles verified.')
