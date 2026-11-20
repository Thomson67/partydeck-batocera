using System;
using System.Runtime.CompilerServices;
using WindowsParty.NativeWide;
public class Dummy {
 public float Value; public int Calls;
 public (float,float) Pixels(Dummy camera){Value=camera.Value;return (1,1);}
 [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
 public float Read(){Calls++;return 16f/9;}
 public void Overscan(float v){Calls++;Value=v;}
 private void Awake(){Calls++;}
 public void CallAwake()=>Awake();
}
public class Program {
 private (float,float) AfterPixels(object self)=>(2560,720);
 private float AfterRead(object self){if(((Dummy)self).Calls!=1)throw new Exception("Original not called");return 32f/9;}
 private void AfterAwake(object self){((Dummy)self).Calls+=10;}
 public static void Main(string[] args){var p=new Program();var d=new Dummy();
 var read=(Func<Func<Dummy,float>,Dummy,float>)CameraHooks.Build(typeof(Dummy),"Read",typeof(float),p,"AfterRead",false,out var readMethod);
 if(Math.Abs(read(x=>x.Read(),d)-32f/9)>0.001)throw new Exception("Result override failed");
 var scan=(Action<Action<Dummy,float>,Dummy,float>)CameraHooks.Build(typeof(Dummy),"Overscan",typeof(void),p,null,true,out var scanMethod);
 scan((x,v)=>x.Overscan(v),d,.25f);if(d.Value!=0)throw new Exception("Overscan override failed");
 d.Calls=0;var awake=(Action<Action<Dummy>,Dummy>)CameraHooks.Build(typeof(Dummy),"Awake",typeof(void),p,"AfterAwake",false,out var awakeMethod);
 awake(x=>x.CallAwake(),d);if(d.Calls!=11||awakeMethod.IsPublic)throw new Exception("Private lifecycle signature failed");
 var other=new Dummy{Value=7};
 var pixels=(Func<Func<Dummy,Dummy,(float,float)>,Dummy,Dummy,(float,float)>)CameraHooks.Build(typeof(Dummy),"Pixels",typeof((float,float)),p,"AfterPixels",false,out var pixelMethod,new[]{typeof(Dummy)});
 if(pixels((x,c)=>x.Pixels(c),d,other)!=(2560f,720f)||d.Value!=7)throw new Exception("tk2d-style camera parameter not preserved");
 // Regression: MonoMod must receive an instance method with its matching target,
 // never the closed static implementation returned by Expression.Compile.
 var invoke=read.GetType().GetMethod("Invoke");
 if(invoke.IsStatic||!invoke.DeclaringType.IsInstanceOfType(read))throw new Exception("Invalid hook target binding");
 d.Calls=0;
 if((float)invoke.Invoke(read,new object[]{new Func<Dummy,float>(x=>x.Read()),d})!=32f/9)throw new Exception("Instance Invoke adapter failed");
 if(Array.IndexOf(args,"--runtime")>=0){
  d.Calls=0;
  using(var hook=CameraHooks.Create(typeof(Dummy),"Read",typeof(float),p,"AfterRead")){
   if(d.Read()!=32f/9)throw new Exception("Runtime detour failed");
  }
  if(d.Read()!=16f/9)throw new Exception("Runtime detour was not restored");
  Console.WriteLine("PASS: runtime detour installation, invocation and disposal");
 }
 Console.WriteLine("PASS: camera parameter preserved; delegate signatures, original invocation, aspect result override, zero overscan, private lifecycle method");
 }
}
