"""Apply MangoHud only to final native Wine game commands, in private mounts."""
from pathlib import Path
import re,shlex,shutil,subprocess
from partydeck_i18n import tr

RUNTIME=Path('/userdata/system/ultimate-wine-toolbox/runtime/mangohud')


def instrument(source,enabled,runtime=RUNTIME):
    pattern=re.compile(r'(?m)^(?P<indent>[ \t]*)WINE_ENV=\$\(getWine_var "\$\{(?:WINEPOINT|GAMENAME)\}" "ENV" ""\)[ \t]*$')
    if len(pattern.findall(source))<3:
        raise RuntimeError(tr('Lanceur Wine non reconnu : MangoHud non appliqué.'))
    # Append after user ENV so explicit Party choices win, without touching the
    # autorun, other game variables, Wine configuration commands or Gamescope.
    payload='MANGOHUD=1 DISABLE_MANGOHUD=0' if enabled else 'MANGOHUD=0 DISABLE_MANGOHUD=1'
    extra=''
    paths=[runtime/'lib64/mangohud',runtime/'lib32/mangohud']
    if enabled and all((p/'libMangoHud_shim.so').is_file() for p in paths):
        # Respect custom preloads/library paths already present in the game's
        # ENV. The installed UWT runtime provides an architecture-aware shim.
        library=':'.join(str(p) for p in paths)
        extra=("\nif [[ \" $WINE_ENV \" != *' LD_PRELOAD='* ]]; then WINE_ENV+=\" LD_PRELOAD=libMangoHud_shim.so\"; fi"
               +"\nif [[ \" $WINE_ENV \" != *' LD_LIBRARY_PATH='* ]]; then WINE_ENV+="
               +shlex.quote(" LD_LIBRARY_PATH="+shlex.quote(library)+':"${LD_LIBRARY_PATH:-}"')+'; fi'
               +'\nWINE_ENV+='+shlex.quote(' UMU_BATOCERA_EXTRA_RO='+shlex.quote(str(runtime))+':"${UMU_BATOCERA_EXTRA_RO:-}"'))
    def replace(match):
        return match[0]+extra+'\nWINE_ENV+='+shlex.quote(' '+payload)
    return pattern.sub(replace,source)


def install_hook(rom,player):
    from partydeck_profiles import selected_party_switch,atomic_write
    selected=selected_party_switch(rom,'mangohud')
    if selected is None:return
    binary=shutil.which('batocera-wine')
    if not binary:raise RuntimeError(tr('batocera-wine introuvable.'))
    binary=Path(binary).resolve()
    replacement=player/'batocera-wine-mangohud'
    atomic_write(replacement,instrument(binary.read_text(),selected=='1'),0o755)
    subprocess.run(['bash','-n',str(replacement)],check=True)
    subprocess.run(['mount','--bind',str(replacement),str(binary)],check=True)
    print(tr('Windows Party : MangoHud={p0}.',p0=selected),flush=True)
