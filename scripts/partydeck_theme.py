"""Per-system logo override, keeping the user's current Windows theme layout."""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MARKER = "Logo géré par Windows Party"
VIEWS = ("system", "basic", "detailed", "grid", "video", "gamecarousel")


def logo_elements(source):
    """Find named header logos in included layouts, including theme extras."""
    found = {view: {"logo": {}} for view in VIEWS}
    visited = set()
    variables = {"system.theme": "windows", "system.name": "windows-party"}

    def expand(value):
        for key, replacement in variables.items():
            value = value.replace("${" + key + "}", replacement)
        return value.replace("$system", "windows")

    def inspect(path):
        path = path.resolve()
        if path in visited or len(visited) >= 500 or not path.is_file():
            return
        visited.add(path)
        try:
            root = ET.parse(path).getroot()
        except (ET.ParseError, OSError):
            return
        for group in root.iter("variables"):
            for node in group:
                if node.text:
                    variables[node.tag] = expand(node.text.strip())
        for node in root.iter("include"):
            value = expand((node.text or "").strip())
            if value and "$" not in value:
                inspect(path.parent / value)
        for view in root.iter("view"):
            scopes = [v for v in re.split(r"[\s,]+", view.get("name", "")) if v in VIEWS]
            for image in view.findall("image"):
                names = re.split(r"[\s,]+", image.get("name", ""))
                asset = expand(image.findtext("path", "")).lower()
                windows_asset = (Path(asset).stem in {"windows", "windows-logo", "windows_logo"}
                                 or ("windows/" in asset and "logo" in Path(asset).name))
                for name in names:
                    normalized = re.sub(r"[^a-z0-9]", "", name.lower())
                    if name and (normalized in {"logo", "systemlogo", "logosystem", "headerlogo", "logoheader", "mdsystemlogo", "logosmall", "logo2"}
                                 or windows_asset):
                        for scope in scopes:
                            attributes = {key: image.attrib[key] for key in ("extra",) if key in image.attrib}
                            found[scope][name] = attributes
    inspect(source)
    return found


def install_logo(base, roms=Path("/userdata/roms/windows-party"),
                 settings=Path("/userdata/system/configs/emulationstation/es_settings.cfg"),
                 theme_roots=(Path("/userdata/themes"), Path("/usr/share/emulationstation/themes"))):
    from partydeck_profiles import atomic_write
    logo = base / "assets" / "windows-party.png"
    if not logo.is_file():
        return False
    theme_name = "es-theme-carbon"
    if settings.is_file():
        entry = ET.parse(settings).find(".//string[@name='ThemeSet']")
        if entry is not None:
            theme_name = entry.get("value", theme_name)
    if Path(theme_name).name != theme_name:
        raise ValueError("Nom de thème EmulationStation invalide.")
    selected = next((root / theme_name for root in theme_roots if (root / theme_name).is_dir()), None)
    source = None
    if selected is not None:
        source = next((p for p in (selected / "windows/theme.xml", selected / "theme.xml") if p.is_file()), None)
    if source is None:
        print("Logo Windows Party installé ; thème courant introuvable, habillage Windows conservé.")
        return False
    destination = roms / "theme.xml"
    if destination.is_symlink() or (destination.exists() and MARKER not in destination.read_text()):
        print("Thème local Windows Party personnalisé conservé ; logo disponible dans " + str(logo))
        return False
    # EmulationStation checks ROM/theme.xml before the current theme set. Include
    # the existing Windows layout, overriding just this system's logo image.
    root = ET.Element("theme")
    root.append(ET.Comment(" " + MARKER + " "))
    ET.SubElement(root, "formatVersion").text = "7"
    ET.SubElement(root, "include").text = str(source.absolute())
    for scope, elements in logo_elements(source).items():
        view = ET.SubElement(root, "view", name=scope)
        for name, attributes in elements.items():
            image = ET.SubElement(view, "image", name=name, **attributes)
            ET.SubElement(image, "path").text = str(logo.absolute())
            ET.SubElement(image, "color").text = "FFFFFFFF"
    ET.indent(root, space="  ")
    atomic_write(destination, ET.tostring(root, encoding="unicode") + "\n", 0o644)
    print("Logo Windows Party activé pour le thème " + theme_name)
    return True


if __name__ == "__main__":
    install_logo(Path(sys.argv[1]))
