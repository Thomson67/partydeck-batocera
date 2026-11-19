"""Experimental, session-owned LAN. All links live in private network namespaces.

No named namespaces, host interfaces, NAT, firewall or host routes are created.
Namespace FDs pin ownership; the setns helper refuses the host namespace.
"""
from pathlib import Path
import ctypes,os,select,shutil,subprocess,sys
from partydeck_i18n import tr


def enter(fd,host,command):
    stat=os.fstat(fd)
    if (stat.st_dev,stat.st_ino)==host:
        raise RuntimeError(tr('LAN privé : espace réseau hôte refusé.'))
    if not command:raise ValueError(tr('LAN privé : commande cible absente.'))
    libc=ctypes.CDLL(None,use_errno=True)
    libc.setns.argtypes=[ctypes.c_int,ctypes.c_int]
    libc.setns.restype=ctypes.c_int
    if libc.setns(fd,0x40000000)!=0:
        err=ctypes.get_errno();raise OSError(err,os.strerror(err))
    os.close(fd)
    os.execvp(command[0],command)


def enter_path(path,expected,host,command):
    # Gamescope can close inherited FDs when spawning its child. Open the
    # supervisor-owned namespace here and validate its identity before setns.
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
    stat=os.fstat(fd)
    if (stat.st_dev,stat.st_ino)!=expected:
        os.close(fd)
        raise RuntimeError(tr('LAN privé : espace réseau terminé.'))
    enter(fd,host,command)


class PrivateLAN:
    def __init__(self,count):
        if type(count) is not int or count not in (2,3,4):
            raise ValueError(tr('LAN privé : choisissez de 2 à 4 joueurs.'))
        self.count=count;self.holders=[];self.fds=[]
        self.host=os.stat('/proc/self/ns/net')

    def address(self,index):return f'192.168.247.{11+index}'

    def prefix(self,index):
        fd=self.fds[index];stat=os.fstat(fd)
        if (stat.st_dev,stat.st_ino)==(self.host.st_dev,self.host.st_ino):
            raise RuntimeError(tr('LAN privé : espace réseau hôte refusé.'))
        if self.holders[index].poll() is not None:
            raise RuntimeError(tr('LAN privé : espace réseau terminé.'))
        return [sys.executable,__file__,'_enter',str(fd),
                str(self.host.st_dev),str(self.host.st_ino),'--']

    def child_prefix(self,index):
        self.prefix(index)  # Recheck ownership and holder lifetime.
        stat=os.fstat(self.fds[index])
        return [sys.executable,__file__,'_enter-path',
                f'/proc/{self.holders[index].pid}/ns/net',
                str(stat.st_dev),str(stat.st_ino),
                str(self.host.st_dev),str(self.host.st_ino),'--']

    def command(self,index,args,**kwargs):
        return subprocess.run(self.prefix(index)+args,pass_fds=(self.fds[index],),
                              stdin=subprocess.DEVNULL,check=True,timeout=5,**kwargs)

    def start(self):
        for tool in ('ip',):
            if not shutil.which(tool):raise RuntimeError(tr('LAN privé : commande absente ({p0}).',p0=tool))
        try:
            for index in range(self.count):
                process=subprocess.Popen([sys.executable,__file__,'_hold'],stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True)
                self.holders.append(process)
                if not select.select([process.stdout],[],[],5)[0]:
                    raise RuntimeError(tr('LAN privé : création de l’espace réseau trop longue.'))
                line=process.stdout.readline().decode(errors='replace').strip()
                if line!='READY':raise RuntimeError(tr('LAN privé indisponible : {p0}',p0=line))
                process.stdout.close()
                self.fds.append(os.open(f'/proc/{process.pid}/ns/net',os.O_RDONLY|os.O_CLOEXEC))
                self.command(index,['ip','link','set','lo','up'])
            self.command(0,['ip','link','add','br0','type','bridge'])
            self.command(0,['ip','addr','add',self.address(0)+'/24','dev','br0'])
            self.command(0,['ip','link','set','br0','up'])
            for index in range(1,self.count):
                port,peer=f'p{index}',f'e{index}'
                # Both veth ends are born inside player 1's private namespace.
                self.command(0,['ip','link','add',port,'type','veth','peer','name',peer])
                self.command(0,['ip','link','set',peer,'netns',str(self.holders[index].pid)])
                self.command(0,['ip','link','set',port,'master','br0'])
                self.command(0,['ip','link','set',port,'up'])
                self.command(index,['ip','link','set',peer,'name','eth0'])
                self.command(index,['ip','addr','add',self.address(index)+'/24','dev','eth0'])
                self.command(index,['ip','link','set','eth0','up'])
            for index in range(self.count):
                interface='br0' if index==0 else 'eth0'
                self.command(index,['ip','route','add','255.255.255.255/32','dev',interface])
                self.command(index,['ip','route','add','unreachable','default'])
                print(tr('LAN privé J{p0} : {p1} ; Internet désactivé pour cette instance.',p0=index+1,p1=self.address(index)),flush=True)
            return self
        except BaseException:
            self.close();raise

    def close(self):
        for fd in self.fds:os.close(fd)
        self.fds=[]
        for process in reversed(self.holders):
            try:
                if process.stdin:process.stdin.close()
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=2)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                else:process.wait()
                if process.stdout:process.stdout.close()
            except OSError:pass
        self.holders=[]


