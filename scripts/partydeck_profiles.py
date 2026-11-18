#!/usr/bin/env python3
"""Persistent Windows Party profiles and their optional graphical editor."""
from partydeck_i18n import tr, choice_label
import hashlib
import fcntl
import html
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

ROM_TYPES = {".wine", ".pc", ".wsquashfs"}
MARKER = "# Entrée gérée par PartyDeck Wine"
PARTY_ROMS = Path("/userdata/roms/windows-party")


def profile_path(base, rom):
    digest = hashlib.sha256(os.fsencode(rom)).hexdigest()[:16]
    return base / "profiles" / f"{digest}.json"


def defaults(rom):
    data = dict(version=1, rom=str(rom), players="auto", split="horizontal",
                input="auto", configure_before_launch=False, keyboard_player=True)
    from partydeck_borderlands2 import matches, defaults as bl2_defaults
    if matches(rom):
        data.update(adapter='borderlands2',borderlands2=bl2_defaults())
    from partydeck_sm64coopdx import matches as matches_sm64, defaults as sm64_defaults
    if matches_sm64(rom):
        data.update(adapter='sm64coopdx',sm64coopdx=sm64_defaults())
    from partydeck_l4d2 import matches as matches_l4d2, defaults as l4d2_defaults
    if matches_l4d2(rom):
        data.update(adapter='l4d2-goldberg',l4d2=l4d2_defaults())
    return data


def validate(data, rom):
    if (not isinstance(data, dict) or data.get("version") != 1
            or data.get("rom") != str(rom)
            or data.get("players") not in ("auto", "1", "2", "3", "4")
            or data.get("split") not in ("horizontal", "vertical")
            or data.get("input") not in ("auto", "clavier-j1", "clavier-j2")
            or type(data.get("configure_before_launch")) is not bool):
        raise ValueError(tr('Profil Windows Party invalide pour {p0}', p0=rom))
    if type(data.get("keyboard_player", True)) is not bool:
        raise ValueError(tr("Option clavier comme joueur invalide."))
    if data.get("adapter", "standard") not in ("standard", "soh-anchor", "borderlands2", "sm64coopdx", "l4d2-goldberg"):
        raise ValueError(tr("Adaptateur Windows Party inconnu."))
    if data.get("adapter") == "soh-anchor":
        from partydeck_anchor import validate as validate_anchor
        validate_anchor(data.get("anchor"))
    if data.get('adapter') == 'borderlands2':
        from partydeck_borderlands2 import validate as validate_bl2
        data['borderlands2'] = validate_bl2(data.get('borderlands2'))
    if data.get('adapter') == 'sm64coopdx':
        from partydeck_sm64coopdx import validate as validate_sm64
        data['sm64coopdx'] = validate_sm64(data.get('sm64coopdx'))
    if data.get('adapter') == 'l4d2-goldberg':
        from partydeck_l4d2 import validate as validate_l4d2
        data['l4d2'] = validate_l4d2(data.get('l4d2'))
    return data


def read_profile(base, rom):
    path = profile_path(base, rom)
    if path.is_symlink():
        raise ValueError(tr('Le profil est un lien symbolique : {p0}', p0=path))
    return validate(json.loads(path.read_text()), rom)


