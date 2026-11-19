"""MangoHud scope, native final-command environment and UWT shim composition."""
import os,sys,subprocess,tempfile,json,shlex
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_mangohud as m
import partydeck_profiles as p
native='''#!/bin/bash
getWine_var() { printf '%s' "KEEP='value with spaces' MANGOHUD=0 DISABLE_MANGOHUD=1"; }
WINEPOINT=/private
GAMENAME=/private
'''+''.join('WINE_ENV=$(getWine_var "${WINEPOINT}" "ENV" "")\n' for _ in range(3))
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp)
 probe=root/'probe.py';probe.write_text("import os,json;print(json.dumps({k:os.environ.get(k) for k in ('MANGOHUD','DISABLE_MANGOHUD','KEEP')}))")
 for enabled in (True,False):
  source=m.instrument(native,enabled,root/'absent')
  subprocess.run(['bash','-n'],input=source,text=True,check=True)
  source+='\neval "$WINE_ENV" '+sys.executable+' '+str(probe)+'\n'
  done=subprocess.run(['bash'],input=source,text=True,capture_output=True,check=True)
  assert json.loads(done.stdout)==dict(MANGOHUD=str(int(enabled)),DISABLE_MANGOHUD=None if enabled else '1',KEEP='value with spaces')
 runtime=root/'runtime'
 for lib in ('lib64','lib32'):
  path=runtime/lib/'mangohud';path.mkdir(parents=True);(path/'libMangoHud_shim.so').touch()
 source=m.instrument(native,True,runtime)
 subprocess.run(['bash','-n'],input=source,text=True,check=True)
 assert 'libMangoHud_shim.so' in source and 'UMU_BATOCERA_EXTRA_RO' in source
 # Auto must leave launchers/settings alone.
 with patch.object(p,'selected_party_switch',return_value=None),patch.object(m,'selected_profile',return_value=None),patch.object(m.subprocess,'run') as run:
  m.install_hook(Path('/game.wine'),root);run.assert_not_called()
for key in ('mangohud','enable_hidraw'):
 with patch.object(p.shutil,'which',return_value='settings'),patch.object(p.subprocess,'run',side_effect=[Mock(returncode=0,stdout='auto'),Mock(returncode=0,stdout='0')]) as run:
  assert p.selected_party_switch(Path('/game.wsquashfs'),key)=='0'
  assert run.call_args_list[1].args[0][1]==f'windows-party.{key}'
print('MangoHud: Auto, explicit on/off, original ENV, final commands and private UWT runtime verified.')

with tempfile.TemporaryDirectory(prefix='hud layers ') as temp:
 root=Path(temp);runtime=root/'runtime';player=root/'j1'
 for bits in ('32','64'):
  path=runtime/f'lib{bits}/mangohud';path.mkdir(parents=True)
  (path/'libMangoHud.so').touch()
 layers=m.prepare_layers(player,runtime)
 assert len(list(layers.glob('*.json')))==2
 for path in layers.glob('*.json'):
  layer=json.loads(path.read_text())['layer']
  assert Path(layer['library_path']).is_file()
  assert layer['library_arch'] in ('32','64')
 # Run the actual emitted shell, including a preexisting hidden profile and
 # unrelated PV mounts. Check both paths survive in one extra-RO assignment.
 native_profiles=native.replace("MANGOHUD=0 DISABLE_MANGOHUD=1", "MANGOHUD=0 DISABLE_MANGOHUD=1 MANGOHUD_CONFIG=no_display")
 probe=root/'env.py';probe.write_text("import os,json;print(json.dumps(dict(os.environ)))")
 for profile in m.PROFILES:
  source=m.instrument(native_profiles,True,runtime,profile,layers)
  source+='\neval "$WINE_ENV" '+shlex.quote(shlex.join([sys.executable,str(probe)]))+'\n'
  done=subprocess.run(['bash'],input=source,text=True,capture_output=True,check=True,env=dict(os.environ,UMU_BATOCERA_EXTRA_RO='/other'))
  env=json.loads(done.stdout)
  assert env['MANGOHUD_CONFIG']==m.PROFILES[profile]
  assert 'DISABLE_MANGOHUD' not in env
  assert env['UMU_BATOCERA_EXTRA_RO'].split(':')==[str(runtime),str(layers),'/other']
  assert env['VK_ADD_IMPLICIT_LAYER_PATH'].split(':')[0]==str(layers)
 # Missing runtime leaves native Vulkan support alone and removes stale manifests.
 (runtime/'lib32/mangohud/libMangoHud.so').unlink()
 m.prepare_layers(player,runtime)
 assert len(list(layers.glob('*.json')))==1
print('MangoHud profiles: explicit visible configurations, private 32/64 manifests, shell execution and combined runtime exports verified.')
