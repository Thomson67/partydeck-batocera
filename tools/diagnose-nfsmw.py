#!/usr/bin/env python3
"""Read-only snapshot for comparing a working solo MW and a stalled party.

Print only selected runtime/graphics variables and module paths. Do not dump
full environments, command lines, tokens, game files or save contents.
Standalone: may be downloaded independently of the installed PartyDeck version.
"""
import json
import re
from pathlib import Path

KEYS = ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE', 'WINEPREFIX',
        'WINELOADER', 'WINESERVER', 'WINEARCH', 'WINEDEBUG', 'WINEDLLOVERRIDES',
        'PROTONPATH', 'STEAM_COMPAT_DATA_PATH', 'PROTON_USE_WINED3D',
        'LD_LIBRARY_PATH', 'LD_PRELOAD', '__NV_PRIME_RENDER_OFFLOAD',
        '__VK_LAYER_NV_optimus', '__GLX_VENDOR_LIBRARY_NAME', 'DRI_PRIME',
        'VK_DRIVER_FILES', 'VK_ICD_FILENAMES', 'VK_LOADER_DRIVERS_SELECT',
        'MESA_VK_DEVICE_SELECT', 'DXVK_CONFIG_FILE', 'DXVK_FILTER_DEVICE_NAME',
        'DXVK_LOG_LEVEL', 'ENABLE_GAMESCOPE_WSI')
MODULE = re.compile(r'wine/custom/|wine/[^/]+-unix/|(?:dxvk|d3d9|d3d11|dxgi|wined3d|winevulkan|vulkan|nvidia|libGL|libEGL|iris_dri|swrast|libgallium)', re.I)


def collect(proc=Path('/proc')):
    result = []
    for process in sorted(proc.glob('[0-9]*'), key=lambda p: int(p.name)):
        row = None
        try:
            if (process/'comm').read_text().strip().casefold() != 'speed.exe':
                continue
            raw = (process/'environ').read_bytes().split(b'\0')
            env = dict(item.decode(errors='replace').split('=', 1)
                       for item in raw if b'=' in item)
            row = {'pid': int(process.name), 'environment': {key: env[key] for key in KEYS if key in env}}
            modules = []
            for line in (process/'maps').read_text(errors='replace').splitlines():
                parts = line.split(maxsplit=5)
                if len(parts) == 6 and parts[5].startswith('/') and MODULE.search(parts[5]):
                    modules.append(parts[5])
            row['loaded_modules'] = sorted(set(modules))
            result.append(row)
        except (OSError, ValueError) as error:
            # Processes can exit between reads. Keep any preceding snapshots.
            if row is not None:
                row['read_error'] = type(error).__name__
                result.append(row)
    return result


if __name__ == '__main__':
    rows = collect()
    print(json.dumps({'speed_exe': rows}, indent=2, ensure_ascii=False))
    if not rows:
        print('Aucun speed.exe actif / No running speed.exe')
