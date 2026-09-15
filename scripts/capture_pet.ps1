$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$targetPid = [int]$args[0]
$best = $null
$bestArea = 0

$cb = [W+EnumProc]{
  param($h, $l)
  $pidOut = 0
  [W]::GetWindowThreadProcessId($h, [ref]$pidOut) | Out-Null
  if ($pidOut -eq $targetPid -and [W]::IsWindowVisible($h)) {
    $r = New-Object W+RECT
    [W]::GetWindowRect($h, [ref]$r) | Out-Null
    $area = ($r.Right - $r.Left) * ($r.Bottom - $r.Top)
    if ($area -gt $script:bestArea) {
      $script:bestArea = $area
      $script:best = $r
    }
  }
  return $true
}
[W]::EnumWindows($cb, [IntPtr]::Zero) | Out-Null

if ($best -eq $null) { Write-Output "WINDOW NOT FOUND"; exit 1 }

$w = $best.Right - $best.Left
$h = $best.Bottom - $best.Top
$x = $best.Left - 40
$y = $best.Top - 60
$bmp = New-Object System.Drawing.Bitmap ($w + 80), ($h + 100)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, $bmp.Size)
$out = "D:\tools\desktop-pet\.tmp_shot.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output ("CAPTURED rect=" + $best.Left + "," + $best.Top + "," + $best.Right + "," + $best.Bottom + " size=" + ($w+80) + "x" + ($h+100))
