#!/usr/bin/env python3
"""Launch concurrent native Batocera Wine sessions in nested Gamescope windows."""
import argparse
import ctypes as C
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import unquote_to_bytes

from partydeck_storage import session as storage_session, settings as storage_settings
from partydeck_i18n import tr


ROM_TYPES = {".wine", ".pc", ".wsquashfs"}
PARTY_ROMS = Path("/userdata/roms/windows-party")
PARTY_SAVES = Path("/userdata/saves/windows-party")
GAMEPADS = "ID_INPUT_JOYSTICK"
KEYBOARDS = "ID_INPUT_KEYBOARD"
MICE = "ID_INPUT_MOUSE"
WRITABLE = {
    "/userdata/system/wine-bottles/windows": "bottles",
    "/userdata/saves/windows": "saves",
    "/var/run/wine": "wine-run",
    "/userdata/system/cache": "cache",
    "/userdata/system/logs": "logs",
    "/var/cache/ldconfig": "ldconfig-cache",
}
UMU_HOME = Path("/userdata/system/umu")
UMU_LOGS = Path("/userdata/system/logs/umu-runner")
UMU_SESSION_STATE = Path("/run/umu-batocera")
UMU_PRIVATE = ("compatdata", "materialized-prefixes", "merged-prefixes",
               "gameviews", "exports")
SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
MOUNT_CAPS = ["--cap-add", "CAP_SYS_ADMIN", "--cap-add", "CAP_MKNOD"]
# AppRun and sharun set these for the bundled compositor. The native Wine
# runner must resolve its utilities and graphics libraries as on Batocera.
NATIVE_GRAPHICS_ENV = (
    "PATH", "LD_LIBRARY_PATH", "LD_PRELOAD", "XDG_CONFIG_DIRS", "XDG_DATA_DIRS",
    "LIBGL_DRIVERS_PATH", "LIBVA_DRIVERS_PATH", "GBM_BACKENDS_PATH", "DRIRC_CONFIGDIR",
    "__EGL_VENDOR_LIBRARY_DIRS", "__EGL_VENDOR_LIBRARY_FILENAMES", "__GLX_VENDOR_LIBRARY_NAME",
    "VK_DRIVER_FILES", "VK_ICD_FILENAMES", "VK_LAYER_PATH", "VK_ADD_LAYER_PATH",
    "MESA_LOADER_DRIVER_OVERRIDE", "LIBGL_KOPPER_DRI2", "SDL_VIDEO_X11_WMCLASS",
    "__NV_PRIME_RENDER_OFFLOAD", "__VK_LAYER_NV_optimus", "VK_LOADER_DRIVERS_SELECT",
)


def hybrid_nvidia(devices=Path('/sys/bus/pci/devices')):
    """Require a bound proprietary NVIDIA display driver and another GPU."""
    nvidia,other=False,False
    for device in devices.glob('*'):
        try:
            if int((device/'class').read_text().strip(),16)>>16 != 3:continue
            vendor=int((device/'vendor').read_text().strip(),16)
            nvidia |= vendor==0x10de and (device/'driver').resolve().name=='nvidia'
            other |= vendor!=0x10de
        except (OSError,ValueError):continue
    return nvidia and other


def graphics_environment(environment,mode='auto'):
    # Honor explicit Vulkan/PRIME choices. A GLX vendor alone does not select
    # Gamescope's Vulkan GPU (as observed on Intel + NVIDIA Batocera Xorg).
    selectors=('VK_DRIVER_FILES','VK_ICD_FILENAMES','VK_LOADER_DRIVERS_SELECT',
               'DRI_PRIME','MESA_VK_DEVICE_SELECT','__NV_PRIME_RENDER_OFFLOAD','__VK_LAYER_NV_optimus')
    if mode=='system':return {}
    if mode=='auto' and (any(environment.get(key) for key in selectors) or not hybrid_nvidia()):return {}
    return dict(__NV_PRIME_RENDER_OFFLOAD='1',__VK_LAYER_NV_optimus='NVIDIA_only',
                __GLX_VENDOR_LIBRARY_NAME='nvidia',VK_LOADER_DRIVERS_SELECT='*nvidia*')


@dataclass(frozen=True)
class Device:
    node: Path
    category: str
    identity: str
    sysfs: Path

    @property
    def joystick_nodes(self):
        return [Path("/dev/input") / p.name for p in self.sysfs.glob("js*")
                if (Path("/dev/input") / p.name).exists()]


