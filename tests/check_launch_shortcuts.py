"""Start launches, Select adds, HK+Start wins; no launch while editing a modal."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['PARTYDECK_LANGUAGE']='fr'
from pathlib import Path
import sys,tempfile
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_couch import App
from partydeck_profiles import defaults,save_profile
with tempfile.TemporaryDirectory() as folder:
    base=Path(folder);rom=base/'Game.wsquashfs';rom.touch();save_profile(base,rom,defaults(rom))
    app=App(base,windowed=True)
    pad=Mock();pad.name='DualSense';pad.get_name.return_value='8BitDo';pad.get_axis.return_value=0
    pressed=set();pad.get_button.side_effect=lambda button:button in pressed
    for kind in ('sdl','es'):
        mapping={} if kind=='sdl' else {'start':dict(type='button',id='7',value='1'),
            'select':dict(type='button',id='8',value='1'), 'hotkeyenable':dict(type='button',id='9',value='1')}
        app.pads.devices=[(kind,pad,mapping)];app.pads.raw=[] if kind=='sdl' else [(pad,mapping)]
        pressed.clear();app.pads.previous.clear()
        start=6 if kind=='sdl' else 7;select=4 if kind=='sdl' else 8;hotkey=5 if kind=='sdl' else 9
        pressed.add(start);assert app.pads.poll()==['launch'];assert app.pads.poll()==[]
        pressed.clear();app.pads.poll();pressed.add(select);assert app.pads.poll()==['add']
        pressed.clear();app.pads.poll();pressed.update((hotkey,start));assert app.pads.poll()==['quit']
        assert app.pads.poll()==[]
    with patch.object(app,'launch') as launch:
        app.action('launch');launch.assert_called_once()
        app.action('add');assert app.add_menu==0
        app.action('launch');assert launch.call_count==1
        app.action('back')
        app.edit('Name','test',lambda value:None);app.action('launch');assert launch.call_count==1
        app.action('back');app.pane='library';app.library=len(app.model.rows)
        app.action('launch');assert launch.call_count==1
        app.library=len(app.model.rows)+1;app.action('launch');assert launch.call_count==1
        app.library=0;app.action('launch');assert launch.call_count==2
    app.pads.devices=[];app.pads.raw=[]
    app.pg.event.post(app.pg.event.Event(app.pg.KEYDOWN,key=app.pg.K_F5))
    with patch.object(app,'launch') as launch,patch.object(app,'draw',side_effect=lambda:setattr(app,'running',False)):
        app.run();launch.assert_called_once()
print('Start/Select: SDL and ES mappings, one-shot presses, HK+Start priority, modal/settings guards and F5 verified.')
