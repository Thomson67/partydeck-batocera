"""SoH Anchor adapter; configuration is applied inside each private Wine view."""
from partydeck_i18n import tr
import json
import copy
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import sys
import uuid

VOLUME_FIELDS = (("Master", "Volume général"), ("MainMusic", "Musique principale"),
                 ("SubMusic", "Musique secondaire"), ("Fanfare", "Fanfares"),
                 ("SFX", "Bruitages et voix"))


def defaults():
    return dict(enabled=True, host="anchor.hm64.org", port=43383,
                room="windows-party-" + uuid.uuid4().hex[:12],
                config="shipofharkinian.json", pvp=0, locations=1, teleport=1, sync=True,
                names=[tr('Joueur{p0}', p0=i) for i in range(1, 5)], teams=["default"] * 4)


def graphics_defaults():
    return dict(internal_resolution=1.0, msaa=4, vsync=True, texture_filter=0,
                music_j1_only=True)


def validate_graphics(options):
    if (not isinstance(options, dict)
            or type(options.get("internal_resolution")) not in (float, int)
            or not 0.5 <= options["internal_resolution"] <= 2.0
            or type(options.get("msaa")) is not int or not 1 <= options["msaa"] <= 8
            or type(options.get("vsync")) is not bool
            or type(options.get("music_j1_only")) is not bool
            or type(options.get("texture_filter")) is not int
            or options["texture_filter"] not in (0, 1, 2)):
        raise ValueError(tr("Options graphiques ou audio SoH invalides."))
    volumes = options.get("volumes", {})
    if (not isinstance(volumes, dict) or any(key not in dict(VOLUME_FIELDS) for key in volumes)
            or any(type(value) is not int or not 0 <= value <= 100 for value in volumes.values())):
        raise ValueError(tr("Les volumes SoH doivent être des entiers de 0 à 100 %."))
    return options


def validate(settings):
    if not isinstance(settings, dict):
        raise ValueError(tr("Profil Anchor invalide."))
    for key in ("host", "room", "config"):
        if not isinstance(settings.get(key), str) or not settings[key].strip():
            raise ValueError(tr('Champ Anchor vide ou invalide : {p0}', p0=key))
    relative = PurePosixPath(settings["config"])
    if relative.is_absolute() or ".." in relative.parts or relative.suffix.lower() != ".json":
        raise ValueError(tr("Le fichier SoH doit être un chemin JSON relatif au dossier de lancement."))
    if type(settings.get("port")) is not int or not 1024 < settings["port"] < 65535:
        raise ValueError(tr("Le port Anchor doit être compris entre 1025 et 65534."))
    for key in ("enabled", "sync"):
        if type(settings.get(key)) is not bool:
            raise ValueError(tr('Option Anchor invalide : {p0}', p0=key))
    for key in ("pvp", "locations", "teleport"):
        if type(settings.get(key)) is not int or settings[key] not in (0, 1, 2):
            raise ValueError(tr('Mode Anchor invalide : {p0}', p0=key))
    for key in ("names", "teams"):
        values = settings.get(key)
        if (not isinstance(values, list) or len(values) != 4
                or any(not isinstance(v, str) or not v.strip() for v in values)):
            raise ValueError(tr("Définissez un nom et une équipe pour chacun des quatre joueurs."))
    if len(set(settings["names"])) != 4:
        raise ValueError(tr("Chaque joueur doit avoir un nom différent."))
    validate_graphics(settings.get("graphics", graphics_defaults()))
    return settings


