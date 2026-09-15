$ErrorActionPreference = "Stop"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W2 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder sb, int max);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
$targetPid = [int]$args[0]
$cb = [W2+EnumProc]{
  param($h, $l)
  $pidOut = 0
  [W2]::GetWindowThreadProcessId($h, [ref]$pidOut) | Out-Null
  if ($pidOut -eq $targetPid) {
    $r = New-Object W2+RECT
    [W2]::GetWindowRect($h, [ref]$r) | Out-Null
    $sb = New-Object System.Text.StringBuilder 256
    [W2]::GetWindowText($h, $sb, 256) | Out-Null
    Write-Output ("hwnd=" + $h + " vis=" + [W2]::IsWindowVisible($h) + " rect=" + $r.Left + "," + $r.Top + "," + $r.Right + "," + $r.Bottom + " title='" + $sb.ToString() + "'")
  }
  return $true
}
[W2]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
