"""Render sonrası: altın parlama (bloom), kenar kararması, hafif film greni."""
import sys
import numpy as np
from PIL import Image, ImageFilter

def finish(img, seed=0, grain=1.4):
    a = np.asarray(img.convert('RGB')).astype(np.float32) / 255
    h, w = a.shape[:2]; k = w / 720
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hi = a * np.clip((lum - 0.50) / 0.50, 0, 1)[..., None]
    hi_img = Image.fromarray((hi * 255).astype(np.uint8))
    acc = np.zeros_like(a)
    for r, wt in ((5, 0.45), (16, 0.35), (44, 0.28)):
        acc += np.asarray(hi_img.filter(ImageFilter.GaussianBlur(r * k))).astype(np.float32) / 255 * wt
    acc *= np.array([1.0, 0.82, 0.55], np.float32)
    out = 1 - (1 - a) * (1 - np.clip(acc, 0, 1))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w * 0.80)) ** 2 + ((yy - h * 0.56) / (h * 0.60)) ** 2)
    out *= np.clip(1.15 - d * 0.55, 0.45, 1.0)[..., None]
    rng = np.random.default_rng(seed)
    out += rng.normal(0, grain / 255, out.shape[:2])[..., None].astype(np.float32)
    return Image.fromarray((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))

if __name__ == '__main__':
    finish(Image.open(sys.argv[1])).save(sys.argv[2])
