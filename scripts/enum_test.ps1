$ErrorActionPreference = "Stop"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W3 {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
}
"@
$count = 0
$matches = 0
$cb = [W3+EnumProc]{
  param($h, $l)
  $script:count++
  $p = 0
  [W3]::GetWindowThreadProcessId($h, [ref]$p) | Out-Null
  if ($p -eq $args[0] -and [W3]::IsWindowVisible($h)) { $script:matches++ }
  return $true
}
[W3]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null
Write-Output ("TOTAL_WINDOWS=" + $count + " MATCH_PID=" + [int]$args[0] + " VISIBLE_MATCH=" + $matches)
