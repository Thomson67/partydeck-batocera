# NVIDIA : essai Wine imbriqué / Nested Wine experiment

Base : révision 8ace0d95ff0226c7560e2ed22a6b307ff46e21ea, avant contrôles virtuels
et LAN privé. Le relevé réel confirme le même runner TKG-v41, le même d3d9.dll
DXVK et les mêmes bibliothèques NVIDIA en solo et en PartyDeck. Le solo utilise
les manifestes Vulkan NVIDIA ; PartyDeck transmet aussi PRIME à Wine.

Cet essai conserve PRIME pour Gamescope et choisit directement les manifestes
NVIDIA disponibles (y compris 32 bits) pour Wine. Aucun chemin propre à un PC
n’est codé en dur. Sans manifeste NVIDIA reconnu, le comportement antérieur est
conservé. Les choix graphiques explicites hérités et le mode Système ne sont
pas remplacés par la détection automatique. Le fournisseur GLX NVIDIA reste
sélectionné lorsque PartyDeck demande explicitement ce GPU.

La différence observée motive cet essai ; elle ne prouve pas encore la cause
du blocage. Le lancement du jeu reste à valider sur Batocera.

## English

Based on 8ace0d95ff0226c7560e2ed22a6b307ff46e21ea, before virtual controls and
private LAN. Captures show the same TKG-v41 runner, DXVK d3d9.dll and NVIDIA
libraries for working solo and stalled PartyDeck launches. Solo selects NVIDIA
Vulkan manifests; PartyDeck additionally imposes PRIME on Wine.

This experiment keeps PRIME for Gamescope and selects available NVIDIA Vulkan
manifests directly for Wine, including 32-bit manifests. No PC-specific paths
are hardcoded. Missing manifests retain previous behavior. Explicit inherited
GPU selectors and System mode bypass automatic replacement. NVIDIA GLX vendor
selection remains when PartyDeck requests this GPU.

The observed difference motivates the test but does not establish the cause.
Actual game startup still needs validation on Batocera.
