"""Global display/GPU preferences and active-output geometry discovery."""
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from partydeck_i18n import tr

DEFAULTS = dict(version=1, output='auto', gpu='auto')


def settings(base):
    path=Path(base)/'desktop.json'
    if path.is_symlink():raise ValueError(tr('Réglages écran/GPU invalides.'))
    return validate(json.loads(path.read_text())) if path.exists() else dict(DEFAULTS)


def validate(data):
    if not isinstance(data,dict):raise ValueError(tr('Réglages écran/GPU invalides.'))
    result={key:data.get(key,value) for key,value in DEFAULTS.items()}
    if (type(result['version']) is not int or result['version']!=1 or result['gpu'] not in ('auto','system','nvidia')
            or not isinstance(result['output'],str) or not result['output']
            or len(result['output'])>128 or any(c in result['output'] for c in '\0\r\n')):
        raise ValueError(tr('Réglages écran/GPU invalides.'))
    return result


def save_settings(base,data):
    from partydeck_profiles import atomic_write
    atomic_write(Path(base)/'desktop.json',json.dumps(validate(data),ensure_ascii=False,indent=2)+'\n')


@dataclass(frozen=True)
class Output:
    name: str
    rectangle: tuple | None
    description: str = ''
    primary: bool = False


def parse_wayland(text):
    records=[];item=None
    for line in text.splitlines():
        match=re.match(r'^(\S+)\s+"(.*)"$',line)
        if match:
            item=dict(name=match[1],description=match[2],enabled=False,scale=1.0,transform='normal')
            records.append(item)
        elif item is not None:
            value=line.strip()
            if value.startswith('Enabled:'):item['enabled']=value.split(':',1)[1].strip()=='yes'
            elif value.startswith('Position:'):
                match=re.fullmatch(r'Position:\s*(-?\d+),\s*(-?\d+)',value)
                if match:item['position']=tuple(map(int,match.groups()))
            elif value.startswith('Scale:'):
                try:item['scale']=float(value.split(':',1)[1])
                except ValueError:item['scale']=0
            elif value.startswith('Transform:'):item['transform']=value.split(':',1)[1].strip()
            elif 'current' in value:
                match=re.match(r'(\d+)x(\d+) px,',value)
                if match:item['mode']=tuple(map(int,match.groups()))
    result=[]
    for item in records:
        rectangle=None;scale=item['scale']
        if (item['enabled'] and 'position' in item and 'mode' in item
                and math.isfinite(scale) and scale>0):
            width,height=item['mode']
            if item['transform'] in ('90','270','flipped-90','flipped-270'):
                width,height=height,width
            rectangle=(*item['position'],max(1,round(width/scale)),max(1,round(height/scale)))
        result.append(Output(item['name'],rectangle,item['description']))
    return result


def parse_xrandr(text):
    pattern=r'^\s*\d+:\s+(\S+)\s+(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)\s+(\S+)'
    return [Output(name,(int(x),int(y),int(width),int(height)),primary='*' in flags)
            for flags,width,height,x,y,name in re.findall(pattern,text,re.M)]


def align_x11(outputs,monitors):
    # Window moves use the host Xwayland coordinate system. Prefer its bounds
    # for connectors that Wayland confirms are active (never revive a stale,
    # disabled RandR output). Preserve logical Wayland bounds if names differ.
    by_name={output.name:output for output in monitors}
    return [Output(o.name,by_name[o.name].rectangle,o.description,by_name[o.name].primary)
            if o.rectangle is not None and o.name in by_name else o for o in outputs]


def discover_outputs():
    commands=[]
    if os.environ.get('WAYLAND_DISPLAY') and shutil.which('wlr-randr'):
        commands.append((['wlr-randr'],parse_wayland))
    if shutil.which('xrandr'):commands.append((['xrandr','--listactivemonitors'],parse_xrandr))
    for command,parse in commands:
        try:
            done=subprocess.run(command,capture_output=True,text=True,timeout=3)
            if done.returncode==0:
                outputs=parse(done.stdout)
                if outputs:
                    if command==['wlr-randr'] and shutil.which('xrandr'):
                        try:
                            randr=subprocess.run(['xrandr','--listactivemonitors'],capture_output=True,text=True,timeout=3)
                            if randr.returncode==0:outputs=align_x11(outputs,parse_xrandr(randr.stdout))
                        except (OSError,subprocess.SubprocessError):pass
                    return outputs
        except (OSError,subprocess.SubprocessError):pass
    # Retain the single-screen fallback on older Xorg installations.
    try:
        width,height=map(int,subprocess.check_output(['xdotool','getdisplaygeometry'],text=True,timeout=3).split())
        if width>0 and height>0:return [Output('default',(0,0,width,height))]
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return []


def choose_output(outputs,name='auto'):
    active=[o for o in outputs if o.rectangle is not None]
    chosen=next((o for o in active if o.name==name),None)
    if chosen:return chosen
    if not active:raise RuntimeError(tr('Aucun écran actif détecté.'))
    return min(active,key=lambda o:(not o.primary,o.rectangle[0],o.rectangle[1],o.name))


def output_choices(outputs,saved='auto'):
    values=['auto',*[o.name for o in outputs]]
    if saved not in values:values.append(saved)
    return values


def output_label(outputs,name):
    if name=='auto':return tr('Automatique · écran actif')
    output=next((o for o in outputs if o.name==name),None)
    if output is None or output.rectangle is None:
        return tr('{p0} · indisponible (repli automatique)',p0=name)
    x,y,width,height=output.rectangle
    return f'{name} · {width}×{height} · {x},{y}'
