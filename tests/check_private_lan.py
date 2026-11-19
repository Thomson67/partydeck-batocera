"""Private-only topology planning, pinned namespace ownership and rollback.

Kernel namespace creation cannot be exercised in the CI container. The shipped
verifier performs the actual same-port UDP exchange on the Batocera host.
"""
import io,os,sys,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import partydeck_private_lan as n

for bad in (1,0,5,True,'2'):
    try:n.PrivateLAN(bad);raise AssertionError(bad)
    except ValueError:pass
lan=n.PrivateLAN(2)
fd=os.open('/proc/self/ns/net',os.O_RDONLY)
lan.fds=[fd];lan.holders=[Mock(**{'poll.return_value':None})]
try:
    try:lan.prefix(0);raise AssertionError('host netns accepted')
    except RuntimeError:pass
finally:os.close(fd)

def holder(pid):
    p=Mock(pid=pid,stdin=Mock(),stdout=io.BytesIO(b'READY\n'))
    p.poll.return_value=None
    return p

for count in (2,3,4):
    lan=n.PrivateLAN(count);holders=[holder(100+i) for i in range(count)]
    with patch.object(n.shutil,'which',return_value='/bin/tool'),\
         patch.object(n.subprocess,'Popen',side_effect=holders),\
         patch.object(n.select,'select',side_effect=lambda *a:([a[0][0]],[],[])),\
         patch.object(n.os,'open',side_effect=range(200,200+count)),\
         patch.object(n.os,'fstat',side_effect=lambda fd:SimpleNamespace(st_dev=lan.host.st_dev,st_ino=lan.host.st_ino+fd)),\
         patch.object(n.os,'close') as close,\
         patch.object(n.subprocess,'run',return_value=Mock(returncode=0)) as run:
        lan.start()
        assert [lan.address(i) for i in range(count)]==[f'192.168.247.{11+i}' for i in range(count)]
        commands=[call.args[0] for call in run.call_args_list]
        # Every mutation is prefixed with a pinned, private network FD.
        assert all(cmd[:1]==['nsenter'] and cmd[1].startswith('--net=/proc/self/fd/') and cmd[2]=='--' for cmd in commands)
        assert sum('veth' in cmd for cmd in commands)==count-1
        assert sum('unreachable' in cmd for cmd in commands)==count
        assert all(call.kwargs['pass_fds'] for call in run.call_args_list)
        for i in range(1,count):
            assert ['nsenter','--net=/proc/self/fd/200','--','ip','link','set',f'e{i}','netns',str(100+i)] in commands
        lan.close()
        assert close.call_count==count and lan.fds==[]
        assert all(p.terminate.called for p in holders)
        lan.close()  # Cleanup is idempotent.

lan=n.PrivateLAN(2);holders=[holder(100),holder(101)]
with patch.object(n.shutil,'which',return_value='/bin/tool'),\
     patch.object(n.subprocess,'Popen',side_effect=holders),\
     patch.object(n.select,'select',side_effect=lambda *a:([a[0][0]],[],[])),\
     patch.object(n.os,'open',side_effect=[200,201]),\
     patch.object(n.os,'fstat',side_effect=lambda fd:SimpleNamespace(st_dev=lan.host.st_dev,st_ino=lan.host.st_ino+fd)),\
     patch.object(n.os,'close') as close,\
     patch.object(n.subprocess,'run',side_effect=[Mock(returncode=0),subprocess.CalledProcessError(1,'ip')]):
    try:lan.start();raise AssertionError('failure swallowed')
    except subprocess.CalledProcessError:pass
    assert close.call_count==2 and all(p.terminate.called for p in holders)
    assert not lan.fds and not lan.holders
print('LAN privé : topologies 2–4 joueurs, refus de l’espace hôte, descripteurs épinglés et nettoyage après échec vérifiés.')
