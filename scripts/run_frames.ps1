$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -Path "D:\tools\desktop-pet\scripts\FrameCleaner2.cs" -ReferencedAssemblies System.Drawing
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "run1", 240, 640, 600, $true, $true)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "run2", 240, 640, 600, $true, $true)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "run3", 240, 640, 600, $true, $true)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "run4", 240, 640, 600, $true, $false)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "walk1", 240, 640, 600, $true, $true)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "walk2", 240, 640, 600, $true, $true)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "walk3", 240, 640, 600, $true, $false)
[FrameCleaner2]::Process("D:\tools\desktop-pet\sprites_raw", "walk4", 240, 640, 600, $true, $true)
Copy-Item sprites_raw\*.png sprites\ -Force
