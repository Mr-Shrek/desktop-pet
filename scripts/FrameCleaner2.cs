using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Collections.Generic;

public class FrameCleaner2 {
    // 泛洪去背景(近白) → 只保留最大连通前景块(清碎块) → 边缘羽化 →
    // 内容等比 fit 进统一画布(Wset x Hset) → 底部对齐居中 → 保存主帧 + 水平镜像副本(_l)。
    // flipLeft=true 时主帧额外做水平翻转(用于把朝左的源帧统一成朝右)。
    public static void Process(string src, string name, int TH, int Wset, int Hset, bool mirror, bool flipLeft) {
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
            int[,] lab = new int[h, w];
            Queue<int[]> q = new Queue<int[]>();
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
            int best = 0, bestSz = 0;
            foreach (var kv in compSize) if (kv.Value > bestSz) { bestSz = kv.Value; best = kv.Key; }
            int[,] alpha = new int[h, w];
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++)
                    alpha[y, x] = (lab[y, x] == best) ? 255 : 0;
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
                // 等比 fit 进 (Wset, Hset)，底部对齐 + 水平居中
                double scale = Math.Min((double)Wset / cw, (double)Hset / ch);
                int nw = Math.Max(1, (int)Math.Round(cw * scale));
                int nh = Math.Max(1, (int)Math.Round(ch * scale));
                string info = name + ": bbox=" + cw + "x" + ch + " fit=" + nw + "x" + nh + " comps=" + ncomp;
                using (Bitmap canvas = new Bitmap(Wset, Hset, PixelFormat.Format32bppArgb)) {
                    using (Graphics g = Graphics.FromImage(canvas)) {
                        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                        g.Clear(Color.Transparent);
                        g.DrawImage(outBmp, (Wset - nw) / 2, Hset - nh, nw, nh);
                    }
                    if (flipLeft) canvas.RotateFlip(RotateFlipType.RotateNoneFlipX);
                    canvas.Save(System.IO.Path.Combine(src, name + ".png"), ImageFormat.Png);
                    if (mirror) {
                        Bitmap fl = (Bitmap)canvas.Clone();
                        fl.RotateFlip(RotateFlipType.RotateNoneFlipX);
                        fl.Save(System.IO.Path.Combine(src, name + "_l.png"), ImageFormat.Png);
                        fl.Dispose();
                    }
                }
                Console.WriteLine(info);
            }
        }
    }
}