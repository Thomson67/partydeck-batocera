"""Archive preparation and isolated configuration for Ocarina Story Co-op."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_story_coop as story
from partydeck_catalog import recipe_for
from partydeck_profiles import defaults, read_profile, save_profile


with TemporaryDirectory() as folder:
    base = Path(folder)
    fixture = base / 'oot.o2r'
    fixture.write_bytes(b'user assets')
    binary = b'official client fixture'
    server = b'official server fixture'
    config = b'{"dataDir": "data"}'
    windows = base / 'windows.zip'
    linux = base / 'linux.tar.gz'
    with zipfile.ZipFile(windows, 'w') as package:
        for name, contents in (('soh.exe', binary), ('soh.o2r', b'ship assets'),
                               ('gamecontrollerdb.txt', b'gamepads'), ('assets\\extractor.xml', b'xml'),
                               ('steam_api64.dll', b'steam'), ('OOTSteamLink.exe', b'relay')):
            package.writestr(f'release\\{name}', contents)
    with tarfile.open(linux, 'w:gz') as package:
        for name, contents in (('OOTServer', server), ('config.json', config)):
            entry = tarfile.TarInfo(f'OcarinaStoryCoop-{story.VERSION}-linux/server/{name}')
            entry.size = len(contents)
            package.addfile(entry, io.BytesIO(contents))
    prefix = base / 'Ocarina of Time Story Co-op.wine'
    archive = prefix.with_suffix('.wsquashfs')
    with patch.object(story, 'download', side_effect=[windows, linux, windows, linux]):
        story.prepare(fixture, prefix)
        game = prefix / story.GAME_DIR
        assert (prefix/'autorun.cmd').read_text() == 'DIR=drive_c/game\nCMD=soh.exe\n'
        assert (game/'oot.o2r').read_bytes() == fixture.read_bytes()
        assert (game/'assets/extractor.xml').read_bytes() == b'xml'
        assert (game/'soh.exe').read_bytes() == binary
        assert not (game/'steam_api64.dll').exists()
        assert not (game/'OOTSteamLink.exe').exists()

        def squash(command, **options):
            assert (Path(command[1])/story.GAME_DIR/story.SERVER_DIR/'OOTServer').read_bytes() == server
            Path(command[2]).write_bytes(b'archive')

        with patch.object(story.subprocess, 'run', side_effect=squash):
            story.prepare(fixture, archive)
        assert archive.read_bytes() == b'archive'
        try:
            story.prepare(fixture, archive)
        except FileExistsError:
            assert archive.read_bytes() == b'archive'
        else:
            raise AssertionError('Existing archive was accepted')
    assert defaults(archive)['adapter'] == story.ADAPTER
    assert recipe_for(archive).adapter == story.ADAPTER
    assert recipe_for(base/'SoH Story Co-op.wsquashfs').adapter == story.ADAPTER
    assert recipe_for(base/'SoH.wsquashfs').adapter == 'soh-anchor'
    save_profile(base, archive, defaults(archive))
    assert read_profile(base, archive)['adapter'] == story.ADAPTER
    assert read_profile(base, archive)[story.ADAPTER] == story.defaults()
    legacy = defaults(archive)
    del legacy[story.ADAPTER]
    from partydeck_profiles import profile_path
    profile_path(base, archive).write_text(json.dumps(legacy))
    assert read_profile(base, archive)[story.ADAPTER] == story.defaults()

    expected = {'OOTServer': server, 'config.json': config}
    checksums = {name: hashlib.sha256(data).hexdigest() for name, data in expected.items()}
    with patch.object(story, 'SERVER_FILES', checksums):
        assert story.bundled_server_files(prefix) == expected
        custom_dir = Path('drive_c/SoH-Blair-Charlie-Win64')
        (prefix / 'autorun.cmd').write_bytes(f'DIR={custom_dir}\r\nCMD=soh.exe\r\n'.encode())
        game.rename(prefix / custom_dir)
        assert story.bundled_server_files(prefix) == expected
        def extract(command, **options):
            assert command[:3] == ['unsquashfs', '-cat', str(archive)]
            member = Path(command[3])
            if member.name == 'autorun.cmd':
                return subprocess.CompletedProcess(command, 0, (prefix / 'autorun.cmd').read_bytes())
            assert member.parent == custom_dir / story.SERVER_DIR
            return subprocess.CompletedProcess(command, 0, expected[member.name])
        with patch.object(story.subprocess, 'run', side_effect=extract):
            assert story.bundled_server_files(archive) == expected
        with patch.object(story.subprocess, 'run', side_effect=lambda command, **kw:
                          subprocess.CompletedProcess(command, 2, b'', b'cat: no matches for /member')):
            assert story.bundled_server_files(archive) is None
        game = prefix / custom_dir
        (game/story.SERVER_DIR/'OOTServer').write_bytes(b'unrecognized executable')
        try:
            story.bundled_server_files(prefix)
        except ValueError:
            pass
        else:
            raise AssertionError('Unrecognized server executable was accepted')
        (game/story.SERVER_DIR/'OOTServer').unlink()
        assert story.bundled_server_files(prefix) is None
        cache = base / 'dependencies' / story.VERSION
        with patch.object(story, 'download', return_value=linux) as download:
            assert story.cached_server_files(cache) == expected
            assert story.cached_server_files(cache) == expected
            assert download.call_count == 1
            (cache/'OOTServer').write_bytes(b'damaged cache')
            assert story.cached_server_files(cache) == expected
            assert download.call_count == 2

    options = story.defaults()
    options.update(port=21053, names=['J1', 'Invité', 'J3', 'J4'], skins=['link', '', '', ''])
    options['graphics'].update(msaa=2, volumes={'MainMusic': 70, 'SFX': 55})
    token = 'a' * 32
    for index in (1, 2):
        player = base / f'j{index}'
        private = player / story.GAME_DIR
        private.mkdir(parents=True)
        client = private / 'soh.exe'
        client.hardlink_to(game / 'soh.exe')
        (private/'oot.o2r').write_bytes(fixture.read_bytes())
        path = private / 'shipofharkinian.json'
        cvars = {'gRemote': {'Anchor': {'Enabled': 1}},
                 'gZeldaOnline': {'Party': {'StoryCode': 'existing-campaign'}}}
        if index == 2:
            cvars['gSettings'] = {'BootSequence': 1, 'Language': 2}
        path.write_text(json.dumps({'CVars': cvars, 'Window': {'Backend': {'Id': 1}}}))
        fixed = binary.replace(b'client', b'stable', 1)
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player),
                        PARTYDECK_PLAYER_WIDTH='1920', PARTYDECK_PLAYER_HEIGHT='540',
                        PARTYDECK_STORY_COOP=token), \
             patch.multiple(story, CLIENT_DIGEST=hashlib.sha256(binary).hexdigest(),
                            FIXED_CLIENT_DIGEST=hashlib.sha256(fixed).hexdigest(),
                            AUDIO_GUARD_OFFSET=binary.index(b'client'),
                            AUDIO_GUARD_ORIGINAL=b'client', AUDIO_GUARD_PATCH=b'stable'):
            story.configure_client(player, archive, private, player, options)
            assert client.read_bytes() == fixed
            inode = client.stat().st_ino
            story.configure_client(player, archive, private, player, options)
            assert client.stat().st_ino == inode
        data = json.loads(path.read_text())
        graphics = data['CVars']['gSettings']
        assert graphics['BootSequence'] == 2 and graphics['MSAAValue'] == 2
        assert graphics['Volume']['SFX'] == 55
        assert graphics['Volume']['MainMusic'] == (70 if index == 1 else 0)
        online = {
            'AutoConnect': 1, 'Enabled': 1, 'Host': story.client_host(index), 'Port': 21053,
            'Nickname': options['names'][index - 1],
            'Party': {'StoryCoop': 1, 'StoryCode': 'existing-campaign'}}
        if index == 1:
            online['Skin'] = 'link'
            assert json.loads(story.session_config(player, token).read_text())['storyCode'] == 'existing-campaign'
        else:
            assert not story.session_config(player, token).exists()
            assert graphics['Language'] == 2
        assert data['CVars']['gZeldaOnline'] == online
        assert data['CVars']['gRemote']['Anchor']['Enabled'] == 0
        assert data['Window']['Backend'] == {'Id': 1}
        assert not data['Window']['Fullscreen']['Enabled']
        assert (data['Window']['Width'], data['Window']['Height']) == (1920, 540)
    assert not (game/'shipofharkinian.json').exists()
    assert (game/'soh.exe').read_bytes() == binary
    mods = game / 'mods'
    mods.mkdir()
    for filename, resource in (('linkle.o2r', 'linkle/objects/object_link_child/Link'),
                               ('linkle-textures.o2r', 'linkle/textures/icon'),
                               ('standard.o2r', 'objects/object_link_child/Link')):
        with zipfile.ZipFile(mods / filename, 'w') as package:
            package.writestr(resource, b'data')
    assert story.skin_choices(base, prefix) == ['linkle|linkle-textures.o2r,linkle.o2r']
    invalid = base / 'unknown-soh.exe'
    invalid.write_bytes(b'unsupported Windows build')
    try:
        story.repair_client_audio(invalid)
    except ValueError:
        assert invalid.read_bytes() == b'unsupported Windows build'
    else:
        raise AssertionError('An unknown executable was accepted for the audio fix')

print('Story Co-op: archive contents, private audio fix, file selection and campaign continuity verified.')