def read_input_devices(dev=Path("/dev/input"), sys_input=Path("/sys/class/input"),
                       database=Path("/run/udev/data")):
    stable = {}
    for directory in (dev / "by-path", dev / "by-id"):
        for link in sorted(directory.glob("*-event-*")):
            stable[link.resolve()] = str(link)
    devices = []
    for node in dev.glob("event[0-9]*"):
        n = node.stat().st_rdev
        path = database / f"c{os.major(n)}:{os.minor(n)}"
        try:
            tags = set(path.read_text().splitlines())
        except FileNotFoundError:
            continue
        category = next((kind for kind in (GAMEPADS, KEYBOARDS, MICE)
                         if f"E:{kind}=1" in tags), None)
        if category:
            sysfs = (sys_input / node.name / "device").resolve()
            devices.append(Device(node, category, stable.get(node, ""), sysfs))
    return sorted(devices, key=lambda dev: (not dev.identity, dev.identity,
                                            int(dev.node.name[5:])))


def assign_players(devices, count, input_mode, allow_keyboard_player=True):
    pads = [d for d in devices if d.category == GAMEPADS]
    if not allow_keyboard_player:
        wanted = min(4, len(pads)) if count == "auto" else int(count)
        if wanted < 1 or len(pads) < wanted:
            raise ValueError("Manettes insuffisantes : le clavier/souris est réservé aux menus pour ce jeu.")
        return [[pad] for pad in pads[:wanted]]
    keyboard_mouse = [next((d for d in devices if d.category == kind), None)
                      for kind in (KEYBOARDS, MICE)]
    available = all(keyboard_mouse)
    if count == "auto":
        add_keyboard = input_mode != "auto" or (available and len(pads) == 1)
        count = max(1, min(4, len(pads) + add_keyboard))
        if input_mode == "clavier-j2":
            count = max(2, count)
    count = int(count)
    use_keyboard = input_mode != "auto" or len(pads) < count
    keyboard_index = 0 if input_mode == "clavier-j1" else (
        1 if input_mode == "clavier-j2" else count - 1)
    if use_keyboard and (not available or keyboard_index >= count or len(pads) < count - 1):
        raise ValueError("Périphériques insuffisants pour la configuration demandée.")
    return [keyboard_mouse if use_keyboard and i == keyboard_index else [pads.pop(0)]
            for i in range(count)]


def layout(monitor, count, split):
    x, y, width, height = monitor
    columns = 2 if count > 2 or (count == 2 and split == "vertical") else 1
    rows = 2 if count > 2 or (count == 2 and split == "horizontal") else 1
    rectangles = []
    for index in range(count):
        row, column = divmod(index, columns)
        left, right = width * column // columns, width * (column + 1) // columns
        top, bottom = height * row // rows, height * (row + 1) // rows
        rectangles.append((x + left, y + top, right - left, bottom - top))
    return rectangles


