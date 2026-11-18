import os
os.environ['PARTYDECK_LANGUAGE'] = 'fr'  # Existing French UI contract checks.
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

path = Path(__file__).resolve().parents[1] / "scripts/partydeck-batocera-coop.py"
sys.path.insert(0, str(path.parent))
from partydeck_profiles import defaults, save_profile
spec = importlib.util.spec_from_file_location("coop", path)
coop = importlib.util.module_from_spec(spec)
sys.modules["coop"] = coop
spec.loader.exec_module(coop)

pad, another, keyboard, mouse = [
    coop.Device(Path(f"/dev/input/event{i}"), category, "", Path(f"/sys/mock/{i}"))
    for i, category in enumerate((coop.GAMEPADS, coop.GAMEPADS, coop.KEYBOARDS, coop.MICE))
]
assert coop.assign_players([pad, keyboard, mouse], "auto", "auto") == [[pad], [keyboard, mouse]]
assert coop.assign_players([pad], "auto", "auto") == [[pad]]
assert coop.assign_players([keyboard, mouse], "auto", "auto") == [[keyboard, mouse]]
assert coop.assign_players([pad, another, keyboard, mouse], "auto", "auto") == [[pad], [another]]
assert coop.assign_players([pad, keyboard, mouse], "1", "auto") == [[pad]]
assert coop.assign_players([pad, keyboard, mouse], "2", "clavier-j1") == [[keyboard, mouse], [pad]]
assert coop.assign_players([pad, keyboard, mouse], "auto", "auto", False) == [[pad]]
assert coop.assign_players([pad, another, keyboard, mouse], "auto", "auto", False) == [[pad], [another]]
assert coop.assign_players([pad, another, keyboard, mouse], "2", "clavier-j2", False) == [[pad], [another]]
for devices, count in (([keyboard, mouse], "auto"), ([pad, keyboard, mouse], "2")):
    try:
        coop.assign_players(devices, count, "auto", False)
        raise AssertionError("Keyboard assigned despite disabled option")
    except ValueError:
        pass

with patch.object(coop.subprocess, "run") as run:
    run.return_value.stdout = "321\n"
    run.return_value.returncode = 0
    assert coop.top_window("partydeck-coop-123-j1") == "321"
    assert run.call_args.args[0] == ["xdotool", "search", "--onlyvisible", "--class",
                                    "^partydeck-coop-123-j1$"]

with tempfile.TemporaryDirectory() as temp, patch.object(coop, "sandbox_arguments", return_value=[]), patch.object(coop.subprocess,"Popen") as popen:
    base = Path(temp)
    game = base / "Game.wsquashfs"
    coop.start_player(base, base / "j2", game, game, [], (960, 0, 960, 1080), "test-j2")
    assert popen.call_args.kwargs["env"]["SDL_VIDEO_X11_WMCLASS"] == "test-j2"
    assert "test-j2" not in popen.call_args.args[0]
    assert "-W" in popen.call_args.args[0]
    assert "--backend-disable-keyboard" not in popen.call_args.args[0]
    assert "--backend-disable-mouse" not in popen.call_args.args[0]
    assert "--grab" not in popen.call_args.args[0]
    coop.start_player(base, base / "j2", game, game, [keyboard, mouse],
                      (960, 0, 960, 1080), "test-j2", shared_keyboard_mouse=False)
    exclusive = popen.call_args.args[0]
    assert "--backend-disable-keyboard" in exclusive
    assert "--backend-disable-mouse" in exclusive
    assert "--grab" in exclusive
    assert "--libinput-hold-dev=/dev/input/event2,/dev/input/event3," in exclusive

for split, second_position, inputs, shared, party in [
    ("horizontal", (0, 540, 1920, 540), [pad, keyboard, mouse], False, False),
    ("vertical", (960, 0, 960, 1080), [pad, keyboard, mouse], False, False),
    ("horizontal", (0, 540, 1920, 540), [pad, another], True, False),
    ("vertical", (960, 0, 960, 1080), [pad, another], True, False),
    ("horizontal", (0, 540, 1920, 540), [pad, another, keyboard, mouse], True, True),
]:
    with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
        def mock(obj, attr, **kwargs):
            return stack.enter_context(patch.object(obj, attr, **kwargs))
        base = Path(temp)
        game = base / "Game.wsquashfs"
        if party:
            profile = defaults(game)
            profile['keyboard_player'] = False
            save_profile(base, game, profile)
            mock(coop, "PARTY_SAVES", new=base / "party-saves")
        mock(coop.shutil, "which", return_value="/path")
        mock(coop, "read_input_devices", return_value=inputs)
        mock(coop, "primary_monitor", return_value=(0, 0, 1920, 1080))
        mock(coop.subprocess, "run", return_value=Mock(returncode=0))
        mock(coop.signal, "signal")
        mock(coop, "stop_players")
        processes = [Mock(pid=123, **{"poll.return_value": None, "wait.return_value": 0}),
                     Mock(pid=456, **{"poll.return_value": None, "wait.return_value": 0})]
        starts = mock(coop, "start_player", side_effect=processes)
        classes = [f"partydeck-coop-{os.getpid()}-j1", f"partydeck-coop-{os.getpid()}-j2"]
        windows = mock(coop, "top_window", side_effect={classes[0]:"810", classes[1]:"811"}.get)
        place = mock(coop, "place_window", return_value=True)
        for process in processes:
            process.poll.side_effect = lambda: 0 if place.call_count==2 else None
        output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        assert coop.run_session(base, base, game, game, "auto", split, "auto", party=party) == 0
        assert [call.args[0] for call in windows.call_args_list] == classes
        assert [call.args[-1] for call in starts.call_args_list] == classes
        assert all(call.kwargs["shared_keyboard_mouse"] is shared
                   for call in starts.call_args_list)
        if party:
            assert all(d.category == coop.GAMEPADS for call in starts.call_args_list for d in call.args[4])
        assert place.call_args_list[1].args == ("811", second_position)
        assert "Joueurs : 2" in output.getvalue() and "Fenêtre J2 placée : 811" in output.getvalue()
print("Attribution auto, classes J1/J2 et placement horizontal/vertical vérifiés.")