def apply_config(directory, payload):
    from partydeck_profiles import atomic_write
    settings = validate(payload["settings"])
    index = payload["index"]
    if type(index) is not int or index not in range(4):
        raise ValueError(tr("Numéro de joueur Anchor invalide."))
    directory = directory.resolve()
    path = directory / settings["config"]
    # Never follow a config directory into a solo save or another player's view.
    cursor = directory
    for part in PurePosixPath(settings["config"]).parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(tr('Configuration SoH liée à un autre emplacement : {p0}', p0=cursor))
    previous = json.loads(path.read_text()) if path.exists() else {}
    data = copy.deepcopy(payload["template"]) if "template" in payload else previous
    if not isinstance(data, dict) or not isinstance(previous, dict):
        raise ValueError(tr("La configuration SoH doit être un objet JSON."))
    if "template" in payload and path.exists():
        backup = Path(payload["identity_stamp"]).parent / "soh-before-common.json"
        if not backup.exists():
            atomic_write(backup, json.dumps(previous, ensure_ascii=False, indent=2) + "\n")
    anchor = data
    for key in ("CVars", "gRemote", "Anchor"):
        anchor = anchor.setdefault(key, {})
        if not isinstance(anchor, dict):
            raise ValueError(tr('Structure SoH invalide : {p0}', p0=key))
    anchor.update(Enabled=int(settings["enabled"]), Host=settings["host"], Port=settings["port"],
                  RoomId=settings["room"], Name=settings["names"][index], TeamId=settings["teams"][index])
    rules = anchor.setdefault("RoomSettings", {})
    if not isinstance(rules, dict):
        raise ValueError(tr("Structure SoH invalide : RoomSettings"))
    rules.update(PvpMode=settings["pvp"], ShowLocationsMode=settings["locations"],
                 TeleportMode=settings["teleport"], SyncItemsAndFlags=int(settings["sync"]))
    # Discard a copied solo identity once, then keep the server-assigned ID on
    # subsequent launches. Each player has a separate persistent stamp.
    stamp = Path(payload["identity_stamp"]) if payload.get("identity_stamp") else None
    identity = json.dumps([settings["host"], settings["port"], settings["room"], settings["names"][index]])
    if stamp is None or not stamp.exists() or stamp.read_text() != identity:
        anchor["LastClientId"] = 0
    elif "template" in payload:
        anchor["LastClientId"] = previous.get("CVars", {}).get("gRemote", {}).get("Anchor", {}).get("LastClientId", 0)
    if "template" in payload:
        options = validate_graphics(settings.get("graphics", graphics_defaults()))
        graphics = data["CVars"].setdefault("gSettings", {})
        graphics.update(InternalResolution=float(options["internal_resolution"]),
                        MSAAValue=options["msaa"], VsyncEnabled=int(options["vsync"]),
                        TextureFilter=options["texture_filter"])
        # Advanced fixed/pixel-perfect resolution overrides the normal scale
        # slider in SoH. Disable it so the selected multiplier actually applies.
        advanced = graphics.setdefault("AdvancedResolution", {})
        advanced.update(Enabled=0, VerticalResolutionToggle=0, PixelPerfectMode=0)
        # Apply the selected common mix first. J1-only music takes precedence
        # over those levels on the other players, without muting their SFX.
        graphics.setdefault("Volume", {}).update(options.get("volumes", {}))
        if options["music_j1_only"] and index > 0:
            graphics.setdefault("Volume", {}).update(MainMusic=0, SubMusic=0, Fanfare=0)
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    if stamp is not None:
        atomic_write(stamp, identity)
    print(tr('Anchor J{p0} : configuration appliquée (connexion={p1}).', p0=index + 1, p1=settings['enabled']), flush=True)


def instrument_native(source, hook, prefix_argument=False):
    # The native launcher selects/mounts the ROM and its saves before these cd
    # statements. Run the adapter synchronously there, before Wine/UMU starts.
    # Fail closed if a future Batocera changes this contract.
    pattern = re.compile(r'(\(cd "\$\{(?:WINEPOINT|GAMENAME)\}/\$\{WINE_DIR\}" && )')
    functions = re.split(r'(?m)^(?=\w+\(\) \{)', source)
    for name in ("play_wine", "play_pc", "play_squashfs"):
        bodies = [body for body in functions if body.startswith(name + "() {")]
        if len(bodies) != 1 or len(pattern.findall(bodies[0])) != 2:
            raise RuntimeError(tr('Lanceur batocera-wine non reconnu ({p0}) : adaptateur de jeu refusé.', p0=name))
    arguments = ' "$PWD"' + (' "${WINEPOINT:-${GAMENAME}}"' if prefix_argument else '')
    rewritten, count = pattern.subn(lambda m: m[0] + shlex.join(hook) + arguments + ' && ', source)
    if count < 6:
        raise RuntimeError(tr("Lanceur batocera-wine non reconnu : profil non appliqué. Aucune modification système effectuée."))
    return rewritten


def install_hook(base, rom, player):
    from partydeck_profiles import profile_path, read_profile, atomic_write
    if not profile_path(base, rom).exists():
        return
    profile = read_profile(base, rom)
    if profile.get("adapter", "standard") != "soh-anchor":
        return
    settings = validate(profile["anchor"])
    template = base / "templates" / "soh-common.json"
    if not template.is_file():
        raise ValueError(tr("JSON commun SoH absent : réinstallez Windows Party."))
    common = json.loads(template.read_text())
    if not isinstance(common, dict) or not isinstance(common.get("CVars"), dict):
        raise ValueError(tr("Le JSON commun SoH est invalide."))
    index = int(player.name.removeprefix("j")) - 1
    payload = player / "anchor-launch.json"
    atomic_write(payload, json.dumps(dict(settings=settings, index=index, template=common,
                                         identity_stamp=str(player / "anchor-identity.json"))))
    binary = shutil.which("batocera-wine")
    if not binary:
        raise RuntimeError(tr("batocera-wine introuvable."))
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
