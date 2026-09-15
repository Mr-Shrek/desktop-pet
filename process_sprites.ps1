# 桌宠形象素材处理：绿幕抠图 → 透明 PNG 600x600 → 生成 _l 镜像
# 输入: sprites_raw/<pet>/<frame>.jpg (1024x1024 绿幕)
# 输出: sprites/<pet>/<frame>.png (600x600 透明) + <frame>_l.png (仅 run/walk)
Add-Type -AssemblyName System.Drawing

$root = 'D:\tools\desktop-pet'
$srcRoot = Join-Path $root 'sprites_raw'
$dstRoot = Join-Path $root 'sprites'
$SIZE = 600

function Process-Frame {
    param([string]$srcPath, [string]$dstPath)
    $src = [System.Drawing.Image]::FromFile($srcPath)
    $bmp = New-Object System.Drawing.Bitmap($SIZE, $SIZE, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.DrawImage($src, 0, 0, $SIZE, $SIZE)
    $g.Dispose(); $src.Dispose()

    # 色键抠图: 绿色像素 -> alpha=0
    $rect = New-Object System.Drawing.Rectangle(0, 0, $SIZE, $SIZE)
    $data = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadWrite, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $stride = $data.Stride
    $bytes = New-Object byte[] ($stride * $SIZE)
    [System.Runtime.InteropServices.Marshal]::Copy($data.Scan0, $bytes, 0, $bytes.Length)
    $cut = 0
    for ($y = 0; $y -lt $SIZE; $y++) {
        for ($x = 0; $x -lt $SIZE; $x++) {
            $i = $y * $stride + $x * 4
            $b = $bytes[$i]; $gv = $bytes[$i+1]; $r = $bytes[$i+2]
            if ($gv -gt 100 -and $gv -gt $r * 1.25 -and $gv -gt $b * 1.25) {
                $bytes[$i] = 0; $bytes[$i+1] = 0; $bytes[$i+2] = 0; $bytes[$i+3] = 0
                $cut++
            }
        }
    }
    [System.Runtime.InteropServices.Marshal]::Copy($bytes, 0, $data.Scan0, $bytes.Length)
    $bmp.UnlockBits($data)
    $bmp.Save($dstPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    return $cut
}

function New-Mirror {
    param([string]$srcPath, [string]$dstPath)
    $src = [System.Drawing.Image]::FromFile($srcPath)
    $bmp = New-Object System.Drawing.Bitmap($SIZE, $SIZE, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.Clear([System.Drawing.Color]::FromArgb(0, 0, 0, 0))
    $g.TranslateTransform($SIZE, 0)
    $g.ScaleTransform(-1, 1)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.DrawImage($src, 0, 0, $SIZE, $SIZE)
    $g.Dispose(); $src.Dispose()
    $bmp.Save($dstPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

$pets = @('redpanda', 'panda', 'capybara', 'husky')
$motion = @('run1','run2','run3','run4','walk1','walk2','walk3','walk4')
$all = @('idle','happy','sleep','surprise') + $motion

foreach ($pet in $pets) {
    $d = Join-Path $dstRoot $pet
    New-Item -ItemType Directory -Force -Path $d | Out-Null
    foreach ($name in $all) {
        $src = Join-Path (Join-Path $srcRoot $pet) ($name + '.jpg')
        $dst = Join-Path $d ($name + '.png')
        if (-not (Test-Path $src)) { Write-Output "MISSING $src"; continue }
        $cut = Process-Frame -srcPath $src -dstPath $dst
        if ($motion -contains $name) {
            New-Mirror -srcPath $dst -dstPath (Join-Path $d ($name + '_l.png'))
        }
        Write-Output ("{0}/{1}: cut={2}" -f $pet, $name, $cut)
    }
}
Write-Output 'ALL DONE'
