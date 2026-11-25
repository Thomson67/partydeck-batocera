"""Skin catalogue and local archive cache for Zelda Online v1.0.5."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

from partydeck_anchor import config_path
from partydeck_i18n import tr

RESOURCE_SERVER = 'http://awu.fks.mybluehost.me/'  # ZeldaOnlineClient.cpp
CONVERTER_URL = 'https://raw.githubusercontent.com/cranebeaker/ocarina-coop/7b912675f2e0627fb5c9a7e4a5ae937e574160f1/tools/skinconv/'
CONVERTER_FILES = {
    'skinconv.py': 'a77105231626dd2f37f3d2f90c7cb7e495c9d516c81821c2fb8a353fd07d6b89',
    'mpq.py': '1be0747ae94b252c32421d0b9f41626eec9e5d7e9f3d86c1fca6816dea88074d',
}
# The server's display names and reference names, with the resource archive SHA-256.
CATALOGUE = {
    'link': ('Link', None),
    '3DSLink': ('3DSLink By MalonRose', 'bf55c92513bda48c021c7ceb9f3db0509aff6c82bfc5f6804f069d21b7edbd08'),
    'YoungLinkPants': ('YoungLinkPants By Sky Blue', '7f0a58a3b8e3d656b8f98579e73065f616f32e1e8dceb4e7e4f05ffdf1e647c5'),
    'MMLink': ('MMLink By nickelndime246', '1b9bc6e9adab9a34a9f1bb8c8912ed1267282c4e89cfac3f5d7c6273a9b680f7'),
    'FierceDeity': ('FierceDeity By nickelndime246', 'd351dcc640ebfcca3750d244e92940f2c1e539ac8ae12f9c7d3f1eaf23c0964b'),
    'amara64': ('Amara64 by Jameriquiah', '790917e9d4b0d1f1d947ebcdb351abfce00dbe3ccf0e11854fd1c51bca3ef3ee'),
    'christmalon': ('Christmas Malon by MalonRose', 'c98604a7d0c2d8e179e9cf3280d583e8575e8c6e4b90236a703855f9affede43'),
    'linkle': ('Linkle by DanatheElf', '6303a568fc7271c273020f877982d6ad29500c43e26f62a266e542975db5b4c2'),
    'Saria': ('Saria By MalonRose', '283d0c9b41c6b9eabbd8dcda746a95c893f4688dbd75d3ab48ae3e8c07914ec8'),
    'kris': ('Kris by BanzMarten', '22544cb5db91564966cb50b782f42f53adc89606af316d487a79efbebc038c18'),
    'malon1': ('Malon by MalonRose', 'a338f57afbb72e85f3d64b28a3c847729d90cd7aa7950d05f8673f568cd2b684'),
    'mario': ('Mario by cy888', '996d5e1fc057dcfe324ce21752ca94442a35ee61f313bac712660075c75b1eb5'),
    'turezi': ('Turezi by Emkay', '6f2ff9ee3d34a8e6c0ee0578880f1ff78a4bb90bd75b74e1f8b24bf3775dc660'),
    'malon2': ('Malon (alt) by ascendantlight', 'b8e0759f6e67b3c78bece4cde63a30b3032e8f7ee0efd4822b661da7eba2bf94'),
    'zelda': ('Zelda by BungleTavern', '6ffab39eac6047528bbedd9e84fafef57d974ffb1e02ccd12e620b2b7562ce59'),
    'MasterChief': ('MasterChief By PxExYxTxOxN', '7c3f52d870bbab6438283701f6a09467bc6cb791d94e9c261cf2671e63ae4ea9'),
    '3DSLinkNoHat': ('3DSLinkNoHat By MalonRose', '2e0dd7c41bce4ac510ceebc63038b35ecd8047aeb42953f89542ae253e123dbb'),
    'TPLink': ('TPLink By PurpleHato', '6f9361a1a156fd4c51d43b569771840f272095aa1de60ca58dfcc15a0faf2fb1'),
    'BombchuGirl': ('Bombchu Girl (Adult) By theinsanebanana', '66b85bd8b301fa2626df1547ca7352cf7afd7b6ba4cee26854ccfb2729769ed5'),
    'Kafei': ('Kafei By ascendantlight', '7dbd93fc9f9ba48916bdecc9b7621dde74118098ce835685fdecc9d1b74b4449'),
    'Waluigi': ('Waluigi By Batts Electronics', '4061370146f1680752fda02e33c1e8d8fa291b7e195990472bca9e0d384391eb'),
}

LINK_PACK = re.compile(r'\benhanced[\W_]+3ds[\W_]+(?:(?:adult|young|child)[\W_]+)?link\b', re.I)
LINK_SKELETON = re.compile(r'(?:alt/)?objects/object_link_(?:boy|child)/gLink(?:Adult|Child)Skel$', re.I)
LOCAL_SKIN = re.compile(r'partydeck-[0-9a-f]{16}')


def valid_archive(path, checksum):
    if path.is_file() and not path.is_symlink():
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == checksum
    return False


def prepare(selected, cache):
    """Fetch selected catalogue archives before the players enter the offline LAN."""
    references = [ref for ref in dict.fromkeys(selected) if ref in CATALOGUE and CATALOGUE[ref][1]]
    if references:
        with ThreadPoolExecutor(max_workers=len(references)) as workers:
            list(workers.map(lambda ref: cache_skin(ref, cache), references))


def cache_skin(reference, cache):
    _, checksum = CATALOGUE[reference]
    target = cache / f'{reference}.o2r'
    try:
        if valid_archive(target, checksum):
            return
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            archive = Path(temporary) / target.name
            subprocess.run(['curl', '-fLsS', '--proto', '=http,https', '--proto-redir', '=http,https',
                            '--connect-timeout', '5', '--max-time', '15', '--max-filesize', '8388608',
                            RESOURCE_SERVER + target.name, '-o', str(archive)], check=True, timeout=17)
            if not valid_archive(archive, checksum):
                raise ValueError(tr('Archive Story Co-op invalide ({p0}).', p0=target.name))
            archive.chmod(0o644)
            archive.replace(target)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(tr('Story Co-op : skin {p0} indisponible ({p1}).', p0=reference, p1=error), flush=True)


def stage(selected, cache, directory, installed):
    """Make every selected catalogue skin visible to each local client."""
    from partydeck_borderlands2 import write_bytes

    for reference in dict.fromkeys(selected):
        _, checksum = CATALOGUE.get(reference, (None, None))
        if not checksum or reference in installed:
            continue
        filename = f'{reference}.o2r'
        archive = cache / filename
        try:
            if valid_archive(archive, checksum):
                path = config_path(directory, f'mods/PartyDeck-Story-Skins/{filename}')
                write_bytes(path, archive.read_bytes())
                installed.add(reference)
        except (OSError, ValueError) as error:
            print(tr('Story Co-op : skin {p0} indisponible ({p1}).', p0=reference, p1=error), flush=True)


def replaces_link(path):
    if LINK_PACK.search(path.name):
        return True
    if path.suffix.lower() == '.o2r':
        try:
            with zipfile.ZipFile(path) as archive:
                return any(LINK_SKELETON.fullmatch(name.replace('\\', '/')) for name in archive.namelist())
        except (OSError, zipfile.BadZipFile):
            pass
    return False


def local_mod_archives(rom, mods):
    """Find the same Link packs the private skin view excludes."""
    compressed = rom.suffix.lower() == '.wsquashfs'
    if compressed:
        result = subprocess.run(['unsquashfs', '-ls', str(rom), str(mods)], capture_output=True, timeout=15)
        if result.returncode == 2 and b'no matches for ' in result.stderr:
            return []
        result.check_returncode()
        prefix = 'squashfs-root/'
        candidates = [Path(line[len(prefix):]) for line in os.fsdecode(result.stdout).splitlines()
                      if line.startswith(prefix)]
    else:
        base = rom / mods
        if not base.is_dir() or base.is_symlink():
            return []
        candidates = [path.relative_to(rom) for path in base.rglob('*') if path.is_file() and not path.is_symlink()]
    selected = []
    for path in candidates:
        if path.is_absolute() or '..' in path.parts or not path.is_relative_to(mods) or path.suffix.lower() not in ('.otr', '.o2r'):
            continue
        relative = path.relative_to(mods)
        loose_o2r = len(relative.parts) == 1 and path.suffix.lower() == '.o2r'
        if LINK_PACK.search(relative.parts[0]) or (loose_o2r and not compressed and replaces_link(rom / path)):
            selected.append(path)
    return sorted(selected)


def converter(cache):
    tools = cache / 'skinconv'
    tools.mkdir(parents=True, exist_ok=True)
    for name, checksum in CONVERTER_FILES.items():
        target = tools / name
        if valid_archive(target, checksum):
            continue
        with tempfile.TemporaryDirectory(dir=tools) as temporary:
            download = Path(temporary) / name
            subprocess.run(['curl', '-fLsS', '--proto', '=https', '--max-time', '15',
                            CONVERTER_URL + name, '-o', str(download)], check=True, timeout=17)
            if not valid_archive(download, checksum):
                raise ValueError(tr('Archive Story Co-op invalide ({p0}).', p0=name))
            download.replace(target)
    return tools / 'skinconv.py'


def prepare_game_skin(rom, game_directories, cache):
    """Convert a vanilla-path Link pack for the other players before launch."""
    try:
        for game in game_directories:
            mods = game / 'mods'
            archives = local_mod_archives(rom, mods)
            if archives:
                return convert_game_skin(rom, mods, archives, cache)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(tr('Story Co-op : partage du mod de Link indisponible ({p0}).', p0=error), flush=True)
    return ''


def convert_game_skin(rom, mods, archives, cache):
    from sys import executable

    compressed = rom.suffix.lower() == '.wsquashfs'
    material = hashlib.sha256(str(CONVERTER_FILES).encode())
    paths = (rom,) if compressed else (rom / path for path in archives)
    for path in paths:
        stat = path.stat()
        material.update(os.fsencode(path))
        material.update(f':{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}'.encode())
    reference = f'partydeck-{material.hexdigest()[:16]}'
    target = cache / 'local' / f'{reference}.o2r'
    if target.is_file() and not target.is_symlink():
        return reference
    tool = converter(cache)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        workspace = Path(temporary)
        source = workspace / 'input'
        generated = workspace / target.name
        for path in archives:
            destination = source / path.relative_to(mods)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if compressed:
                with destination.open('wb') as output:
                    subprocess.run(['unsquashfs', '-cat', '-no-wildcards', str(rom), str(path)],
                                   stdout=output, check=True, timeout=25)
            else:
                shutil.copyfile(rom / path, destination)
        subprocess.run([executable, str(tool), str(source), reference, '-o', str(generated)],
                       stdout=subprocess.DEVNULL, check=True, timeout=45)
        with zipfile.ZipFile(generated) as archive:
            entries = archive.namelist()
            if not all(name.startswith(reference + '/') for name in entries) or not any(
                    LINK_SKELETON.fullmatch(name.partition('/')[2]) for name in entries):
                raise ValueError(tr('Archive Story Co-op invalide ({p0}).', p0=generated.name))
        generated.replace(target)
    print(tr('Story Co-op : mod de Link préparé pour les autres joueurs.'), flush=True)
    return reference


def stage_game_skin(reference, cache, directory):
    from partydeck_borderlands2 import write_bytes

    if not LOCAL_SKIN.fullmatch(reference):
        return
    filename = f'{reference}.o2r'
    source = cache / 'local' / filename
    target = config_path(directory, f'mods/PartyDeck-Story-Skins/{filename}')
    if not target.is_file():
        write_bytes(target, source.read_bytes())
    for previous in target.parent.glob('partydeck-*.o2r'):
        if previous != target and LOCAL_SKIN.fullmatch(previous.stem) and not previous.is_symlink():
            previous.unlink()


def mask_link_overrides(directory, player):
    """Remove Link replacements in a disposable view of this player's mods."""
    mods = config_path(directory, 'mods')
    if not mods.is_dir():
        return
    packs = [path for path in mods.iterdir() if path.is_dir() and not path.is_symlink()
             and LINK_PACK.search(path.name)]
    archives = [path for path in mods.rglob('*')
                if path.suffix.lower() == '.o2r' and path.is_file() and not path.is_symlink()
                and not any(path.is_relative_to(pack) for pack in packs) and replaces_link(path)]
    if not packs and not archives:
        return
    # /tmp is backed by the player's private tmpfs. Bind the lower directory
    # by a safe short path so ROM names may contain overlay option separators.
    root = Path(tempfile.mkdtemp(prefix='story-mods-', dir='/tmp'))
    lower, upper, work, view, empty = (root / name for name in ('lower', 'upper', 'work', 'view', 'empty'))
    for path in (lower, upper, work, view, empty):
        path.mkdir()
    subprocess.run(['mount', '--bind', str(mods), str(lower)], check=True, timeout=5)
    options = f'lowerdir={lower},upperdir={upper},workdir={work},index=off'
    subprocess.run(['mount', '-t', 'overlay', '-o', options, 'overlay', str(view)], check=True, timeout=5)
    for archive in archives:
        (view / archive.relative_to(mods)).unlink()
    for pack in packs:
        subprocess.run(['mount', '--bind', str(empty), str(view / pack.relative_to(mods))], check=True, timeout=5)
    # Publish the completed view atomically. The source directory and the
    # other player's mods remain untouched even when filtering fails.
    subprocess.run(['mount', '--rbind', str(view), str(mods)], check=True, timeout=5)
    print(tr('Story Co-op {p0} : {p1} remplacement(s) de Link masqué(s).',
             p0=player.name.upper(), p1=len(packs) + len(archives)), flush=True)
