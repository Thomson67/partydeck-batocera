#!/usr/bin/env python3
"""Install and launch the standalone Windows Party Minecraft Java port."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import unquote
from zipfile import ZipFile

BASE = Path("/userdata/system/windows-party")
OLD_JAVA = Path("/userdata/system/partydeck/runtime/java")
PORTS = Path("/userdata/roms/ports")
PROFILE = "fabric-loader-0.16.5-1.21.1"
JRE = "temurin-21.0.13.1+2"
FX = "javafx-21.0.13.1"
SK = "SKlauncher-3.2.18.jar"
FILES = ("partydeck_minecraft.py", "downloads.json", f"{PROFILE}.json")
PORT_MARKER = "# PartyDeck Batocera: Minecraft Java"


def write_atomic(destination, content, mode=0o600):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, prefix=".minecraft-", delete=False) as output:
        staged = Path(output.name)
        try:
            output.write(content)
            output.close()
            staged.chmod(mode)
            staged.replace(destination)
        finally:
            staged.unlink(missing_ok=True)


def digest(path, algorithm):
    with path.open("rb") as source:
        result = hashlib.new(algorithm)
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
        return result.hexdigest()


def download(asset, destination):
    url, algorithm, checksum = asset
    if destination.is_file() and digest(destination, algorithm) == checksum:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    name = unquote(url.rsplit("/", 1)[-1])
    print(f"Téléchargement de {name}", flush=True)
    with TemporaryDirectory(dir=destination.parent, prefix=".download-") as directory:
        staged = Path(directory) / "download"
        subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--location", "--retry", "2",
            "--connect-timeout", "15", "--max-time", "300", "--proto", "=https", "--proto-redir",
            "=https", "--output", str(staged), url,
        ], check=True)
        if digest(staged, algorithm) != checksum:
            raise ValueError(f"Somme {algorithm} incorrecte pour {name}.")
        staged.replace(destination)


def java_version(executable):
    if not os.access(executable, os.X_OK):
        return None
    try:
        result = subprocess.run([executable, "-version"], stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r'version "(21(?:[.+-][^"]*)?)"', result.stdout)
    return match.group(1) if result.returncode == 0 and match else None


def find_java(root):
    for executable in (root / "bin/java", root / JRE / "bin/java",
                       *sorted(root.glob("*/bin/java"))):
        if java_version(executable):
            return executable
    return None


def install_java(runtime, asset):
    java = find_java(runtime)
    if java:
        return java
    runtime.mkdir(parents=True, exist_ok=True)
    destination = runtime / JRE
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Runtime Java invalide dans {destination}.")
    previous = find_java(OLD_JAVA)
    with TemporaryDirectory(dir=runtime, prefix=".java-") as directory:
        staging = Path(directory)
        if previous:
            print(f"Copie de Java 21 depuis {previous.parent.parent}", flush=True)
            extracted = staging / JRE
            shutil.copytree(previous.resolve().parent.parent, extracted, symlinks=True)
        else:
            archive = staging / "java.tar.gz"
            download(asset, archive)
            with tarfile.open(archive) as source:
                source.extractall(staging, filter="data")
            extracted = staging / f"jdk-{JRE.removeprefix('temurin-')}-jre"
        if not java_version(extracted / "bin/java"):
            raise ValueError("Java 21 ne démarre pas sur ce système.")
        extracted.rename(destination)
    return destination / "bin/java"


def java_fx_options(runtime):
    return ["--module-path", str(runtime / FX / "lib"), "--add-modules",
            "javafx.controls,javafx.fxml,javafx.media,javafx.web"]


def check_java_fx(java, runtime):
    result = subprocess.run([java, *java_fx_options(runtime), "--list-modules"],
                            capture_output=True, text=True, timeout=20)
    return result.returncode == 0 and "javafx.controls@" in result.stdout


def install_fx(java, runtime, asset):
    if check_java_fx(java, runtime):
        return
    destination = runtime / FX
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Runtime JavaFX invalide dans {destination}.")
    with TemporaryDirectory(dir=runtime, prefix=".javafx-") as directory:
        staging = Path(directory)
        archive = staging / "javafx.zip"
        download(asset, archive)
        with ZipFile(archive) as source:
            source.extractall(staging)
        (staging / "javafx-sdk-21.0.13.1").rename(destination)
        if not check_java_fx(java, runtime):
            shutil.rmtree(destination)
            raise ValueError("JavaFX ne démarre pas avec Java 21.")


def seed_profiles(work, java):
    path = work / "launcher_profiles.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    profiles = data.setdefault("profiles", {})
    date = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    for key, name, version, folder, icon in (
        ("partydeck-minecraft-split", "PartyDeck - Minecraft Coop", PROFILE, "coop", "Furnace"),
        ("partydeck-minecraft-vanilla", "PartyDeck - Minecraft Vanilla", "1.21.1", "vanilla", "Grass"),
    ):
        game = work.parent / folder
        game.mkdir(parents=True, exist_ok=True)
        profile = profiles.setdefault(key, {
            "name": name, "type": "custom", "gameDir": str(game), "icon": icon,
            "created": date, "lastUsed": date,
            "lastVersionId": version, "javaArgs": "-Xmx2G", "javaDir": str(java),
            "launcherVisibilityOnGameClose": "hide launcher and re-open when game closes",
        })
        # SKlauncher stores a selected Java executable with each installation.
        # Keep this reference current when Windows Party changes Java runtimes.
        profile["javaDir"] = str(java)
    write_atomic(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


def port_is_managed(path):
    if not os.path.lexists(path):
        return True
    if not stat.S_ISREG(path.lstat().st_mode):
        return False
    with path.open() as source:
        return source.readline() == "#!/bin/sh\n" and source.readline().strip() == PORT_MARKER


def install(root, ports, runtime):
    bundle = Path(__file__).resolve().parent
    port = ports / "PartyDeck - Minecraft Java.sh"
    if not port_is_managed(port):
        raise ValueError(f"Une entrée existe déjà dans {port}.")
    assets = json.loads((bundle / "downloads.json").read_text())
    java = install_java(runtime, assets["java"])
    install_fx(java, runtime, assets["javafx"])
    download(assets["launcher"], root / SK)
    coop = root / "coop"
    for asset in assets["mods"]:
        download(asset, coop / "mods" / unquote(asset[0].rsplit("/", 1)[1]))
    sdl = assets["sdl"]
    download(sdl, coop / "natives" / sdl[0].rsplit("/", 1)[1])
    legacy_options = coop / "config/legacy_options.txt"
    if not legacy_options.exists():
        write_atomic(legacy_options, b"lastLoadedVersion:1.7.4\nselectedControllerHandler:sdl3\n")
    work = root / "sklauncher"
    version_dir = work / "versions" / PROFILE
    definition = (bundle / f"{PROFILE}.json").read_bytes()
    target = version_dir / f"{PROFILE}.json"
    if not target.exists():
        write_atomic(target, definition)
    seed_profiles(work, java)
    for name in FILES:
        write_atomic(root / name, (bundle / name).read_bytes(), 0o755 if name.endswith(".py") else 0o644)
    command = shlex.join(["python3", str(root / FILES[0]), "jouer"])
    write_atomic(port, f"#!/bin/sh\n{PORT_MARKER}\nexec {command}\n".encode(), 0o755)
    print(f"Minecraft Java installé. Actualise la liste des jeux de Ports.\n{port}")


def graphical_env():
    env = os.environ.copy()
    keys = {"DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR",
            "DBUS_SESSION_BUS_ADDRESS", "PULSE_SERVER", "PIPEWIRE_REMOTE"}
    result = subprocess.run(["pidof", "emulationstation"], capture_output=True, text=True)
    for pid in result.stdout.split():
        try:
            entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            continue
        session = dict(os.fsdecode(item).split("=", 1) for item in entries if b"=" in item)
        if session.get("DISPLAY") or session.get("WAYLAND_DISPLAY"):
            for key in keys:
                if key in session:
                    env[key] = session[key]
                elif key in {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY"}:
                    env.pop(key, None)
            break
    env.setdefault("DISPLAY", ":0")
    # Use X11 windows so the split-screen mod can move them under Xorg and Xwayland.
    env.update(GDK_BACKEND="x11", GDK_SCALE="1", GDK_DPI_SCALE="1")
    return env


def screen_status(env):
    display = env["DISPLAY"]
    if not shutil.which("xrandr"):
        return f"DISPLAY={display} (xrandr indisponible)"
    result = subprocess.run(["xrandr", "--current"], env=env, capture_output=True,
                            text=True, timeout=10)
    if result.returncode:
        raise ValueError(f"Affichage X11 inaccessible sur DISPLAY={display}. Lance depuis Ports.")
    current = re.search(r"current (\d+) x (\d+)", result.stdout)
    if not current:
        return f"DISPLAY={display}"
    width, height = map(int, current.groups())
    detail = f"DISPLAY={display} ({width}×{height})"
    if width < 320 or height < 200:
        detail += " — XWayland signale une petite surface avant ouverture de la fenêtre."
    return detail


@contextmanager
def session_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "minecraft.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Une autre opération Minecraft est déjà en cours.") from error
        yield lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("installer", "jouer", "verifier"))
    args = parser.parse_args()
    if platform.machine() != "x86_64" or not shutil.which("batocera-version"):
        parser.exit(1, "Minecraft PartyDeck est prévu pour Batocera x86_64.\n")
    root = BASE / "minecraft"
    runtime = BASE / "runtime/java"
    try:
        with session_lock(root) as lock:
            if args.action == "installer":
                install(root, PORTS, runtime)
                return 0
            java = find_java(runtime)
            if not java or not check_java_fx(java, runtime) or not (root / SK).is_file():
                raise ValueError("Installation incomplète. Relance l’installateur Minecraft.")
            env = graphical_env()
            print(f"Java {java_version(java)} · {java}\n{screen_status(env)}", flush=True)
            if args.action == "verifier":
                print(f"JavaFX · {runtime / FX}\nSKlauncher · {root / SK}")
                return 0
            # SKlauncher loads JavaFX on the classpath and uses some of its internal APIs.
            javafx = sorted((runtime / FX / "lib").glob("javafx.*.jar"))
            classpath = os.pathsep.join(map(str, [root / SK, *javafx]))
            command = [java, "-Djava.awt.headless=false", "-cp", classpath,
                       "pl.skmedix.bootstrap.Main", "--workDir", root / "sklauncher"]
            env["JAVA_HOME"] = str(java.parent.parent)
            env["PATH"] = f"{java.parent}:{env.get('PATH', os.defpath)}"
            # Preserve the lock for the launcher's lifetime, including when launched from Ports.
            os.set_inheritable(lock.fileno(), True)
            os.chdir(root)
            os.execve(java, command, env)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        parser.exit(1, f"Minecraft PartyDeck : {error}\n")


if __name__ == "__main__":
    sys.exit(main())
