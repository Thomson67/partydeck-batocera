"""Dock gap, scaling, Xorg primary output, preferences and controller UI."""
import os
os.environ['SDL_VIDEODRIVER']='dummy';os.environ['PARTYDECK_LANGUAGE']='fr'
from pathlib import Path
import importlib.util,json,sys,tempfile
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_display as d
from partydeck_profiles import defaults,save_profile,profile_path
from partydeck_couch import App
from partydeck_i18n import set_language
spec=importlib.util.spec_from_file_location('display_coop',Path(__file__).resolve().parents[1]/'scripts/partydeck-batocera-coop.py')
coop=importlib.util.module_from_spec(spec);sys.modules[spec.name]=coop;spec.loader.exec_module(coop)

DOCK='''DP-7 "Iiyama PL2792H 1172012012054 (DP-7)"
  Enabled: yes
    1920x1080 px, 60.000000 Hz (preferred, current)
  Position: 3840,0
  Transform: normal
  Scale: 1.000000
DP-4 "Iiyama PL2792H 1172012012051 (DP-4)"
  Enabled: yes
    1920x1080 px, 60.000000 Hz (preferred, current)
  Position: 1920,0
  Transform: normal
  Scale: 1.000000
eDP-1 "Chimei Innolux 0x152E (eDP-1)"
  Enabled: no
    1920x1080 px, 60.001999 Hz (preferred)
'''
outputs=d.parse_wayland(DOCK)
assert len(outputs)==3 and outputs[2].rectangle is None
assert d.choose_output(outputs).name=='DP-4'
assert coop.layout(d.choose_output(outputs).rectangle,2,'horizontal')==[(1920,0,1920,540),(1920,540,1920,540)]
assert d.choose_output(outputs,'DP-7').rectangle==(3840,0,1920,1080)
assert d.choose_output(outputs,'eDP-1').name=='DP-4'  # Never fall back to disabled 0,0.
laptop=[d.Output('eDP-1',(0,0,1920,1080))]
assert d.choose_output(laptop,'DP-7')==laptop[0]
assert d.choose_output(outputs,'DP-7').name=='DP-7'  # Reconnect restores preference.
assert 'DP-7' in d.output_choices(laptop,'DP-7')
# Xwayland may translate the desktop origin. Use its matching connector
# coordinates, while Wayland remains authoritative about disabled outputs.
aligned=d.align_x11(outputs,[d.Output('DP-4',(0,0,1920,1080)),d.Output('eDP-1',(0,0,1920,1080))])
assert d.choose_output(aligned,'DP-4').rectangle==(0,0,1920,1080)
assert aligned[2].rectangle is None
rotated=DOCK.split('DP-4 ')[0].replace('Position: 3840,0','Position: -720,-100').replace('Transform: normal','Transform: 90').replace('Scale: 1.000000','Scale: 1.500000')
assert d.parse_wayland(rotated)[0].rectangle==(-720,-100,720,1280)
xorg=d.parse_xrandr('Monitors: 2\n 0: +HDMI-1 1920/600x1080/340+0+0 HDMI-1\n 1: +*DP-1 2560/600x1440/340+1920-100 DP-1\n')
assert d.choose_output(xorg).name=='DP-1' and d.choose_output(xorg).rectangle==(1920,-100,2560,1440)
with patch.dict(os.environ,WAYLAND_DISPLAY='wayland-0'),patch.object(d.shutil,'which',return_value='/usr/bin/tool'),patch.object(d.subprocess,'run',return_value=Mock(returncode=0,stdout=DOCK)) as run:
    assert d.discover_outputs()==outputs
    assert run.call_args_list[0].args[0]==['wlr-randr']
try:d.choose_output([d.Output('eDP-1',None)]);raise AssertionError('disabled output used')
except RuntimeError:pass
with patch.object(coop,'top_window',side_effect=['81','82']),patch.object(coop,'place_window',return_value=True) as place:
    assert coop.reposition_windows(['own-j1','own-j2'],coop.layout(outputs[1].rectangle,2,'horizontal'))
    assert [c.args for c in place.call_args_list]==[('81',(1920,0,1920,540)),('82',(1920,540,1920,540))]