def atomic_write(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(tr('Le fichier est un lien symbolique : {p0}', p0=path))
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".partydeck-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            temporary.chmod(mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def save_profile(base, rom, data):
    validate(data, rom)
    atomic_write(profile_path(base, rom), json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def prepare_profile(base, rom, count, split, input_mode):
    path = profile_path(base, rom)
    data = read_profile(base, rom) if path.exists() or path.is_symlink() else defaults(rom)
    data.update(players=count, split=split, input=input_mode)
    save_profile(base, rom, data)


def remove_profile(base, rom, roms=None):
    """Remove only our generated launcher and its settings; never ROM/save data."""
    roms = PARTY_ROMS if roms is None else roms
    with (base/'test.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(tr('Attendez la fin de la session ou de l’installation avant de retirer ce jeu.')) from None
        path = profile_path(base,rom)
        if path.exists() or path.is_symlink():
            read_profile(base,rom)
        digest = hashlib.sha256(os.fsencode(rom)).hexdigest()[:10]
        entry = roms/f'{rom.stem[:90]} [{digest}].sh'
        if entry.is_symlink():
            raise ValueError(tr('Le lanceur est un lien utilisateur ; retrait refusé.'))
        if entry.exists():
            lines = entry.read_text().splitlines()
            command = shlex.split(lines[2]) if len(lines) == 3 else []
            expected = ['exec',str(base/'partydeck-test'),'profil',str(rom)]
            legacy = len(command)==7 and command[:4] == ['exec',str(base/'partydeck-test'),'party',str(rom)]
            if len(lines)!=3 or lines[1]!=MARKER or (command!=expected and not legacy):
                raise ValueError(tr('Le lanceur a été personnalisé ; retrait automatique refusé.'))
        previous = entry.read_text() if entry.exists() else None
        entry.unlink(missing_ok=True)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            if previous is not None:
                atomic_write(entry,previous,0o755)
            raise


def yad(arguments):
    binary = shutil.which("yad")
    if binary is None:
        raise RuntimeError(tr("Yad est requis pour l'éditeur graphique. Les profils JSON restent modifiables dans le dossier profiles."))
    return subprocess.run([binary, "--title=Windows Party", "--center", "--on-top",
                           *arguments], text=True, stdout=subprocess.PIPE)


def edit_profile(base, rom):
    if os.environ.get("PARTYDECK_UI") == "legacy":
        return edit_profile_legacy(base, rom)
    from partydeck_couch import configure as couch_configure
    return couch_configure(base, rom, single=True)


def edit_profile_legacy(base, rom):
    if shutil.which("batocera-mouse"):
        subprocess.run(["batocera-mouse", "show"], check=False)
    path = profile_path(base, rom)
    data = read_profile(base, rom) if path.exists() or path.is_symlink() else defaults(rom)
    def choices(key, values):
        return "!".join(choice_label(key,v) for v in [data[key], *(v for v in values if v != data[key])])
    result = yad(["--form", "--width=620", "--separator=\x1f",
                  "--text=" + html.escape(rom.name),
                  tr("--field=Joueurs:CB"), choices("players", ["auto", "1", "2", "3", "4"]),
                  tr("--field=Disposition:CB"), choices("split", ["horizontal", "vertical"]),
                  tr("--field=Entrées:CB"), choices("input", ["auto", "clavier-j1", "clavier-j2"]),
                  tr("--field=Afficher ces réglages avant chaque lancement:CHK"),
                  str(data["configure_before_launch"]).upper(),
                  tr("--button=Annuler:1"), "--button=SoH / Anchor:2", tr("--button=Enregistrer:0")])
    if result.returncode in {1, 252}:
        return False
    if result.returncode not in {0, 2}:
        raise RuntimeError(tr("Impossible d'ouvrir l'éditeur Yad (code {p0}).", p0=result.returncode))
    fields = result.stdout.rstrip("\n").split("\x1f")
    if len(fields) == 5 and not fields[-1]:
        fields.pop()
    if len(fields) != 4 or fields[3].upper() not in {"TRUE", "FALSE"}:
        raise ValueError(tr("Réponse de l'éditeur Windows Party invalide."))
    for index,(key,raw) in enumerate((('players',['auto','1','2','3','4']),('split',['horizontal','vertical']),
                                      ('input',['auto','clavier-j1','clavier-j2']))):
        fields[index] = {choice_label(key,v):v for v in raw}.get(fields[index],fields[index])
    data.update(players=fields[0], split=fields[1], input=fields[2],
                configure_before_launch=fields[3].upper() == "TRUE")
    if result.returncode == 2 and not edit_anchor(data):
        return False
    save_profile(base, rom, data)
    return True


def edit_anchor(data):
    from partydeck_anchor import defaults as anchor_defaults, validate as validate_anchor
    settings = dict(data.get("anchor") or anchor_defaults())
    labels = {
        "pvp": [tr("Désactivé"), tr("Activé"), tr("Activé + tirs alliés")],
        "locations": [tr("Personne"), tr("Même équipe"), tr("Tous")],
        "teleport": [tr("Personne"), tr("Même équipe"), tr("Tous")],
    }
    fields = ["--form", "--width=960", "--columns=2", "--separator=\x1f",
              tr("--text=SoH / Anchor — règles communes et identité de chaque joueur.\n"
              "Les règles de salle dépendent des droits administrateur sur le serveur.\n"
              "Le chemin JSON est relatif au dossier de lancement du jeu."),
              tr("--field=Gérer ce jeu avec le profil Anchor:CHK"), str(data.get("adapter") == "soh-anchor").upper(),
              tr("--field=Connexion automatique:CHK"), str(settings["enabled"]).upper(),
              tr("--field=Room ID commun"), settings["room"],
              tr("--field=Serveur"), settings["host"],
              tr("--field=Port"), str(settings["port"]),
              tr("--field=Configuration SoH (chemin relatif)"), settings["config"]]
    for key, label in (("pvp", tr("PvP")), ("locations", tr("Afficher les positions")), ("teleport", tr("Autoriser la téléportation"))):
        values = labels[key]
        current = values[settings[key]]
        fields.extend([f"--field={label}:CB", "!".join([current, *(v for v in values if v != current)])])
    fields.extend([tr("--field=Synchroniser objets et progression:CHK"), str(settings["sync"]).upper()])
    for index in range(4):
        fields.extend([tr('--field=J{p0} — nom', p0=index + 1), settings["names"][index],
                       tr('--field=J{p0} — Team ID', p0=index + 1), settings["teams"][index]])
    result = yad([*fields, tr("--button=Annuler:1"), tr("--button=Graphismes / Audio:2"), tr("--button=Enregistrer:0")])
    if result.returncode in {1, 252}:
        return False
    if result.returncode not in {0, 2}:
        raise RuntimeError(tr("Impossible d'ouvrir les paramètres Anchor."))
    values = result.stdout.rstrip("\n").split("\x1f")
    if values and not values[-1]:
        values.pop()
    if len(values) != 18 or any(values[i].upper() not in {"TRUE", "FALSE"} for i in (0, 1, 9)):
        raise ValueError(tr("Réponse de l'éditeur Anchor invalide."))
    settings.update(enabled=values[1].upper() == "TRUE", room=values[2], host=values[3],
                    port=int(values[4]), config=values[5], sync=values[9].upper() == "TRUE",
                    names=values[10::2], teams=values[11::2])
    for index, key in enumerate(("pvp", "locations", "teleport"), 6):
        settings[key] = labels[key].index(values[index])
    validate_anchor(settings)
    if result.returncode == 2 and not edit_soh_graphics(settings):
        return False
    data.update(adapter="soh-anchor" if values[0].upper() == "TRUE" else "standard", anchor=settings)
    return True


def edit_soh_graphics(settings):
    from partydeck_anchor import graphics_defaults, validate_graphics, VOLUME_FIELDS
    current = settings.get("graphics", graphics_defaults())
    filters = [tr("Trois points (N64)"), tr("Linéaire"), tr("Aucun")]
    selected = filters[current["texture_filter"]]
    arguments = ["--form", "--width=700", "--separator=\x1f",
                  tr("--text=Réglages communs à tous les joueurs SoH.\n"
                  "Résolution interne : multiplicateur de la fenêtre de chaque joueur.\n"
                  "La musique peut être réservée à J1 ; les bruitages restent actifs pour tous.\n"
                  "Volumes : de 0 à 100 %, ou vide pour conserver la valeur du JSON commun.\n"
                  "SoH regroupe les voix et les bruitages dans le même volume."),
                  tr("--field=Résolution interne (0,5 à 2)"), str(current["internal_resolution"]),
                  tr("--field=Anti-aliasing MSAA (1 = désactivé, 2 à 8)"), str(current["msaa"]),
                  tr("--field=VSync:CHK"), str(current["vsync"]).upper(),
                  tr("--field=Filtre des textures:CB"), "!".join([selected, *(v for v in filters if v != selected)]),
                  tr("--field=Musique uniquement pour J1:CHK"), str(current["music_j1_only"]).upper()]
    for key, label in VOLUME_FIELDS:
        arguments.extend([f"--field={tr(label)} (%)", str(current.get("volumes", {}).get(key, ""))])
    result = yad([*arguments, tr("--button=Annuler:1"), tr("--button=Enregistrer:0")])
    if result.returncode in {1, 252}:
        return False
    if result.returncode:
        raise RuntimeError(tr("Impossible d'ouvrir les réglages graphiques SoH."))
    values = result.stdout.rstrip("\n").split("\x1f")
    if values and not values[-1]:
        values.pop()
    if len(values) != 10 or any(values[i].upper() not in {"TRUE", "FALSE"} for i in (2, 4)):
        raise ValueError(tr("Réponse des réglages graphiques SoH invalide."))
    options = dict(internal_resolution=float(values[0].replace(",", ".")),
                                                msaa=int(values[1]), vsync=values[2].upper() == "TRUE",
                                                texture_filter=filters.index(values[3]),
                   music_j1_only=values[4].upper() == "TRUE")
    volumes = {key: int(value.strip()) for (key, _), value in zip(VOLUME_FIELDS, values[5:]) if value.strip()}
    if volumes:
        options["volumes"] = volumes
    settings["graphics"] = validate_graphics(options)
    return True


def launch_profile(base, rom):
    path = profile_path(base, rom)
    missing = not path.exists()
    data = defaults(rom) if missing else read_profile(base, rom)
    if missing or data["configure_before_launch"]:
        if not edit_profile(base, rom):
            return 0
        data = read_profile(base, rom)
    command = [str(base / "partydeck-test"), "party", str(rom),
               data["players"], data["split"], data["input"]]
    os.execv(command[0], command)


def install_menu(base, roms=PARTY_ROMS):
    # Upgrade only the exact command format produced by the previous installer.
    # JSON data already edited by the user takes priority on reinstall.
    for entry in sorted(roms.glob("*.sh")):
        if entry.is_symlink():
            continue
        lines = entry.read_text().splitlines()
        if len(lines) != 3 or lines[1] != MARKER or not lines[2].startswith("exec "):
            continue
        command = shlex.split(lines[2])
        if len(command) != 7 or command[:3] != ["exec", str(base / "partydeck-test"), "party"]:
            continue
        rom = Path(command[3])
        path = profile_path(base, rom)
        if not path.exists() and not path.is_symlink():
            prepare_profile(base, rom, *command[4:])
        else:
            read_profile(base, rom)
        atomic_write(entry, f"#!/bin/bash\n{MARKER}\nexec " +
                     shlex.join([str(base / "partydeck-test"), "profil", str(rom)]) + "\n", 0o755)
    menu = roms / "Configurer Windows Party.sh"
    marker = "# Configuration gérée par Windows Party"
    if menu.exists() and marker not in menu.read_text().splitlines()[:2]:
        raise ValueError(tr('Une entrée utilisateur existe déjà : {p0}', p0=menu))
    atomic_write(menu, f"#!/bin/bash\n{marker}\nexec " +
                 shlex.join([str(base / "partydeck-test"), "configurer"]) + "\n", 0o755)


def choose_rom():
    kind = yad([tr("--text=Choisissez le format du jeu Windows."),
                tr("--button=Annuler:1"), tr("--button=Dossier .wine ou .pc:2"),
                tr("--button=Archive .wsquashfs:0")])
    if kind.returncode in {1, 252}:
        return None
    if kind.returncode not in {0, 2}:
        raise RuntimeError(tr("Le sélecteur de format n'a pas pu s'ouvrir."))
    options = ["--file-selection", "--filename=/userdata/roms/windows/"]
    if kind.returncode == 2:
        options.append("--directory")
    else:
        options.append(tr("--file-filter=Jeux Wine | *.wsquashfs *.WSQUASHFS"))
    result = yad(options)
    if result.returncode in {1, 252}:
        return None
    if result.returncode:
        raise RuntimeError(tr("Le sélecteur de jeu n'a pas pu s'ouvrir."))
    rom = Path(result.stdout.rstrip("\n")).absolute()
    if (rom.suffix.lower() not in ROM_TYPES or not rom.exists()
            or (rom.suffix.lower() == ".wsquashfs") != rom.is_file()):
        raise ValueError(tr("Choisissez une archive .wsquashfs ou un dossier .wine ou .pc."))
    return rom


def configure(base, rom=None):
    if os.environ.get("PARTYDECK_UI") != "legacy":
        from partydeck_couch import configure as couch_configure
        couch_configure(base, rom)
        return 0
    return configure_legacy(base, rom)


def configure_legacy(base, rom=None):
    if shutil.which("batocera-mouse"):
        subprocess.run(["batocera-mouse", "show"], check=False)
    while True:
        if rom is None:
            rows = []
            for path in sorted((base / "profiles").glob("*.json")):
                data = json.loads(path.read_text())
                source = Path(data["rom"])
                validate(data, source)
                rows.extend([str(source), source.stem])
            result = yad(["--list", "--width=760", "--height=440", "--separator=\x1f",
                          "--column=ROM", tr("--column=Jeu"), "--hide-column=1", "--print-column=1",
                          tr("--button=Fermer:1"), tr("--button=Ajouter un jeu:2"), tr("--button=Configurer:0"),
                          *rows])
            if result.returncode in {1, 252}:
                return 0
            if result.returncode == 2:
                selected = choose_rom()
            elif result.returncode == 0:
                value = result.stdout.rstrip("\n").removesuffix("\x1f")
                selected = Path(value) if value else None
            else:
                raise RuntimeError(tr("Le gestionnaire Windows Party n'a pas pu s'ouvrir."))
        else:
            selected = rom
        if selected is not None and edit_profile(base, selected):
            data = read_profile(base, selected)
            subprocess.run([str(base / "partydeck-test"), "ajouter", str(selected),
                            data["players"], data["split"], data["input"]], check=True)
        if rom is not None:
            return 0


def main():
    mode, folder, *arguments = sys.argv[1:]
    base = Path(folder)
    if mode == "installer":
        install_menu(base)
        return 0
    rom = Path(arguments[0]).absolute() if arguments else None
    if mode == "configurer":
        return configure(base, rom)
    if mode == "profil" and rom is not None:
        return launch_profile(base, rom)
    raise ValueError(tr("Commande de profil Windows Party invalide."))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Windows Party : {error}", file=sys.stderr)
        if shutil.which("yad") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            yad(["--error", "--text=" + html.escape(str(error))])
        raise SystemExit(1)
