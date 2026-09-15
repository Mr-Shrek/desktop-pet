$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$dir = "D:\tools\desktop-pet\sprites"
foreach ($n in @("run1", "run2", "run3", "run4", "walk1", "walk2", "walk3", "walk4", "run1_l", "walk3_l")) {
    $bmp = [System.Drawing.Bitmap]::FromFile((Join-Path $dir ($n + ".png")))
    $trans = 0; $total = 0
    for ($y = 0; $y -lt $bmp.Height; $y += 3) {
        for ($x = 0; $x -lt $bmp.Width; $x += 3) {
            $p = $bmp.GetPixel($x, $y)
            $total++
            if ($p.A -lt 200) { $trans++ }
        }
    }
    Write-Output ("{0} : alpha<200={1}%" -f $n, [math]::Round(100 * $trans / $total))
    $bmp.Dispose()
}
