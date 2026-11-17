"""Community configuration recipes, independent of the user's game files."""
from dataclasses import dataclass
import os
from pathlib import Path
import re


@dataclass(frozen=True)
class CommonGame:
    id: str
    name: str
    adapter: str
    matches: tuple = ()

    @property
    def stem(self):
        return self.name


COMMON = (CommonGame('soh', 'Ship of Harkinian · profil commun', 'soh-anchor'),)


def is_rom(path):
    suffix = path.suffix.lower()
    return ((suffix in {'.wine', '.pc'} and path.is_dir())
            or (suffix == '.wsquashfs' and path.is_file()))


def matches_soh(path):
    name = path.stem.casefold()
    return bool(re.search(r'ship[\s_-]*of[\s_-]*harkinian|(?<![a-z0-9])soh(?![a-z0-9])', name))


def discover(root):
    """Inspect names only; never enter Wine prefixes or mount/extract archives."""
    found = []
    for i, (folder, dirs, files) in enumerate(os.walk(root, followlinks=False)):
        if i >= 2000:
            break
        parent = Path(folder)
        depth = len(parent.relative_to(root).parts)
        keep = []
        for name in dirs:
            path = parent / name
            if name.startswith('.'):
                continue
            if path.suffix.lower() in {'.wine', '.pc'}:
                if matches_soh(path) and is_rom(path):
                    found.append(path)
            elif depth < 3:
                keep.append(name)
        dirs[:] = keep
        for name in files:
            path = parent / name
            if path.suffix.lower() == '.wsquashfs' and matches_soh(path) and is_rom(path):
                found.append(path)
    return tuple(sorted(found, key=lambda p: str(p).casefold()))
