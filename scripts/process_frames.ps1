$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$cs = @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Collections.Generic;

public class FrameCleaner2 {
    // 从边缘泛洪去背景（近白），随后只保留最大连通前景块（清掉棋盘格残留/碎块），
    // 边缘 1px 淡出，内容底部对齐缩放到统一画布，并可生成水平镜像副本。
    public static void Process(string src, string name, int TH, int Hset, bool mirror) {
        string path = System.IO.Path.Combine(src, name + ".png");
        byte[] bytes = System.IO.File.ReadAllBytes(path);
        using (Bitmap bmp = new Bitmap(new System.IO.MemoryStream(bytes))) {
            int w = bmp.Width, h = bmp.Height;
            bool[,] bg = new bool[h, w];
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++) {
                    Color p = bmp.GetPixel(x, y);
                    bg[y, x] = p.R >= TH && p.G >= TH && p.B >= TH;
                }
            int[,] lab = new int[h, w];   // 0=背景  >0=前景连通块编号
            Queue<int[]> q = new Queue<int[]>();
            // 边缘泛洪：标记背景
            for (int x = 0; x < w; x++) {
                if (bg[0, x] && lab[0, x] == 0) { lab[0, x] = -1; q.Enqueue(new int[]{0, x}); }
                if (bg[h-1, x] && lab[h-1, x] == 0) { lab[h-1, x] = -1; q.Enqueue(new int[]{h-1, x}); }
            }
            for (int y = 0; y < h; y++) {
                if (bg[y, 0] && lab[y, 0] == 0) { lab[y, 0] = -1; q.Enqueue(new int[]{y, 0}); }
                if (bg[y, w-1] && lab[y, w-1] == 0) { lab[y, w-1] = -1; q.Enqueue(new int[]{y, w-1}); }
            }
            while (q.Count > 0) {
                int[] c = q.Dequeue();
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (dx == 0 && dy == 0) continue;
                        int ny = c[0] + dy, nx = c[1] + dx;
                        if (ny >= 0 && ny < h && nx >= 0 && nx < w && bg[ny, nx] && lab[ny, nx] == 0) {
                            lab[ny, nx] = -1;
                            q.Enqueue(new int[]{ny, nx});
                        }
                    }
            }
            // 连通前景块标记（4 邻域），并统计各块大小
            Dictionary<int, int> compSize = new Dictionary<int, int>();
            int ncomp = 0;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++) {
                    if (lab[y, x] == 0 && !bg[y, x]) {
                        ncomp++;
                        int sz = 0;
                        lab[y, x] = ncomp;
                        q.Enqueue(new int[]{y, x});
                        while (q.Count > 0) {
                            int[] c = q.Dequeue(); sz++;
                            for (int dy = -1; dy <= 1; dy++)
                                for (int dx = -1; dx <= 1; dx++) {
                                    if (dx == 0 && dy == 0) continue;
                                    int ny = c[0] + dy, nx = c[1] + dx;
                                    if (ny >= 0 && ny < h && nx >= 0 && nx < w && lab[ny, nx] == 0 && !bg[ny, nx]) {
                                        lab[ny, nx] = ncomp;
                                        q.Enqueue(new int[]{ny, nx});
                                    }
                                }
                        }
                        compSize[ncomp] = sz;
                    }
                }
            // 最大连通块 = 猫体，其余碎块全清除
            int best = 0, bestSz = 0;
            foreach (var kv in compSize) if (kv.Value > bestSz) { bestSz = kv.Value; best = kv.Key; }
            int[,] alpha = new int[h, w];
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    alpha[y, x] = (lab[y, x] == best) ? 255 : 0;
            // 边缘 1px 淡出
            int[,] a2 = (int[,])alpha.Clone();
            for (int y = 1; y < h-1; y++)
                for (int x = 1; x < w-1; x++) {
                    if (alpha[y, x] != 255) continue;
                    bool nearT = false;
                    for (int dy = -1; dy <= 1 && !nearT; dy++)
                        for (int dx = -1; dx <= 1; dx++)
                            if (alpha[y+dy, x+dx] == 0) { nearT = true; break; }
                    if (nearT) a2[y, x] = 128;
                }
            // 内容包围盒
            int minX = w, minY = h, maxX = -1, maxY = -1;
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    if (a2[y, x] > 8) {
                        if (x < minX) minX = x;
                        if (x > maxX) maxX = x;
                        if (y < minY) minY = y;
                        if (y > maxY) maxY = y;
                    }
            int cw = maxX - minX + 1, ch = maxY - minY + 1;
            using (Bitmap outBmp = new Bitmap(cw, ch, PixelFormat.Format32bppArgb)) {
                for (int y = 0; y < ch; y++)
                    for (int x = 0; x < cw; x++) {
                        Color p = bmp.GetPixel(minX + x, minY + y);
                        outBmp.SetPixel(x, y, Color.FromArgb(a2[minY + y, minX + x], p.R, p.G, p.B));
                    }
                // 统一高度 Hset，宽度等比，底部对齐
                double scale = (double)Hset / ch;
                int nw = Math.Max(1, (int)(cw * scale));
                int nh = Hset;
                using (Bitmap canvas = new Bitmap(600, 600, PixelFormat.Format32bppArgb)) {
                    using (Graphics g = Graphics.FromImage(canvas)) {
                        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                        g.Clear(Color.Transparent);
                        g.DrawImage(outBmp, (600 - nw) / 2, 600 - nh, nw, nh);
                    }
                    canvas.Save(System.IO.Path.Combine(src, name + ".png"), ImageFormat.Png);
                    if (mirror) {
                        Bitmap fl = (Bitmap)canvas.Clone();
                        fl.RotateFlip(RotateFlipType.RotateNoneFlipX);
                        fl.Save(System.IO.Path.Combine(src, name + "_l.png"), ImageFormat.Png);
                        fl.Dispose();
                    }
                }
            }
            Console.WriteLine(name + ": bbox=" + cw + "x" + ch + " comps=" + ncomp);
        }
    }
}
"@
Add-Type -TypeDefinition $cs -ReferencedAssemblies System.Drawing

# 先看每帧内容高度，统一到各套帧的最大高度
$names = @("run1", "run2", "run3", "run4", "walk1", "walk2", "walk3", "walk4")
# 跑步帧统一高度 460，走路帧统一高度 420（保证脚底对齐、大小一致）
foreach ($n in @("run1", "run2", "run3", "run4")) {
    [FrameCleaner2]::Process("D:\tools\desktop-pet\sprites", $n, 240, 460, $true)
}
foreach ($n in @("walk1", "walk2", "walk3", "walk4")) {
    [FrameCleaner2]::Process("D:\tools\desktop-pet\sprites", $n, 240, 420, $true)
}
