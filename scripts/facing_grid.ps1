$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$names = @("run1", "run3")
$g = New-Object System.Drawing.Bitmap(1520, 920)
$gr = [System.Drawing.Graphics]::FromImage($g)
$gr.Clear([System.Drawing.Color]::White)
for ($i = 0; $i -lt 2; $i++) {
    $a = [System.Drawing.Bitmap]::FromFile("D:\tools\desktop-pet\sprites\$($names[$i]).png")
    $b = [System.Drawing.Bitmap]::FromFile("D:\tools\desktop-pet\sprites\$($names[$i])_l.png")
    $yy = $i * 460
    $gr.DrawImage($a, 0, $yy, 640, 600)
    $gr.DrawImage($b, 760, $yy, 640, 600)
    $gr.DrawRectangle([System.Drawing.Pens]::Red, 0, $yy, 640, 600)
    $gr.DrawRectangle([System.Drawing.Pens]::Blue, 760, $yy, 640, 600)
    $a.Dispose(); $b.Dispose()
}
$g.Save("D:\tools\desktop-pet\.tmp_facing_run.png", [System.Drawing.Imaging.ImageFormat]::Png)
$gr.Dispose(); $g.Dispose()
Write-Output "SAVED"
