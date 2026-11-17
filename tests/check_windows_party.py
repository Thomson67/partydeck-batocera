"""Regression checks for custom-system launchers and private player save paths."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

script = Path(__file__).resolve().parents[1] / "scripts/partydeck-batocera-coop.py"
spec = importlib.util.spec_from_file_location("party", script)
party = importlib.util.module_from_spec(spec)
sys.modules["party"] = party
spec.loader.exec_module(party)

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    roms = root / "roms"
    saves = root / "saves"
    config = root / "es"
    stock = root / "es_systems.cfg"
    command = "emulatorlauncher %CONTROLLERSCONFIG% -system %SYSTEM% -rom %ROM% -emulator %EMULATOR% -core %CORE%"
    stock.write_text('<systemList><system><name>ports</name><command>' + command +
                     '</command><emulators><emulator name="sh"><cores><core default="true">sh</core>'
                     '</cores></emulator></emulators></system></systemList>')
    with patch.object(party, "PARTY_ROMS", roms), patch.object(party, "PARTY_SAVES", saves):
        party.install_system(config, stock)
        party.install_system(config, stock)
    system_path = config / "es_systems_windows-party.cfg"
    system = ET.parse(system_path).find("system")
    assert system.findtext("fullname") == "Windows Party"
    assert system.findtext("name") == "windows-party"
    assert system.findtext("command") == command.replace("%SYSTEM%", "ports")
    assert system.findtext("path") == str(roms)
    assert system.findtext("platform") == "windows"
    assert system.find("group") is None
    assert system.find("emulators/emulator").get("name") == "sh"
    system_path.write_text("<systemList/>")
    with patch.object(party, "PARTY_ROMS", roms), patch.object(party, "PARTY_SAVES", saves):
        try:
            party.install_system(config, stock)
        except ValueError:
            pass
        else:
            raise AssertionError("overwrote a user configuration")
    assert system_path.read_text() == "<systemList/>"

    # Execute a launcher with shell metacharacters/spaces in its ROM name.
    output = root / "arguments.json"
    launcher = root / "record arguments"
    launcher.write_text("#!" + sys.executable + "\nimport json,sys\n"
                        "from pathlib import Path\n"
                        f"Path({str(output)!r}).write_text(json.dumps(sys.argv[1:]))\n")
    launcher.chmod(0o755)
    original = root / "original" / "Game ' & $(touch injected).wsquashfs"
    original.parent.mkdir()
    original.write_bytes(b"game data")
    first = party.write_port(roms, launcher, original, "2", "horizontal", "auto", mode="party")
    second = party.write_port(roms, launcher, original, "2", "vertical", "auto", mode="party")
    assert first == second and len(list(roms.glob("*.sh"))) == 1
    subprocess.run(["bash", str(second)], check=True, cwd=root)
    assert json.loads(output.read_text()) == ["party", str(original), "2", "vertical", "auto"]
    assert original.read_bytes() == b"game data"
    assert not (root / "injected").exists()

    host = root / "host"
    mappings = {str(host/"windows"): "saves", str(host/"bottles"): "bottles",
                str(host/"cache"): "cache"}
    for index in (1, 2):
        player = root / "runtime" / f"j{index}"
        dedicated = saves / "Game" / f"j{index}"
        with patch.object(party, "WRITABLE", mappings), patch.object(party, "UMU_HOME", root/"no-umu"):
            binds = list(party.player_paths(player, dedicated))
        assert ("--bind", str(dedicated/"windows"), str(host/"windows")) in binds
        assert ("--bind", str(dedicated/"prefixes"), str(host/"bottles")) in binds
        assert ("--bind", str(player/"cache"), str(host/"cache")) in binds
        for suffix in (".wine", ".pc", ".wsquashfs"):
            game = Path("/example/Game" + suffix)
            with patch.object(party, "UMU_HOME", root/"no-umu"), patch.object(party, "mount_overlay") as overlay, patch.object(party.subprocess, "run", return_value=Mock(returncode=0)) as run:
                assert party.run_wine(game, game, player, dedicated) == 0
                if suffix == ".wsquashfs":
                    overlay.assert_not_called()
                else:
                    overlay.assert_called_once_with(game, dedicated/"content")
                run.assert_called_once_with(["batocera-wine", "windows", "play", str(game)])
print("Windows Party : système, lancement des ROMs et sauvegardes J1/J2 vérifiés.")
