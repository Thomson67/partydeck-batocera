using System;
using System.Collections.Generic;
using System.Linq;
using System.Linq.Expressions;
using System.Reflection;
using MonoMod.RuntimeDetour;

namespace WindowsParty.NativeWide
{
    internal static class CameraHooks
    {
        // Generate delegates using the game's exact runtime types, including
        // tk2dCamera from the separate Unity 6 TeamCherry.TK2D assembly.
        internal static Hook Create(Type type, string name, Type result, object owner, string after, bool zeroOverscan = false,
            Type[] parameterTypesOverride = null)
        {
            Delegate replacement = Build(type, name, result, owner, after, zeroOverscan, out MethodInfo method, parameterTypesOverride);
            // Expression.Compile produces a closed static method on Mono:
            // replacement.Method.IsStatic is true while Target is a Closure.
            // RuntimeDetour rejects that combination. Bind the delegate's
            // genuine instance Invoke method instead, keeping its closure alive.
            MethodInfo invoke = replacement.GetType().GetMethod("Invoke")
                ?? throw new MissingMethodException(replacement.GetType().FullName, "Invoke");
            return new Hook(method, invoke, replacement);
        }

        internal static Delegate Build(Type type, string name, Type result, object owner, string after,
            bool zeroOverscan, out MethodInfo method, Type[] parameterTypesOverride = null)
        {
            Type[] parameterTypes = parameterTypesOverride ?? (zeroOverscan ? new[] { typeof(float) } : Type.EmptyTypes);
            method = type.GetMethod(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance, null, parameterTypes, null)
                ?? throw new MissingMethodException(type.FullName, name);
            if (method.IsStatic || method.ReturnType != result)
                throw new InvalidOperationException("Unexpected camera signature: " + method);
            Type[] signature = new[] { type }.Concat(parameterTypes).Concat(new[] { result }).ToArray();
            Type originalType = Expression.GetDelegateType(signature);
            var original = Expression.Parameter(originalType, "original");
            var self = Expression.Parameter(type, "self");
            var arguments = parameterTypes.Select((t, i) => Expression.Parameter(t, "arg" + i)).ToArray();
            var callArguments = new List<Expression> { self };
            callArguments.AddRange(arguments.Select(a => zeroOverscan ? (Expression)Expression.Constant(0f) : a));
            Expression body = Expression.Invoke(original, callArguments);
            if (after != null)
            {
                MethodInfo callback = owner.GetType().GetMethod(after, BindingFlags.NonPublic | BindingFlags.Instance);
                body = Expression.Block(body, Expression.Call(Expression.Constant(owner), callback,
                    Expression.Convert(self, typeof(object))));
            }
            Type hookType = Expression.GetDelegateType(new[] { originalType }.Concat(signature).ToArray());
            Delegate replacement = Expression.Lambda(hookType, body,
                new[] { original, self }.Concat(arguments)).Compile();
            return replacement;
        }

    }
}
