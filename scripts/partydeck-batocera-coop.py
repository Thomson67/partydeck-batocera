#!/usr/bin/env python3
"""Launch concurrent native Batocera Wine sessions in nested Gamescope windows."""
import argparse
import ctypes as C
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import resource
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
from partydeck_migrate import PARTY_ROMS


ROM_TYPES = {".wine", ".pc", ".wsquashfs"}
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


def primary_monitor(output='auto'):
    from partydeck_display import discover_outputs,choose_output
    return choose_output(discover_outputs(),output).rectangle


def reposition_windows(classes,boxes):
    complete=True
    for window_class,rectangle in zip(classes,boxes):
        window=top_window(window_class)
        if not window:
            complete=False
            continue
        try:
            complete=place_window(window,rectangle) and complete
        except (OSError,subprocess.SubprocessError):
            complete=False
    return complete


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
    # A window launched from SSH may still be unmapped behind the desktop.
    # Match only this player's exact class, and never choose an ambiguous ID.
    for visible in (True, False):
        command = ["xdotool", "search"]
        if visible:
            command.append("--onlyvisible")
        result = subprocess.run(command + ["--class", f"^{window_class}$"],
                                text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        ids = result.stdout.split()
        if result.returncode == 0 and ids:
            return ids[0] if len(ids) == 1 else None
    return None


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
    # Ask the WM/compositor to activate Xwayland windows over native ES.
    # Keep the map/raise/focus fallback that works on Batocera Xorg.
    commands = (["xdotool", "windowmap", window],
                ["xdotool", "windowactivate", window],
                ["xdotool", "windowraise", window, "windowfocus", window])
    for command in commands:
        try:
            subprocess.run(command, check=False, timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired):
            pass


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
            if relative == "saves":
                source = saves / "windows"
            else:
                from partydeck_bottles import location
                source = location(player) / "prefixes"
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
        from partydeck_bottles import location
        area = location(player)
        area.mkdir(parents=True, exist_ok=True)
        args.extend(["--bind", str(area), str(area)])
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


NESTED_DISPLAY_ENV = ('DISPLAY', 'WAYLAND_DISPLAY', 'GAMESCOPE_WAYLAND_DISPLAY',
                      'XAUTHORITY', 'XDG_RUNTIME_DIR')


def publish_nested_display(state):
    from partydeck_profiles import atomic_write
    environment = {key: os.environ[key] for key in NESTED_DISPLAY_ENV if key in os.environ}
    atomic_write(state.with_suffix('.display'), json.dumps(environment))
    while (code := read_wine_exit(state)) is None:
        time.sleep(.1)
    return code


def await_nested_display(state, command):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            environment = json.loads(state.with_suffix('.display').read_text())
        except FileNotFoundError:
            time.sleep(.1)
            continue
        for key in NESTED_DISPLAY_ENV:
            if key in environment:
                os.environ[key] = environment[key]
            else:
                os.environ.pop(key, None)
        # This exec is supervised directly by PartyDeck. Bubblewrap still dies
        # with its parent, but a lost Gamescope/Xwayland cannot kill Wine mid-sync.
        os.execv(command[0], command)
    return 1


def mount_overlay(target, area, shared=None):
    upper, work, view = (area / name for name in ("upper", "work", "view"))
    for path in (upper, work, view):
        path.mkdir(parents=True, exist_ok=True)
    lower = str(target)
    if shared is not None and shared.is_dir():
        from partydeck_bottles import regular_directory, _safe_path
        regular_directory(shared)
        _safe_path(shared)
        subprocess.run(["mount", "--bind", str(shared), str(shared)], check=True)
        subprocess.run(["mount", "-o", "remount,bind,ro", str(shared)], check=True)
        lower = f"{shared}:{lower}"
    options = f"lowerdir={lower},upperdir={upper},workdir={work},redirect_dir=on"
    subprocess.run(["mount", "-t", "overlay", "-o", options, "overlay", str(view)], check=True)
    subprocess.run(["mount", "--bind", str(view), str(target)], check=True)


def mount_umu_home(home, area):
    from partydeck_umu import installed_steam_runtimes, STEAM_RUNTIME_HOME
    from partydeck_bottles import regular_directory, _safe_path
    shared = installed_steam_runtimes(home)
    if shared:
        cache = area / 'runtime-cache'
        source, upper, work = (regular_directory(cache / name)
                               for name in ('source', 'upper', 'work'))
        for path in (source, upper, work):
            _safe_path(path)
        # Pin the host runtime before the per-player overlay covers UMU home.
        subprocess.run(['mount', '--bind', str(home / STEAM_RUNTIME_HOME), str(source)], check=True)
        subprocess.run(['mount', '-o', 'remount,bind,ro', str(source)], check=True)
    mount_overlay(home, area, shared=area / 'shared')
    if shared:
        destination = regular_directory(home / STEAM_RUNTIME_HOME)
        lower = str(source)
        fallback = area / 'shared' / STEAM_RUNTIME_HOME
        if fallback.is_dir():
            _safe_path(regular_directory(fallback))
            lower = f'{fallback}:{lower}'
        options = f'lowerdir={lower},upperdir={upper},workdir={work},redirect_dir=on'
        subprocess.run(['mount', '-t', 'overlay', '-o', options, 'overlay', str(destination)], check=True)
    return shared


def run_wine(original, target, player, saves=None):
    # Gamescope's SDL backend can stay alive after its primary Wine child exits.
    # Report native completion independently of the compositor's lifetime/code.
    status = 1
    try:
        from partydeck_bo2 import AUTO_JOIN
        if os.environ.get(AUTO_JOIN) == '1':
            from partydeck_bo2 import automatic_path
            from partydeck_profiles import atomic_write
            token = os.environ['PARTYDECK_SESSION_TOKEN']
            display = {key: os.environ[key] for key in ('DISPLAY', 'XAUTHORITY') if key in os.environ}
            atomic_write(automatic_path(player, token, 'display'), json.dumps(display))
        status = _run_wine(original,target,player,saves)
        return status
    finally:
        state = os.environ.get('PARTYDECK_EXIT_STATE')
        if state:
            from partydeck_profiles import atomic_write
            path = Path(state)
            if path.parent.resolve() != player.resolve() or not re.fullmatch(r'session-[0-9a-f]{32}\.json',path.name):
                raise ValueError(tr('État de fin Wine hors du dossier privé du joueur.'))
            atomic_write(path,json.dumps(dict(version=1,wine_exit=status)))


def _run_wine(original, target, player, saves=None):
    goldberg_result=None
    nfsmw_result=None
    windows_views=[]
    if saves is not None:
        from partydeck_bottles import location, mount_windows
        windows_views=mount_windows(player)
    hkmp_result=None
    hkmultiplayer_result=None
    if original.suffix.lower() != ".wsquashfs":
        mount_overlay(target, (location(player) if saves is not None else player) / "content")
    shared_runtimes = ()
    if UMU_HOME.is_dir():
        area = player / "umu"
        shared_runtimes = mount_umu_home(UMU_HOME, area)
        for name in UMU_PRIVATE:
            private = player / "umu-private" / name
            private.mkdir(parents=True, exist_ok=True)
            destination = UMU_HOME / name
            destination.mkdir(parents=True, exist_ok=True)
            subprocess.run(["mount", "--bind", str(private), str(destination)], check=True)
    if saves is not None:
        from partydeck_profiles import install_party_runner_hook
        install_party_runner_hook(original, player, track_runner=os.environ.get('PARTYDECK_TRACK_RUNNER') == '1',
                                  mono_cache=player.parents[2]/'mono-cache')
        from partydeck_mangohud import install_hook as install_mangohud
        install_mangohud(original,player)
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
        from partydeck_hkmp import install_hook as install_hkmp, finish_launch as finish_hkmp
        hkmp_result=install_hkmp(Path(__file__).resolve().parent,original,player)
        from partydeck_hkmultiplayer import install_hook as install_multi, finish_launch as finish_multi
        hkmultiplayer_result=install_multi(Path(__file__).resolve().parent,original,player)
        from partydeck_bo2 import install_hook as install_bo2
        install_bo2(Path(__file__).resolve().parent, original, player)
        from partydeck_celestenet import install_hook as install_celestenet
        install_celestenet(Path(__file__).resolve().parent,player)
        if os.environ.get('PARTYDECK_DST') == '1':
            from partydeck_dst import install_hook as install_dst
            install_dst(Path(__file__).resolve().parent, player, original)
    # Keep the original ROM name for Batocera's per-game runner/settings lookup.
    if saves is not None:
        from partydeck_autoconnect import install_hook as install_autoconnect
        install_autoconnect(Path(__file__).resolve().parent,original,player)
    # All UMU distributions receive cheap COW views: native Wine resolves the
    # selected runner itself, including per-ROM and filename overrides.
    from partydeck_umu import runner_views,pressure_vessel_environment
    from partydeck_controls import Confirmation
    confirm=False
    if saves is not None:
        from partydeck_profiles import profile_path,read_profile
        base=Path(__file__).resolve().parent
        if profile_path(base,original).exists():
            profile=read_profile(base,original)
            confirm=profile.get('adapter')=='nfsmw-lan' and profile['nfsmw']['controller_enter']
    try:
        with runner_views(player, shared_runtimes=shared_runtimes) as views,Confirmation(confirm,player=player.name):
            if windows_views:
                from partydeck_bottles import adapt_prefix_isolation
                adapt_prefix_isolation(views,windows_views)
            exports=[*views,*windows_views]
            environment={'env':pressure_vessel_environment(exports)} if exports else {}
            if os.environ.get('PARTYDECK_DST') == '1':
                from partydeck_dst import readiness_dir
                ready = readiness_dir(player, os.environ.get('PARTYDECK_SESSION_TOKEN'))
                environment['env'] = pressure_vessel_environment(
                    [ready], environment.get('env'), writable=player.name == 'j1')
            status = run_native_wine(original, environment, watch_umu=bool(views) or
                                     os.environ.get('PARTYDECK_TRACK_RUNNER') == '1')
            if goldberg_result is not None:
                status=finish_l4d2(goldberg_result,status)
            if nfsmw_result is not None:
                status=finish_mw(nfsmw_result,status)
            if hkmp_result is not None:
                status=finish_hkmp(hkmp_result,status)
            if hkmultiplayer_result is not None:
                status=finish_multi(hkmultiplayer_result,status)
    finally:
        if goldberg_result is not None:
            goldberg_result.unlink(missing_ok=True)
        if nfsmw_result is not None:
            nfsmw_result.unlink(missing_ok=True)
        if hkmp_result is not None:
            hkmp_result.unlink(missing_ok=True)
        if hkmultiplayer_result is not None:
            hkmultiplayer_result.unlink(missing_ok=True)
    print(f"{player.name.upper()} batocera-wine : code {status}", flush=True)
    return 128 - status if status < 0 else status


def run_native_wine(original, options, watch_umu=False):
    command = ["batocera-wine", "windows", "play", str(original)]
    state_path = os.environ.get('PARTYDECK_EXIT_STATE')
    if not watch_umu or not state_path:
        return subprocess.run(command, **options).returncode

    state = Path(state_path)
    ready, request = state.with_suffix('.umu-ready'), state.with_suffix('.stop')
    with subprocess.Popen(command, **options) as wine:
        try:
            stop_command = None
            while True:
                try:
                    return wine.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    pass
                if stop_command is None:
                    stop_command = umu_stop_command()
                    command_env = None
                    if stop_command is None:
                        native = native_stop_command(state, options.get('env', os.environ))
                        if native is not None:
                            stop_command, command_env = native
                    if stop_command is not None:
                        ready.touch()
                if stop_command is not None and request.exists():
                    try:
                        subprocess.run(stop_command, env=command_env, check=True, timeout=12)
                    except (OSError, subprocess.SubprocessError) as error:
                        ready.unlink(missing_ok=True)
                        print(f"UMU stop: {error}", flush=True)
                    return wine.wait()
        finally:
            ready.unlink(missing_ok=True)


def umu_stop_command():
    # These state files and PIDs are visible only within the player's sandbox.
    # The runner validates the owner token before asking its wineserver to stop.
    for state in UMU_SESSION_STATE.glob('session-*.state'):
        try:
            fields = state.read_text().splitlines()
        except (OSError, UnicodeError):
            continue
        if len(fields) < 7 or not fields[5].isdecimal() or not fields[6]:
            continue
        runner = Path(fields[4])
        helper = runner / 'umu-batocera/runtime-prefix.py'
        if runner.is_absolute() and helper.is_file():
            return [sys.executable, str(helper), 'stop-hotkey', '--state-file', str(state),
                    '--pid', fields[5], '--owner-token', fields[6]]
    return None


def native_stop_command(state, environment):
    if os.environ.get('PARTYDECK_TRACK_RUNNER') != '1':
        return None
    try:
        server, prefix, libraries = state.with_suffix('.native').read_text().splitlines()
    except (OSError, ValueError):
        return None
    binary = Path(server)
    if (binary.name != 'wineserver' or not binary.is_file() or not binary.is_absolute()
            or not Path(prefix).is_absolute() or not Path(prefix).is_dir()):
        return None
    return [server, '-k'], dict(environment, WINEPREFIX=prefix, LD_LIBRARY_PATH=libraries)


def run_compositor(command):
    # ES can pass a low soft limit to its ports. Raise it in the freshly
    # spawned child only, before Gamescope creates Vulkan/Wayland descriptors.
    # Keep the host hard limit and any already higher soft limit untouched.
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = 65536 if hard == resource.RLIM_INFINITY else min(65536, hard)
    if soft != resource.RLIM_INFINITY and soft < target:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
        except (OSError, ValueError) as error:
            print(tr('Gamescope : relèvement de la limite de fichiers impossible : {p0}',p0=error),flush=True)
    current, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    print(tr('Gamescope : fichiers ouverts autorisés {p0} → {p1} (maximum {p2}).',
             p0=soft,p1=current,p2=hard),flush=True)
    os.execv(command[0], command)


def start_player(app, player, original, target, devices, rectangle, window_class,
                 shared_keyboard_mouse=True, saves=None, exit_state=None,network=None,network_index=0,
                 session_token=None,player_count=1,l4d2_launch=None,celestenet=False,celeste_options=None,
                 track_runner=False, dst=False, split=None):
    _, _, width, height = rectangle
    bo2_resolution = None
    bo2_automatic = False
    from partydeck_bo2 import ADAPTER as BO2, AUTO_JOIN, PLUTONIUM_MODES, render_size
    args = [str(app / "AppRun"), "gamescope-kbm", "--backend=sdl", "--borderless",
            "-W", str(width), "-H", str(height)]
    if saves is not None:
        from partydeck_profiles import profile_path, read_profile
        base = Path(__file__).resolve().parent
        if profile_path(base,original).exists():
            profile = read_profile(base,original)
            adapter = profile.get('adapter')
            if adapter == BO2:
                settings = profile['bo2']
                bo2_automatic = (network is not None and settings['mode'] in PLUTONIUM_MODES
                                 and settings['automatic_join'])
                horizontal_render = 'standard'
                if player_count == 2 and split == 'horizontal' and settings['mode'] in PLUTONIUM_MODES:
                    horizontal_render = settings['horizontal_render']
                render_width, render_height = render_size(width, height, horizontal_render=horizontal_render)
                args.extend(['-w', str(render_width), '-h', str(render_height)])
                bo2_resolution = f'{render_width}x{render_height}'
                print(tr('Black Ops II {p0} : rendu {p1}, fenêtre {p2}.',
                         p0=player.name.upper(), p1=bo2_resolution, p2=f'{width}x{height}'), flush=True)
            elif adapter in ('borderlands2','l4d2-goldberg','nfsmw-lan','hollowknight-hkmp','hollowknight-hkmultiplayer'):
                args.extend(['-w',str(width),'-h',str(height)])
    if dst:
        args.extend(['-w', str(width), '-h', str(height)])
    if celestenet:
        from partydeck_celestenet import viewport_variant
        if viewport_variant(width, height):
            # The game's XWayland display must match the output as well.
            args.extend(['-w', str(width), '-h', str(height)])
    if not shared_keyboard_mouse:
        args.extend(["--backend-disable-keyboard", "--backend-disable-mouse"])
    kb_mouse = [str(d.node) for d in devices if d.category in {KEYBOARDS, MICE}]
    if kb_mouse:
        args.extend(["--libinput-hold-dev=" + ",".join(kb_mouse) + ",", "--grab"])
    helper = str(Path(__file__).resolve())
    sandbox=list(sandbox_arguments(player,devices,saves=saves))
    if dst:
        from partydeck_dst import readiness_dir
        ready = str(readiness_dir(player, session_token))
        sandbox.extend(['--bind' if player.name == 'j1' else '--ro-bind', ready, ready])
    if network is not None:
        sandbox.extend(['--setenv','PARTYDECK_PRIVATE_LAN_IP',network.address(network_index)])
    outer_display = os.environ.get("DISPLAY", "")
    wine_command = [*(network.child_prefix(network_index) if network is not None else []),
                    sys.executable, helper, "_sandbox", outer_display,
                    *bubblewrap_command(app), *sandbox,
                    "--", sys.executable, helper, "_wine", str(original), str(target), str(player)]
    if saves is not None:
        wine_command.append(str(saves))
    # SDL writes this identifier to the outer X11 window's WM_CLASS. The
    # AppImage's launcher PID and the game's title can both differ.
    environment = {**os.environ, "SDL_VIDEODRIVER": "x11",
                                       "SDL_VIDEO_X11_WMCLASS": window_class,
                                       "PARTYDECK_PLAYER_WIDTH": str(width),
                                       "PARTYDECK_PLAYER_HEIGHT": str(height)}
    environment.pop('PARTYDECK_PRIVATE_LAN_IP',None)
    environment.pop('PARTYDECK_BO2_RESOLUTION', None)
    environment.pop(AUTO_JOIN, None)
    if bo2_automatic:
        environment[AUTO_JOIN] = '1'
    if bo2_resolution is not None:
        environment['PARTYDECK_BO2_RESOLUTION'] = bo2_resolution
    environment.pop('PARTYDECK_SESSION_TOKEN',None)
    environment['PARTYDECK_SESSION_PLAYERS']=str(player_count)
    if session_token is not None:environment['PARTYDECK_SESSION_TOKEN']=session_token
    environment.pop('PARTYDECK_L4D2_LAUNCH',None)
    if l4d2_launch is not None:environment['PARTYDECK_L4D2_LAUNCH']=json.dumps(l4d2_launch)
    environment.pop('PARTYDECK_CELESTE_OPTIONS', None)
    if celeste_options is not None:
        environment['PARTYDECK_CELESTE_OPTIONS'] = json.dumps(celeste_options)
    environment.pop('PARTYDECK_CELESTENET',None)
    environment.pop('PARTYDECK_DST', None)
    if dst:
        environment['PARTYDECK_DST'] = '1'
    if celestenet:
        environment['PARTYDECK_CELESTENET']='1'
    environment.pop('PARTYDECK_EXIT_STATE',None)
    environment.pop('PARTYDECK_TRACK_RUNNER',None)
    if track_runner:
        environment['PARTYDECK_TRACK_RUNNER'] = '1'
    if exit_state is not None:
        environment['PARTYDECK_EXIT_STATE'] = str(exit_state)
    supervise_wine = exit_state is not None and UMU_HOME.is_dir()
    nested_command = ([sys.executable, helper, "_publish-display", str(exit_state)]
                      if supervise_wine else wine_command)
    args.extend(["--", "/bin/sh", "-c", 'unset LD_LIBRARY_PATH LD_PRELOAD; exec "$@"',
                 "sh", *nested_command])
    process = subprocess.Popen([sys.executable, helper, "_gamescope", *args], env=environment,
                               start_new_session=True, stdin=subprocess.DEVNULL)
    if supervise_wine:
        sandbox_environment = environment.copy()
        sandbox_environment.pop('LD_LIBRARY_PATH', None)
        sandbox_environment.pop('LD_PRELOAD', None)
        try:
            process.wine_sandbox = subprocess.Popen(
                [sys.executable, helper, "_await-display", str(exit_state), *wine_command],
                env=sandbox_environment, start_new_session=True, stdin=subprocess.DEVNULL)
        except BaseException:
            stop_players([process])
            exit_state.with_suffix('.display').unlink(missing_ok=True)
            raise
    return process


def stop_players(processes, timeout=5, states=(), sync_timeout=120):
    # Every compositor has its own process group. Never use a global process
    # name or wineserver kill: solo games and unrelated sessions must survive.
    sandboxes = [vars(process).get('wine_sandbox') for process in processes]
    syncing = []
    for process, sandbox, state in zip(processes, sandboxes, states):
        owner = sandbox if sandbox is not None else process
        if owner.poll() is None and state.with_suffix('.umu-ready').exists():
            state.with_suffix('.stop').touch()
            syncing.append((owner, state))
            print(f"Windows Party {state.parent.name.upper()}: graceful Wine stop requested.", flush=True)
    deadline = time.monotonic() + sync_timeout
    while syncing and time.monotonic() < deadline:
        syncing = [(process, state) for process, state in syncing
                   if process.poll() is None and read_wine_exit(state) is None
                   and state.with_suffix('.umu-ready').exists()]
        if syncing:
            time.sleep(.1)
    if syncing:
        print("UMU: prefix synchronization timed out.", flush=True)
    owned = [*processes, *(sandbox for sandbox in sandboxes if sandbox is not None)]
    active = [process for process in owned if process.poll() is None]
    for process in active:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic()+timeout
    for process in owned:
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
    for process in owned:
        process.wait()


class SessionStopped(Exception):
    pass


def handle_exit(signum, _frame):
    raise SessionStopped(signum)


HOTKEY_STATE = (Path('/run/hotkeygen.state'), Path('/run/hotkeygen.context'))


def hotkey_context():
    for path in HOTKEY_STATE:
        try:
            state = json.loads(path.read_text())
            context = state.get('context', state)
            if isinstance(context['name'], str) and isinstance(context['keys'], dict):
                return context['name'], context['keys'], state.get('include_common', False)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return None


def process_start_time(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def stop_session_from_hotkey(pid, start):
    if start and process_start_time(pid) == start:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    return 0


def set_hotkey_context(binary, context):
    name, keys, common = context
    command = [binary, '--new-context', name, json.dumps(keys)]
    if not common:
        command.append('--disable-common')
    subprocess.run(command, check=True, timeout=5)


class SessionHotkey:
    def __init__(self):
        self.binary = shutil.which('hotkeygen')
        self.previous = None
        self.action = None

    def start(self):
        pid = os.getpid()
        stamp = process_start_time(pid)
        if not self.binary or not stamp:
            return
        self.previous = hotkey_context()
        _, keys, common = self.previous or ('', {}, True)
        if self.previous and self.previous[0] == 'windows-party':
            self.previous = None
        self.action = shlex.join([sys.executable, str(Path(__file__).resolve()),
                                  '_stop-session', str(pid), stamp])
        try:
            set_hotkey_context(self.binary, ('windows-party', {**keys, 'exit': self.action}, common))
            print('Windows Party: session hotkey registered.', flush=True)
        except (OSError, subprocess.SubprocessError) as error:
            print(f'Windows Party hotkey: {error}', flush=True)

    def close(self):
        if not self.action:
            return
        current = hotkey_context()
        if current is None or current[0] != 'windows-party' or current[1].get('exit') != self.action:
            return
        try:
            if self.previous:
                set_hotkey_context(self.binary, self.previous)
            else:
                subprocess.run([self.binary, '--default-context'], check=True, timeout=5)
        except (OSError, subprocess.SubprocessError) as error:
            print(f'Windows Party hotkey restore: {error}', flush=True)


def read_wine_exit(path):
    import json
    try:
        data = json.loads(path.read_text())
        code = data.get('wine_exit') if isinstance(data,dict) and data.get('version')==1 else None
        return code if type(code) is int and 0 <= code <= 255 else None
    except (OSError,ValueError):
        return None


def successful_runner(state, started):
    report = state.with_suffix('.runner')
    if read_wine_exit(state) != 0 or report.is_symlink() or not report.is_file():
        return None
    active = report.read_text().rstrip('\n')
    if Path(active).parent.name.endswith('-UMU'):
        logs = [path for path in (state.parent/'umu-logs').glob('runner-*.log')
                if not path.is_symlink() and path.stat().st_mtime_ns >= started]
        if not logs:
            return None
        last = max(logs, key=lambda path: path.stat().st_mtime_ns)
        if 'wine_persistence_rc=0' not in last.read_text(errors='replace').splitlines():
            return None
    return active


def exit_code(status):
    # Passing -11 to SystemExit used to wrap it to 245 at the shell boundary.
    return 128-status if status < 0 else status


def session_result(processes, states, wayland):
    statuses = [process.poll() for process in processes]
    wine = [read_wine_exit(path) for path in states]
    for index, process in enumerate(processes):
        sandbox = vars(process).get('wine_sandbox')
        if wine[index] is None and sandbox is not None:
            code = sandbox.poll()
            if code is not None:
                wine[index] = exit_code(code)
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
    from partydeck_display import settings as desktop_settings
    desktop=desktop_settings(base)
    keyboard_player = True
    profile=None
    gpu=desktop['gpu']
    if party:
        from partydeck_profiles import profile_path, read_profile
        if profile_path(base, original).exists():
            profile=read_profile(base, original)
            keyboard_player = profile.get("keyboard_player", True)
            if profile.get('gpu','auto')!='auto':gpu=profile['gpu']
    if profile and profile.get('adapter')=='hollowknight-hkmultiplayer':
        from partydeck_hkmultiplayer import session_code
        os.environ['PARTYDECK_HKMULTIPLAYER_CODE']=session_code()
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
    monitor=primary_monitor(desktop['output'])
    boxes = layout(monitor, len(players), split)
    session_token=uuid.uuid4().hex
    started = time.time_ns()
    from partydeck_bo2 import ADAPTER as BO2, PLUTONIUM_MODES, AutoJoin, automatic_path
    bo2_mode = PLUTONIUM_MODES.get(profile['bo2']['mode']) if profile and profile.get('adapter') == BO2 else None
    if bo2_mode:
        from partydeck_plutonium import prepare as prepare_plutonium
        prepare_plutonium(base, bo2_mode)
    track_runner = party and original.suffix.lower() == '.wsquashfs'
    keep_latest_runner = track_runner and storage_settings(base)['keep_latest_runner']
    from partydeck_celestenet import ADAPTER as CELESTENET
    celeste_options = profile[CELESTENET] if party and (profile or {}).get('adapter') == CELESTENET else None
    celestenet = celeste_options is not None and len(players) > 1
    from partydeck_dst import ADAPTER as DST
    dst = party and len(players) > 1 and (profile or {}).get('adapter') == DST
    bl2_lan=None
    l4d2_launch=None
    if party and len(players)>1:
        from partydeck_autoconnect import prepare_sdk, options as session_options, ADAPTERS, udp_bound, bl2_lan_address, BL2Host
        kind=ADAPTERS.get((profile or {}).get('adapter'))
        if kind:
            automatic=session_options(profile[kind],kind)
            if automatic['automatic'] and automatic['host_player']>len(players):
                raise ValueError(tr('Le joueur hôte choisi ne participe pas à cette session.'))
            if automatic['automatic'] and udp_bound(automatic['port']):
                raise ValueError(tr('Le port de la partie est déjà occupé. Changez le port dans le profil.'))
            if kind=='borderlands2' and automatic['automatic']:
                bl2_lan=(automatic['host_player'],automatic['port'],bl2_lan_address())
            if kind=='l4d2' and automatic['automatic']:
                from partydeck_couch import choose_l4d2_session
                l4d2_launch=choose_l4d2_session(profile[kind],len(players))
                if l4d2_launch is None:
                    return 0
        prepare_sdk(base,profile)
    print(tr('Écran demandé : {p0} · zone active : {p1}',p0=desktop['output'],p1=monitor),flush=True)
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
    if party:
        from partydeck_bottles import ROOT as bottles_root,regular_directory
        regular_directory(bottles_root)
        helper=Path(__file__).resolve().with_name('partydeck_bottles.py')
        bottle_probe=subprocess.run([*bubblewrap_command(app),*MOUNT_CAPS,
            "--ro-bind","/","/","--bind",str(bottles_root),str(bottles_root),
            "--unshare-pid","--proc","/proc","--",sys.executable,str(helper),"_probe"])
        if bottle_probe.returncode:
            raise RuntimeError(tr('Le disque des bottles ne permet pas la copie privée Windows. Aucune migration effectuée.'))
    game_id = hashlib.sha256(os.fsencode(original)).hexdigest()[:16]
    for index in range(1,len(players)+1):
        (base / ('runtime' if party else 'coop') / game_id / f'j{index}').mkdir(parents=True,exist_ok=True)
    save_name = f"{original.stem[:90]} [{game_id[:10]}]"
    processes, states = [], []
    bottle_players=[]
    from partydeck_umu import clean_shared_steam_runtimes, prepare_shared_steam_runtimes
    shared_runtimes = ()
    virtual_watcher=None
    network=None
    celeste_processes=[]
    bo2_join = None
    bo2_automatic = False
    bl2_host=None
    wayland = bool(os.environ.get('WAYLAND_DISPLAY'))
    window_classes = [f"partydeck-coop-{os.getpid()}-j{i}" for i in range(1, len(players) + 1)]
    handlers = {signum:signal.signal(signum,handle_exit) for signum in SIGNALS}
    hotkey = SessionHotkey()
    dst_ready = None
    try:
        if party:
            from partydeck_mono import prepare_mono
            prepare_mono(original, base/'mono-cache')
        shared_runtimes = prepare_shared_steam_runtimes(
            UMU_HOME, base / ('runtime' if party else 'coop') / game_id)
        if shared_runtimes:
            from partydeck_storage import ensure_idle
            ensure_idle(base)
            for folder in (base / 'runtime', base / 'coop'):
                for game in folder.glob('*'):
                    if re.fullmatch('[0-9a-f]{16}', game.name):
                        for index in range(1, 5):
                            clean_shared_steam_runtimes(game / f'j{index}', shared_runtimes)
        if bl2_lan is not None:
            host,port,address=bl2_lan
            bl2_host=BL2Host(base/'runtime'/game_id/f'j{host}',port,session_token,address)
        from partydeck_profiles import private_lan_enabled,PRIVATE_LAN_PROFILES
        requested=os.environ.get('PARTYDECK_PRIVATE_LAN',os.environ.get('PARTYDECK_NFSMW_PRIVATE_LAN'))
        use_private=private_lan_enabled(profile,len(players))
        if requested=='1':
            if not (celestenet or dst) and (not profile or profile.get('adapter') not in PRIVATE_LAN_PROFILES):
                raise ValueError(tr('Le LAN privé exige un profil compatible.'))
            use_private=True
        elif requested=='0':use_private=False
        if celestenet or dst:
            use_private=True
        if use_private:
            from partydeck_private_lan import PrivateLAN
            network=PrivateLAN(len(players),shared=True) if celestenet else PrivateLAN(len(players))
            network.start()
        if network is not None and bo2_mode:
            bo2_automatic = profile['bo2']['automatic_join']
        if celestenet:
            from partydeck_celestenet import start_server, start_join
            celeste_processes.append(start_server(base,base/'runtime'/game_id/'celestenet',network))
        if dst:
            from partydeck_dst import readiness_dir
            dst_ready = readiness_dir(base/'runtime'/game_id/'j1', session_token)
            dst_ready.mkdir(parents=True, exist_ok=False)
        hotkey.start()
        for index, (devices, rectangle) in enumerate(zip(players, boxes), 1):
            player = base / ("runtime" if party else "coop") / game_id / f"j{index}"
            saves = PARTY_SAVES / save_name / f"j{index}" if party else None
            player.mkdir(parents=True, exist_ok=True)
            if saves is not None:
                from partydeck_bottles import prepare
                saves.mkdir(parents=True, exist_ok=True)
                prepare(player,saves,original,target)
                bottle_players.append((player,saves))
            print(f"J{index} : {', '.join(str(d.node) for d in devices)} → {rectangle}", flush=True)
            state = player/f'session-{uuid.uuid4().hex}.json'
            processes.append(start_player(app, player, original, target, devices, rectangle,
                                          window_classes[index - 1],
                                          shared_keyboard_mouse=shared_keyboard_mouse or virtual_input, saves=saves,exit_state=state,
                                          network=network,network_index=0 if celestenet else index-1,
                                          session_token=session_token,player_count=len(players),
                                          l4d2_launch=l4d2_launch,celestenet=celestenet,
                                          celeste_options=celeste_options,track_runner=track_runner,dst=dst,
                                          split=split))
            if celestenet and celeste_options['automatic']:
                celeste_processes.append(start_join(network,index-1))
            states.append(state)
        if bo2_automatic:
            bo2_join = AutoJoin([state.parent for state in states], session_token,
                                profile['bo2']['mode'], os.environ.get('DISPLAY', ''), started)
            bo2_join.start()
        if virtual_input:
            virtual_watcher=Watcher(base,original,processes,players,window_classes)
            virtual_watcher.start()
        pending = dict(enumerate(processes))
        seen_windows = {}
        next_attempt = dict.fromkeys(pending, 0)
        deadline = time.monotonic() + 120
        while pending and time.monotonic() < deadline:
            if bl2_host is not None:bl2_host.poll()
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
                        focus_window(window)
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
        next_output_check=time.monotonic()+2
        while True:
            if bl2_host is not None:bl2_host.poll()
            result = session_result(processes,states,wayland)
            if result is not None:
                return result
            if time.monotonic()>=next_output_check:
                next_output_check=time.monotonic()+2
                try:
                    current=primary_monitor(desktop['output'])
                    if current!=monitor and reposition_windows(window_classes,layout(current,len(players),split)):
                        monitor=current
                        print(tr('Écran reconnecté : fenêtres replacées sur {p0}.',p0=current),flush=True)
                except (OSError,RuntimeError,subprocess.SubprocessError):
                    pass  # A dock can temporarily report no active outputs.
            time.sleep(0.1)
    except SessionStopped as stopped:
        print(tr('Fermeture de la session demandée (signal {p0}).',p0=stopped.args[0]),flush=True)
        return 0
    finally:
        for signum in SIGNALS:
            signal.signal(signum, signal.SIG_IGN)
        try:
            try:
                if bo2_join is not None:
                    bo2_join.close()
                if virtual_watcher is not None:virtual_watcher.close()
            finally:
                try:stop_players(processes,states=states)
                finally:
                    try:
                        if celeste_processes:
                            from partydeck_celestenet import stop
                            for process in reversed(celeste_processes):
                                stop(process)
                    finally:
                        if network is not None:network.close()
        finally:
            hotkey.close()
            if bl2_host is not None:bl2_host.close()
            if states:
                try:
                    from partydeck_storage import clean_umu_work,ensure_idle
                    ensure_idle(base)
                    result = clean_umu_work(states[0].parent.parent)
                    if result['removed']:
                        print(f"UMU: deferred prefix cleanup removed={result['removed']}", flush=True)
                except (OSError, RuntimeError, ValueError) as error:
                    print(f"UMU: deferred prefix cleanup: {error}", flush=True)
            # All Wine namespaces must be gone before touching physical uppers.
            # A failed optimization never masks the game exit or removes saves.
            if bottle_players:
                try:
                    from partydeck_storage import ensure_idle
                    from partydeck_bottles import prepare,collect_objects,prune_inherited_dependencies
                    from partydeck_umu import compact_steam_runtime
                    ensure_idle(base)
                    for player,saves in bottle_players:
                        area = prepare(player,saves,original,target)
                        freed = prune_inherited_dependencies(area,target)
                        if freed:
                            print(f"UMU {player.name.upper()}: inherited dependency bytes removed={freed}", flush=True)
                        if not shared_runtimes:
                            compact_steam_runtime(player)
                    if keep_latest_runner and len(states) == len(players):
                        from partydeck_bottles import retire_runner_bottles
                        reports = [successful_runner(state, started) for state in states]
                        if all(reports):
                            for (player, _), report in zip(bottle_players, reports):
                                count = retire_runner_bottles(player, original, report)
                                if count:
                                    print(f"Windows Party {player.name.upper()}: retired runner bottles={count}", flush=True)
                    collect_objects()
                except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as error:
                    print(tr('Optimisation des bottles différée : {p0}',p0=error),flush=True)
            for path in states:
                if shared_runtimes:
                    try:
                        from partydeck_storage import ensure_idle
                        ensure_idle(base)
                        clean_shared_steam_runtimes(path.parent, shared_runtimes)
                    except (OSError, RuntimeError) as error:
                        print(f"UMU runtime cache: {error}", flush=True)
                path.unlink(missing_ok=True)
                path.with_suffix('.umu-ready').unlink(missing_ok=True)
                path.with_suffix('.stop').unlink(missing_ok=True)
                path.with_suffix('.display').unlink(missing_ok=True)
                path.with_suffix('.runner').unlink(missing_ok=True)
                path.with_suffix('.native').unlink(missing_ok=True)
                if bo2_automatic:
                    for kind in ('log', 'display'):
                        automatic_path(path.parent, session_token, kind).unlink(missing_ok=True)
                if dst:
                    (path.parent/'dst-scripts.zip').unlink(missing_ok=True)
            if dst_ready is not None:
                try:
                    (dst_ready/'ready').unlink(missing_ok=True)
                    dst_ready.rmdir()
                except OSError as error:
                    print(f'PartyDeck DST: readiness cleanup: {error}', flush=True)
            for signum,handler in handlers.items():
                signal.signal(signum,handler)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "_gamescope":
        run_compositor(sys.argv[2:])
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "_stop-session":
        return stop_session_from_hotkey(int(sys.argv[2]), sys.argv[3])
    if sys.argv[1:] == ["install-system"]:
        install_system()
        return 0
    if len(sys.argv) > 3 and sys.argv[1] == "_sandbox":
        enter_sandbox(sys.argv[2], sys.argv[3:])
    if len(sys.argv) == 3 and sys.argv[1] == "_publish-display":
        return publish_nested_display(Path(sys.argv[2]))
    if len(sys.argv) > 3 and sys.argv[1] == "_await-display":
        return await_nested_display(Path(sys.argv[2]), sys.argv[3:])
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
                          args.base / "windows-party", original,
                          args.count, args.split, args.input_mode,
                          mode="party" if party else "coop", profile=party)
        if party:
            from partydeck_bo2 import ADAPTER as BO2, PLUTONIUM_MODES
            from partydeck_profiles import read_profile
            profile = read_profile(args.base, original)
            if profile.get('adapter') == BO2:
                mode = PLUTONIUM_MODES.get(profile['bo2']['mode'])
                if mode:
                    from partydeck_plutonium import prefetch
                    prefetch(args.base, mode)
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
