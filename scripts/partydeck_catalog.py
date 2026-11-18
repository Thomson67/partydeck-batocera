"""Community configuration recipes, independent of the user's game files."""
from partydeck_i18n import tr
from dataclasses import dataclass
import json
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
        return tr(self.name)


COMMON = (CommonGame('soh', 'Ship of Harkinian · profil commun', 'soh-anchor'),
          CommonGame('borderlands2', 'Borderlands 2 · profil commun', 'borderlands2'))


def is_rom(path):
    suffix = path.suffix.lower()
    return ((suffix in {'.wine', '.pc'} and path.is_dir())
            or (suffix == '.wsquashfs' and path.is_file()))


def matches_soh(path):
    name = path.stem.casefold()
    return bool(re.search(r'ship[\s_-]*of[\s_-]*harkinian|(?<![a-z0-9])soh(?![a-z0-9])', name))


def recipe_for(rom, adapter=None):
    from partydeck_borderlands2 import matches as matches_bl2
    if adapter is not None:
        return next((r for r in COMMON if r.adapter == adapter), None)
    return COMMON[0] if matches_soh(rom) else COMMON[1] if matches_bl2(rom) else None


def unlinked(base):
    path = base/'catalog.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(data,dict):
        raise ValueError(tr('État du catalogue Windows Party invalide.'))
    ids = data.get('unlinked',[])
    if not isinstance(ids,list) or any(i not in {r.id for r in COMMON} for i in ids):
        raise ValueError(tr('État du catalogue Windows Party invalide.'))
    return set(ids)


def set_unlinked(base, recipe, value):
    from partydeck_profiles import atomic_write
    ids = unlinked(base)
    ids.add(recipe.id) if value else ids.discard(recipe.id)
    atomic_write(base/'catalog.json',json.dumps(dict(unlinked=sorted(ids)))+'\n')


def discover(root, matcher=matches_soh):
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
                if matcher(path) and is_rom(path):
                    found.append(path)
            elif depth < 3:
                keep.append(name)
        dirs[:] = keep
        for name in files:
            path = parent / name
            if path.suffix.lower() == '.wsquashfs' and matcher(path) and is_rom(path):
                found.append(path)
    return tuple(sorted(found, key=lambda p: str(p).casefold()))
