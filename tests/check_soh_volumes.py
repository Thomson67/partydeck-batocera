"""Volume mix persistence and precedence of J1-only music on all four players."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import partydeck_anchor as anchor
import partydeck_profiles as profiles

settings = anchor.defaults()
fields = ["1", "4", "TRUE", "Trois points (N64)", "TRUE", "55", "65", "35", "20", "80"]
with patch.object(profiles, "yad", return_value=Mock(returncode=0, stdout="\x1f".join(fields) + "\x1f\n")):
    assert profiles.edit_soh_graphics(settings)
mix = dict(Master=55, MainMusic=65, SubMusic=35, Fanfare=20, SFX=80)
assert settings["graphics"]["volumes"] == mix
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    rom = root / "SoH.wsquashfs"
    profile = profiles.defaults(rom)
    profile.update(adapter="soh-anchor", anchor=settings)
    profiles.save_profile(root, rom, profile)
    assert profiles.read_profile(root, rom)["anchor"]["graphics"]["volumes"] == mix
    template = {"CVars": {"gSettings": {"Volume": dict(Master=40, SFX=90, OtherSetting=42)}}}
    for index in range(4):
        game = root / f"j{index+1}"
        game.mkdir()
        payload = dict(template=template, settings=settings, index=index,
                       identity_stamp=str(game / "identity.json"))
        anchor.apply_config(game, payload)
        result = json.loads((game / "shipofharkinian.json").read_text())["CVars"]["gSettings"]["Volume"]
        expected = dict(mix, OtherSetting=42)
        if index:
            expected.update(MainMusic=0, SubMusic=0, Fanfare=0)
        assert result == expected
    settings["graphics"]["music_j1_only"] = False
    anchor.apply_config(game, payload)
    result = json.loads((game / "shipofharkinian.json").read_text())["CVars"]["gSettings"]["Volume"]
    assert result == dict(mix, OtherSetting=42)
    settings["graphics"]["volumes"] = dict(Master=0, SFX=100)
    anchor.apply_config(game, payload)
    result = json.loads((game / "shipofharkinian.json").read_text())["CVars"]["gSettings"]["Volume"]
    assert result == dict(Master=0, SFX=100, OtherSetting=42)

before = copy.deepcopy(settings)
for invalid in ("-1", "101", "5.5", "abc"):
    fields[5] = invalid
    with patch.object(profiles, "yad", return_value=Mock(returncode=0, stdout="\x1f".join(fields) + "\x1f\n")):
        try:
            profiles.edit_soh_graphics(settings)
            raise AssertionError("Invalid volume accepted")
        except ValueError:
            pass
    assert settings == before
for invalid in (True, -1, 101, 0.5, "25"):
    try:
        anchor.validate_graphics(dict(anchor.graphics_defaults(), volumes={"Master": invalid}))
        raise AssertionError("Invalid JSON volume accepted")
    except ValueError:
        pass
print("Volumes SoH : cinq canaux, profils persistants, J1-J4, héritage JSON et validation vérifiés.")
