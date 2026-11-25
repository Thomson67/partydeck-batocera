"""Skin catalogue and local archive cache for Zelda Online v1.0.5."""
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

from partydeck_anchor import config_path
from partydeck_i18n import tr

RESOURCE_SERVER = 'http://awu.fks.mybluehost.me/'  # ZeldaOnlineClient.cpp
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


def valid_archive(path, checksum):
    if path.is_file() and not path.is_symlink():
        with path.open('rb') as stream:
            return hashlib.file_digest(stream, 'sha256').hexdigest() == checksum
    return False


def prepare(selected, cache):
    """Fetch selected catalogue archives before the players enter the offline LAN."""
    for reference in dict.fromkeys(selected):
        _, checksum = CATALOGUE.get(reference, (None, None))
        if not checksum:
            continue
        target = cache / f'{reference}.o2r'
        try:
            if valid_archive(target, checksum):
                continue
            cache.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=cache) as temporary:
                archive = Path(temporary) / target.name
                subprocess.run(['curl', '-fLsS', '--proto', '=http,https', '--proto-redir', '=http,https',
                                '--connect-timeout', '5', '--max-time', '15', '--max-filesize', '8388608',
                                RESOURCE_SERVER + target.name, '-o', str(archive)], check=True)
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
        if valid_archive(archive, checksum):
            path = config_path(directory, f'mods/PartyDeck-Story-Skins/{filename}')
            path.parent.mkdir(parents=True, exist_ok=True)
            write_bytes(path, archive.read_bytes())
            installed.add(reference)


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


def mask_link_overrides(directory, player):
    """Hide global Link replacements with mounts that live only for this player."""
    mods = config_path(directory, 'mods')
    if not mods.is_dir():
        return
    packs = [path for path in mods.iterdir() if path.is_dir() and not path.is_symlink()
             and LINK_PACK.search(path.name)]
    archives = [path for path in mods.rglob('*')
                if path.suffix.lower() == '.o2r' and path.is_file() and not path.is_symlink()
                and not any(path.is_relative_to(pack) for pack in packs) and replaces_link(path)]
    if packs or archives:
        empty = config_path(player, 'story-empty-mods')
        empty.mkdir(exist_ok=True)
        for pack in packs:
            subprocess.run(['mount', '--bind', str(empty), str(pack)], check=True)
        if archives:
            blank = config_path(player, 'story-empty.o2r')
            with zipfile.ZipFile(blank, 'w'):
                pass
            for archive in archives:
                subprocess.run(['mount', '--bind', str(blank), str(archive)], check=True)
        print(tr('Story Co-op {p0} : {p1} remplacement(s) de Link masqué(s).',
                 p0=player.name.upper(), p1=len(packs) + len(archives)), flush=True)
