"""Shared SoH base, player-only audio, graphics settings and logo installation."""
import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import copy
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

scripts = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(scripts))
import partydeck_anchor as anchor
import partydeck_profiles as profiles
from partydeck_theme import install_logo, logo_elements

common = json.loads((scripts.parent / "templates/soh-common.json").read_text())
assert "RoomId" not in common["CVars"]["gRemote"]["Anchor"]
common["CVars"]["gSettings"]["Volume"] = dict(MainMusic=70, SubMusic=65, Fanfare=80, SFX=90, Master=40)
original = copy.deepcopy(common)
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    settings = anchor.defaults()
    options = anchor.graphics_defaults()
    options.update(internal_resolution=1.5, msaa=8, vsync=False, texture_filter=2)
    settings["graphics"] = options
    normalized = []
    for index in range(4):
        player = root / f"j{index+1}"
        game = player / "game"
        game.mkdir(parents=True)
        target = game / "shipofharkinian.json"
        target.write_text(json.dumps({"OldPlayerSetting": index}))
        payload = dict(settings=settings, index=index, template=common,
                       identity_stamp=str(player / "identity.json"))
        anchor.apply_config(game, payload)
        data = json.loads(target.read_text())
        assert "OldPlayerSetting" not in data
        assert json.loads((player / "soh-before-common.json").read_text()) == {"OldPlayerSetting": index}
        graphics = data["CVars"]["gSettings"]
        assert graphics["InternalResolution"] == 1.5 and graphics["MSAAValue"] == 8
        assert graphics["VsyncEnabled"] == 0 and graphics["TextureFilter"] == 2
        assert graphics["AdvancedResolution"]["PixelPerfectMode"] == 0
        assert graphics["Volume"]["SFX"] == 90 and graphics["Volume"]["Master"] == 40
        for key in ("MainMusic", "SubMusic", "Fanfare"):
            assert graphics["Volume"][key] == (common["CVars"]["gSettings"]["Volume"][key] if index == 0 else 0)
        data["CVars"]["gRemote"]["Anchor"]["LastClientId"] = 1200 + index
        target.write_text(json.dumps(data))
        anchor.apply_config(game, payload)
        assert json.loads(target.read_text())["CVars"]["gRemote"]["Anchor"]["LastClientId"] == 1200 + index
        # All common data is identical after removing intentional overrides.
        for key in ("Name", "LastClientId"):
            data["CVars"]["gRemote"]["Anchor"].pop(key)
        data["CVars"]["gSettings"]["Volume"] = common["CVars"]["gSettings"]["Volume"]
        normalized.append(data)
    assert all(d == normalized[0] for d in normalized)
    assert common == original  # Applying J2 never mutes J1's shared template.
    settings["graphics"]["music_j1_only"] = False
    anchor.apply_config(game, payload)
    assert json.loads(target.read_text())["CVars"]["gSettings"]["Volume"]["MainMusic"] == 70
    with patch.object(profiles, "yad", return_value=Mock(returncode=0, stdout="1,25\x1f4\x1fTRUE\x1fLinéaire\x1fTRUE" + "\x1f" * 6 + "\n")):
        assert profiles.edit_soh_graphics(settings)
    assert settings["graphics"] == dict(internal_resolution=1.25, msaa=4, vsync=True, texture_filter=1, music_j1_only=True)
    before = copy.deepcopy(settings)
    with patch.object(profiles, "yad", return_value=Mock(returncode=1)):
        assert not profiles.edit_soh_graphics(settings)
    assert settings == before
    # Local ROM theme wraps the selected Windows layout without changing it.
    assets = root / "assets"
    assets.mkdir()
    (assets / "windows-party.png").write_bytes(b"logo")
    themes = root / "themes"
    native = themes / "custom/windows/theme.xml"
    native.parent.mkdir(parents=True)
    native.write_text("<theme><formatVersion>7</formatVersion></theme>")
    cfg = root / "es_settings.cfg"
    cfg.write_text('<config><string name="ThemeSet" value="custom"/></config>')
    roms = root / "roms"
    assert install_logo(root, roms, cfg, (themes,))
    theme = ET.parse(roms / "theme.xml")
    assert theme.findtext("include") == str(native)
    assert theme.findtext("view/image/path") == str(assets / "windows-party.png")
    before = (roms / "theme.xml").read_bytes()
    assert install_logo(root, roms, cfg, (themes,))
    assert (roms / "theme.xml").read_bytes() == before
    assert native.read_text() == "<theme><formatVersion>7</formatVersion></theme>"
    included = native.parent / "headers.xml"
    included.write_text('<theme><include>theme.xml</include><feature supported="grid">'
                        '<view name="basic,detailed,grid,video,gamecarousel">'
                        '<image name="systemLogo" extra="true"><path>../windows/logo.svg</path></image>'
                        '<image name="publisher"><path>publisher.png</path></image>'
                        '</view></feature></theme>')
    native.write_text('<theme><variables><headers>headers.xml</headers></variables>'
                      '<include>${headers}</include></theme>')
    assert install_logo(root, roms, cfg, (themes,))
    theme = ET.parse(roms / "theme.xml")
    for view in ("basic", "detailed", "grid", "video", "gamecarousel"):
        element = theme.find(f"view[@name='{view}']/image[@name='systemLogo']")
        assert element is not None and element.get("extra") == "true"
        assert element.findtext("path") == str(assets / "windows-party.png")
        assert theme.find(f"view[@name='{view}']/image[@name='publisher']") is None
    assert "logo" in logo_elements(native)["system"]
    (roms / "theme.xml").write_text("<theme><!-- personal --></theme>")
    assert not install_logo(root, roms, cfg, (themes,))
    assert "personal" in (roms / "theme.xml").read_text()
print("SoH commun : base J1-J4, graphismes, musique J1, identités et thème local vérifiés.")
