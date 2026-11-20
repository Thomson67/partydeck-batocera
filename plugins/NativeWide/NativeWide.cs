using System;
using System.Collections.Generic;
using System.Reflection;
using Modding;
using MonoMod.RuntimeDetour;
using UnityEngine;

namespace WindowsParty.NativeWide
{
    // Uses the MonoMod already installed by HKMultiplayer's API. No loader or
    // replacement dependency assemblies are shipped with this mod.
    public sealed class NativeWide : Mod
    {
        private const BindingFlags Members = BindingFlags.Public | BindingFlags.NonPublic |
                                             BindingFlags.Instance | BindingFlags.Static;
        private readonly List<Hook> hooks = new List<Hook>();
        private FieldInfo tk2dField, hudField;
        private PropertyInfo viewportAspect;
        private bool reportedError;
        private int lastWidth, lastHeight;

        public NativeWide() : base("Windows Party Native Wide") { }
        public override string GetVersion() => "0.1.1-test";

        public override void Initialize()
        {
            if (hooks.Count != 0) return;
            try
            {
                Type force = typeof(Mod).Assembly.GetType("ForceCameraAspect", true);
                Type cameras = typeof(Mod).Assembly.GetType("GameCameras", true);
                tk2dField = force.GetField("tk2dCam", Members)
                    ?? throw new MissingFieldException(force.FullName, "tk2dCam");
                hudField = force.GetField("hudCam", Members)
                    ?? throw new MissingFieldException(force.FullName, "hudCam");
                viewportAspect = force.GetProperty("CurrentViewportAspect", Members)
                    ?? throw new MissingMemberException(force.FullName, "CurrentViewportAspect");

                Install(tk2dField.FieldType, "GetScreenPixelDimensions", typeof(Vector2),
                    nameof(AfterPixelDimensions), false, new[] { tk2dField.FieldType });
                Install(force, "AutoScaleViewport", typeof(float), nameof(AfterViewport));
                Install(force, "Awake", typeof(void), nameof(AfterAwake));
                Install(force, "SetOverscanViewport", typeof(void), null, true);
                Install(cameras, "SetOverscan", typeof(void), null, true);
                Log("Native camera hooks active; BepInEx is not required.");
                foreach (UnityEngine.Object obj in Resources.FindObjectsOfTypeAll(force))
                    AfterAwake(obj);
            }
            catch (Exception ex)
            {
                for (int i = hooks.Count - 1; i >= 0; --i) hooks[i].Dispose();
                hooks.Clear();
                LogError("Native Wide disabled: " + ex);
            }
        }

        private void Install(Type type, string name, Type result, string after, bool zeroOverscan = false,
            Type[] parameterTypesOverride = null)
        {
            hooks.Add(CameraHooks.Create(type, name, result, this, after, zeroOverscan, parameterTypesOverride));
            Log("Hook installed: " + type.FullName + "." + name);
        }

        private float Aspect => Screen.width / (float)Math.Max(1, Screen.height);

        private Vector2 AfterPixelDimensions(object self)
        {
            try { FillTk2dViewport(self); }
            catch (Exception ex) { ReportOnce(ex); }
            return new Vector2(Screen.width, Screen.height);
        }

        private float AfterViewport(object self)
        {
            AfterAwake(self);
            return Aspect;
        }

        private void AfterAwake(object self)
        {
            try
            {
                FillTk2dViewport(tk2dField.GetValue(self));
                if (hudField.GetValue(self) is Camera hud) hud.rect = new Rect(0, 0, 1, 1);
                viewportAspect.SetValue(null, Aspect, null);
                if (Screen.width != lastWidth || Screen.height != lastHeight)
                {
                    lastWidth = Screen.width; lastHeight = Screen.height;
                    Log("Viewport " + lastWidth + "x" + lastHeight + "; aspect " + Aspect);
                }
            }
            catch (Exception ex) { ReportOnce(ex); }
        }

        private static void FillTk2dViewport(object camera)
        {
            if (camera == null) return;
            Type type = camera.GetType();
            PropertyInfo property = type.GetProperty("CameraSettings", Members);
            FieldInfo field = type.GetField("CameraSettings", Members);
            object settings = property != null ? property.GetValue(camera, null) : field?.GetValue(camera);
            if (settings == null) throw new MissingMemberException(type.FullName, "CameraSettings");
            Type settingsType = settings.GetType();
            Rect full = new Rect(0, 0, 1, 1);
            FieldInfo rectField = settingsType.GetField("rect", Members);
            if (rectField != null) rectField.SetValue(settings, full);
            else
            {
                PropertyInfo rectProperty = settingsType.GetProperty("rect", Members)
                    ?? throw new MissingMemberException(settingsType.FullName, "rect");
                rectProperty.SetValue(settings, full, null);
            }
            // Preserve changes if a later game revision uses a settings struct.
            if (settingsType.IsValueType)
            {
                if (property?.CanWrite == true) property.SetValue(camera, settings, null);
                else if (field != null) field.SetValue(camera, settings);
                else throw new InvalidOperationException("Read-only camera settings struct");
            }
        }

        private void ReportOnce(Exception ex)
        {
            if (reportedError) return;
            reportedError = true;
            LogError("Viewport could not be adjusted: " + ex);
        }
    }
}
