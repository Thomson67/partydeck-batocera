"""Private Proton distribution writes, read-only wrapper view and rollback."""
import os,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_umu as u
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);runners=root/'runners';runners.mkdir();player=root/'j1';player.mkdir()
 selected=runners/'GE-Proton11-UMU';selected.mkdir();(selected/'proton').write_bytes(b'IMMUTABLE')
 (runners/'TKG').mkdir();(runners/'TKG/proton').write_bytes(b'CLASSIC')
 env={'PARTYDECK_PRIVATE_PLAYER':str(player)}
 with patch.dict(os.environ,env,clear=True),patch.object(u.subprocess,'run',return_value=Mock(returncode=0)) as run:
  with u.runner_views(player,runners) as views:
   mounts=[call.args[0] for call in run.call_args_list]
   assert mounts[0][:3]==['mount','-t','overlay'] and f'lowerdir={selected}' in mounts[0][4]
   assert mounts[1][:2]==['mount','--bind'] and mounts[1][-1]==str(selected)
   assert mounts[2]==['mount','-o','remount,bind,ro',str(selected)]
   assert views==[mounts[0][-1]]
   private=next(player.glob('.proton-*'))
   assert views[0]==str(player/'proton-runners'/selected.name)
   assert private.parent==player and private.name.startswith('.proton-')
   exported=u.pressure_vessel_environment(views,{'PRESSURE_VESSEL_FILESYSTEMS_RW':'/saves:/logs'})
   assert exported['PRESSURE_VESSEL_FILESYSTEMS_RW']==f'/saves:/logs:{views[0]}'
   assert u.pressure_vessel_environment(views,exported)==exported
  assert run.call_args_list[-2].args[0]==['umount','--',str(selected)]
  assert run.call_args_list[-1].args[0]==['umount','--',mounts[0][-1]]
  assert not private.exists()
 assert (selected/'proton').read_bytes()==b'IMMUTABLE' and not (selected/'dist.lock').exists()
 # Failure after mounting the private lower view must still unmount it and
 # remove its temporary upper, without chmod/remounting the shared runner RW.
 with patch.dict(os.environ,env,clear=True),patch.object(u.subprocess,'run') as run:
  run.side_effect=[Mock(returncode=0),subprocess.CalledProcessError(1,['mount']),Mock(returncode=0)]
  try:
   with u.runner_views(player,runners):raise AssertionError('failed bind accepted')
  except subprocess.CalledProcessError:pass
  assert run.call_args.args[0][:2]==['umount','--']
 assert not list(player.glob('.proton-*'))
 with patch.dict(os.environ,{},clear=True),patch.object(u.subprocess,'run') as run:
  try:
   with u.runner_views(player,runners):raise AssertionError('outside sandbox accepted')
  except RuntimeError:pass
  run.assert_not_called()
 with u.runner_views(player,root/'missing') as paths:assert paths==[]
 assert u.pressure_vessel_environment([],{'A':'B'})=={'A':'B'}
 # Two players must never share an upper layer or mutable Proton lock.
 player2=root/'j2';player2.mkdir()
 with patch.object(u.subprocess,'run',return_value=Mock(returncode=0)):
  with patch.dict(os.environ,{'PARTYDECK_PRIVATE_PLAYER':str(player)},clear=True):
   with u.runner_views(player,runners):
    with patch.dict(os.environ,{'PARTYDECK_PRIVATE_PLAYER':str(player2)},clear=True):
     with u.runner_views(player2,runners):
      assert next(player.glob('.proton-*'))!=next(player2.glob('.proton-*'))
print('UMU : vues Proton privées, export RW limité aux overlays, intégrité des fichiers source, joueurs séparés et nettoyage/échec vérifiés.')

# Execute the relay against a real zipapp: mocks cannot check entrypoint,
# import resolution or argument forwarding through the nested runpy calls.
import json,zipapp
with tempfile.TemporaryDirectory(prefix='umu relay ') as temp:
 root=Path(temp);app=root/'app';app.mkdir();out=root/'result.json'
 (app/'__main__.py').write_text("import os,sys,json\nfrom pathlib import Path\n"
     +f"Path({str(out)!r}).write_text(json.dumps([os.environ['PROTONPATH'],sys.argv[1:]]))\n")
 original=root/'original.pyz';zipapp.create_archive(app,original)
 relay=root/'relay.py';source=root/'installed UMU';alias=root/'private view'
 relay.write_text(u.launcher_relay(original,{str(source):str(alias)},root/'j1'))
 for selected,expected in ((source,alias),(root/'other',root/'other')):
  subprocess.run([sys.executable,str(relay),'game.exe','arg with space'],
      env=dict(os.environ,PROTONPATH=str(selected)),check=True)
  assert json.loads(out.read_text())==[str(expected),['game.exe','arg with space']]
 # Pin the original launcher before installing the relay; remove both binds
 # before unmounting the distribution views.
 runners=root/'runners';runners.mkdir();runner=runners/'GE-UMU';runner.mkdir()
 (runner/'proton').touch();player=root/'j1';player.mkdir()
 with patch.dict(os.environ,{'PARTYDECK_PRIVATE_PLAYER':str(player)}),patch.object(u.subprocess,'run',return_value=Mock(returncode=0)) as run:
  with u.runner_views(player,runners,original) as views:
   calls=[c.args[0] for c in run.call_args_list]
   assert calls[3][:2]==['mount','--bind'] and calls[3][2]==str(original)
   assert calls[4][:2]==['mount','--bind'] and calls[4][-1]==str(original)
   assert views[0] in Path(calls[4][2]).read_text()
  unmounts=[c.args[0] for c in run.call_args_list if c.args[0][0]=='umount']
  assert unmounts[0]==['umount','--',str(original)]
  assert unmounts[1]==['umount','--',calls[3][-1]]
print('UMU relay: real zipapp execution, native selection, arguments and mount lifetime verified.')
