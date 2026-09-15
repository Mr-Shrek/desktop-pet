$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$w = 560; $h = 420
$x = $b.X + [math]::Max(0, ($b.Width - $w) / 2)
$y = $b.Y + [math]::Max(0, ($b.Height / 3) - 70)
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen([int]$x, [int]$y, 0, 0, $bmp.Size)
$bmp.Save("D:\tools\desktop-pet\.tmp_popup.png", [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Output ("PRIMARY-REGION x=" + $x + " y=" + $y + " " + $w + "x" + $h)
