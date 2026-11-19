// Windows Party's optional HKMP 2.4.3 bridge. No game/HKMP binaries required.
using BepInEx;
using System;
using System.Linq;
using System.Reflection;
using UnityEngine;

[BepInPlugin("windows.party.hkmp", "Windows Party HKMP", "0.1.0")]
public sealed class PartyHkmp : BaseUnityPlugin
{
    const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    int width, height, player, port, attempts;
    string address, username;
    bool automationEnabled, autoNetwork, hosted, connectedOnce, failed;
    float next, networkNext, resolutionNext;
    object client, netClient, server;
    Type gameManager;

    void Awake()
    {
        automationEnabled = Config.Bind("Session", "Enabled", false).Value;
        if (!automationEnabled) return; // Never automate solo launches.
        width = Config.Bind("Display", "Width", 0).Value;
        height = Config.Bind("Display", "Height", 0).Value;
        player = Config.Bind("Session", "Player", 1).Value;
        port = Config.Bind("Network", "Port", 7777).Value;
        address = Config.Bind("Network", "Address", "127.0.0.1").Value;
        username = Config.Bind("Network", "Username", "J1").Value;
        autoNetwork = Config.Bind("Network", "Automatic", true).Value;
        if (width < 64 || width > 16384 || height < 64 || height > 16384 || player < 1 || player > 4 || port < 1 || port > 65535)
        {
            automationEnabled = false;
            failed = true;
            Logger.LogError("Invalid Windows Party viewport/player/port; automation disabled.");
            return;
        }
        Screen.SetResolution(width, height, false);
        Logger.LogInfo($"J{player}: viewport {width}x{height}, automatic network={autoNetwork}");
    }

    static object Field(object instance, string name)
    {
        for (var t = instance.GetType(); t != null; t = t.BaseType)
        {
            var f = t.GetField(name, All | BindingFlags.DeclaredOnly);
            if (f != null) return f.GetValue(instance);
        }
        throw new MissingFieldException(instance.GetType().FullName, name);
    }

    // HKMP's chat subscribes ClientManager.OnChatInput. Retrieve its target;
    // do not invoke the delegate or send simulated keyboard/chat input.
    bool FindClient()
    {
        var hkmp = AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(a => a.GetType("Hkmp.Ui.UiManager") != null);
        if (hkmp == null) return false;
        // ESoulLink/Pouch register addons while the Modding API loads mods.
        // Do not host/join until that pass (including addon loading) is over.
        var loader = AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType("Modding.ModLoader")).FirstOrDefault(t => t != null);
        if (loader == null || (Convert.ToInt32(loader.GetField("LoadState", All).GetValue(null)) & 4) == 0) return false;
        var chat = hkmp.GetType("Hkmp.Ui.UiManager").GetField("InternalChatBox", All).GetValue(null);
        if (chat == null) return false;
        var callbacks = (Delegate)Field(chat, "ChatInputEvent");
        client = callbacks?.GetInvocationList().Select(d => d.Target).FirstOrDefault(o => o?.GetType().FullName == "Hkmp.Game.Client.ClientManager");
        if (client == null) return false;
        netClient = Field(client, "_netClient");
        server = Field(client, "_serverManager");
        gameManager = AppDomain.CurrentDomain.GetAssemblies().Select(a => a.GetType("GameManager")).FirstOrDefault(t => t != null);
        Logger.LogInfo("HKMP client ready; waiting for gameplay before connecting.");
        return true;
    }

    bool Gameplay()
    {
        if (gameManager == null) return false;
        var instance = gameManager.GetProperty("instance", All)?.GetValue(null, null)
            ?? gameManager.GetField("instance", All)?.GetValue(null);
        var heroType = gameManager.Assembly.GetType("HeroController");
        var hero = heroType?.GetProperty("instance", All)?.GetValue(null, null)
            ?? heroType?.GetField("instance", All)?.GetValue(null);
        return instance != null && hero != null && (bool)gameManager.GetMethod("IsGameplayScene", All, null, Type.EmptyTypes, null).Invoke(instance, null);
    }

    void Update()
    {
        if (!automationEnabled || Time.realtimeSinceStartup < next) return;
        next = Time.realtimeSinceStartup + .5f;
        // The game can restore its own saved screen size on entering a save.
        // Reinstate this player's viewport, without changing graphics quality.
        if ((Screen.width != width || Screen.height != height || Screen.fullScreen) && Time.realtimeSinceStartup >= resolutionNext)
        {
            Screen.SetResolution(width, height, false);
            resolutionNext = Time.realtimeSinceStartup + 2;
        }
        if (!autoNetwork || connectedOnce || failed) return;
        try
        {
            if (client == null && !FindClient()) return;
            if (player == 1 && !hosted)
            {
                server.GetType().GetMethod("Start", All).Invoke(server, new object[] { port });
                hosted = true;
                Logger.LogInfo($"J1: started HKMP server on port {port}");
            }
            if ((bool)netClient.GetType().GetProperty("IsConnected").GetValue(netClient, null))
            {
                connectedOnce = true;
                Logger.LogInfo($"J{player}: connected as {username}; automatic joining finished.");
                return;
            }
            if (!Gameplay() || (bool)netClient.GetType().GetProperty("IsConnecting").GetValue(netClient, null)
                || Time.realtimeSinceStartup < networkNext) return;
            if (++attempts > 12)
            {
                failed = true;
                Logger.LogWarning("Automatic connection failed after 12 attempts; use HKMP's network panel.");
                return;
            }
            client.GetType().GetMethod("Connect", All).Invoke(client, new object[] { address, port, username });
            networkNext = Time.realtimeSinceStartup + 5;
            Logger.LogInfo($"J{player}: connecting to {address}:{port} as {username}, attempt {attempts}");
        }
        catch (Exception e)
        {
            // Fail once on API changes, leave the normal HKMP menu available.
            failed = true;
            Logger.LogError("HKMP automation stopped: " + (e.InnerException ?? e));
        }
    }
}
