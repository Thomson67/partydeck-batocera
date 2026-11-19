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

# The entry helper rejects the host FD itself, even if invoked directly.
fd=os.open('/proc/self/ns/net',os.O_RDONLY)
try:
    result=subprocess.run([sys.executable,n.__file__,'_enter',str(fd),str(lan.host.st_dev),str(lan.host.st_ino),'--','/bin/true'],
                          pass_fds=(fd,),capture_output=True,text=True)
    assert result.returncode==1 and ('host network' in result.stderr or 'réseau hôte' in result.stderr)
finally:os.close(fd)

# The syscall helper enters the pinned FD, closes it, and execs argv literally.
with patch.object(n.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=2)),\
     patch.object(n.ctypes,'CDLL') as library,patch.object(n.os,'close') as close,\
     patch.object(n.os,'execvp') as execute:
    library.return_value.setns.return_value=0
    n.enter(44,(1,3),['/bin/echo','literal $(not a shell)'])
    library.return_value.setns.assert_called_once_with(44,0x40000000)
    close.assert_called_once_with(44)
    execute.assert_called_once_with('/bin/echo',['/bin/echo','literal $(not a shell)'])
with patch.object(n.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=2)),\
     patch.object(n.ctypes,'CDLL') as library,patch.object(n.ctypes,'get_errno',return_value=1),\
     patch.object(n.os,'execvp') as execute:
    library.return_value.setns.return_value=-1
    try:n.enter(44,(1,3),['/bin/true']);raise AssertionError('failed setns accepted')
    except OSError:pass
    execute.assert_not_called()

# Opening by path never trusts a recycled holder PID or a host namespace.
with patch.object(n.os,'open',return_value=44), \
     patch.object(n.os,'fstat',return_value=SimpleNamespace(st_dev=1,st_ino=2)), \
     patch.object(n.os,'close') as close,patch.object(n,'enter') as enter:
    n.enter_path('/proc/123/ns/net',(1,2),(1,3),['/bin/true'])
    enter.assert_called_once_with(44,(1,3),['/bin/true'])
    close.assert_not_called()
    enter.reset_mock()
    try:n.enter_path('/proc/123/ns/net',(1,4),(1,3),['/bin/true']);raise AssertionError('recycled PID accepted')
    except RuntimeError:pass
    close.assert_called_once_with(44)
    enter.assert_not_called()
fd=os.open('/proc/self/ns/net',os.O_RDONLY)
try:
    stat=os.fstat(fd)
    result=subprocess.run([sys.executable,n.__file__,'_enter-path',f'/proc/{os.getpid()}/ns/net',
                          str(stat.st_dev),str(stat.st_ino),str(stat.st_dev),str(stat.st_ino),'--','/bin/true'],
                          capture_output=True,text=True)
    assert result.returncode==1 and ('host network' in result.stderr or 'réseau hôte' in result.stderr)
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
        assert all(cmd[:3]==[sys.executable,n.__file__,'_enter'] and cmd[6]=='--' for cmd in commands)
        assert sum('veth' in cmd for cmd in commands)==count-1
        assert not any('default' in cmd for cmd in commands)  # ENETUNREACH, not EHOSTUNREACH.
        assert all(call.kwargs['pass_fds'] for call in run.call_args_list)
        for i in range(1,count):
            assert [sys.executable,n.__file__,'_enter','200',str(lan.host.st_dev),str(lan.host.st_ino),'--',
                    'ip','link','set',f'e{i}','netns',str(100+i)] in commands
        prefix=lan.child_prefix(count-1)
        assert prefix[2]=='_enter-path' and prefix[3]==f'/proc/{100+count-1}/ns/net'
        assert prefix[-1]=='--' and prefix[4:6]==[str(lan.host.st_dev),str(lan.host.st_ino+200+count-1)]
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

# UMU 1.4.4 handles ENETUNREACH as offline, but re-raises EHOSTUNREACH.
# The verifier must detect this regression without ever sending UDP payloads.
with patch.object(n.socket,'socket') as factory:
    probe=factory.return_value.__enter__.return_value
    probe.connect.side_effect=OSError(n.errno.ENETUNREACH,'Network unreachable')
    n.verify_offline()
    probe.connect.assert_called_once_with(('1.1.1.1',53))
    for error in (OSError(n.errno.EHOSTUNREACH,'No route to host'),None):
        probe.connect.side_effect=error
        try:n.verify_offline();raise AssertionError('incorrect offline state accepted')
        except RuntimeError:pass
    probe.send.assert_not_called();probe.sendto.assert_not_called()
print('UMU : sonde hors ligne ENETUNREACH, refus de EHOSTUNREACH et absence de route Internet vérifiés.')
