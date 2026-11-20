using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Modding;
using UnityEngine;

namespace WindowsParty.HKMultiplayer
{
    public sealed class PartyMultiplayer : Mod
    {
        public PartyMultiplayer() : base("Windows Party HKMultiplayer") { }
        public override string GetVersion() => "0.1.0-test";

        public override void Initialize()
        {
            try
            {
                string path = Path.Combine(Path.GetDirectoryName(GetType().Assembly.Location), "windows-party.cfg");
                if (!File.Exists(path)) return; // No side effects in an ordinary solo launch.
                var options = File.ReadAllLines(path).Where(l => l.Contains("="))
                    .Select(l => l.Split(new[] { '=' }, 2)).ToDictionary(p => p[0].Trim(), p => p[1].Trim());
                if (!options.TryGetValue("Enabled", out string enabled) || enabled != "true") return;
                var gameObject = new GameObject("WindowsPartyHKMultiplayer");
                UnityEngine.Object.DontDestroyOnLoad(gameObject);
                gameObject.AddComponent<PartyConnection>().Initialize(options, s => Log(s), s => LogError(s));
            }
            catch (Exception e) { LogError("Party initialization failed: " + e); }
        }
    }

    public sealed class PartyConnection : MonoBehaviour
    {
        const BindingFlags All = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
        Dictionary<string, string> options;
        Action<string> info, error;
        int player, width, height, port, attempts;
        bool automatic, stopped, connected, hostSettingsApplied;
        float nextTick, nextResolution, nextNetwork, deadline;
        Type runnerType, savesType, storeType, hostSettingsType;
        object runner;

        public void Initialize(Dictionary<string, string> config, Action<string> log, Action<string> logError)
        {
            enabled = false;
            options = config; info = log; error = logError;
            player = Number("Player"); width = Number("Width"); height = Number("Height"); port = Number("Port");
            if (player < 1 || player > 4 || width < 64 || width > 16384 || height < 64 || height > 16384 || port < 1024 || port > 65535)
                throw new InvalidDataException("Invalid player, viewport or port");
            automatic = options["Automatic"] == "true";
            if (options["FixControllers"] == "true") ApplyControllerFix();
            Screen.SetResolution(width, height, false);
            deadline = Time.realtimeSinceStartup + 240f;
            info($"J{player}: viewport {width}x{height}; auto-network={automatic}; HIDRAW preserved.");
            enabled = true;
        }

        int Number(string key) => int.Parse(options[key], CultureInfo.InvariantCulture);
        static object Get(object obj, string name)
        {
            Type type = obj as Type ?? obj.GetType();
            object target = obj is Type ? null : obj;
            return type.GetProperty(name, All)?.GetValue(target, null) ?? type.GetField(name, All)?.GetValue(target);
        }
        static object Call(object obj, string name, params object[] args)
        {
            Type type = obj as Type ?? obj.GetType();
            MethodInfo method = type.GetMethods(All).Single(m => m.Name == name && m.GetParameters().Length == args.Length);
            return method.Invoke(obj is Type ? null : obj, args);
        }

        void ApplyControllerFix()
        {
            // This is the game's own Native Controller Input preference, not a
            // Wine backend override. Assigned HIDRAW devices remain available.
            PlayerPrefs.SetInt("NativeInput", 0);
            PlayerPrefs.Save();
            Assembly game = typeof(Mod).Assembly;
            Type settingsType = game.GetType("GameSettings", true);
            Type gmType = game.GetType("GameManager", true);
            object gm = Get(gmType, "instance");
            object settings = gm != null ? Get(gm, "gameSettings") : null;
            if (settings != null) settingsType.GetField("nativeInput", All).SetValue(settings, false);
            Type input = game.GetType("InControl.InputManager", true);
            bool wasNative = (bool)Get(input, "EnableNativeInput");
            input.GetProperty("EnableNativeInput", All).SetValue(null, false, null);
            Type manager = game.GetType("InControl.InControlManager", true);
            foreach (UnityEngine.Object obj in Resources.FindObjectsOfTypeAll(manager))
                manager.GetField("enableNativeInput", All).SetValue(obj, false);
            if (wasNative && (bool)Get(input, "IsSetup")) Call(input, "Reload");
            info("Native Controller Input disabled; bindings retained; assigned HIDRAW devices retained.");
        }

