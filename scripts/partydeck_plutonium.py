"""Install the Plutonium T5/T6 client from its published update manifest."""

from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen

from partydeck_i18n import tr

MANIFEST = 'https://cdn.plutoniummod.com/updater/prod/info.json'
CDN_HOSTS = {'cdn.plutoniummod.com', 'cdn.plutonium.pw'}
BOOTSTRAPPER = 'plutonium-bootstrapper-win32.exe'
GAMES = {'t5': ('t5mp', 't5sp'), 't6': ('t6mp', 't6zm')}


def client_path(base, mode):
    manual = base / 'plutonium'
    cached = base / 'dependencies' / f'plutonium-{str(mode)[:2]}' / 'client'
    required = (f'bin/{BOOTSTRAPPER}', f'games/{mode}.exe')
    for root in (manual, cached):
        if all((root / path).is_file() for path in required):
            return root
    return None


def cdn_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc not in CDN_HOSTS:
        raise ValueError(tr('Plutonium : adresse de téléchargement invalide.'))
    return url


def manifest_files(family='t6'):
    required = {f'bin/{BOOTSTRAPPER}', *(f'games/{mode}.exe' for mode in GAMES[family])}
    folders = ('bin/', f'storage/{family}/', 'storage/demonware/')
    with urlopen(MANIFEST, timeout=20) as response:
        cdn_url(response.geturl())
        manifest = json.loads(response.read(1024 * 1024))
    try:
        base_url = cdn_url(manifest['baseUrl'])
        revision = manifest['revision']
        candidates = manifest['files']
        if not base_url.endswith('/') or type(revision) is not int or not isinstance(candidates, list):
            raise ValueError
        files = {}
        for entry in candidates:
            name = entry['name']
            if name not in required and not name.startswith(folders):
                continue
            parts = name.split('/')
            size, digest = entry['size'], entry['hash']
            if (any(part in ('', '.', '..') or re.search(r'[\\:\x00-\x1f]', part) for part in parts)
                    or name.casefold() in files or type(size) is not int or not 0 < size <= 128 * 1024**2
                    or not re.fullmatch(r'[a-f0-9]{40}', digest)):
                raise ValueError
            files[name.casefold()] = name, size, digest
        if not required.issubset(files) or sum(row[1] for row in files.values()) > 512 * 1024**2:
            raise ValueError
    except (KeyError, AttributeError, TypeError, ValueError):
        raise ValueError(tr('Plutonium : manifeste du client {p0} invalide.', p0=family.upper())) from None
    return revision, base_url, tuple(files.values())


def download_file(base_url, directory, entry):
    name, size, expected = entry
    digest = hashlib.sha1()
    total = 0
    with urlopen(base_url + expected, timeout=25) as response, (directory / name).open('wb') as output:
        cdn_url(response.geturl())
        while chunk := response.read(256 * 1024):
            total += len(chunk)
            if total > size:
                break
            digest.update(chunk)
            output.write(chunk)
    if size != total or digest.hexdigest() != expected:
        raise ValueError(tr('Plutonium : fichier téléchargé invalide ({p0}).', p0=name))


def prepare(base, mode):
    available = client_path(base, mode)
    if available is not None:
        return available
    family = mode[:2]
    root = base / 'dependencies' / f'plutonium-{family}'
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        available = client_path(base, mode)
        if available is not None:
            return available
        print(tr('Plutonium : téléchargement du client {p0} officiel.', p0=family.upper()), flush=True)
        revision, cdn, files = manifest_files(family)
        with tempfile.TemporaryDirectory(dir=root, prefix='.download-') as temporary:
            staging = Path(temporary)
            client = staging / 'client'
            target = root / 'client'
            previous = staging / 'previous'
            for name, _, _ in files:
                (client / name).parent.mkdir(parents=True, exist_ok=True)
            with ThreadPoolExecutor(max_workers=5) as workers:
                tasks = [workers.submit(download_file, cdn, client, entry) for entry in files]
                for task in tasks:
                    task.result()
            if target.exists() or target.is_symlink():
                target.rename(previous)
            try:
                client.rename(target)
            except OSError:
                if previous.exists() or previous.is_symlink():
                    previous.rename(target)
                raise
        print(tr('Plutonium : client {p0} r{p1} installé.', p0=family.upper(), p1=revision), flush=True)
        return target


def prefetch(base, mode):
    if client_path(base, mode) is not None:
        return
    log_path = base / 'logs' / f'plutonium-{mode[:2]}.log'
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open('a') as log:
            subprocess.Popen([sys.executable, __file__, str(base), mode], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True)
    except OSError as error:
        print(tr('Plutonium : téléchargement différé au prochain lancement ({p0}).', p0=error), flush=True)


if __name__ == '__main__':
    try:
        prepare(Path(sys.argv[1]), sys.argv[2])
    except (OSError, ValueError) as error:
        print(tr('Plutonium : installation impossible ({p0}).', p0=error), file=sys.stderr)
        raise SystemExit(1)