split = [(0, 0, 1920, 540), (0, 540, 1920, 540)]
centered = (0, 270, 1920, 540)
with patch.object(coop, 'top_window', side_effect=['81', '90']) as search, \
     patch.object(coop, 'window_geometry', side_effect=[split[0], centered]), \
     patch.object(coop, 'place_window', return_value=True) as place, \
     patch.object(coop, 'focus_window') as focus:
    assert coop.reposition_windows(['own-j1', 'own-j2'], split, mapped_only=True)
    place.assert_called_once_with('90', split[1])
    focus.assert_not_called()
    assert all(call.kwargs['visible_only'] for call in search.call_args_list)
with patch.object(coop, 'window_geometry', side_effect=[centered, centered, split[1]]), \
     patch.object(coop, 'remove_fullscreen'), patch.object(coop.time, 'sleep'), \
     patch.object(coop.subprocess, 'run') as move:
    assert coop.place_window('90', split[1])
    assert move.call_args.args[0] == ['xdotool', 'windowmove', '90', '0', '540']
with tempfile.TemporaryDirectory() as temp:
    base=Path(temp);rom=base/'Example.wsquashfs';rom.touch();save_profile(base,rom,defaults(rom));before=profile_path(base,rom).read_bytes()
    assert d.settings(base)==d.DEFAULTS
    with patch('partydeck_couch.discover_outputs',return_value=outputs):
        app=App(base,windowed=True)
        app.library=len(app.model.rows);app.action('ok')
        assert app.desktop_open and app.help_context()=='desktop'
        app.action('right')
        assert d.settings(base)['output']=='DP-7'
        app.action('down');app.action('right')
        assert d.settings(base)['gpu']=='system'
        for language in ('fr','en'):
            set_language(language)
            for family in ('keyboard','xbox','ps'):
                app.input_mode=family;app.draw()
        app.action('down');app.action('ok')  # Explicit rescan retains selected output.
        assert d.settings(base)['output']=='DP-7'
        app.action('back');assert not app.desktop_open
        assert profile_path(base,rom).read_bytes()==before
        app.pg.quit()
    for bad in (dict(gpu='wrong'),dict(output=''),dict(output='DP-1\n'),[]):
        try:d.save_settings(base,bad);raise AssertionError(bad)
        except ValueError:pass
    assert d.settings(base)['output']=='DP-7'
print('Écrans : station 1920/3840, sortie désactivée, rotation/échelle, Xorg, repli/reconnexion et paramètres globaux FR/EN/manette vérifiés.')

# Run the real session loop through a dock geometry change. Existing players
# are moved without restarting Wine or rewriting game-specific preferences.
import contextlib,itertools,io
with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
    base=Path(temp);rom=base/'Example.wsquashfs';rom.touch()
    def mock(obj,key,**kwargs):return stack.enter_context(patch.object(obj,key,**kwargs))
    mock(coop.shutil,'which',return_value='/tool')
    mock(coop,'graphics_environment',return_value={})
    mock(coop,'read_input_devices',return_value=[])
    mock(coop,'assign_players',return_value=[[],[]])
    mock(coop,'primary_monitor',side_effect=itertools.chain([(1920,0,1920,1080)],itertools.repeat((0,0,1920,1080))))
    mock(coop.subprocess,'run',return_value=Mock(returncode=0))
    mock(coop.signal,'signal')
    mock(coop,'stop_players')
    import partydeck_virtual_input as v
    mock(v,'probe',return_value=False)
    starts=mock(coop,'start_player',side_effect=[Mock(pid=31,**{'poll.return_value':None}),Mock(pid=32,**{'poll.return_value':None})])
    mock(coop,'top_window',side_effect=['81','82'])
    mock(coop,'place_window',return_value=True)
    mock(coop,'focus_window')
    move=mock(coop,'reposition_windows',return_value=True)
    mock(coop,'session_result',side_effect=[None,None,None,0])
    mock(coop.time,'monotonic',side_effect=lambda:next(ticks))
    ticks=itertools.count(0,3)
    mock(coop.time,'sleep')
    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    assert coop.run_session(base,base,rom,rom,'2','horizontal','auto')==0
    assert starts.call_count==2
    assert move.call_args_list[0].args[1] == split
    assert move.call_args_list[1].args[1] == split
    assert move.call_args_list[1].kwargs == {'mapped_only': True}