        bool FindRunner()
        {
            Assembly multiplayer = AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(a => a.GetType("HKMultiplayer.Game.MultiplayerRunner") != null);
            if (multiplayer == null) return false;
            Type mod = multiplayer.GetType("HKMultiplayer.HKMultiplayerMod", true);
            string version = (string)mod.GetField("Version", All).GetRawConstantValue();
            if (version != "0.36.2") throw new NotSupportedException("Expected HKMultiplayer 0.36.2; found " + version);
            runnerType = multiplayer.GetType("HKMultiplayer.Game.MultiplayerRunner", true);
            runner = Get(runnerType, "Instance");
            if (runner == null) return false;
            savesType = multiplayer.GetType("HKMultiplayer.Game.World.CoopSaves", true);
            storeType = multiplayer.GetType("HKMultiplayer.Game.World.WorldStore", true);
            hostSettingsType = multiplayer.GetType("HKMultiplayer.Game.Features.HostSettings", true);
            // IP only: this local session should not open a Steam lobby.
            object settings = Get(mod, "Settings");
            settings.GetType().GetProperty("SteamAccess").SetValue(settings, 2, null);
            info("HKMultiplayer ready; waiting for the main menu.");
            return true;
        }

        object ChooseWorld()
        {
            var worlds = ((IEnumerable)Call(storeType, "List")).Cast<object>().ToList();
            object world = options["World"] == "latest" ? worlds.FirstOrDefault()
                : worlds.FirstOrDefault(w => string.Equals((string)Get(w, "Name"), options["WorldName"], StringComparison.Ordinal));
            if (world == null) world = Call(storeType, "Create", options["WorldName"]);
            if (world == null) throw new InvalidOperationException("Could not create a coop world; all four world slots may be occupied.");
            info("Opening coop world: " + Get(world, "Name"));
            return world;
        }

        void ApplyHostSettings()
        {
            if (hostSettingsApplied || player != 1) return;
            object world = Get(savesType, "ActiveWorld");
            if (world == null) return;
            object current = Get(hostSettingsType, "Current");
            // HostSettings loads the world's settings on its next update after
            // HostWorld. Wait for that pass so it cannot overwrite our choices.
            if (!Equals(Get(current, "_loadedWorld"), Get(world, "Id"))) return;
            var available = ((IEnumerable)Get(hostSettingsType, "Options")).Cast<object>().ToList();
            foreach (var pair in options.Where(p => p.Key.StartsWith("Host.", StringComparison.Ordinal)))
            {
                string key = pair.Key.Substring(5);
                object option = available.Single(o => (string)Get(o, "Key") == key);
                float value = float.Parse(pair.Value, CultureInfo.InvariantCulture);
                float[] values = (float[])Get(option, "Values");
                int index = Array.FindIndex(values, v => Math.Abs(v - value) < 0.001f);
                if (index < 0) throw new InvalidDataException("Unsupported host option: " + key);
                Call(current, "Set", option, index);
            }
            hostSettingsApplied = true;
            info("Coop settings applied through HKMultiplayer's host API.");
        }

        void Update()
        {
            if (options == null || Time.realtimeSinceStartup < nextTick) return;
            nextTick = Time.realtimeSinceStartup + .5f;
            if ((Screen.width != width || Screen.height != height || Screen.fullScreen)
                && Time.realtimeSinceStartup >= nextResolution)
            {
                Screen.SetResolution(width, height, false);
                nextResolution = Time.realtimeSinceStartup + 2f;
            }
            if (!automatic || stopped) return;
            try
            {
                if (runner == null && !FindRunner())
                {
                    if (Time.realtimeSinceStartup > deadline) throw new TimeoutException("HKMultiplayer runner not found");
                    return;
                }
                ApplyHostSettings();
                if (connected) return; // Leaving intentionally does not auto-rejoin.
                object session = Get(runner, "Session");
                if (session != null)
                {
                    if ((bool)Get(session, "CanSend"))
                    {
                        connected = true;
                        info($"J{player}: connected; code supplied automatically.");
                    }
                    return; // Do not restart an ongoing handshake.
                }
                if (Time.realtimeSinceStartup > deadline) throw new TimeoutException("Automatic host/join timed out");
                if (!(bool)Get(savesType, "CanStart") || Time.realtimeSinceStartup < nextNetwork) return;
                if (++attempts > 18) throw new TimeoutException("Too many connection attempts");
                if (player == 1)
                {
                    object world = ChooseWorld();
                    bool ok = (bool)Call(runner, "HostWorld", world, options["Username"], port, options["Code"]);
                    if (!ok) throw new InvalidOperationException("HostWorld refused: " + Get(runner, "StatusMessage"));
                    info("J1: coop world started; guests may now join.");
                }
                else
                {
                    bool ok = (bool)Call(runner, "Join", options["Address"], port, options["Code"], options["Username"]);
                    if (!ok) throw new InvalidOperationException("Join refused: " + Get(runner, "StatusMessage"));
                    info($"J{player}: joining local J1, attempt {attempts}.");
                }
                nextNetwork = Time.realtimeSinceStartup + 12f;
            }
            catch (Exception e)
            {
                stopped = true;
                error("Automatic connection stopped; normal multiplayer menu remains available: " + (e.InnerException ?? e));
            }
        }
    }
}
