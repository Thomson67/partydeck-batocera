"""Anchor field mapping, cancellation, private launch ordering and safety checks."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import partydeck_anchor as anchor
import partydeck_profiles as profiles

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = anchor.defaults()
    settings.update(room="test-room", names=["Alice", "Bob", "Chloé", "David"],
                    teams=["bleu", "rouge", "bleu", "rouge"], pvp=2, locations=2, teleport=0, sync=False)
    before = {"Window": {"Width": 1920}, "CVars": {"gRemote": {"Anchor": {"Color": {"R": 12}, "LastClientId": 88}},
                                                   "gOther": {"value": 42}}}
    for i in range(4):
        view = root / f"j{i + 1}"
        view.mkdir()
        target = view / "shipofharkinian.json"
        target.write_text(json.dumps(before))
        anchor.apply_config(view, dict(settings=settings, index=i))
        result = json.loads(target.read_text())
        value = result["CVars"]["gRemote"]["Anchor"]
        assert value["Name"] == settings["names"][i] and value["TeamId"] == settings["teams"][i]
        assert value["Enabled"] == 1 and value["RoomId"] == "test-room" and value["LastClientId"] == 0
        assert value["RoomSettings"] == dict(PvpMode=2, ShowLocationsMode=2, TeleportMode=0, SyncItemsAndFlags=0)
        assert result["Window"] == before["Window"] and result["CVars"]["gOther"] == before["CVars"]["gOther"]
        assert value["Color"] == {"R": 12}
    # A server-issued ID survives the next launch of that same player/room.
    stamp = root / "identity.json"
    identity_payload = dict(settings=settings, index=3, identity_stamp=str(stamp))
    anchor.apply_config(view, identity_payload)
    current = json.loads(target.read_text())
    current["CVars"]["gRemote"]["Anchor"]["LastClientId"] = 123
    target.write_text(json.dumps(current))
    anchor.apply_config(view, identity_payload)
    assert json.loads(target.read_text())["CVars"]["gRemote"]["Anchor"]["LastClientId"] == 123
    changed = dict(settings, room="another-room")
    anchor.apply_config(view, dict(identity_payload, settings=changed))
    assert json.loads(target.read_text())["CVars"]["gRemote"]["Anchor"]["LastClientId"] == 0
    target.write_text("broken json")
    try:
        anchor.apply_config(view, dict(settings=settings, index=3))
        raise AssertionError("Broken JSON overwritten")
    except ValueError:
        assert target.read_text() == "broken json"
    target.unlink()
    solo = root / "solo.json"
    solo.write_text(json.dumps(before))
    target.symlink_to(solo)
    try:
        anchor.apply_config(view, dict(settings=settings, index=3))
        raise AssertionError("Solo link followed")
    except ValueError:
        assert json.loads(solo.read_text()) == before
    for key, value in (("config", "../solo.json"), ("port", 1), ("names", ["same"] * 4)):
        try:
            anchor.validate({**settings, key: value})
            raise AssertionError("Invalid Anchor settings accepted")
        except ValueError:
            pass
    data = profiles.defaults(root / "test.wsquashfs")
    original = dict(data)
    with patch.object(profiles, "yad", return_value=Mock(returncode=1)):
        assert not profiles.edit_anchor(data)
    assert data == original
    fields = ["TRUE", "TRUE", "new-room", "anchor.hm64.org", "43383", "shipofharkinian.json",
              "Activé + tirs alliés", "Tous", "Personne", "FALSE",
              "Alice", "bleu", "Bob", "rouge", "Chloé", "bleu", "David", "rouge"]
    with patch.object(profiles, "yad", return_value=Mock(returncode=0, stdout="\x1f".join(fields) + "\x1f\n")):
        assert profiles.edit_anchor(data)
    profiles.validate(data, root / "test.wsquashfs")
    assert data["anchor"]["pvp"] == 2 and data["anchor"]["teams"] == settings["teams"]
    # Hook creation is opt-in and mounts only a private replacement, after
    # validation and shell syntax checking; the on-disk launcher stays intact.
    source_rom = root / "test.wsquashfs"
    profiles.save_profile(root, source_rom, data)
    (root / "templates").mkdir()
    (root / "templates/soh-common.json").write_text(json.dumps(before))
    # Execute a simulated native launcher: config must exist before Wine starts,
    # and mounting/setup must complete before the config hook runs.
    target.unlink()
    payload = root / "payload with spaces.json"
    payload.write_text(json.dumps(dict(settings=settings, index=3)))
    hook = [sys.executable, str(Path(anchor.__file__)), str(payload)]
    source = "#!/bin/bash\nset -e\n"
    for name in ("play_wine", "play_pc", "play_squashfs"):
        source += name + '() {\n if [[ -n "${WINE_LANG:-}" ]]; then\n'
        source += ' (cd "${WINEPOINT}/${WINE_DIR}" && test -f shipofharkinian.json)\n else\n'
        source += ' (cd "${WINEPOINT}/${WINE_DIR}" && test -f shipofharkinian.json)\n fi\n}\n'
    source += f"WINEPOINT={shlex.quote(str(view))}\nWINE_DIR=.\nplay_squashfs\n"
    native = root / "native.sh"
    native.write_text(anchor.instrument_native(source, hook))
    subprocess.run(["bash", str(native)], check=True)
    assert json.loads(target.read_text())["CVars"]["gRemote"]["Anchor"]["Name"] == "David"
    try:
        anchor.instrument_native(source.replace("play_squashfs()", "new_launcher()"), hook)
        raise AssertionError("Unsupported native launch structure accepted")
    except RuntimeError:
        pass
    native.write_text(source)
    player = root / "j1"
    with patch.object(anchor.shutil, "which", return_value=str(native)), patch.object(anchor.subprocess, "run") as run:
        anchor.install_hook(root, source_rom, player)
        assert run.call_args_list[-1].args[0] == ["mount", "--bind", str(player / "batocera-wine-anchor"), str(native)]
    assert native.read_text() == source
    data["adapter"] = "standard"
    profiles.save_profile(root, source_rom, data)
    with patch.object(anchor.subprocess, "run") as run:
        anchor.install_hook(root, source_rom, player)
        run.assert_not_called()
print("Anchor : options, J1–J4, préservation JSON, liens solo, annulation et application avant Wine vérifiés.")
