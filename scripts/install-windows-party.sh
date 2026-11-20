#!/usr/bin/env bash
set -euo pipefail

version='v0.8.7-e'
asset="partydeck-${version}-anylinux-x86_64.AppImage"
checksum='9a6df7a214f5320154bf5344a65431d118ded24917cc65a3d578280e82f42acd'
base='/userdata/system/windows-party'
release="$base/releases/$version"
appdir="$release/AppDir"
launcher="$base/windows-party"
coop_helper="$base/partydeck-batocera-coop.py"
profiles_helper="$base/partydeck_profiles.py"
xwayland_dir="$base/releases/xwayland-24.1.15-1"
ports_dir='/userdata/roms/ports'

die() { printf 'Erreur : %s\n' "$*" >&2; exit 1; }

load_graphical_environment() {
    for pid in $(pidof emulationstation 2>/dev/null || true); do
        [[ -r /proc/$pid/environ ]] || continue
        unset DISPLAY WAYLAND_DISPLAY XAUTHORITY
        while IFS= read -r -d '' item; do
            case "$item" in
                DISPLAY=*|WAYLAND_DISPLAY=*|XDG_RUNTIME_DIR=*|XAUTHORITY=*|DBUS_SESSION_BUS_ADDRESS=*)
                    export "$item" ;;
            esac
        done < "/proc/$pid/environ"
        break
    done
    export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/var/run}"
    [[ ${DISPLAY:-} =~ ^:[0-9]+(\.[0-9]+)?$ ]] || export DISPLAY=:0
}

usage() {
    cat <<'HELP'
Windows Party — Batocera
  windows-party verifier
  windows-party configurer ["/chemin/Jeu.wsquashfs"]
  windows-party ajouter "/chemin/Jeu.wine" [auto|1|2|3|4] [horizontal|vertical] [auto|clavier-j1|clavier-j2]
  windows-party profil "/chemin/Jeu.wsquashfs"
  windows-party stockage [bilan|nettoyer|purger-caches|reglages]
Formats : .wine, .pc, .wsquashfs
HELP
}

