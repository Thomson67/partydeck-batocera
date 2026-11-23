"""Real temporary installs: preserve progress, isolate cleanup, restore and UI."""
import os
os.environ['SDL_VIDEODRIVER']='dummy'
os.environ['PARTYDECK_LANGUAGE']='fr'
from pathlib import Path
import fcntl
import json
import shlex
import sys
import tempfile
import xml.etree.ElementTree as ET
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_uninstall as u
from partydeck_couch import App
from partydeck_i18n import set_language


def put(path, data=b'data'):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else data.encode())
    return path


def fixture(directory):
    layout=u.Layout(Path(directory)/'userdata')
    put(layout.base/'windows-party',b'installer')
    put(layout.base/'cache/large.bin',b'cache')
    put(layout.base/'profiles/game.json',b'profile')
    put(layout.base/'runtime/game/j1/user.reg',b'identity')
    put(layout.base/'archive/legacy/game/save.dat',b'legacy save')
    put(layout.bottles/'players/game/j1/prefixes/save.dat',b'prefix save')
    # A lower hardlink remains readable after deleting the shared object store.
    obj=put(layout.bottles/'objects/object',b'Windows lower')
    lower=layout.bottles/'players/game/j1/prefixes-lower/lower.dll'
    lower.parent.mkdir(parents=True);os.link(obj,lower)
    put(layout.bottles/'seeds/windows.dll',b'seed')
    put(layout.saves/'Game/j1/windows/slot.sav',b'external save')
    (layout.saves/'Game/j1/prefixes').symlink_to(layout.bottles/'players/game/j1/prefixes',target_is_directory=True)
    layout.legacy.symlink_to(layout.base,target_is_directory=True)
    script=put(layout.roms/'Game.sh','#!/bin/bash\n# Entrée gérée par PartyDeck Wine\n'+shlex.join(['exec',str(layout.base/'windows-party'),'profil','/original/Game.wine'])+'\n')
    put(layout.legacy_roms/script.name,script.read_bytes())
    old=put(layout.ports/'Old test.sh','#!/bin/bash\n# Entrée gérée par partydeck-test\n'+shlex.join(['exec',str(layout.legacy/'partydeck-test'),'jouer','game.exe'])+'\n')
    put(layout.ports/'Personal.sh',b'#!/bin/bash\necho personal\n')
    for folder, name, extras in ((layout.roms,script.name,False),(layout.legacy_roms,script.name,False),
                                (layout.ports,old.name,True)):
        root=ET.Element('gameList');node=ET.SubElement(root,'game');ET.SubElement(node,'path').text='./'+name
        if extras:
            node=ET.SubElement(root,'game');ET.SubElement(node,'path').text='./Personal.sh'
        put(folder/'gamelist.xml',ET.tostring(root))
    put(layout.roms/'theme.xml','<theme><!-- Logo géré par Windows Party --></theme>')
    original=put(layout.userdata/'roms/windows/media/original.png',b'ORIGINAL ART')
    (layout.roms/'media').symlink_to(original.parent,target_is_directory=True)
    root=ET.Element('systemList')
    for name,path in [('windows-party',layout.roms),('ports',layout.ports)]:
        node=ET.SubElement(root,'system');ET.SubElement(node,'name').text=name;ET.SubElement(node,'path').text=str(path)
    put(layout.config/'es_systems.cfg',ET.tostring(root))
    own=ET.Element('systemList');own.append(ET.fromstring(ET.tostring(root[0])))
    put(layout.config/'es_systems_windows-party.cfg',ET.tostring(own))
    put(layout.config/'es_settings.cfg','<config><string name="windows-party.foo" value="x"/><string name="ThemeSet" value="mytheme"/></config>')
    return layout,original


