"""Exercise controller actions, modal text entry, persistence and SDL rendering."""
import copy
import json
import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from partydeck_couch import App, KEYS, Pads, get, put
from partydeck_profiles import defaults, save_profile, read_profile

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    for name in ('Ship of Harkinian', 'Super Mario 64 Coop Deluxe'):
        rom = base / (name+'.wsquashfs')
        rom.touch()
        save_profile(base, rom, defaults(rom))
    app = App(base, windowed=True)
    app.single = False
    assert not app.model.dirty()
    app.action('right')
    app.action('ok')
    assert app.model.data['players'] == '1' and app.model.dirty()
    app.action('next')
    app.action('down')  # Room ID
    app.action('ok')
    assert app.keyboard is not None
    app.keyboard['value'] = ''
    for letter in 'test-room':
        r, c = next((r, row.index(letter)) for r, row in enumerate(KEYS) if letter in row)
        app.keyboard.update(row=r, col=c)
        app.action('ok')
    app.action('save')
    assert app.model.data['anchor']['room'] == 'test-room'
    app.action('ok')
    app.keyboard['value'] = 'cancelled'
    app.action('back')
    assert app.model.data['anchor']['room'] == 'test-room'
    # Every field is reachable and every tab is renderable with no desktop dialog.
    for i in range(4):
        app.tab = i
        app.draw()
    app.tab, app.row = 3, 5
    app.action('ok')  # Master volume
    app.keyboard['value'] = '101'
    app.action('save')
    assert app.keyboard is not None and get(app.model.data, 'anchor.graphics.volumes.Master') == ''
    app.keyboard['value'] = '55'
    app.action('save')
    assert get(app.model.data, 'anchor.graphics.volumes.Master') == 55
    app.action('back')  # Library
    app.action('down')  # Dirty switch confirmation
    assert app.modal
    app.action('back')  # Cancel switching
    assert app.model.data['players'] == '1'
    with patch('partydeck_couch.subprocess.run', return_value=Mock(returncode=0)):
        app.action('save')
    saved = read_profile(base, app.model.rom)
    assert saved['players'] == '1' and saved['anchor']['graphics']['volumes']['Master'] == 55
    assert not app.model.dirty()
    # Never write invalid profiles or lose the previous file after launcher failure.
    prior = copy.deepcopy(saved)
    app.model.data['players'] = '2'
    with patch('partydeck_couch.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'test')):
        assert not app.save()
    assert read_profile(base, app.model.rom) == prior
    app.model.select(app.model.rom)
    # Directory browser chooses ROMs without a desktop file picker.
    app.browse(base)
    app.row = app.browser_rows.index(base/'Super Mario 64 Coop Deluxe.wsquashfs')
    app.action('ok')
    assert app.model.rom.name.startswith('Super Mario') and app.browser is None
    # Fake standardized SDL controller: held buttons trigger once; hat navigation repeats.
    fake = Mock()
    buttons = {0}
    fake.get_button.side_effect = lambda n: n in buttons
    fake.get_axis.return_value = 0
    app.pads.devices = [('sdl', fake, {})]
    app.pads.previous.clear()
    assert app.pads.poll() == ['ok']
    assert app.pads.poll() == []
    buttons.clear()
    app.pads.poll()
    buttons.add(12)
    assert app.pads.poll() == ['down']
    app.pads.timers['down'] = 0
    assert app.pads.poll() == ['down']
    # ES fallback reads hat/button indices instead of assuming model-specific numbers.
    fake.get_hat.return_value = (1, 0)
    app.pads.devices = [('es', fake, {'right':dict(type='hat',id='0',value='2')})]
    app.pads.previous.clear()
    assert app.pads.poll() == ['right']
    app.edit('Room ID', 'windows-party', lambda value: None)
    app.draw()
    app.action('back')
    app.pg.quit()
print('Interface : navigation, clavier virtuel, volumes, annulation, sauvegarde, navigateur et mappings vérifiés.')