install_portable_xwayland() {
    local staging checksum path package
    staging=$(mktemp -d "$base/releases/.xwayland-XXXXXX")
    trap 'rm -rf -- "$staging"' EXIT
    printf 'Installation de Xwayland portable dans le dossier PartyDeck.\n'

    # Debian upstream packages, pinned by SHA-256 from the amd64 package indexes.
    # PartyDeck's pinned AppImage provides glibc, Mesa and the Wayland libraries.
    while read -r checksum path; do
        package="${path##*/}"
        curl --fail --silent --show-error --location --retry 2 --connect-timeout 15 \
            --proto '=https' "https://deb.debian.org/debian/$path" --output "$staging/$package" ||
            die "Téléchargement de $package impossible."
        (cd "$staging" && printf '%s  %s\n' "$checksum" "$package" | sha256sum -c -) ||
            die "Somme SHA-256 incorrecte pour $package."
    done <<'PACKAGES'
bd43e020b8fed399db3eebf098111f10fba4c436fff99ccad72cc7e27c9764ec pool/main/e/e2fsprogs/libcom-err2_1.47.2-3+b12_amd64.deb
e4947f3291528f03d574f2b01d5c5fc45c58c47480f32888a5cdf0f231ab584e pool/main/f/freetype/libfreetype6_2.13.3+dfsg-1+deb13u1_amd64.deb
0b11ad17be0300b63ad4eeb4c6450fed24d34b7b740f23e5363dcb29ee6d5eba pool/main/k/keyutils/libkeyutils1_1.6.3-6_amd64.deb
30847c1fde4240567d7ed3aeab4f655dd591203758b857e85e824045aae70299 pool/main/k/krb5/libgssapi-krb5-2_1.21.3-5+deb13u1_amd64.deb
7da07ee674b47f1f0be7cc89317c25310086a1f1761217d0f72e6ae2c5a69b84 pool/main/k/krb5/libk5crypto3_1.21.3-5+deb13u1_amd64.deb
47d71d6a7f2e59b9bae5f89602397594805113b95889ad18fa703cd53abafc97 pool/main/k/krb5/libkrb5-3_1.21.3-5+deb13u1_amd64.deb
3a0acd8b37955c0e102c756b52c97df2a31f67b96453c35dab70df218d309117 pool/main/k/krb5/libkrb5support0_1.21.3-5+deb13u1_amd64.deb
de3e735f2ecf97cdcd51251ec5c1f84d5ff0ce9f8f822dd7b345dc293af446f0 pool/main/libe/libei/libei1_1.3.901-1_amd64.deb
d61d40a3dfc0b7030854237c5445f6b9b469c6c3b53a2ff1f98dfa0ae0c7b3f1 pool/main/libe/libei/liboeffis1_1.3.901-1_amd64.deb
4c4c8024f2175086de65bca9fdc3fbb967f2863ebf249d489c66d0c8103dd3a3 pool/main/libe/libepoxy/libepoxy0_1.5.10-2_amd64.deb
49f7330e1bbe3f48946fee5c07870df660374f9f77b378840d6edf1a3b3444cd pool/main/libf/libfontenc/libfontenc1_1.1.8-1+b2_amd64.deb
e2736abceb853d036da0eb0e9f93992dcd31636fe667ef3372d203f53fe30d9c pool/main/libg/libgcrypt20/libgcrypt20_1.12.4-2_amd64.deb
ef307016953fca2d257786cb323ad7c3b8b84fe9e17a64c9adeaae5d5a434d30 pool/main/libg/libgpg-error/libgpg-error0_1.61-5_amd64.deb
2465b4e9fa85cff54dc10a6da3e64074d8d9292c86e4a8f989b809d6b158e97e pool/main/libp/libpng1.6/libpng16-16t64_1.6.48-1+deb13u5_amd64.deb
ef4536c09bf5063554310e22d586ae90990100ba66d2fe7c35660e9e658913b6 pool/main/libt/libtirpc/libtirpc3t64_1.3.6+ds-1_amd64.deb
0faccb95f5d306fc30c8b128572b92ff97bf59c547f1f8a46b57e0b4c6dd045b pool/main/libx/libxcvt/libxcvt0_0.1.3-1_amd64.deb
79a7f56e4a0c7b1defa706c7b1f3076f7d80aaeea9de253b2a87406253319681 pool/main/libx/libxfont/libxfont2_2.0.6-1+deb13u1_amd64.deb
312acac8172454463645ebaf574eb586b2a04a93d6c62349df7bf46ee3daf78d pool/main/x/xwayland/xwayland_24.1.15-1_amd64.deb
PACKAGES

    python3 - "$staging" <<'PYTHON'
import io
from pathlib import Path
import sys
import tarfile

destination = Path(sys.argv[1])
for deb in destination.glob("*.deb"):
    with deb.open("rb") as archive:
        if archive.read(8) != b"!<arch>\n":
            raise ValueError(f"Invalid Debian archive: {deb.name}")
        while header := archive.read(60):
            size = int(header[48:58])
            if header[:16].strip().rstrip(b"/") == b"data.tar.xz":
                payload = archive.read(size)
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:xz") as data:
                    members = (
                        entry for entry in data
                        if entry.name.removeprefix("./") == "usr/bin/Xwayland"
                        or entry.name.removeprefix("./").startswith("usr/lib/x86_64-linux-gnu/")
                    )
                    data.extractall(destination, members=members, filter="data")
                break
            archive.seek(size + size % 2, io.SEEK_CUR)
        else:
            raise ValueError(f"Missing data.tar.xz in {deb.name}")
    deb.unlink()
PYTHON

    cat > "$staging/Xwayland" <<'WRAPPER'
#!/bin/sh
runtime=${0%/*}
partydeck_lib="$PARTYDECK_XWAYLAND_APPDIR/lib"
exec "$partydeck_lib/ld-linux-x86-64.so.2" \
    --library-path "$runtime/usr/lib/x86_64-linux-gnu:$partydeck_lib" \
    "$runtime/usr/bin/Xwayland" "$@"
WRAPPER
    chmod 0755 "$staging/Xwayland"
    "$staging/Xwayland" -version || die 'Le Xwayland portable ne démarre pas.'
    mv -T -- "$staging" "$xwayland_dir"
    trap - EXIT
}

prepare_batocera_umu() {
    local bin="$appdir/bin"
    local bridge_revision="2c541f40f62f40a8c8c58d6430cd5c1731711ce7"
    local bridge_checksum="12d6c194bea55b0ee723a45e9379e1551cd8f9d07a1ea84263613074b60f6239"
    local upstream_checksum="d0005a58602041229cc467dab03dc0c0b9e8cce09a8145b16b7683244cf17804"
    local bridge_url="https://raw.githubusercontent.com/Thomson67/umu-runner-toolbox/$bridge_revision/toolbox/overlay/umu-batocera/umu-root-runner.py"
    local marker='# PartyDeck Batocera UMU bridge'
    local staging original="$bin/umu-run.upstream"

    if [[ -x $original && -f $bin/umu-root-runner.py ]] &&
       grep -qxF -- "$marker" "$bin/umu-run"; then
        return
    fi

    staging=$(mktemp -d "$bin/.umu-batocera-XXXXXX")
    trap 'rm -rf -- "$staging"' EXIT
    curl --fail --silent --show-error --location --retry 2 --connect-timeout 15 \
        --proto '=https' "$bridge_url" --output "$staging/umu-root-runner.py" ||
        die 'Téléchargement du pont UMU pour Batocera impossible.'
    (cd "$staging" && printf '%s  %s\n' "$bridge_checksum" umu-root-runner.py | sha256sum -c -) ||
        die 'Somme SHA-256 incorrecte pour le pont UMU.'

    if [[ ! -x $original ]]; then
        (cd "$bin" && printf '%s  %s\n' "$upstream_checksum" umu-run | sha256sum -c -) ||
            die 'Le binaire UMU ne correspond pas à celui de l’AppImage PartyDeck.'
        cp -p -- "$bin/umu-run" "$staging/umu-run.upstream"
        mv -fT -- "$staging/umu-run.upstream" "$original"
    fi

    cat > "$staging/umu-run" <<'WRAPPER'
#!/bin/sh
# PartyDeck Batocera UMU bridge
bin=${0%/*}
if [ "$(id -u)" = 0 ]; then
    exec python3 "$bin/umu-root-runner.py" "$bin/umu-run.upstream" "$@"
fi
exec "$bin/umu-run.upstream" "$@"
WRAPPER
    chmod 0755 "$staging/umu-run"
    mv -fT -- "$staging/umu-root-runner.py" "$bin/umu-root-runner.py"
    mv -fT -- "$staging/umu-run" "$bin/umu-run"
    rm -rf -- "$staging"
    trap - EXIT
}

case "${1:-verifier}" in
    -h|--help) usage; exit 0 ;;
    configurer) [[ $# -le 2 ]] || { usage; exit 2; } ;;
    profil) [[ $# -eq 2 ]] || { usage; exit 2; } ;;
    installer|verifier) [[ $# -le 1 ]] || die 'Argument inattendu.' ;;
    stockage) [[ $# -le 2 ]] || { usage; exit 2; } ;;
    coop|preparer-coop|party|ajouter) [[ $# -ge 2 && $# -le 5 ]] || { usage; exit 2; } ;;
    *) usage; exit 2 ;;
esac

command -v batocera-version >/dev/null || die 'À exécuter sur Batocera.'
[[ $(uname -m) == x86_64 ]] || die 'Cette version de PartyDeck est destinée aux PC x86_64.'
for cmd in curl sha256sum python3 flock realpath; do
    command -v "$cmd" >/dev/null || die "Commande requise : $cmd"
done

if [[ ${1:-verifier} == installer ]]; then
    source_dir=$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")
    python3 "$source_dir/partydeck_migrate.py" prepare /userdata/system/partydeck-test "$base"
fi
mkdir -p "$base/releases" "$base/logs" "$base/cache"
if [[ ${1:-verifier} == configurer || ${1:-verifier} == profil ]]; then
    [[ -f $profiles_helper ]] || die 'Réinstallez Windows Party pour restaurer le gestionnaire de profils.'
    mode=$1
    shift
    load_graphical_environment
    exec python3 "$profiles_helper" "$mode" "$base" "$@"
fi

if [[ ${1:-verifier} == stockage ]]; then
    shift
    exec python3 "$base/partydeck_storage.py" "${1:-bilan}" "$base"
fi

exec 9>"$base/session.lock"
flock -n 9 || die 'Une session Windows Party est déjà en cours.'

if [[ ${1:-verifier} == preparer-coop || ${1:-verifier} == ajouter ]]; then
    [[ -x $launcher && -f $coop_helper ]] || die 'Installez cette version de PartyDeck avant de préparer un port coop.'
    mode=prepare
    [[ $1 != ajouter ]] || mode=prepare-party
    shift
    python3 "$coop_helper" "$mode" "$appdir" "$base" "$ports_dir" "$@" 9>&-
    exit 0
fi

if [[ ${1:-verifier} == installer ]]; then
    if ! PYGAME_HIDE_SUPPORT_PROMPT=1 python3 -c 'import pygame; assert pygame.version.vernum[0] >= 2' >/dev/null 2>&1; then
        printf 'Attention : Pygame 2 est requis pour le configurateur manette. Ancienne interface accessible avec PARTYDECK_UI=legacy.\n' >&2
    fi
    source_dir=$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")
    source_helper="$source_dir/partydeck-batocera-coop.py"
    [[ -f $source_dir/partydeck_umu.py ]] || die 'Module UMU privé absent / Private UMU module missing.'
    [[ -f $source_dir/partydeck_mangohud.py && -f $source_dir/partydeck_controls.py ]] || die 'Modules Windows Party absents / Windows Party modules missing.'
    [[ -f $source_dir/partydeck_couch.py ]] || die 'Module du configurateur manette absent du paquet.'
    [[ -f $source_dir/partydeck_display.py ]] || die 'Module écran/GPU absent / Display/GPU module missing.'
    [[ -f $source_dir/partydeck_bottles.py ]] || die 'Module bottles absent / Bottles module missing.'
    [[ -f $source_dir/partydeck_storage.py ]] || die 'Module stockage absent du paquet.'
    [[ -f $source_dir/partydeck_borderlands2.py ]] || die 'Module Borderlands 2 absent du paquet.'
    [[ -f $source_dir/partydeck_sm64coopdx.py && -f $source_dir/../templates/sm64coopdx-common.txt ]] || die 'Profil SM64CoopDX absent du paquet.'
    [[ -f $source_dir/partydeck_hkmultiplayer.py && -f $source_dir/../plugins/WindowsParty.HKMultiplayer.dll && -f $source_dir/../plugins/WindowsParty.NativeWide.dll ]] || die 'Module HKMultiplayer absent / HKMultiplayer module missing.'
    [[ -f $source_dir/partydeck_hkmp.py && -f $source_dir/../plugins/WindowsParty.HKMP.dll ]] || die 'Module Hollow Knight absent du paquet.'
    [[ -f $source_dir/partydeck_nfsmw.py ]] || die 'Module Most Wanted absent du paquet.'
    [[ -f $source_dir/partydeck_l4d2.py ]] || die 'Module Left 4 Dead 2 absent du paquet.'
    [[ -f $source_dir/partydeck_i18n.py ]] || die 'Module de langues absent du paquet.'
    [[ -f $source_dir/partydeck_catalog.py ]] || die 'Catalogue commun absent du paquet.'
    [[ -f $source_dir/partydeck_virtual_input.py ]] || die 'Module contrôles virtuels absent du paquet.'
    [[ -f $source_dir/partydeck_private_lan.py ]] || die 'Module LAN privé absent / Private LAN module missing.'
    [[ -f $source_helper && -f $source_dir/partydeck_profiles.py && -f $source_dir/partydeck_anchor.py && -f $source_dir/partydeck_theme.py && -f $source_dir/../assets/windows-party.png && -f $source_dir/../templates/soh-common.json ]] ||
        die 'Extrayez le paquet complet PartyDeck Batocera, puis lancez scripts/install-windows-party.sh installer.'
fi

if [[ -f $base/partydeck_storage.py && ${1:-verifier} != party && ${1:-verifier} != coop ]]; then
    python3 "$base/partydeck_storage.py" _maintenance "$base" ||
        printf 'Entretien stockage différé ; consultez le configurateur.\n' >&2
fi

log=$(mktemp "$base/logs/partydeck-$(date +%Y%m%d-%H%M%S)-XXXXXX")
printf 'Journal : %s\n' "$log"
# Only this shell owns the session lock. A logger, Wine server or background
# service must not keep it alive after the shell has finished its session.
exec > >(tee -a "$log" 9>&-) 2>&1
printf 'Batocera %s\nPartyDeck %s\n' "$(batocera-version)" "$version"
df -h "$base"

if [[ ! -x $appdir/AppRun ]]; then
    staging=$(mktemp -d "$base/releases/.partydeck-XXXXXX")
    trap 'rm -rf -- "$staging"' EXIT
    curl --fail --show-error --location --retry 2 --connect-timeout 15 --proto '=https' \
        "https://github.com/partydeck/partydeck/releases/download/$version/$asset" \
        --output "$staging/$asset"
    (cd "$staging" && printf '%s  %s\n' "$checksum" "$asset" | sha256sum -c -)
    chmod 0755 "$staging/$asset"
    (cd "$staging" && "./$asset" --appimage-extract >/dev/null)
    [[ -x $staging/AppDir/AppRun && -x $staging/AppDir/bin/umu-run ]] ||
        die 'Le contenu extrait ne correspond pas au paquet PartyDeck attendu.'
    rm -- "$staging/squashfs-root"
    [[ ! -e $release ]] || die "Installation incomplète dans $release."
    mv -T -- "$staging" "$release"
    trap - EXIT
fi

prepare_batocera_umu

# PartyDeck masque /tmp dans chaque instance. Son AppImage est extraite dans
# un emplacement persistant pour que le lanceur UMU reste accessible.
export APPDIR="$appdir" APPIMAGE="$release/$asset"
export XDG_DATA_HOME="$base/data" XDG_CACHE_HOME="$base/cache" USE_HOST_XDG_CACHE_HOME=1
unset ARGV0

"$appdir/AppRun" --help 9>&-
if [[ ${1:-verifier} == installer ]]; then
    staging=$(mktemp -d "$base/.coop-XXXXXX")
    trap 'rm -rf -- "$staging"' EXIT
    cp -- "$source_dir/partydeck_i18n.py" "$staging/partydeck_i18n.py"
    mv -fT -- "$staging/partydeck_i18n.py" "$base/partydeck_i18n.py"
    cp -- "$source_helper" "$staging/partydeck-batocera-coop.py"
    cp -- "$source_dir/partydeck_profiles.py" "$staging/partydeck_profiles.py"
    cp -- "$source_dir/partydeck_anchor.py" "$staging/partydeck_anchor.py"
    cp -- "$source_dir/partydeck_theme.py" "$staging/partydeck_theme.py"
    cp -- "$source_dir/partydeck_couch.py" "$staging/partydeck_couch.py"
    cp -- "$source_dir/partydeck_borderlands2.py" "$staging/partydeck_borderlands2.py"
    mv -fT -- "$staging/partydeck_borderlands2.py" "$base/partydeck_borderlands2.py"
    cp -- "$source_dir/partydeck_sm64coopdx.py" "$staging/partydeck_sm64coopdx.py"
    mv -fT -- "$staging/partydeck_sm64coopdx.py" "$base/partydeck_sm64coopdx.py"
    mkdir -p -- "$base/plugins"
    cp -- "$source_dir/../plugins/WindowsParty.HKMP.dll" "$staging/WindowsParty.HKMP.dll"
    mv -fT -- "$staging/WindowsParty.HKMP.dll" "$base/plugins/WindowsParty.HKMP.dll"
    for module in WindowsParty.HKMultiplayer.dll WindowsParty.NativeWide.dll; do
        cp -- "$source_dir/../plugins/$module" "$staging/$module"
        mv -fT -- "$staging/$module" "$base/plugins/$module"
    done
    cp -- "$source_dir/partydeck_hkmultiplayer.py" "$staging/partydeck_hkmultiplayer.py"
    mv -fT -- "$staging/partydeck_hkmultiplayer.py" "$base/partydeck_hkmultiplayer.py"
    cp -- "$source_dir/partydeck_hkmp.py" "$staging/partydeck_hkmp.py"
    mv -fT -- "$staging/partydeck_hkmp.py" "$base/partydeck_hkmp.py"
    cp -- "$source_dir/partydeck_nfsmw.py" "$staging/partydeck_nfsmw.py"
    mv -fT -- "$staging/partydeck_nfsmw.py" "$base/partydeck_nfsmw.py"
    cp -- "$source_dir/partydeck_l4d2.py" "$staging/partydeck_l4d2.py"
    mv -fT -- "$staging/partydeck_l4d2.py" "$base/partydeck_l4d2.py"
    cp -- "$source_dir/partydeck_umu.py" "$base/partydeck_umu.py"
    cp -- "$source_dir/partydeck_mangohud.py" "$base/partydeck_mangohud.py"
    cp -- "$source_dir/partydeck_controls.py" "$base/partydeck_controls.py"
    cp -- "$source_dir/partydeck_migrate.py" "$base/partydeck_migrate.py"
    cp -- "$source_dir/partydeck_display.py" "$staging/partydeck_display.py"
    mv -fT -- "$staging/partydeck_display.py" "$base/partydeck_display.py"
    cp -- "$source_dir/partydeck_bottles.py" "$staging/partydeck_bottles.py"
    mv -fT -- "$staging/partydeck_bottles.py" "$base/partydeck_bottles.py"
    cp -- "$source_dir/partydeck_storage.py" "$staging/partydeck_storage.py"
    mv -fT -- "$staging/partydeck_storage.py" "$base/partydeck_storage.py"
    cp -- "$source_dir/partydeck_catalog.py" "$staging/partydeck_catalog.py"
    mv -fT -- "$staging/partydeck_catalog.py" "$base/partydeck_catalog.py"
    cp -- "$source_dir/partydeck_virtual_input.py" "$staging/partydeck_virtual_input.py"
    mv -fT -- "$staging/partydeck_virtual_input.py" "$base/partydeck_virtual_input.py"
    cp -- "$source_dir/partydeck_private_lan.py" "$staging/partydeck_private_lan.py"
    mv -fT -- "$staging/partydeck_private_lan.py" "$base/partydeck_private_lan.py"
    mv -fT -- "$staging/partydeck_couch.py" "$base/partydeck_couch.py"
    mkdir -p -- "$base/assets" "$base/templates"
    cp -- "$source_dir/../assets/windows-party.png" "$staging/windows-party.png"
    mv -fT -- "$staging/windows-party.png" "$base/assets/windows-party.png"
    if [[ ! -e $base/templates/soh-common.json && ! -L $base/templates/soh-common.json ]]; then
        cp -- "$source_dir/../templates/soh-common.json" "$base/templates/soh-common.json"
        chmod 0600 "$base/templates/soh-common.json"
    fi
    if [[ ! -e $base/templates/sm64coopdx-common.txt && ! -L $base/templates/sm64coopdx-common.txt ]]; then
        cp -- "$source_dir/../templates/sm64coopdx-common.txt" "$base/templates/sm64coopdx-common.txt"
        chmod 0600 "$base/templates/sm64coopdx-common.txt"
    fi
    mv -fT -- "$staging/partydeck_theme.py" "$base/partydeck_theme.py"
    mv -fT -- "$staging/partydeck_anchor.py" "$base/partydeck_anchor.py"
    mv -fT -- "$staging/partydeck_profiles.py" "$profiles_helper"
    mv -fT -- "$staging/partydeck-batocera-coop.py" "$coop_helper"
    rmdir -- "$staging"
    trap - EXIT

    temporary_launcher=$(mktemp "$base/.launcher-XXXXXX")
    trap 'rm -f -- "$temporary_launcher"' EXIT
    cp -- "${BASH_SOURCE[0]}" "$temporary_launcher"
    chmod 0755 "$temporary_launcher"
    mv -fT -- "$temporary_launcher" "$launcher"
    trap - EXIT
    # Finalization borrows the installer's already-held lock by identity.
    # Unlike game helpers it must inherit fd 9 to avoid locking itself out.
    python3 "$base/partydeck_migrate.py" finalize "$base" /userdata/system/partydeck-test /userdata/roms/windows-party "$ports_dir"
    python3 "$coop_helper" install-system 9>&-
    python3 "$profiles_helper" installer "$base" 9>&-
    python3 "$base/partydeck_theme.py" "$base" 9>&-
    printf 'Ajoutez un jeu avec : %s ajouter "/userdata/roms/windows/Jeu.wsquashfs" 2 horizontal auto\n' "$launcher"
    printf 'Redémarrez EmulationStation pour charger le nouveau système Windows Party.\n'
    printf '\nWindows Party installé. Quand EmulationStation est affiché, lancez :\n%s verifier\n' "$launcher"
    exit 0
fi

"$appdir/bin/gamescope-kbm" --help >"$base/logs/gamescope-help.log" 2>&1 ||
    die "Le Gamescope fourni ne démarre pas. Voir $base/logs/gamescope-help.log"
"$appdir/bin/umu-run" --version 9>&-
"$appdir/bin/bwrap" --die-with-parent --dev-bind / / --tmpfs /tmp /bin/true ||
    die 'Bubblewrap ne peut pas créer le namespace requis sur cette build.'

# Récupère l'environnement graphique local d'EmulationStation, même en SSH.
# Lit uniquement les variables attendues, sans évaluer le contenu du processus.
load_graphical_environment

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/var/run}"
wayland_socket="${WAYLAND_DISPLAY:-wayland-0}"
[[ $wayland_socket == /* ]] || wayland_socket="$XDG_RUNTIME_DIR/$wayland_socket"
if [[ -S $wayland_socket ]]; then
    export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
    session=Wayland
else
    unset WAYLAND_DISPLAY
    session=Xorg
fi

# Le backend SDL de ce PartyDeck utilise le display X11 parent, sous Xorg
# comme sous labwc. Gamescope lance aussi son propre serveur Xwayland.
[[ ${DISPLAY:-} =~ ^:[0-9]+(\.[0-9]+)?$ ]] || export DISPLAY=:0.0
printf 'Session : %s | DISPLAY=%s | WAYLAND_DISPLAY=%s | XDG_RUNTIME_DIR=%s\n' \
    "$session" "$DISPLAY" "${WAYLAND_DISPLAY:-}" "$XDG_RUNTIME_DIR"

if command -v xdpyinfo >/dev/null; then
    xdpyinfo >/dev/null || die "Display X11 local inaccessible ($DISPLAY)."
elif command -v xrandr >/dev/null; then
    xrandr --query >/dev/null || die "Display X11 local inaccessible ($DISPLAY)."
else
    display_number=${DISPLAY#:}
    [[ -S /tmp/.X11-unix/X${display_number%%.*} ]] ||
        die "Socket X11 introuvable ($DISPLAY)."
fi

# Even on Xorg, Gamescope uses its own Xwayland server. Recent wlroots
# builds use a compiled-in path unless WLR_XWAYLAND is set explicitly.
if native_xwayland=$(command -v Xwayland); then
    export WLR_XWAYLAND="$native_xwayland"
else
    export PARTYDECK_XWAYLAND_APPDIR="$appdir"
    if [[ ! -x $xwayland_dir/Xwayland ]]; then
        install_portable_xwayland
    fi
    export WLR_XWAYLAND="$xwayland_dir/Xwayland"
fi
printf 'Xwayland utilisé par Gamescope : %s\n' "$WLR_XWAYLAND"
"$WLR_XWAYLAND" -version || die 'Le Xwayland sélectionné ne démarre pas.'

if [[ ${1:-verifier} == verifier ]]; then
    if [[ $session == Wayland ]] && command -v labwc >/dev/null; then
        labwc --version || true
    fi
    if command -v xrandr >/dev/null; then
        xrandr --listactivemonitors || true
    fi
    if command -v xdotool >/dev/null; then
        printf 'Dimensions X11 vues par le lanceur : '
        xdotool getdisplaygeometry || true
    else
        printf 'xdotool absent. Le placement automatique des fenêtres coop en a besoin.\n'
    fi
    printf '\nVérifications de base Windows Party OK.\n'
    exit 0
fi

if [[ ${1:-verifier} == coop || ${1:-verifier} == party ]]; then
    [[ -f $coop_helper ]] || die 'Réinstallez le lanceur pour restaurer le module coop.'
    mode=play
    [[ $1 != party ]] || mode=play-party
    shift
    python3 "$coop_helper" "$mode" "$appdir" "$base" "$ports_dir" "$@" 9>&-
    exit 0
fi

die 'Commande Windows Party inconnue.'
