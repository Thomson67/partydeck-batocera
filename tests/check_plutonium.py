"""First-use Plutonium installation, validation and cache reuse."""
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_plutonium as pluto

cdn = 'https://cdn.plutoniummod.com/updater/prod/files/'
payloads = {
    f'bin/{pluto.BOOTSTRAPPER}': b'bootstrapper',
    'games/t6mp.exe': b'multiplayer',
    'games/t6zm.exe': b'zombies',
    'storage/t6/zone/plutonium_mp.ff': b'client asset',
    'games/t5mp.exe': b'excluded',
}
files = [dict(name=name, size=len(value), hash=hashlib.sha1(value).hexdigest())
         for name, value in payloads.items()]
packages = {hashlib.sha1(value).hexdigest(): value for value in payloads.values()}
manifest = dict(revision=5369, baseUrl=cdn, files=files)


class Response(io.BytesIO):
    def __init__(self, url, body):
        self.url = url
        super().__init__(body)

    def geturl(self):
        return self.url


def fetch(url, *, timeout):
    if url == pluto.MANIFEST:
        return Response(url, json.dumps(manifest).encode())
    assert url.startswith(cdn)
    return Response(url, packages[url.removeprefix(cdn)])


with TemporaryDirectory() as root:
    base = Path(root)
    with patch.object(pluto, 'urlopen', side_effect=fetch):
        damaged = files[1]['hash']
        original = packages[damaged]
        packages[damaged] = b'invalid'
        try:
            pluto.prepare(base, 't6mp')
        except ValueError:
            assert pluto.client_path(base, 't6mp') is None
        else:
            raise AssertionError('A damaged download was installed')
        packages[damaged] = original
        client = pluto.prepare(base, 't6mp')
        assert client == pluto.client_path(base, 't6zm')
        assert set(path.relative_to(client).as_posix() for path in client.rglob('*') if path.is_file()) == (
            set(payloads) - {'games/t5mp.exe'})
        assert (client / 'games/t6mp.exe').read_bytes() == original

    with patch.object(pluto, 'urlopen', side_effect=AssertionError('unexpected download')):
        assert pluto.prepare(base, 't6zm') == client
        with patch.object(pluto.subprocess, 'Popen') as spawn:
            pluto.prefetch(base, 't6mp')
            spawn.assert_not_called()
            empty = base / 'empty'
            pluto.prefetch(empty, 't6mp')
            spawn.assert_called_once()
            assert spawn.call_args.args[0][-2:] == [str(empty), 't6mp']

        manual = base / 'plutonium'
        (manual / 'bin').mkdir(parents=True)
        (manual / 'games').mkdir()
        (manual / 'bin' / pluto.BOOTSTRAPPER).touch()
        (manual / 'games/t6mp.exe').touch()
        assert pluto.prepare(base, 't6mp') == manual
        assert pluto.prepare(base, 't6zm') == client

    files.append(dict(files[0], name='storage/t6/../../outside'))
    with patch.object(pluto, 'urlopen', side_effect=fetch):
        try:
            pluto.manifest_files()
        except ValueError:
            pass
        else:
            raise AssertionError('A path outside the client was accepted')

print('Plutonium: official-file selection, hash verification, background prefetch and manual override verified.')
