#!/usr/bin/env python3
"""Install and run the native Minecraft 26.3 Couchcraft port."""

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from partydeck_minecraft import (
    BASE, PORT_MARKER, PORTS, download, graphical_env, port_is_managed,
    screen_status, session_lock, write_atomic,
)

VERSION = "26.3"
APP = "CLauncher-1.0.3"
JAVA = "25.0.5.1+2"
MOD = "couchcraft-0.2.0.jar"
INSTANCE = "Couchcraft"
BUNDLE = Path(__file__).resolve().parent
PORT = "PartyDeck - Minecraft 26.3 (Couchcraft).sh"
JVM_OPTIONS = "-Dfabric.debug.disableModIds=sodium,iris"


def install_java25(runtime, asset):
    destination = runtime / f"temurin-{JAVA}"
    java = destination / "bin/java"
    if java.is_file():
        check_java25(java)
        return java
    runtime.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=runtime, prefix=".java25-") as directory:
        staging = Path(directory)
        archive = staging / "java25.tar.gz"
        download(asset, archive)
        with tarfile.open(archive) as source:
            source.extractall(staging, filter="data")
        extracted = staging / f"jdk-{JAVA}-jre"
        check_java25(extracted / "bin/java")
        extracted.rename(destination)
    return java


def check_java25(executable):
    result = subprocess.run([executable, "-version"], capture_output=True, text=True,
                            timeout=15, check=True)
    version = re.search(r'version "(25(?:[.+-][^"]*)?)"', result.stderr + result.stdout)
    if not version:
        raise ValueError(f"Java 25 attendu dans {executable}.")
    return version.group(1)


def install_clauncher(root, asset):
    destination = root / APP
    if (destination / "AppRun").is_file():
        return
    with TemporaryDirectory(dir=root, prefix=".clauncher-") as directory:
        staging = Path(directory)
        archive = staging / "clauncher.zip"
        download(asset, archive)
        image = staging / "CLauncher.AppImage"
        # Upstream's release ZIP contains a second ZIP with the AppImage.
        with ZipFile(archive) as outer, ZipFile(BytesIO(outer.read("CLauncher-Linux.zip"))) as inner:
            image.write_bytes(inner.read("CLauncher-Linux/CLauncher-x86_64.AppImage"))
        image.chmod(0o755)
        subprocess.run([image, "--appimage-extract"], cwd=staging, check=True,
                       stdout=subprocess.DEVNULL, timeout=60)
        extracted = staging / "squashfs-root"
        if not os.access(extracted / "AppRun", os.X_OK):
            raise ValueError("Exécutable absent de l’AppImage CLauncher.")
        extracted.rename(destination)


def data_dir(root):
    return root / "home/.clauncher"


def seed_instance(data, java):
    instance = data / "instances" / INSTANCE
    manifest = instance / "instance.json"
    profile = json.loads(manifest.read_text()) if manifest.exists() else {
        "name": INSTANCE, "mc_version": VERSION, "version_id": VERSION,
        "mod_loader": "fabric", "memory_mb": 4096, "nickname": "Joueur1",
    }
    profile["java_path"] = str(java)
    write_atomic(manifest, (json.dumps(profile, indent=2) + "\n").encode())
    settings = data / "launcher_settings.json"
    if not settings.exists():
        defaults = {"nickname": profile["nickname"], "selected_version": VERSION,
                    "mod_loader": 1, "lang": "en", "memory_index": 4}
        write_atomic(settings, (json.dumps(defaults, indent=2) + "\n").encode())

    # CLauncher uses its managed runtime path for installing Fabric even when its
    # game instance already specifies a custom Java executable.
    java_link = data / "runtime/java25"
    java_link.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(java_link):
        java_link.symlink_to(java.parent.parent, target_is_directory=True)
    elif java_link.is_symlink() and java_link.resolve() != java.parent.parent.resolve():
        raise ValueError(f"Lien Java inattendu dans {java_link}.")
    elif not java_link.is_symlink():
        check_java25(java_link / "bin/java")

    return instance / ".minecraft"


def install(root, ports, runtime):
    port = ports / PORT
    if not port_is_managed(port):
        raise ValueError(f"Une entrée existe déjà dans {port}.")
    assets = json.loads((BUNDLE / "couchcraft-downloads.json").read_text())
    java = install_java25(runtime, assets["java"])
    install_clauncher(root, assets["launcher"])
    data = data_dir(root)
    game = seed_instance(data, java)
    download(assets["fabric"], data / "cache/fabric-installer.jar")
    download(assets["couchcraft"], game / "mods" / MOD)
    for name in (Path(__file__).name, "partydeck_minecraft.py"):
        write_atomic(root / name, (BUNDLE / name).read_bytes(), 0o755)
    command = shlex.join(["python3", str(root / Path(__file__).name), "jouer"])
    write_atomic(port, f"#!/bin/sh\n{PORT_MARKER}\nexec {command}\n".encode(), 0o755)
    print(f"Couchcraft installé. Actualise les listes dans EmulationStation.\n{port}")


def launcher_env(root):
    env = graphical_env()
    if "XAUTHORITY" not in env:
        authority = Path.home() / ".Xauthority"
        if authority.is_file():
            env["XAUTHORITY"] = str(authority)
    env.update(HOME=str(root / "home"), APPDIR=str(root / APP))
    # The upstream launcher ticks its performance mods option on every startup.
    # Fabric skips these conflicting mod IDs even if the launcher downloads them.
    previous = env.get("JAVA_TOOL_OPTIONS", "").strip()
    env["JAVA_TOOL_OPTIONS"] = f"{previous} {JVM_OPTIONS}".lstrip()
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("installer", "jouer", "verifier"))
    args = parser.parse_args()
    if platform.machine() != "x86_64" or not shutil.which("batocera-version"):
        parser.exit(1, "Minecraft Couchcraft est prévu pour Batocera x86_64.\n")

    root = BASE / "minecraft/couchcraft"
    runtime = BASE / "runtime/java"
    try:
        with session_lock(root) as lock:
            if args.action == "installer":
                install(root, PORTS, runtime)
                return 0
            app = root / APP / "AppRun"
            java = runtime / f"temurin-{JAVA}/bin/java"
            version = check_java25(java)
            env = launcher_env(root)
            print(f"Java {version} · {java}\n{screen_status(env)}", flush=True)
            if not app.is_file():
                raise ValueError("CLauncher est introuvable. Relance l’installateur.")
            if args.action == "verifier":
                print(f"CLauncher · {app}\nDonnées · {data_dir(root)}")
                return 0
            # Hold the lock until CLauncher exits, including its game session.
            os.set_inheritable(lock.fileno(), True)
            os.chdir(root)
            os.execve(app, [app], env)
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError, BadZipFile) as error:
        parser.exit(1, f"Minecraft Couchcraft : {error}\n")


if __name__ == "__main__":
    sys.exit(main())