def primary_monitor():
    if shutil.which("xrandr"):
        result = subprocess.run(["xrandr", "--listactivemonitors"], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        pattern = r"^\s*\d+:\s+(\S+)\s+(\d+)/\d+x(\d+)/\d+([+-]\d+)([+-]\d+)"
        monitors = re.findall(pattern, result.stdout, re.M)
        if monitors:
            _, width, height, x, y = next((m for m in monitors if "*" in m[0]), monitors[0])
            return tuple(map(int, (x, y, width, height)))
    width, height = map(int, subprocess.check_output(["xdotool", "getdisplaygeometry"]).split())
    return 0, 0, width, height


class ClientMessage(C.Structure):
    _fields_ = [
        ("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
        ("display", C.c_void_p), ("window", C.c_ulong),
        ("message_type", C.c_ulong), ("format", C.c_int), ("data", C.c_long * 5),
    ]


class XEvent(C.Union):
    _fields_ = [("message", ClientMessage), ("pad", C.c_long * 24)]


def remove_fullscreen(window):
    x11 = C.CDLL("libX11.so.6")
    x11.XOpenDisplay.argtypes = [C.c_char_p]
    x11.XOpenDisplay.restype = C.c_void_p
    x11.XDefaultRootWindow.argtypes = [C.c_void_p]
    x11.XDefaultRootWindow.restype = C.c_ulong
    x11.XInternAtom.argtypes = [C.c_void_p, C.c_char_p, C.c_int]
    x11.XInternAtom.restype = C.c_ulong
    x11.XSendEvent.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(XEvent)]
    x11.XCloseDisplay.argtypes = [C.c_void_p]
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("Impossible d’ouvrir l’affichage X11.")
    try:
        root = x11.XDefaultRootWindow(display)
        state, full, vertical, horizontal = [
            x11.XInternAtom(display, name, 0) for name in (
                b"_NET_WM_STATE", b"_NET_WM_STATE_FULLSCREEN",
                b"_NET_WM_STATE_MAXIMIZED_VERT", b"_NET_WM_STATE_MAXIMIZED_HORZ",
            )
        ]
        for first, second in ((full, 0), (vertical, horizontal)):
            event = XEvent()
            event.message = ClientMessage(33, 0, 1, display, int(window), state, 32,
                                          (C.c_long * 5)(0, first, second, 2, 0))
            x11.XSendEvent(display, root, 0, (1 << 19) | (1 << 20), C.byref(event))
    finally:
        x11.XCloseDisplay(display)


def top_window(window_class):
    result = subprocess.run(["xdotool", "search", "--onlyvisible", "--class",
                             f"^{window_class}$"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    ids = result.stdout.split()
    return ids[0] if result.returncode == 0 and len(ids) == 1 else None


def place_window(window, rectangle):
    remove_fullscreen(window)
    time.sleep(0.25)
    x, y, width, height = map(str, rectangle)
    subprocess.run(["xdotool", "windowsize", window, width, height,
                    "windowmove", window, x, y], check=True)
    time.sleep(0.15)
    geometry = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", window],
                                       text=True)
    values = dict(line.partition("=")[::2] for line in geometry.splitlines())
    return tuple(int(values[name]) for name in ("X", "Y", "WIDTH", "HEIGHT")) == rectangle


def focus_window(window):
    # EWMH activation is unreliable on some Batocera Xorg sessions. Use the
    # map/raise/focus sequence verified there, targeting only our own window.
    try:
        subprocess.run(['xdotool','windowmap',window,'windowraise',window,
                        'windowfocus',window],check=False,timeout=3,
                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except (OSError,subprocess.TimeoutExpired):pass


def rom_path(value, argument_parser):
    try:
        original = Path(value).absolute()
        target = original.resolve(strict=True)
        suffix = original.suffix.lower()
        if suffix not in ROM_TYPES:
            raise ValueError("Formats acceptés : .wine, .pc, .wsquashfs")
        if suffix == ".wsquashfs" and not target.is_file():
            raise ValueError("Une archive .wsquashfs doit être un fichier.")
        if suffix != ".wsquashfs" and not target.is_dir():
            raise ValueError("Un jeu .wine ou .pc doit être un répertoire.")
        if any(token in str(target) for token in (",", ":", "\\", "\n", "\r")):
            raise ValueError("Le chemin réel contient un caractère incompatible avec OverlayFS.")
        return original, target
    except (OSError, ValueError) as error:
        argument_parser.error(str(error))


def install_system(config_dir=Path("/userdata/system/configs/emulationstation"),
                   stock_config=Path("/usr/share/emulationstation/es_systems.cfg")):
    stock = ET.parse(stock_config).getroot()
    ports = next((s for s in stock.findall("system") if s.findtext("name") == "ports"), None)
    if ports is None or not ports.findtext("command"):
        raise ValueError("Commande Ports absente de la configuration Batocera.")
    command = ports.findtext("command").replace("%SYSTEM%", "ports")
    root = ET.Element("systemList")
    root.append(ET.Comment(" Système géré par PartyDeck Batocera "))
    system = ET.SubElement(root, "system")
    for key, value in (
        ("name", "windows-party"), ("fullname", "Windows Party"),
        ("manufacturer", "PartyDeck"), ("hardware", "computer"),
        ("path", str(PARTY_ROMS)), ("extension", ".sh"),
        ("command", command), ("platform", "windows"), ("theme", "windows"),
    ):
        ET.SubElement(system, key).text = value
    emulators = ports.find("emulators")
    if emulators is not None:
        system.append(ET.fromstring(ET.tostring(emulators)))
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "es_systems_windows-party.cfg"
    if path.is_symlink() or (path.exists() and "Système géré par PartyDeck Batocera" not in path.read_text()):
        raise ValueError(f"Une configuration utilisateur existe déjà : {path}")
    ET.indent(root, space="  ")
    with tempfile.NamedTemporaryFile(dir=config_dir, prefix=".partydeck-system-", delete=False) as staged:
        temporary = Path(staged.name)
        try:
            ET.ElementTree(root).write(staged, encoding="utf-8", xml_declaration=True)
            staged.flush()
            temporary.chmod(0o644)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    from partydeck_profiles import install_runner_editor
    install_runner_editor(config_dir)
    PARTY_ROMS.mkdir(parents=True, exist_ok=True)
    PARTY_SAVES.mkdir(parents=True, exist_ok=True)
    print(f"Système Windows Party installé : {path}")


def write_port(port_dir, launcher, original, count, split, input_mode, mode="coop", profile=False):
    digest = hashlib.sha256(os.fsencode(original)).hexdigest()[:10]
    prefix = "" if mode == "party" else "PartyDeck - "
    port = port_dir / f"{prefix}{original.stem[:90]} [{digest}].sh"
    marker = "# Entrée gérée par PartyDeck Wine"
    port_dir.mkdir(parents=True, exist_ok=True)
    if port.is_symlink() or (port.exists() and marker not in port.read_text().splitlines()[:2]):
        raise ValueError(f"Une entrée utilisateur existe déjà : {port}")
    with tempfile.NamedTemporaryFile(mode="w", prefix=".partydeck-", dir=port_dir,
                                     delete=False) as script:
        staged = Path(script.name)
        try:
            script.write(f"#!/bin/bash\n{marker}\nexec ")
            command = ([str(launcher), "profil", str(original)] if profile else
                       [str(launcher), mode, str(original), count, split, input_mode])
            script.write(shlex.join(command))
            script.write("\n")
            script.flush()
            staged.chmod(0o755)
            staged.replace(port)
        finally:
            staged.unlink(missing_ok=True)
    if mode=="party":
        from partydeck_profiles import inherit_scrapes
        inherit_scrapes([(original,port)],port_dir)
    return port


def player_paths(player, saves=None):
    paths = dict(WRITABLE)
    if UMU_HOME.is_dir():
        paths[str(UMU_LOGS)] = "umu-logs"
    for destination, relative in paths.items():
        Path(destination).mkdir(parents=True, exist_ok=True)
        if saves is not None and relative in {"saves", "bottles"}:
            source = saves / ("windows" if relative == "saves" else "prefixes")
        else:
            source = player / relative
        source.mkdir(parents=True, exist_ok=True)
        yield "--bind", str(source), destination


def bubblewrap_command(app):
    # The AppImage's bin/bwrap wrapper breaks --cap-add argument parsing.
    # Invoke its packaged binary with its own loader, including on Batocera.
    library = app / "lib"
    return [str(library / "ld-linux-x86-64.so.2"), "--library-path",
            str(library), str(app / "shared/bin/bwrap")]


def dbus_socket_mounts(address):
    # Pressure Vessel needs the filesystem socket named by the session address.
    # Abstract addresses and filesystem sockets outside /tmp are already visible.
    for value in dict.fromkeys(re.findall(r"(?:^|;)unix:(?:[^;,]+,)*path=([^;,]+)", address)):
        path = Path(os.path.normpath(os.fsdecode(unquote_to_bytes(value))))
        if path.is_relative_to("/tmp") and path.is_socket():
            yield "--ro-bind", str(path), str(path)


def sandbox_arguments(player, devices, hidraw=Path("/sys/class/hidraw"), saves=None):
    args = ["--die-with-parent", "--unshare-pid", "--ro-bind", "/", "/",
            "--proc", "/proc", "--dev-bind", "/dev", "/dev",
            *MOUNT_CAPS,
            "--tmpfs", "/tmp", "--tmpfs", "/dev/input",
            # The Batocera UMU runner derives its runtime directory from its own HOME.
            "--unsetenv", "XDG_DATA_HOME",
            "--setenv", "ENABLE_GAMESCOPE_WSI", "0",
            "--setenv", "PARTYDECK_PRIVATE_PLAYER", str(player),
            "--bind", str(player), str(player)]
    if saves is not None:
        saves.mkdir(parents=True, exist_ok=True)
        args.extend(["--bind", str(saves), str(saves)])
    for key in NATIVE_GRAPHICS_ENV:
        if key in os.environ:
            args.extend(["--setenv", key, os.environ[key]])
        else:
            args.extend(["--unsetenv", key])
    for item in dbus_socket_mounts(os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")):
        args.extend(item)
    if UMU_HOME.is_dir():
        # Session filenames include a PID, which can repeat across players'
        # PID namespaces. Keep state writable and private to each launch.
        UMU_SESSION_STATE.mkdir(parents=True, exist_ok=True)
        args.extend(["--tmpfs", str(UMU_SESSION_STATE)])
        proton_logs = player / "proton-logs"
        proton_logs.mkdir(exist_ok=True)
        shared = os.environ.get("PRESSURE_VESSEL_FILESYSTEMS_RW", "")
        shared = f"{shared}:{proton_logs}" if shared else str(proton_logs)
        args.extend(["--setenv", "PRESSURE_VESSEL_FILESYSTEMS_RW", shared,
                     "--setenv", "PROTON_LOG", os.environ.get("PROTON_LOG", "1" if storage_settings(player.parents[2])['diagnostic'] else "0"),
                     "--setenv", "PROTON_LOG_DIR", str(proton_logs)])
    for item in player_paths(player, saves):
        args.extend(item)
    for device in devices:
        for node in [device.node, *device.joystick_nodes]:
            args.extend(["--dev-bind", str(node), str(node)])
    pad_paths = [device.sysfs for device in devices if device.category == GAMEPADS]
    for raw in hidraw.glob("hidraw[0-9]*"):
        node = Path("/dev") / raw.name
        parent = (raw / "device").resolve()
        if node.exists() and not any(dev.is_relative_to(parent) for dev in pad_paths):
            args.extend(["--ro-bind", "/dev/null", str(node)])
    return args


def enter_sandbox(outer_display, command):
    # The Gamescope child is the first place where DISPLAY names this player's
    # Xwayland. Pass its socket through the private /tmp for Pressure Vessel.
    display = os.environ.get("DISPLAY", "")
    nested = re.fullmatch(r":([0-9]+)(?:\.[0-9]+)?", display)
    if not nested or display.split(".")[0] == outer_display.split(".")[0]:
        raise RuntimeError(f"Affichage Xwayland du joueur indisponible ({display!r}).")
    socket = Path("/tmp/.X11-unix") / f"X{nested[1]}"
    mounts = []
    if socket.is_socket():
        mounts.extend(["--ro-bind", str(socket), str(socket)])
    authority = os.environ.get("XAUTHORITY")
    if authority:
        path = Path(authority).absolute()
        if path.is_relative_to("/tmp") and path.is_file():
            mounts.extend(["--ro-bind", str(path), str(path)])
    print(f"Wine DISPLAY={display} | socket X11 : "
          f"{socket if socket.is_socket() else 'abstrait uniquement'}", flush=True)
    end = command.index("--")
    command[end:end] = mounts
    os.execv(command[0], command)


def mount_overlay(target, area):
    upper, work, view = (area / name for name in ("upper", "work", "view"))
    for path in (upper, work, view):
        path.mkdir(parents=True, exist_ok=True)
    options = f"lowerdir={target},upperdir={upper},workdir={work},redirect_dir=on"
    subprocess.run(["mount", "-t", "overlay", "-o", options, "overlay", str(view)], check=True)
    subprocess.run(["mount", "--bind", str(view), str(target)], check=True)


def run_wine(original, target, player, saves=None):
    # Gamescope's SDL backend can stay alive after its primary Wine child exits.
    # Report native completion independently of the compositor's lifetime/code.
    status = 1
    try:
        status = _run_wine(original,target,player,saves)
        return status
    finally:
        state = os.environ.get('PARTYDECK_EXIT_STATE')
        if state:
            from partydeck_profiles import atomic_write
            import json
            path = Path(state)
            if path.parent.resolve() != player.resolve() or not re.fullmatch(r'session-[0-9a-f]{32}\.json',path.name):
                raise ValueError(tr('État de fin Wine hors du dossier privé du joueur.'))
            atomic_write(path,json.dumps(dict(version=1,wine_exit=status)))


def _run_wine(original, target, player, saves=None):
    goldberg_result=None
    nfsmw_result=None
    if original.suffix.lower() != ".wsquashfs":
        mount_overlay(target, (saves if saves is not None else player) / "content")
    if UMU_HOME.is_dir():
        mount_overlay(UMU_HOME, player / "umu")
        for name in UMU_PRIVATE:
            private = player / "umu-private" / name
            private.mkdir(parents=True, exist_ok=True)
            destination = UMU_HOME / name
            destination.mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", "--bind", str(private), str(destination)], check=True)
    if saves is not None:
        from partydeck_profiles import install_party_runner_hook
        install_party_runner_hook(original,player)
        from partydeck_anchor import install_hook
        install_hook(Path(__file__).resolve().parent, original, player)
        from partydeck_borderlands2 import install_hook as install_bl2
        install_bl2(Path(__file__).resolve().parent, original, player)
        from partydeck_sm64coopdx import install_hook as install_sm64
        install_sm64(Path(__file__).resolve().parent, original, player)
        from partydeck_l4d2 import install_hook as install_l4d2, finish_launch as finish_l4d2
        goldberg_result=install_l4d2(Path(__file__).resolve().parent, original, player)
        from partydeck_nfsmw import install_hook as install_mw, finish_launch as finish_mw
        nfsmw_result=install_mw(Path(__file__).resolve().parent,original,player)
    # Keep the original ROM name for Batocera's per-game runner/settings lookup.
    try:
        status = subprocess.run(["batocera-wine", "windows", "play", str(original)]).returncode
        if goldberg_result is not None:
            status=finish_l4d2(goldberg_result,status)
        if nfsmw_result is not None:
            status=finish_mw(nfsmw_result,status)
    finally:
        if goldberg_result is not None:
            goldberg_result.unlink(missing_ok=True)
        if nfsmw_result is not None:
            nfsmw_result.unlink(missing_ok=True)
    print(f"{player.name.upper()} batocera-wine : code {status}", flush=True)
    return 128 - status if status < 0 else status


def start_player(app, player, original, target, devices, rectangle, window_class,
                 shared_keyboard_mouse=True, saves=None, exit_state=None,network=None,network_index=0):
    _, _, width, height = rectangle
    args = [str(app / "AppRun"), "gamescope-kbm", "--backend=sdl", "--borderless",
            "-W", str(width), "-H", str(height)]
    if saves is not None:
        from partydeck_profiles import profile_path, read_profile
        base = Path(__file__).resolve().parent
        if profile_path(base,original).exists():
            profile = read_profile(base,original)
            if profile.get('adapter') in ('borderlands2','l4d2-goldberg','nfsmw-lan'):
                args.extend(['-w',str(width),'-h',str(height)])
    if not shared_keyboard_mouse:
        args.extend(["--backend-disable-keyboard", "--backend-disable-mouse"])
    kb_mouse = [str(d.node) for d in devices if d.category in {KEYBOARDS, MICE}]
    if kb_mouse:
        args.extend(["--libinput-hold-dev=" + ",".join(kb_mouse) + ",", "--grab"])
    helper = str(Path(__file__).resolve())
    sandbox=list(sandbox_arguments(player,devices,saves=saves))
    if network is not None:
        sandbox.extend(['--setenv','PARTYDECK_PRIVATE_LAN_IP',network.address(network_index)])
    args.extend(["--", "/bin/sh", "-c", 'unset LD_LIBRARY_PATH LD_PRELOAD; exec "$@"', "sh",
                 sys.executable, helper, "_sandbox", os.environ.get("DISPLAY", ""),
                 *bubblewrap_command(app), *sandbox,
                 "--", sys.executable, helper, "_wine",
                 str(original), str(target), str(player)])
    if saves is not None:
        args.append(str(saves))
    # SDL writes this identifier to the outer X11 window's WM_CLASS. The
    # AppImage's launcher PID and the game's title can both differ.
    environment = {**os.environ, "SDL_VIDEODRIVER": "x11",
                                       "SDL_VIDEO_X11_WMCLASS": window_class,
                                       "PARTYDECK_PLAYER_WIDTH": str(width),
                                       "PARTYDECK_PLAYER_HEIGHT": str(height)}
    environment.pop('PARTYDECK_EXIT_STATE',None)
    if exit_state is not None:
        environment['PARTYDECK_EXIT_STATE'] = str(exit_state)
    if network is not None:
        return subprocess.Popen(network.prefix(network_index)+args,env=environment,start_new_session=True,
                                stdin=subprocess.DEVNULL,pass_fds=(network.fds[network_index],))
    return subprocess.Popen(args,env=environment,start_new_session=True,stdin=subprocess.DEVNULL)


def stop_players(processes, timeout=5):
    # Every compositor has its own process group. Never use a global process
    # name or wineserver kill: solo games and unrelated sessions must survive.
    active = [process for process in processes if process.poll() is None]
    for process in active:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic()+timeout
    for process in processes:
        try:
            process.wait(timeout=max(0,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    # Allow descendants the same grace period if their leader exits first.
    # Never signal a group belonging to a leader reaped earlier in the session:
    # its PID could have been recycled by the time the last Xorg player quits.
    groups = {process.pid for process in active}
    while groups and time.monotonic() < deadline:
        for group in list(groups):
            try:
                os.killpg(group,0)
            except ProcessLookupError:
                groups.remove(group)
        if groups:
            time.sleep(min(.05,max(0,deadline-time.monotonic())))
    for group in groups:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for process in processes:
        process.wait()


class SessionStopped(Exception):
    pass


def handle_exit(signum, _frame):
    raise SessionStopped(signum)


def read_wine_exit(path):
    import json
    try:
        data = json.loads(path.read_text())
        code = data.get('wine_exit') if isinstance(data,dict) and data.get('version')==1 else None
        return code if type(code) is int and 0 <= code <= 255 else None
    except (OSError,ValueError):
        return None


def exit_code(status):
    # Passing -11 to SystemExit used to wrap it to 245 at the shell boundary.
    return 128-status if status < 0 else status


def session_result(processes, states, wayland):
    statuses = [process.poll() for process in processes]
    wine = [read_wine_exit(path) for path in states]
    finished = [i for i,status in enumerate(statuses) if status is not None or (wayland and wine[i] is not None)]
    failed = any((status is not None and status != 0) or
                 (native is not None and native != 0) for status,native in zip(statuses,wine))
    # A failed Xorg player must not strand ES behind a surviving compositor.
    # Normal Xorg exits still wait for every player, as before.
    if failed:
        finished = [i for i,status in enumerate(statuses) if status is not None or wine[i] is not None]
    if not finished or (not wayland and not failed and len(finished) != len(processes)):
        return None
    results = []
    for index in finished:
        status, native = statuses[index],wine[index]
        print(tr('J{p0} : fin Wine={p1}, Gamescope={p2}.',p0=index+1,p1=native,p2=status),flush=True)
        if native is not None:
            results.append(native)
        if status is not None and status != 0:
            # Only a proven normal Wine exit permits treating this Wayland
            # teardown failure as cleanup. Startup/in-game crashes still fail.
            if wayland and native==0 and status in (-signal.SIGSEGV,139,245):
                print(tr('Wine a terminé normalement ; incident Gamescope à la fermeture ({p0}), non transmis à EmulationStation.',p0=status),flush=True)
            else:
                results.append(exit_code(status))
    return next((code for code in results if code),0)


def run_session(app, base, original, target, count, split, input_mode, party=False):
    # Keep maintenance and the whole process lifetime mutually exclusive.
    with storage_session(base, PARTY_SAVES):
        return _run_session(app, base, original, target, count, split, input_mode, party)


def _run_session(app, base, original, target, count, split, input_mode, party=False):
    for tool in ("batocera-wine", "xdotool", "mount"):
        if not shutil.which(tool):
            raise RuntimeError(f"Commande indisponible : {tool}")
    keyboard_player = True
    gpu='auto'
    if party:
        from partydeck_profiles import profile_path, read_profile
        if profile_path(base, original).exists():
            profile=read_profile(base, original)
            keyboard_player = profile.get("keyboard_player", True)
            gpu=profile.get('gpu','auto')
    if gpu=='nvidia':
        for key in ('VK_DRIVER_FILES','VK_ICD_FILENAMES','DRI_PRIME','MESA_VK_DEVICE_SELECT'):
            os.environ.pop(key,None)
    graphics=graphics_environment(os.environ,gpu)
    if graphics:
        os.environ.update(graphics)
        print(tr('GPU hybride : rendu NVIDIA demandé pour Gamescope et Wine.'),flush=True)
    if keyboard_player:
        players = assign_players(read_input_devices(), count, input_mode)
    else:
        input_mode = "auto"
        players = assign_players(read_input_devices(), count, input_mode, allow_keyboard_player=False)
        print("Clavier/souris exclu de l’attribution des joueurs ; accès aux menus conservé.", flush=True)
    # If a player owns the physical keyboard/mouse, its libinput grab routes
    # input exclusively. All-pad sessions use ordinary SDL window focus.
    shared_keyboard_mouse = not any(d.category in {KEYBOARDS, MICE}
                                    for devices in players for d in devices)
    boxes = layout(primary_monitor(), len(players), split)
    print(f"Joueurs : {len(players)} | demande : {count} | entrées : {input_mode} | "
          f"partage : {split}", flush=True)
    if shared_keyboard_mouse:
        print("Clavier et souris disponibles sur la fenêtre sélectionnée.", flush=True)
    from partydeck_virtual_input import probe as virtual_input_probe, Watcher
    virtual_input=party and virtual_input_probe(original)
    probe = subprocess.run([*bubblewrap_command(app), *MOUNT_CAPS,
                            "--ro-bind", "/", "/", "--unshare-pid", "--proc", "/proc",
                            "--", "/bin/true"])
    if probe.returncode:
        raise RuntimeError("Bubblewrap ne peut pas initialiser l’espace de noms Wine.")
    print("Vérification Bubblewrap Wine OK.", flush=True)
    game_id = hashlib.sha256(os.fsencode(original)).hexdigest()[:16]
    save_name = f"{original.stem[:90]} [{game_id[:10]}]"
    processes, states = [], []
    virtual_watcher=None
    network=None
    wayland = bool(os.environ.get('WAYLAND_DISPLAY'))
    window_classes = [f"partydeck-coop-{os.getpid()}-j{i}" for i in range(1, len(players) + 1)]
    handlers = {signum:signal.signal(signum,handle_exit) for signum in SIGNALS}
    try:
        if os.environ.get('PARTYDECK_NFSMW_PRIVATE_LAN')=='1':
            from partydeck_profiles import profile_path,read_profile
            if (not party or not profile_path(base,original).is_file()
                    or read_profile(base,original).get('adapter')!='nfsmw-lan'):
                raise ValueError(tr('Le LAN privé expérimental exige le profil Most Wanted 2005.'))
            from partydeck_private_lan import PrivateLAN
            network=PrivateLAN(len(players))
            network.start()
        for index, (devices, rectangle) in enumerate(zip(players, boxes), 1):
            player = base / ("party" if party else "coop") / game_id / f"j{index}"
            saves = PARTY_SAVES / save_name / f"j{index}" if party else None
            player.mkdir(parents=True, exist_ok=True)
            print(f"J{index} : {', '.join(str(d.node) for d in devices)} → {rectangle}", flush=True)
            state = player/f'session-{uuid.uuid4().hex}.json'
            processes.append(start_player(app, player, original, target, devices, rectangle,
                                          window_classes[index - 1],
                                          shared_keyboard_mouse=shared_keyboard_mouse or virtual_input, saves=saves,exit_state=state,
                                          network=network,network_index=index-1))
            states.append(state)
        if virtual_input:
            virtual_watcher=Watcher(base,original,processes,players,window_classes)
            virtual_watcher.start()
        pending = dict(enumerate(processes))
        seen_windows = {}
        next_attempt = dict.fromkeys(pending, 0)
        deadline = time.monotonic() + 120
        while pending and time.monotonic() < deadline:
            result = session_result(processes,states,wayland)
            if result is not None:
                return result
            for index, process in list(pending.items()):
                status = process.poll()
                if status is not None:
                    print(f"J{index + 1} a quitté avant l’affichage (code {status}).", flush=True)
                    del pending[index]
                    continue
                if time.monotonic() < next_attempt[index]:
                    continue
                window = top_window(window_classes[index])
                if window:
                    if seen_windows.get(index) != window:
                        seen_windows[index] = window
                        print(f"Fenêtre J{index + 1} repérée : {window}", flush=True)
                    next_attempt[index] = time.monotonic() + 1
                    try:
                        if place_window(window, boxes[index]):
                            print(f"Fenêtre J{index + 1} placée : {window}", flush=True)
                            focus_window(window)
                            del pending[index]
                            continue
                    except subprocess.CalledProcessError:
                        pass  # The window can disappear during startup.
            if pending:
                time.sleep(0.5)
        for index in pending:
            if index in seen_windows:
                print(f"Placement J{index + 1} non confirmé : {seen_windows[index]}", flush=True)
            else:
                print(f"Fenêtre J{index + 1} non repérée : {window_classes[index]}", flush=True)
        if seen_windows:
            focus_window(seen_windows[min(seen_windows)])
        while True:
            result = session_result(processes,states,wayland)
            if result is not None:
                return result
            time.sleep(0.1)
    except SessionStopped as stopped:
        print(tr('Fermeture de la session demandée (signal {p0}).',p0=stopped.args[0]),flush=True)
        return 0
    finally:
        for signum in SIGNALS:
            signal.signal(signum, signal.SIG_IGN)
        try:
            try:
                if virtual_watcher is not None:virtual_watcher.close()
            finally:
                try:stop_players(processes)
                finally:
                    if network is not None:network.close()
        finally:
            for path in states:
                path.unlink(missing_ok=True)
            for signum,handler in handlers.items():
                signal.signal(signum,handler)


def main():
    if sys.argv[1:] == ["install-system"]:
        install_system()
        return 0
    if len(sys.argv) > 3 and sys.argv[1] == "_sandbox":
        enter_sandbox(sys.argv[2], sys.argv[3:])
    if len(sys.argv) in {5, 6} and sys.argv[1] == "_wine":
        return run_wine(*(Path(path) for path in sys.argv[2:]))

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "play", "prepare-party", "play-party"))
    parser.add_argument("app", type=Path)
    parser.add_argument("base", type=Path)
    parser.add_argument("ports", type=Path)
    parser.add_argument("rom")
    parser.add_argument("count", nargs="?", default="auto", choices=("auto", "1", "2", "3", "4"))
    parser.add_argument("split", nargs="?", default="horizontal", choices=("horizontal", "vertical"))
    parser.add_argument("input_mode", nargs="?", default="auto",
                        choices=("auto", "clavier-j1", "clavier-j2"))
    args = parser.parse_args()
    original, target = rom_path(args.rom, parser)
    if args.mode in {"prepare", "prepare-party"}:
        party = args.mode == "prepare-party"
        if party:
            from partydeck_profiles import prepare_profile
            prepare_profile(args.base, original, args.count, args.split, args.input_mode)
        port = write_port(PARTY_ROMS if party else args.ports,
                          args.base / "partydeck-test", original,
                          args.count, args.split, args.input_mode,
                          mode="party" if party else "coop", profile=party)
        print(f"Entrée enregistrée : {port}")
        print("Actualise les listes de jeux dans EmulationStation, puis ouvre "
              + ("Windows Party." if party else "Ports."))
        return 0
    return run_session(args.app, args.base, original, target, args.count,
                       args.split, args.input_mode, party=args.mode == "play-party")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"PartyDeck Wine : {exc}", file=sys.stderr)
        raise SystemExit(1)
