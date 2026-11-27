# PartyDeck LAN for D2RLoader

The plugin uses the UI services of D2RLoader 1.3.1-beta. It acts when a player
opens Multiplayer with their offline character. PartyDeck sets LAN Only and
the Direct Join address in the player's private D2RLoader state. Guests wait
for PartyDeck to observe the host's TCP listener.

Build from the repository root with Zig 0.15.2 and the
[D2RLoader Plugin SDK](https://github.com/D2RLoader/PluginSDK) at
`bb0b48e080c51c37fc8296ee415d9daaba7ee33d`. Set `D2RL_SDK` to the SDK checkout.

```sh
resource=$(mktemp --suffix=.res)
zig rc /I "$D2RL_SDK/include" /fo "$resource" plugins/D2RLoader/partydeck_lan.rc &&
  zig c++ -target x86_64-windows-gnu -std=c++20 -O2 -shared -s \
    -I "$D2RL_SDK/include" plugins/D2RLoader/partydeck_lan.cpp "$resource" \
    -o plugins/d2rl-partydeck-lan.dll
rm -f -- "$resource"
```
