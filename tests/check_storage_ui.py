"""Storage navigation, background work, persistent settings and launch refusal."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
os.environ['SDL_VIDEODRIVER'] = 'dummy'
from pathlib import Path
import sys
import tempfile
import threading
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_storage as storage
from partydeck_couch import App
from partydeck_profiles import defaults, save_profile

with tempfile.TemporaryDirectory() as directory:
    base = Path(directory)
    rom = base/'Example.wsquashfs'
    rom.touch()
    save_profile(base, rom, defaults(rom))
    app = App(base, windowed=True)
    while app.library < len(app.model.rows)+1:
        app.action('down')
    app.action('ok')
    assert app.storage_open and app.help_context() == 'storage'
    app.storage_future.result(timeout=10)
    app.poll_storage()
    assert app.storage_result and app.running
    # Edits belong to global storage settings, never to the selected game.
    app.storage_row = 1
    app.action('left')
    assert storage.settings(base)['cache_mib'] == 1792
    app.action('ok')
    assert app.keyboard
    app.keyboard['value'] = '4096'
    app.action('save')
    assert not app.keyboard and storage.settings(base)['cache_mib'] == 4096
    app.action('ok')
    app.keyboard['value'] = '-1'
    app.action('save')
    assert app.keyboard and storage.settings(base)['cache_mib'] == 4096
    app.action('back')
    for mode in ('keyboard','xbox','ps'):
        app.input_mode = mode
        app.draw()
    # Cleaning remains asynchronous; results trigger a fresh asynchronous report.
    app.storage_row = 5
    app.action('ok')
    app.storage_future.result(timeout=10)
    app.poll_storage()
    app.storage_future.result(timeout=10)
    app.poll_storage()
    app.action('next')
    app.action('back')
    assert not app.storage_open and not app.model.dirty()
    # A preflight failure must leave the UI open and render the entire error.
    app.model.select(rom)
    message = 'Espace insuffisant. Libérez de l’espace ou ajustez Stockage. Aucune sauvegarde supprimée.'
    with patch.object(app,'save',return_value=True), patch('partydeck_couch.prepare_launch',side_effect=RuntimeError(message)):
        app.launch()
        try:
            app.storage_future.result(timeout=10)
        except RuntimeError:
            pass
        app.poll_storage()
    assert app.running and not app.accepted and not app.launch_requested
    assert app.launch_error == message and app.help_context() == 'storage-error'
    app.draw()
    app.action('back')
    assert app.launch_error is None
    # Cancel while the worker is running: completion must never start a game.
    gate = threading.Event()
    with patch.object(app,'save',return_value=True), patch('partydeck_couch.prepare_launch',side_effect=lambda _:gate.wait(5)):
        app.launch()
        app.draw()
        app.action('back')
        gate.set()
        app.storage_future.result(timeout=10)
        app.poll_storage()
    assert app.running and not app.accepted and not app.launch_requested
    app.storage_pool.shutdown(wait=True)
    app.pg.quit()
print('Interface stockage : manette/clavier, analyse asynchrone, réglages et refus/annulation de lancement vérifiés.')
