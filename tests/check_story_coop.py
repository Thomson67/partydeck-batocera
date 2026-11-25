"""Archive preparation and isolated configuration for Ocarina Story Co-op."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import sys
import tarfile
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import partydeck_story_coop as story
from partydeck_catalog import recipe_for
from partydeck_profiles import defaults, read_profile, save_profile
from partydeck_soh_camera import configure_freecam
from partydeck_story_lobby import CLIENT_STORY_SHARE_ITEM, Lobby, Player, is_selected_pickup, share_game_skin


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
    for previous in ('keep', 'on', 'off'):
        assert story.validate({'consumables': previous})['consumables'] == dict.fromkeys(story.CONSUMABLES, previous)
    assert story.validate({'camera_axes': {'first_y': 'off'}})['camera_axes'] == {
        'third_x': 'keep', 'third_y': 'keep', 'first_x': 'keep', 'first_y': 'off'}
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
        hidden = fixed.replace(b'fixture', b'quieted', 1)
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player),
                        PARTYDECK_PLAYER_WIDTH='1920', PARTYDECK_PLAYER_HEIGHT='540',
                        PARTYDECK_STORY_COOP=token), \
             patch.multiple(story, CLIENT_DIGEST=hashlib.sha256(binary).hexdigest(),
                            FIXED_CLIENT_DIGEST=hashlib.sha256(fixed).hexdigest(),
                            HIDDEN_WINDOW_DIGEST=hashlib.sha256(hidden).hexdigest(),
                            AUDIO_GUARD_OFFSET=binary.index(b'client'),
                            AUDIO_GUARD_ORIGINAL=b'client', AUDIO_GUARD_PATCH=b'stable',
                            HIDE_WINDOW_OFFSET=binary.index(b'fixture'),
                            HIDE_WINDOW_ORIGINAL=b'fixture', HIDE_WINDOW_PATCH=b'quieted'):
            story.configure_client(player, archive, private, player, options, base / 'skins')
            assert client.read_bytes() == hidden
            inode = client.stat().st_ino
            story.configure_client(player, archive, private, player, options, base / 'skins')
            assert client.stat().st_ino == inode
            assert story.patch_client(client, False) and client.read_bytes() == fixed
            assert story.patch_client(client, True) and client.read_bytes() == hidden
        data = json.loads(path.read_text())
        graphics = data['CVars']['gSettings']
        assert graphics['BootSequence'] == 2 and graphics['MSAAValue'] == 2
        assert graphics['Volume']['SFX'] == 55
        assert graphics['Volume']['MainMusic'] == (70 if index == 1 else 0)
        online = {
            'AutoConnect': 1, 'Enabled': 1, 'Host': story.client_host(index), 'Port': 21053,
            'Nickname': options['names'][index - 1], 'FileServer': '',
            'Party': {'StoryCoop': 1, 'StoryCode': 'existing-campaign'}}
        if index == 1:
            online['Skin'] = 'link'
            host_settings = json.loads(story.session_config(player, token).read_text())
            assert host_settings['storyCode'] == 'existing-campaign' and not host_settings['shareAmmoRupeesHp']
        else:
            online['Skin'] = ''
            assert not story.session_config(player, token).exists()
            assert graphics['Language'] == 2
        assert data['CVars']['gZeldaOnline'] == online
        assert data['CVars']['gRemote']['Anchor']['Enabled'] == 0
        assert data['Window']['Backend'] == {'Id': 1}
        assert not data['Window']['Fullscreen']['Enabled']
        assert (data['Window']['Width'], data['Window']['Height']) == (1920, 540)
        with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player)), \
             patch.object(story, 'patch_client', return_value=False), \
             patch.object(story.skins, 'mask_link_overrides',
                          side_effect=subprocess.CalledProcessError(1, ['mount'])):
            bad_skin = options | {'skins': ['link'] * 4}
            story.configure_client(player, archive, private, player, bad_skin, base / 'skins')
            failed_online = json.loads(path.read_text())['CVars']['gZeldaOnline']
            assert failed_online['AutoConnect'] == 1 and failed_online['FileServer'] == ''
            assert failed_online.get('Skin') == online.get('Skin')
        if index == 2:
            with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player)), \
                 patch.object(story, 'patch_client', return_value=False):
                configured = options | {'camera_axes': {'third_x': 'on', 'third_y': 'off',
                                                        'first_x': 'off', 'first_y': 'on'}}
                expected = {'FreeLook': {'InvertXAxis': 1, 'InvertYAxis': 0},
                            'Controls': {'InvertAimingXAxis': 0, 'InvertAimingYAxis': 1}}
                before = json.loads(path.read_text())
                before['CVars']['gSettings']['FreeLook'] = {'InvertYAxis': 1}
                path.write_text(json.dumps(before))
                for _ in range(2):
                    story.configure_client(player, archive, private, player, configured, base / 'skins')
                    current = json.loads(path.read_text())['CVars']['gSettings']
                    assert {section: current[section] for section in expected} == expected
                story.configure_client(player, archive, private, player, options, base / 'skins')
                restored = json.loads(path.read_text())['CVars']['gSettings']
                assert restored['FreeLook'] == {'InvertYAxis': 1}
                assert restored['Controls'] == {}
                assert not (private / 'partydeck-camera-axes-original.json').exists()
            player_mods = private / 'mods'
            player_mods.mkdir()
            pack = player_mods / '01 - Enhanced 3DS Link Reworked'
            pack.mkdir()
            original_model = pack / 'original.otr'
            original_model.write_bytes(b'original mod')
            with zipfile.ZipFile(player_mods / 'linkle.o2r', 'w') as package:
                package.writestr('linkle/objects/object_link_child/Link', b'catalogue skin')
            with patch.dict(os.environ, PARTYDECK_PRIVATE_PLAYER=str(player)), \
                 patch.object(story, 'patch_client', return_value=False), \
                 patch.object(story.skins, 'mask_link_overrides') as mask:
                selected = options | {'skins': ['link', 'linkle', '', '']}
                story.configure_client(player, archive, private, player, selected, base / 'skins')
                assert json.loads(path.read_text())['CVars']['gZeldaOnline']['Skin'] == 'linkle'
                mask.assert_called_once_with(private, player)
                story.configure_client(player, archive, private, player, options, base / 'skins')
                assert json.loads(path.read_text())['CVars']['gZeldaOnline']['Skin'] == ''
                assert mask.call_count == 1
                assert original_model.read_bytes() == b'original mod'
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
        story.patch_client(invalid, True)
    except ValueError:
        assert invalid.read_bytes() == b'unsupported Windows build'
    else:
        raise AssertionError('An unknown executable was accepted for the audio fix')

    client = base / 'clock-soh.exe'
    binary = b'audio original; time original; window original'
    fixed = binary.replace(b'audio original', b'audio repaired')
    hidden = fixed.replace(b'window original', b'window repaired')
    local = fixed.replace(b'time original', b'time private!')
    local_hidden = hidden.replace(b'time original', b'time private!')
    client.write_bytes(binary)

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    with patch.multiple(story, CLIENT_DIGEST=digest(binary), FIXED_CLIENT_DIGEST=digest(fixed),
                        HIDDEN_WINDOW_DIGEST=digest(hidden), ORIGINAL_TIME_DIGEST=digest(local),
                        ORIGINAL_TIME_HIDDEN_WINDOW_DIGEST=digest(local_hidden),
                        AUDIO_GUARD_OFFSET=0, AUDIO_GUARD_ORIGINAL=b'audio original', AUDIO_GUARD_PATCH=b'audio repaired',
                        HIDE_WINDOW_OFFSET=binary.index(b'window'), HIDE_WINDOW_ORIGINAL=b'window original',
                        HIDE_WINDOW_PATCH=b'window repaired', LOCAL_TIME_OFFSET=binary.index(b'time'),
                        LOCAL_TIME_PATCH=b'time private!', LOCAL_TIME_ORIGINAL=b'time original'):
        for hide_window, original_time, expected in ((True, True, local_hidden), (True, False, hidden),
                                                    (False, True, local), (False, False, fixed)):
            assert story.patch_client(client, hide_window, original_time)
            assert client.read_bytes() == expected
            assert not story.patch_client(client, hide_window, original_time)

    template = Path(__file__).resolve().parents[1] / 'templates' / 'soh-common.json'
    camera = base / 'camera.json'
    graphics = {'FreeLook': {'Enabled': 0, 'InvertYAxis': 1}}
    configure_freecam(graphics, camera, True, template)
    assert graphics['FreeLook'] == {'Enabled': 1, 'InvertYAxis': 1}
    controls = graphics['Controllers']
    port = controls['Port1']
    assert port['RightStick']['UpAxisDirectionMappingIds'] == 'P0-S1-D2-SDLA3-ADN,'
    c_up = port['Buttons']['8ButtonMappingIds'].split(',')
    assert 'P0-B8-SDLB11' in c_up and all('SDLA3' not in entry for entry in c_up)
    configured = json.dumps(graphics)
    configure_freecam(graphics, camera, True, template)
    assert json.dumps(graphics) == configured
    assert configure_freecam(graphics, camera, False, template)
    assert graphics == {'FreeLook': {'Enabled': 0, 'InvertYAxis': 1}}

    reference = 'partydeck-0123456789abcdef'
    empty = b'\x09\x02\x00\x02J2'
    explicit = b'\x09\x02\x04link\x02J2'
    assert share_game_skin(empty, reference) == b'\x09\x02\x1a' + reference.encode() + b'\x02J2'
    assert share_game_skin(explicit, reference) == explicit
    assert share_game_skin(empty, '') == empty
    assert share_game_skin(empty[:-1], reference) == empty[:-1]

    for modes, old, expected in (
            (('on', 'on', 'off'), False, {'rupees', 'ammo'}),
            (('off', 'off', 'on'), False, {'healing'}),
            (('keep', 'off', 'off'), True, {'rupees'}),
            (('keep', 'off', 'off'), False, set()),
            (('off', 'on', 'off'), True, {'ammo'}),
            (('on', 'on', 'on'), False, None),
            (('keep', 'keep', 'keep'), True, None)):
        lobby = Lobby(0, {'consumables': dict(zip(story.CONSUMABLES, modes))}, None)
        host = Player(1, None)
        payload = json.dumps(dict(shareAmmoRupeesHp=old, storyCoop=True, storyCode='existing-campaign')).encode()
        settings = json.loads(lobby.create_party_payload(host, payload))
        assert settings['storyCode'] == 'existing-campaign' and settings['storyCoop']
        assert host.pending_sharing == expected
        assert settings['shareAmmoRupeesHp'] == (expected is None or bool(expected))
        if expected is not None:
            for category, item in (('rupees', 0x4C), ('ammo', 0x49), ('healing', 0x48)):
                packet = struct.pack('<BHH', CLIENT_STORY_SHARE_ITEM, 0, item)
                assert is_selected_pickup(packet, expected) == (category in expected)
            assert not is_selected_pickup(struct.pack('<BHH', CLIENT_STORY_SHARE_ITEM, 0, 0x3D), expected)

print('Story Co-op: private client, campaign continuity and independent consumable settings verified.')