with tempfile.TemporaryDirectory() as directory:
    layout,original=fixture(directory)
    result=u.execute(layout)
    snapshot=Path(result['snapshot'])
    assert not layout.base.exists() and not layout.legacy.is_symlink() and not layout.bottles.exists()
    assert not layout.roms.exists() and not layout.legacy_roms.exists() and result['leftovers'] is None
    assert (layout.saves/'Game/j1/windows/slot.sav').read_bytes()==b'external save'
    assert (snapshot/'bottles/players/game/j1/prefixes/save.dat').read_bytes()==b'prefix save'
    assert (snapshot/'bottles/players/game/j1/prefixes-lower/lower.dll').read_bytes()==b'Windows lower'
    assert (snapshot/'state/windows-party/runtime/game/j1/user.reg').read_bytes()==b'identity'
    assert (snapshot/'state/windows-party/archive/legacy/game/save.dat').read_bytes()==b'legacy save'
    assert original.read_bytes()==b'ORIGINAL ART'
    assert (layout.ports/'Personal.sh').read_bytes()==b'#!/bin/bash\necho personal\n'
    assert ET.parse(layout.ports/'gamelist.xml').findtext('.//path')=='./Personal.sh'
    assert [n.findtext('name') for n in ET.parse(layout.config/'es_systems.cfg').getroot()]==['ports']
    assert not (layout.config/'es_systems_windows-party.cfg').exists()
    assert ET.parse(layout.config/'es_settings.cfg').find('.//string').get('name')=='ThemeSet'
    assert json.loads((snapshot/'receipt.json').read_text())['complete']
    u.restore_preserved(layout)
    assert (layout.saves/'Game/j1/prefixes/save.dat').read_bytes()==b'prefix save'
    assert (layout.base/'runtime/game/j1/user.reg').read_bytes()==b'identity'
    assert not (layout.base/'cache').exists() and not (layout.base/'profiles').exists()
    assert not (layout.bottles/'objects').exists()

for failure in ('lock','mount','badxml','redirect'):
    with tempfile.TemporaryDirectory() as directory:
        layout,original=fixture(directory)
        lock=None
        try:
            if failure=='lock':
                lock=(layout.base/'session.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if failure=='badxml':(layout.config/'es_systems.cfg').write_text('<broken')
            if failure=='redirect':
                (layout.roms/'gamelist.xml').unlink();(layout.roms/'gamelist.xml').symlink_to(original)
            with patch.object(u,'mounted_paths',return_value={layout.base/'runtime/mounted'} if failure=='mount' else set()):
                try:u.execute(layout);raise AssertionError(failure)
                except (RuntimeError,ET.ParseError):pass
            assert (layout.base/'windows-party').exists() and not layout.backup.exists()
            assert original.read_bytes()==b'ORIGINAL ART'
            assert (layout.bottles/'players/game/j1/prefixes/save.dat').read_bytes()==b'prefix save'
        finally:
            if lock:lock.close()

with tempfile.TemporaryDirectory() as directory:
    app=App(Path(directory),windowed=True)
    app.open_desktop();app.desktop_row=3
    with patch.object(u,'preview'),patch.object(u,'execute',return_value=dict(snapshot='test',leftovers=None)) as execute:
        app.action('ok');assert app.uninstall_state=='confirm' and app.uninstall_choice==0
        app.action('ok');assert app.uninstall_state is None and not execute.called
        app.action('ok');app.action('back');assert app.uninstall_state is None
        app.action('ok')
        for language in ('fr','en'):
            set_language(language)
            for mode in ('keyboard','xbox','ps'):app.input_mode=mode;app.draw()
        app.action('right');app.action('ok');assert app.uninstall_state=='running'
        app.uninstall_future.result(timeout=10);app.poll_uninstall()
        assert app.uninstall_state=='done' and execute.call_count==1 and not app.launch_requested
        app.draw();app.action('ok');assert not app.running and not app.accepted
    app.storage_pool.shutdown(wait=True);app.pg.quit()
print('Uninstall: preserved saves, identities, legacy data and lower files; owned frontend cleanup, guards, restore and UI verified.')
