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
   assert views==[selected]
   mounts=[call.args[0] for call in run.call_args_list]
   assert mounts[0][:3]==['mount','-t','overlay'] and f'lowerdir={selected}' in mounts[0][4]
   assert mounts[1][:2]==['mount','--bind'] and mounts[1][-1]==str(selected)
   assert mounts[2]==['mount','-o','remount,bind,ro',str(selected)]
   private=Path(mounts[0][-1]).parents[1]
   assert private.parent==player and private.name.startswith('.proton-')
   exported=u.pressure_vessel_environment(views,{'PRESSURE_VESSEL_FILESYSTEMS_RW':'/saves:/logs'})
   assert exported['PRESSURE_VESSEL_FILESYSTEMS_RW']==f'/saves:/logs:{selected}'
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
