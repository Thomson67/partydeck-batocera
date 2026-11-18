"""Adaptive keyboard / Xbox / PlayStation help and contextual footer checks."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from partydeck_couch import App, control_label, context_hints

assert control_label('add','keyboard')=='Inser'
assert control_label('ok','keyboard')=='Entrée'
assert control_label('back','keyboard')=='Échap'
assert control_label('save','keyboard')=='F2'
assert control_label('search','keyboard')=='F3'
assert control_label('tabs','keyboard')=='PgUp/PgDn'
assert control_label('add','ps')=='OPTIONS'
assert control_label('tabs','ps')=='L1/R1'
assert control_label('ok','ps')=='Croix'
assert control_label('add','xbox')=='START'
assert context_hints('keyboard','keyboard')==[('ok','Valider'),('back','Annuler')]
assert ('ok','Saisir') in context_hints('keyboard','ps')
assert len(context_hints('browser','keyboard'))==3
assert ('add','Ajouter') not in context_hints('browser','ps')
assert ('tabs','Onglets') not in context_hints('main','keyboard',False)
with tempfile.TemporaryDirectory() as folder:
    app=App(Path(folder),windowed=True)
    assert app.input_mode=='keyboard'
    for mode in ('keyboard','xbox','ps'):
        app.input_mode=mode
        app.draw()
        with patch.object(app,'text',wraps=app.text) as output:
            app.hint('add','Ajouter',100,100)
        texts=[str(c.args[0]) for c in output.call_args_list]
        assert control_label('add',mode) in texts
        assert all(control_label('add',other) not in texts for other in ('keyboard','xbox','ps') if other!=mode)
        app.edit('Room ID','test',lambda text:None)
        assert app.help_context()=='keyboard'
        app.draw()
        app.keyboard=None
        app.browse(Path(folder))
        assert app.help_context()=='browser'
        app.draw()
        app.browser=None
        app.modal='Enregistrer ?'
        assert app.help_context()=='confirm'
        app.draw()
        app.modal=None
    # A keyboard event switches immediately; a controller action switches back.
    app.running=True
    app.input_mode='ps'
    app.pg.event.post(app.pg.event.Event(app.pg.KEYDOWN,key=app.pg.K_DOWN))
    def stop_after_frame():
        assert app.input_mode=='keyboard'
        app.running=False
    with patch.object(app.pads,'poll',return_value=[]), patch.object(app,'draw',side_effect=stop_after_frame):
        app.run()
    app=App(Path(folder),windowed=True)
    app.pads.family='ps'
    def stop_after_pad():
        assert app.input_mode=='ps'
        app.running=False
    with patch.object(app.pads,'poll',return_value=['down']), patch.object(app,'draw',side_effect=stop_after_pad):
        app.run()
print('Aide UI : clavier, Xbox, PS, contextes et bascule automatique vérifiés.')
