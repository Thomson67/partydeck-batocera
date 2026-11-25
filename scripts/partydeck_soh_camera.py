"""Configure SoH camera controls for the SDL gamepad on the player's port."""
import json

# direction, SDL axis, sign, N64 C button, SDL D-pad button, N64 D-pad button
CAMERA_DIRECTIONS = (
    ('Left', 2, -1, 2, 13, 512),
    ('Right', 2, 1, 1, 14, 256),
    ('Up', 3, -1, 8, 11, 2048),
    ('Down', 3, 1, 4, 12, 1024),
)
CAMERA_AXES = {
    'third_x': ('FreeLook', 'InvertXAxis', 'Vue 3e personne · inverser l’axe horizontal'),
    'third_y': ('FreeLook', 'InvertYAxis', 'Vue 3e personne · inverser l’axe vertical'),
    'first_x': ('Controls', 'InvertAimingXAxis', 'Vue 1re personne et visée · inverser l’axe horizontal'),
    'first_y': ('Controls', 'InvertAimingYAxis', 'Vue 1re personne et visée · inverser l’axe vertical'),
}
DISTANCE_MODES = {'keep': 'Conserver', 'game': 'Suivre la distance du jeu', 'fixed': 'Distance fixe'}
MIN_DISTANCE, DEFAULT_DISTANCE, MAX_DISTANCE = 100, 185, 900
CAMERA_SETTINGS = {
    **{name: ('gSettings', group, key) for name, (group, key, _) in CAMERA_AXES.items()},
    'use_game_distance': ('gSettings', 'FreeLook', 'UseGameDistance'),
    'max_camera_distance': ('gSettings', 'FreeLook', 'MaxCameraDistance'),
    'remove_black_bars': ('gEnhancements', 'DisableBlackBars'),
}


def configure_camera_settings(cvars, backup, modes, distance_mode, distance, *, persistent):
    from partydeck_profiles import atomic_write

    overrides = {name: int(mode == 'on') for name, mode in modes.items() if mode != 'keep'}
    if distance_mode != 'keep':
        overrides['use_game_distance'] = int(distance_mode == 'game')
    if distance_mode == 'fixed':
        overrides['max_camera_distance'] = distance

    original = json.loads(backup.read_text()) if backup.is_file() else {}
    active = {}
    for name, (*groups, key) in CAMERA_SETTINGS.items():
        if name not in overrides and not (persistent and name in original):
            continue
        section = cvars
        for group in groups:
            section = section.setdefault(group, {})
        if name in overrides:
            active[name] = original.get(name, section.get(key)) if persistent else section.get(key)
            section[key] = overrides[name]
        elif original[name] is None:
            section.pop(key, None)
        else:
            section[key] = original[name]
    saved = original | active
    if original != saved:
        atomic_write(backup, json.dumps(saved))
    return active if saved != active else None


def mapping_ids(value):
    return [identifier for identifier in value.split(',') if identifier]


def store_ids(target, key, ids):
    if ids:
        target[key] = ','.join(ids) + ','
    else:
        target.pop(key, None)


def configure_freecam(settings, backup, enabled, template):
    from partydeck_profiles import atomic_write

    if not enabled:
        if not backup.is_file():
            return False
        before = json.loads(backup.read_text())
        for key, target in (('Controllers', settings), ('Enabled', settings.setdefault('FreeLook', {}))):
            if key in before:
                target[key] = before[key]
            else:
                target.pop(key, None)
        return True

    if not backup.is_file():
        before = {key: settings[key] for key in ('Controllers',) if key in settings}
        free_look = settings.get('FreeLook', {})
        if 'Enabled' in free_look:
            before['Enabled'] = free_look['Enabled']
        atomic_write(backup, json.dumps(before))

    controllers = settings.setdefault('Controllers', {})
    if not controllers.get('Port1', {}).get('HasConfig'):
        defaults = json.loads(template.read_text())['CVars']['gSettings']['Controllers']
        controllers['Port1'] = defaults['Port1']
        for category in ('AxisDirectionMappings', 'ButtonMappings', 'RumbleMappings'):
            controllers.setdefault(category, {}).update(defaults[category])
    setup_controls(controllers)
    settings.setdefault('FreeLook', {})['Enabled'] = 1
    return False


def setup_controls(controllers):
    port = controllers['Port1']
    right_stick = port.setdefault('RightStick', {})
    axes = controllers.setdefault('AxisDirectionMappings', {})
    buttons = controllers.setdefault('ButtonMappings', {})
    bindings = port.setdefault('Buttons', {})
    for direction, (name, axis, sign, c_button, dpad, d_button) in enumerate(CAMERA_DIRECTIONS):
        suffix = 'P' if sign > 0 else 'N'
        identifier = f'P0-S1-D{direction}-SDLA{axis}-AD{suffix}'
        axes[identifier] = {'AxisDirectionMappingClass': 'SDLAxisDirectionToAxisDirectionMapping',
                            'Direction': direction, 'Stick': 1, 'SDLControllerAxis': axis, 'AxisDirection': sign}
        key = f'{name}AxisDirectionMappingIds'
        ids = mapping_ids(right_stick.get(key, ''))
        ids = [entry for entry in ids
               if not axes.get(entry, {}).get('AxisDirectionMappingClass', '').startswith('SDL')]
        store_ids(right_stick, key, [*ids, identifier])

        key = f'{c_button}ButtonMappingIds'
        ids = [entry for entry in mapping_ids(bindings.get(key, ''))
               if buttons.get(entry, {}).get('SDLControllerAxis') not in (2, 3)]
        if not any(buttons.get(entry, {}).get('ButtonMappingClass', '').startswith('SDL') for entry in ids):
            identifier = f'P0-B{c_button}-SDLB{dpad}'
            buttons[identifier] = {'ButtonMappingClass': 'SDLButtonToButtonMapping',
                                   'SDLControllerButton': dpad, 'Bitmask': c_button}
            ids.append(identifier)
            dpad_key = f'{d_button}ButtonMappingIds'
            dpad_ids = mapping_ids(bindings.get(dpad_key, ''))
            store_ids(bindings, dpad_key, [entry for entry in dpad_ids
                                           if buttons.get(entry, {}).get('SDLControllerButton') != dpad])
        store_ids(bindings, key, ids)
