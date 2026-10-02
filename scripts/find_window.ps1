# usage: find_window.ps1 -Title <substring>  -> lines "hwnd|title" of visible top-level windows whose title contains it
param([Parameter(Mandatory)][string]$Title)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -TypeDefinition @"
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public class WinEnum {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public static List<string> Find(string t) {
    var r = new List<string>();
    EnumWindows((h, l) => { if (IsWindowVisible(h)) { var sb = new StringBuilder(512); GetWindowText(h, sb, 512); var s = sb.ToString();
      if (s.Length > 0 && s.IndexOf(t, StringComparison.OrdinalIgnoreCase) >= 0) r.Add(h.ToInt64() + "|" + s); } return true; }, IntPtr.Zero);
    return r;
  }
}
"@
[WinEnum]::Find($Title)
