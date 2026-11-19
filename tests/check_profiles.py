"""Profile migration, editor cancellation and normal direct-launch regression checks."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import importlib.util
import json
os.environ["PARTYDECK_UI"] = "legacy"
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch

script = Path(__file__).resolve().parents[1]/"scripts/partydeck_profiles.py"
sys.path.insert(0, str(script.parent))
spec = importlib.util.spec_from_file_location("profiles", script)
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)

with tempfile.TemporaryDirectory() as folder:
    base = Path(folder)
    rom = base/"Game ' & $(touch injected).wsquashfs"
    rom.touch()
    roms = base/"roms-windows-party"
    roms.mkdir()
    old = roms/"Game.sh"
    launcher = base/"windows-party"
    old.write_text("#!/bin/bash\n" + profiles.MARKER + "\nexec " +
                   shlex.join([str(launcher), "party", str(rom), "2", "vertical", "auto"]) + "\n")
    custom = roms/"User.sh"
    custom.write_text("#!/bin/sh\nexit 0\n")
    profiles.install_menu(base, roms)
    path = profiles.profile_path(base, rom)
    data = profiles.read_profile(base, rom)
    assert data["players"] == "2" and data["split"] == "vertical"
    assert shlex.split(old.read_text().splitlines()[2]) == ["exec", str(launcher), "profil", str(rom)]
    assert custom.read_text() == "#!/bin/sh\nexit 0\n"
    with patch.object(profiles, "edit_profile") as editor, patch.object(profiles.os, "execv") as launch:
        profiles.launch_profile(base, rom)
        editor.assert_not_called()
        launch.assert_called_once_with(str(launcher), [str(launcher), "party", str(rom), "2", "vertical", "auto"])
    before = path.read_bytes()
    with patch.object(profiles, "yad", return_value=Mock(returncode=1)):
        assert profiles.edit_profile(base, rom) is False
    assert path.read_bytes() == before
    with patch.object(profiles, "yad", return_value=Mock(returncode=0, stdout="3\x1fhorizontal\x1fauto\x1fTRUE\x1f\n")):
        assert profiles.edit_profile(base, rom)
    data = profiles.read_profile(base, rom)
    assert data["players"] == "3" and data["configure_before_launch"]
    with patch.object(profiles, "edit_profile", return_value=False) as editor, patch.object(profiles.os, "execv") as launch:
        assert profiles.launch_profile(base, rom) == 0
        editor.assert_called_once_with(base, rom)
        launch.assert_not_called()
    # A reinstall preserves GUI edits, including the optional editor flag.
    profiles.install_menu(base, roms)
    assert profiles.read_profile(base, rom) == data
    profiles.prepare_profile(base, rom, "4", "vertical", "auto")
    assert profiles.read_profile(base, rom)["configure_before_launch"]
    new_rom = base/"New.wine"
    new_rom.mkdir()
    with patch.object(profiles, "edit_profile", return_value=False) as editor, patch.object(profiles.os, "execv") as launch:
        profiles.launch_profile(base, new_rom)
        editor.assert_called_once()
        launch.assert_not_called()
    # Saving malformed data leaves the current profile intact.
    before = path.read_bytes()
    data["players"] = []
    try:
        profiles.save_profile(base, rom, data)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid players accepted")
    assert path.read_bytes() == before
    # The launcher remains valid when a profile contains spaces/metacharacters.
    launcher.write_text("#!" + sys.executable + "\nimport sys,json\nfrom pathlib import Path\n" +
                        f"Path({str(base/'args.json')!r}).write_text(json.dumps(sys.argv[1:]))\n")
    launcher.chmod(0o755)
    subprocess.run(["bash", str(old)], check=True, cwd=base)
    assert json.loads((base/'args.json').read_text()) == ["profil", str(rom)]
    assert not (base/"injected").exists()
print("Profils : migration, lancement direct, édition facultative et annulation vérifiés.")
