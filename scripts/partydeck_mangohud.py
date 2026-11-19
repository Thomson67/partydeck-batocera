"""Apply MangoHud only to final native Wine game commands, in private mounts."""
from pathlib import Path
import json,re,shlex,shutil,subprocess
from partydeck_i18n import tr

RUNTIME=Path('/userdata/system/ultimate-wine-toolbox/runtime/mangohud')
PROFILES={
    'default':'fps,cpu_stats,gpu_stats,frametime,no_display=0,position=top-left',
    'minimal':'fps_only=1,frametime=0,frame_timing=0,no_display=0,position=top-left',
    'detailed':'fps,cpu_stats,gpu_stats,cpu_temp,gpu_temp,ram,vram,frametime,frame_timing,no_display=0,position=top-left',
}


def selected_profile(rom):
    from partydeck_profiles import party_entry_name
    binary=shutil.which('batocera-settings-get')
    if not binary:return None
    name=party_entry_name(rom).replace('=','').replace('#','')
    for key in (f'windows-party["{name}"].mangohud_profile','windows-party.mangohud_profile'):
        result=subprocess.run([binary,key],capture_output=True,text=True,check=False)
        if result.returncode or not isinstance(result.stdout,str):continue
        value=result.stdout.strip()
        if value in ('','auto'):continue
        if value not in PROFILES:raise ValueError(tr('Profil MangoHud invalide.'))
        return value
    return None


def prepare_layers(player,runtime=RUNTIME):
    """Private implicit-layer manifests, with explicit 32/64-bit libraries."""
    from partydeck_profiles import atomic_write
    directory=player/'mangohud-layers'
    directory.mkdir(parents=True,exist_ok=True)
    count=0
    for bits,arch in (('64','x86_64'),('32','x86')):
        library=runtime/f'lib{bits}/mangohud/libMangoHud.so'
        manifest=directory/f'MangoHud.{arch}.json'
        if not library.is_file():
            manifest.unlink(missing_ok=True)
            continue
        layer=dict(name='VK_LAYER_MANGOHUD_overlay_'+arch,type='GLOBAL',
                   library_path=str(library),library_arch=bits,api_version='1.3.0',
                   implementation_version='1',description='Windows Party MangoHud',
                   functions=dict(vkNegotiateLoaderLayerInterfaceVersion='vkNegotiateLoaderLayerInterfaceVersion'),
                   enable_environment=dict(MANGOHUD='1'),disable_environment=dict(DISABLE_MANGOHUD='1'))
        atomic_write(manifest,json.dumps(dict(file_format_version='1.0.0',layer=layer)),0o644)
        count+=1
    return directory if count else None


def instrument(source,enabled,runtime=RUNTIME,profile='default',layers=None):
    pattern=re.compile(r'(?m)^(?P<indent>[ \t]*)WINE_ENV=\$\(getWine_var "\$\{(?:WINEPOINT|GAMENAME)\}" "ENV" ""\)[ \t]*$')
    if len(pattern.findall(source))<3:
        raise RuntimeError(tr('Lanceur Wine non reconnu : MangoHud non appliqué.'))
    # Append after user ENV so explicit Party choices win, without touching the
    # autorun, other game variables, Wine configuration commands or Gamescope.
    if profile not in PROFILES:raise ValueError(tr('Profil MangoHud invalide.'))
    payload='MANGOHUD=1' if enabled else 'MANGOHUD=0 DISABLE_MANGOHUD=1'
    if enabled is None:payload=''
    if enabled is not False:
        payload+=' MANGOHUD_CONFIG='+shlex.quote(PROFILES[profile])
    extra=''
    mounts=[]
    paths=[runtime/'lib64/mangohud',runtime/'lib32/mangohud']
    if enabled and all((p/'libMangoHud_shim.so').is_file() for p in paths):
        # Respect custom preloads/library paths already present in the game's
        # ENV. The installed UWT runtime provides an architecture-aware shim.
        library=':'.join(str(p) for p in paths)
        extra=("\nif [[ \" $WINE_ENV \" != *' LD_PRELOAD='* ]]; then WINE_ENV+=\" LD_PRELOAD=libMangoHud_shim.so\"; fi"
               +"\nif [[ \" $WINE_ENV \" != *' LD_LIBRARY_PATH='* ]]; then WINE_ENV+="
               +shlex.quote(" LD_LIBRARY_PATH="+shlex.quote(library)+':"${LD_LIBRARY_PATH:-}"')+'; fi')
        mounts.append(str(runtime))
    if layers is not None and enabled is not False:
        extra+='\nWINE_ENV+='+shlex.quote(' VK_ADD_IMPLICIT_LAYER_PATH='+shlex.quote(str(layers))+':"${VK_ADD_IMPLICIT_LAYER_PATH:-}"')
        mounts.extend([str(runtime),str(layers)])
    if mounts:
        extra+='\nWINE_ENV+='+shlex.quote(' UMU_BATOCERA_EXTRA_RO='+shlex.quote(':'.join(dict.fromkeys(mounts)))+':"${UMU_BATOCERA_EXTRA_RO:-}"')
    if enabled:
        # Do not define the disable variable at all when enabled. Clear even a
        # disable assignment embedded in the original game ENV, at exec time.
        payload+=' env -u DISABLE_MANGOHUD'
    def replace(match):
        return match[0]+extra+'\nWINE_ENV+='+shlex.quote(' '+payload)
    return pattern.sub(replace,source)


def install_hook(rom,player):
    from partydeck_profiles import selected_party_switch,atomic_write
    selected=selected_party_switch(rom,'mangohud')
    profile=selected_profile(rom)
    if selected is None and profile is None:return
    binary=shutil.which('batocera-wine')
    if not binary:raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve()
    replacement=player/'batocera-wine-mangohud'
    enabled=None if selected is None else selected=='1'
    layers=prepare_layers(player) if enabled is not False else None
    atomic_write(replacement,instrument(binary.read_text(),enabled,profile=profile or 'default',layers=layers),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    print(tr('Windows Party : MangoHud={p0}.',p0=selected),flush=True)
    print(tr('MangoHud : profil {p0} ; couches privées {p1}.',p0=profile or 'default',p1=layers or '-'),flush=True)