def verify(count):
    lan=PrivateLAN(count);server=None
    try:
        lan.start()
        # Prove that two namespaces can own UDP 3658 concurrently and exchange
        # data, before loading any ROM, Wine prefix, graphics or mod.
        code=("import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
              "s.settimeout(10)\ns.bind(('0.0.0.0',3658))\nprint('READY',flush=True)\n"
              f"for _ in range({count-1}):\n data,peer=s.recvfrom(128)\n s.sendto(data,peer)\n")
        server=subprocess.Popen(lan.prefix(0)+[sys.executable,'-u','-c',code],
            pass_fds=(lan.fds[0],),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if not select.select([server.stdout],[],[],5)[0] or server.stdout.readline()!=b'READY\n':
            raise RuntimeError(tr('LAN privé : serveur de test UDP indisponible.'))
        for index in range(1,count):
            client=("import socket\ns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
                    "s.settimeout(3)\ns.bind(('0.0.0.0',3658))\n"
                    f"s.sendto(b'partydeck-udp',({lan.address(0)!r},3658))\n"
                    "assert s.recvfrom(128)[0]==b'partydeck-udp'\n")
            lan.command(index,[sys.executable,'-c',client])
        server.wait(timeout=3)
        if server.returncode:raise RuntimeError(tr('LAN privé : échec du test UDP.'))
        print(tr('LAN privé OK : port UDP 3658 distinct et échanges entre joueurs vérifiés.'),flush=True)
    finally:
        if server is not None:
            if server.poll() is None:server.terminate();server.wait(timeout=3)
            if server.stdout:server.stdout.close()
        lan.close()


if __name__=='__main__':
    try:
        if sys.argv[1:] == ['_hold']:
            libc=ctypes.CDLL(None,use_errno=True)
            if libc.unshare(0x40000000)!=0:
                err=ctypes.get_errno();raise OSError(err,os.strerror(err))
            print('READY',flush=True)
            sys.stdin.buffer.read()
        elif len(sys.argv)>=7 and sys.argv[1]=='_enter' and sys.argv[5]=='--':
            enter(int(sys.argv[2]),(int(sys.argv[3]),int(sys.argv[4])),sys.argv[6:])
        elif len(sys.argv)>=9 and sys.argv[1]=='_enter-path' and sys.argv[7]=='--':
            enter_path(sys.argv[2],(int(sys.argv[3]),int(sys.argv[4])),
                       (int(sys.argv[5]),int(sys.argv[6])),sys.argv[8:])
        elif sys.argv[1:2]==['verifier']:verify(int(sys.argv[2]) if len(sys.argv)>2 else 2)
        else:raise ValueError('Usage: partydeck_private_lan.py verifier [2|3|4]')
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print(tr('LAN privé : {p0}',p0=str(error)),file=sys.stderr);raise SystemExit(1)
