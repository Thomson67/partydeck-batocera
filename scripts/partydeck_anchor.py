"""SoH Anchor adapter; configuration is applied inside each private Wine view."""
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import uuid


def defaults():
    return dict(enabled=True, host="anchor.hm64.org", port=43383,
                room="windows-party-" + uuid.uuid4().hex[:12],
                config="shipofharkinian.json", pvp=0, locations=1, teleport=1, sync=True,
                names=[f"Joueur{i}" for i in range(1, 5)], teams=["default"] * 4)


def validate(settings):
    if not isinstance(settings, dict):
        raise ValueError("Profil Anchor invalide.")
    for key in ("host", "room", "config"):
        if not isinstance(settings.get(key), str) or not settings[key].strip():
            raise ValueError(f"Champ Anchor vide ou invalide : {key}")
    relative = PurePosixPath(settings["config"])
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".json":
        raise ValueError("Le fichier SoH doit être un chemin JSON relatif au dossier de lancement.")
    if type(settings.get("port")) is not int or not 1024 < settings["port"] < 65535:
        raise ValueError("Le port Anchor doit être compris entre 1025 et 65534.")
    for key in ("enabled", "sync"):
        if type(settings.get(key)) is not bool:
            raise ValueError(f"Option Anchor invalide : {key}")
    for key in ("pvp", "locations", "teleport"):
        if type(settings.get(key)) is not int or settings[key] not in (0, 1, 2):
            raise ValueError(f"Mode Anchor invalide : {key}")
    for key in ("names", "teams"):
        values = settings.get(key)
        if (not isinstance(values, list) or len(values) != 4
                or any(not isinstance(v, str) or not v.strip() for v in values)):
            raise ValueError("Définissez un nom et une équipe pour chacun des quatre joueurs.")
    if len(set(settings["names"])) != 4:
        raise ValueError("Chaque joueur doit avoir un nom différent.")
    return settings


def apply_config(directory, payload):
    from partydeck_profiles import atomic_write
    settings = validate(payload["settings"])
    index = payload["index"]
    if type(index) is not int or index not in range(4):
        raise ValueError("Numéro de joueur Anchor invalide.")
    directory = directory.resolve()
    path = directory / settings["config"]
    # Never follow a config directory into a solo save or another player's view.
    cursor = directory
    for part in PurePosixPath(settings["config"]).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"Configuration SoH liée à un autre emplacement : {cursor}")
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data, dict):
        raise ValueError("La configuration SoH doit être un objet JSON.")
    anchor = data
    for key in ("CVars", "gRemote", "Anchor"):
        anchor = anchor.setdefault(key, {})
        if not isinstance(anchor, dict):
            raise ValueError(f"Structure SoH invalide : {key}")
    anchor.update(Enabled=int(settings["enabled"]), Host=settings["host"], Port=settings["port"],
                  RoomId=settings["room"], Name=settings["names"][index], TeamId=settings["teams"][index])
    rules = anchor.setdefault("RoomSettings", {})
    if not isinstance(rules, dict):
        raise ValueError("Structure SoH invalide : RoomSettings")
    rules.update(PvpMode=settings["pvp"], ShowLocationsMode=settings["locations"],
                 TeleportMode=settings["teleport"], SyncItemsAndFlags=int(settings["sync"]))
    # Discard a copied solo identity once, then keep the server-assigned ID on
    # subsequent launches. Each player has a separate persistent stamp.
    stamp = Path(payload["identity_stamp"]) if payload.get("identity_stamp") else None
    identity = json.dumps([settings["host"], settings["port"], settings["room"], settings["names"][index]])
    if stamp is None or not stamp.exists() or stamp.read_text() != identity:
        anchor["LastClientId"] = 0
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if stamp is not None:
        atomic_write(stamp, identity)
    print(f"Anchor J{index + 1} : configuration appliquée (connexion={settings['enabled']}).", flush=True)


def instrument_native(source, hook):
    # The native launcher selects/mounts the ROM and its saves before these cd
    # statements. Run the adapter synchronously there, before Wine/UMU starts.
    # Fail closed if a future Batocera changes this contract.
    pattern = re.compile(r'(\(cd "\$\{(?:WINEPOINT|GAMENAME)\}/\$\{WINE_DIR\}" && )')
    functions = re.split(r'(?m)^(?=\w+\(\) \{)', source)
    for name in ("play_wine", "play_pc", "play_squashfs"):
        bodies = [body for body in functions if body.startswith(name + "() {")]
        if len(bodies) != 1 or len(pattern.findall(bodies[0])) != 2:
            raise RuntimeError(f"Lanceur batocera-wine non reconnu ({name}) : adaptateur Anchor refusé.")
    rewritten, count = pattern.subn(lambda m: m[0] + shlex.join(hook) + ' "$PWD" && ', source)
    if count < 6:
        raise RuntimeError("Lanceur batocera-wine non reconnu : profil Anchor non appliqué. Aucune modification système effectuée.")
    return rewritten


def install_hook(base, rom, player):
    from partydeck_profiles import profile_path, read_profile, atomic_write
    if not profile_path(base, rom).exists():
        return
    profile = read_profile(base, rom)
    if profile.get("adapter", "standard") != "soh-anchor":
        return
    settings = validate(profile["anchor"])
    index = int(player.name.removeprefix("j")) - 1
    payload = player / "anchor-launch.json"
    atomic_write(payload, json.dumps(dict(settings=settings, index=index,
                                         identity_stamp=str(player / "anchor-identity.json"))))
    binary = shutil.which("batocera-wine")
    if not binary:
        raise RuntimeError("batocera-wine introuvable.")
    binary = Path(binary).resolve()
    hook = [sys.executable, str(base / "partydeck_anchor.py"), str(payload)]
    replacement = player / "batocera-wine-anchor"
    atomic_write(replacement, instrument_native(binary.read_text(), hook), 0o755)
    subprocess.run(["bash", "-n", str(replacement)], check=True)
    # Only this player's mount namespace sees this copy; preserve native $0,
    # per-ROM runner selection, mounting and the original solo installation.
    subprocess.run(["mount", "--bind", str(replacement), str(binary)], check=True)


if __name__ == "__main__":
    try:
        apply_config(Path(sys.argv[2]), json.loads(Path(sys.argv[1]).read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Windows Party / Anchor : {error}", file=sys.stderr)
        raise SystemExit(1)
