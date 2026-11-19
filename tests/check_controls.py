"""Most Wanted confirmation: no global focus, one Enter per chord, lifecycle."""
import sys,tempfile,os
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_controls as c
# Both shoulder buttons, not a single shoulder or unrelated button.
for buttons,expected in (([],False),([310],False),([311],False),([310,311],True),([304,305],False)):
 def ioctl(fd,request,data,mutate):
  assert request==c.EVIOCGKEY
  for code in buttons:data[code//8]|=1<<(code%8)
 with patch.object(c.fcntl,'ioctl',side_effect=ioctl):assert c.held(1)==expected
for player in ('j1','j2','j3','j4'):
 with patch.object(c.subprocess,'run',side_effect=[Mock(returncode=0,stdout='123\n'),*[Mock(returncode=0)]*3]) as run,patch.object(c.time,'sleep') as sleep:
  events=Mock()
  events.attach_mock(run,'run');events.attach_mock(sleep,'sleep')
  assert c.send_enter(player)
  assert [event[0] for event in events.mock_calls]==['run','run','sleep','run','sleep','run']
  assert [call.args for call in sleep.call_args_list]==[(1.0,),(1.0,)]
  commands=[call.args[0] for call in run.call_args_list[1:]]
  assert commands[0][:6]==['xdotool','key','--window','123','--delay','0']
  assert commands[0].count('BackSpace')==4 and commands[0].count('Delete')==4
  assert commands[1]==['xdotool','type','--window','123','--delay','0','--',player.upper()]
  assert commands[2]==['xdotool','key','--window','123','--delay','40','Return']
# Never confirm when clearing or typing fails.
for code in (1,2):
 with patch.object(c.subprocess,'run',side_effect=[Mock(returncode=0,stdout='123\n')]+[Mock(returncode=0)]*(code-1)+[Mock(returncode=1)]) as run,patch.object(c.time,'sleep'):
  assert not c.send_enter('j2') and run.call_count==code+1
with patch.object(c.subprocess,'run') as run:
 try:c.send_enter('j5');raise AssertionError('invalid player accepted')
 except ValueError:pass
 run.assert_not_called()
for result in (Mock(returncode=1,stdout=''),Mock(returncode=0,stdout='12\n13\n')):
 with patch.object(c.subprocess,'run',return_value=result) as run:
  assert not c.send_enter('j1') and run.call_count==1
with tempfile.TemporaryDirectory() as temp:
 root=Path(temp);(root/'event19').touch();confirmation=c.Confirmation(True,root)
 states=iter([False,False,True,True,True,False,True])
 def held(fd):
  try:return next(states)
  except StopIteration:confirmation.stop.set();return False
 with patch.object(c,'held',side_effect=held),patch.object(c,'send_enter',return_value=True) as send:
  confirmation.run()
  assert send.call_count==2
  assert all(call.args==('j1',) for call in send.call_args_list)
 with patch.object(c.threading,'Thread') as thread:
  with c.Confirmation(False,root):pass
  thread.assert_not_called()
print('Confirmation: two shoulders, one Enter per press, player X11 target, ambiguity refused and cleanup verified.')
