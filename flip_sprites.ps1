Add-Type -AssemblyName System.Drawing

function Flip-File {
    param([string]$path)
    $S = 600
    $src = [System.Drawing.Image]::FromFile($path)
    $bmp = New-Object System.Drawing.Bitmap($S, $S, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::FromArgb(0, 0, 0, 0))
    $g.TranslateTransform($S, 0)
    $g.ScaleTransform(-1, 1)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.DrawImage($src, 0, 0, $S, $S)
    $g.Dispose()
    $src.Dispose()
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Output ("flipped " + $path)
}

$map = @{
  'husky'    = @('run1','run2','run4','walk2','walk3','walk4')
  'redpanda' = @('run1','run2','run4','walk1','walk2','walk3')
  'capybara' = @('idle','run1','run2','run3','run4','walk1','walk2','walk3','walk4')
}

foreach ($pet in @('husky','redpanda','capybara')) {
    foreach ($f in $map[$pet]) {
        $p = "D:\tools\desktop-pet\sprites\$pet\$f.png"
        if (Test-Path $p) { Flip-File $p }
        $pl = "D:\tools\desktop-pet\sprites\$pet\${f}_l.png"
        if (Test-Path $pl) { Flip-File $pl }
    }
}
Write-Output 'FLIP DONE'
