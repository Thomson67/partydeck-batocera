"""Native ES runner picker, independent selection and private Wine composition."""
import os
os.environ['PARTYDECK_LANGUAGE']='fr'
import sys,subprocess,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_profiles as p
from partydeck_i18n import set_language

native='''#!/bin/bash
get_setting() {
 printf '%s\\n' "windows-$1"
}
printf '%s\\n' "$(get_setting wine-runner windows Game)" "$(get_setting core windows Game)" "$(get_setting dxvk windows Game)"
'''
for runner in ('GE-Proton11-9-UMU',"Runner ' quoted",'x$(touch not-executed)'):
    source=p.instrument_runner(native,runner)
    done=subprocess.run(['bash','-c',source],text=True,capture_output=True,check=True)
    assert done.stdout.splitlines()==[runner,runner,'windows-dxvk']
try:p.instrument_runner('unknown launcher','Runner');raise AssertionError('unknown launcher changed')
except RuntimeError:pass
rom=Path('/userdata/roms/windows/Un jeu #=.wsquashfs')
with patch.object(p.shutil,'which',return_value='/usr/bin/batocera-settings-get'):
    for responses,expected in ((['CustomParty','Unused'],'CustomParty'),(['auto','SystemRunner'],'SystemRunner'),(['',''],None)):
        with patch.object(p.subprocess,'run',side_effect=[Mock(returncode=0,stdout=s) for s in responses]) as run:
            assert p.selected_party_runner(rom)==expected
            first=run.call_args_list[0].args[0][1]
            assert first.startswith('windows-party["') and '#=' not in first and first.endswith('.sh"].wine-runner')
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    for locale,title in (('fr','RUNNER WINE'),('en','WINE RUNNER')):
        set_language(locale)
        path=p.install_runner_editor(root)
        tree=ET.parse(path)
        feature=tree.find('./emulator/systems/system/feature')
        assert tree.find('emulator').get('name')=='sh'
        assert tree.find('./emulator/systems/system').get('name')=='windows-party'
        assert feature.get('name')==title and feature.get('preset')=='runners'
        assert feature.get('value')=='wine-runner'
        hidraw=tree.find('./emulator/systems/system/feature[@value="enable_hidraw"]')
        assert hidraw.get('name')==('ACTIVER HIDRAW' if locale=='fr' else 'ENABLE HIDRAW')
        assert [c.get('value') for c in hidraw.findall('choice')]==['0','1']
        hud=tree.find('./emulator/systems/system/feature[@value="mangohud_profile"]')
        assert [c.get('value') for c in hud.findall('choice')]==['default','minimal','detailed']
        assert hud.get('name')==('Profil MangoHud' if locale=='fr' else 'MangoHud profile')
    path.write_text('USER CONFIG')
    try:p.install_runner_editor(root);raise AssertionError('personal features replaced')
    except ValueError:pass
    assert path.read_text()=='USER CONFIG'
    binary=root/'batocera-wine';binary.write_text(native)
    player=root/'j1';player.mkdir()
    with patch.object(p,'selected_party_hidraw',return_value=None),patch.object(p,'selected_party_runner',return_value='CustomRunner'),patch.object(p.shutil,'which',return_value=str(binary)),patch.object(p.subprocess,'run') as run:
        p.install_party_runner_hook(rom,player)
        assert binary.read_text()==native
        assert run.call_args_list[-1].args[0]==['mount','--bind',str(player/'batocera-wine-party-runner'),str(binary)]
    done=subprocess.run(['bash',str(player/'batocera-wine-party-runner')],text=True,capture_output=True,check=True)
    assert done.stdout.splitlines()[0]=='CustomRunner'
    with patch.object(p,'selected_party_hidraw',return_value=None),patch.object(p,'selected_party_runner',return_value=None),patch.object(p.subprocess,'run') as run:
        p.install_party_runner_hook(rom,player);run.assert_not_called()

# Explicit Off must survive false-like values; Auto delegates to the system
# setting, then native Windows. HIDRAW-only overrides must not change runners.
with patch.object(p.shutil,'which',return_value='/usr/bin/batocera-settings-get'):
    for responses,expected in ((['0'],'0'),(['1'],'1'),(['auto','1'],'1'),(['','0'],'0'),(['auto','auto'],None)):
        with patch.object(p.subprocess,'run',side_effect=[Mock(returncode=0,stdout=s) for s in responses]) as run:
            assert p.selected_party_hidraw(rom)==expected
            assert run.call_args_list[0].args[0][1].endswith('.sh"].enable_hidraw')
            if len(responses)==2:assert run.call_args_list[1].args[0][1]=='windows-party.enable_hidraw'
native_hidraw=native+'printf "%s\\n" "$(get_setting enable_hidraw windows Game)"\n'
for runner,hidraw in ((None,'0'),(None,'1'),('CustomRunner','0'),('CustomRunner','1')):
    done=subprocess.run(['bash','-c',p.instrument_runner(native_hidraw,runner,hidraw)],text=True,capture_output=True,check=True)
    assert done.stdout.splitlines()==[runner or 'windows-wine-runner',runner or 'windows-core','windows-dxvk',hidraw]
try:p.instrument_runner(native,None,'$(touch injected)');raise AssertionError('invalid HIDRAW accepted')
except ValueError:pass
print('Options ES : sélecteur Wine FR/EN, Auto/héritage, priorités dédiées et override Wine privé vérifiés.')
