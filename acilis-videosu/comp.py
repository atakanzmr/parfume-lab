"""Parfüm Lab açılışı · birleştirme.
3D plaka + bölge kareleri → sıvı parlaması → altın duman (2B akışkan) → erlenin çözülmesi → logonun belirmesi.
  python3 comp.py smoke 3.0 4.0 5.0   -> yalnızca duman (siyah üstünde) deneme kareleri
  python3 comp.py frames 60 120 170   -> seçilen kareler
  python3 comp.py all                 -> tüm kareler (out/), sonra encode"""
import os, sys, json, math, subprocess
import numpy as np, cv2
from scipy.ndimage import map_coordinates, gaussian_filter, distance_transform_edt, binary_closing
from scipy.fft import dstn, idstn
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from post import finish

D = os.path.join(HERE, 'frames'); OUT = os.path.join(HERE, 'out')
P = json.load(open(f'{D}/plan.json'))
W, H, FPS = P['RX'], P['RY'], P['FPS']
NF = int(7.2 * FPS)
REG = {k: tuple(v) for k, v in P['regions'].items()}
FIRST_TOP = 58
X0F, Y0F, X1F, Y1F = P['flask_bbox']; RIM_Y = P['rim'][1]; FLOOR_Y = P['floor_y']; CX = W / 2

def sm(a, b, x):
    u = np.clip((np.asarray(x, np.float32) - a) / (b - a), 0, 1); return u * u * (3 - 2 * u)

def ld(path): return np.asarray(Image.open(path).convert('RGB')).astype(np.float32) / 255

def fbm(h, w, seed, octs=((6, .45), (12, .28), (24, .17), (48, .10))):
    rng = np.random.default_rng(seed); acc = np.zeros((h, w), np.float32)
    for cells, amp in octs:
        g = rng.random((max(2, int(cells * h / w)) + 3, cells + 3)).astype(np.float32)
        acc += cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) * amp
    acc -= acc.min(); return acc / acc.max()

YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
GOLD = np.array([1.0, 0.70, 0.30], np.float32)

# ---------------- zaman çizelgesi (sn) ----------------
T_GLOW = (2.2, 3.6); T_SMOKE = (2.6, 3.3, 4.4, 5.0); T_DIS = (3.8, 5.4)
T_EDGE = (4.55, 5.0, 5.5, 6.2); T_FILL = (5.0, 6.1); T_SIL = (4.5, 5.7); T_CLEAR = (5.6, 6.4)

def tau_dis(t): return -0.05 + 1.1 * float(sm(*T_DIS, t))
def tau_fill(t): return -0.10 + 1.25 * float(sm(*T_FILL, t))

# ---------------- statik hazırlık ----------------
def prep_static():
    S = {}
    if os.path.exists(f'{D}/plate.png'):
        S['plate'] = ld(f'{D}/plate.png'); S['empty'] = ld(f'{D}/empty.png')
        # boş plakada zemindeki damlacık parıltıları silinir: erlenle birlikte sönerler
        e8 = (S['empty'] * 255 + 0.5).astype(np.uint8); spk = (S['empty'].max(axis=2) > 0.05) & (YY > 700)
        spk = cv2.dilate(spk.astype(np.uint8), np.ones((9, 9), np.uint8))
        S['empty'] = cv2.inpaint(e8, spk, 5, cv2.INPAINT_TELEA).astype(np.float32) / 255
        diff = np.abs(S['plate'] - S['empty']).max(axis=2)
        fm = gaussian_filter(sm(0.015, 0.06, diff).astype(np.float32), 3)
        box = ((YY > Y0F - 15) & (XX > X0F - 25) & (XX < X1F + 25)).astype(np.float32)   # pipet hariç
        S['flask'] = np.clip(cv2.dilate(fm, np.ones((9, 9), np.uint8)) * 1.3, 0, 1) * box
    # çözülme alanı: yukarıdan aşağı ilerler; yansıma, karşılık geldiği yerle birlikte söner
    ym = np.where(YY > FLOOR_Y, 2 * FLOOR_Y - YY, YY)
    vg = np.clip((ym - Y0F) / (Y1F - Y0F), 0, 1)
    S['ndis'] = (0.45 * vg + 0.55 * fbm(H, W, 3)).astype(np.float32)
    # logo
    logo = Image.open(os.path.join(HERE, 'logo-kaynak.png')).convert('RGB')
    s = 560 / 923; size = round(1254 * s); ox, oy = round(CX - 626 * s), round(500 - 147 * s)
    lg = np.asarray(logo.resize((size, size), Image.LANCZOS)).astype(np.float32) / 255
    can = np.zeros((H, W, 3), np.float32)
    xs0, ys0 = max(0, ox), max(0, oy); xs1, ys1 = min(W, ox + size), min(H, oy + size)
    can[ys0:ys1, xs0:xs1] = lg[ys0 - oy:ys1 - oy, xs0 - ox:xs1 - ox]
    lum = can @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    a = lum > 0.05
    a = binary_closing(a, structure=np.ones((25, 25)), iterations=2)
    a = cv2.morphologyEx(a.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(a)
    keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])); sil = (lab == keep)
    sil = binary_closing(sil, structure=np.ones((31, 31)), iterations=1)
    S['logo'] = can; S['sil'] = gaussian_filter(sil.astype(np.float32), 1.2)
    dist = distance_transform_edt(sil).astype(np.float32); dist /= dist.max()
    S['rfill'] = (0.72 * dist + 0.28 * fbm(H, W, 9)).astype(np.float32)
    gx = cv2.Sobel(gaussian_filter(lum, 1.0), cv2.CV_32F, 1, 0); gy = cv2.Sobel(gaussian_filter(lum, 1.0), cv2.CV_32F, 0, 1)
    e = np.hypot(gx, gy); e /= np.percentile(e[sil], 98) + 1e-6
    S['edges'] = np.clip(e, 0, 1.4) * sil
    S['logo_bottom'] = 1060.0
    return S

# ---------------- duman simülasyonu ----------------
NX, NY = W // 4, H // 4
SY, SX = np.mgrid[0:NY, 0:NX].astype(np.float32)
KX = np.arange(1, NX + 1); KY = np.arange(1, NY + 1)
LAM = (2 * np.cos(np.pi * KX / (NX + 1)) - 2)[None, :] + (2 * np.cos(np.pi * KY / (NY + 1)) - 2)[:, None]

def advect(q, u, v): return map_coordinates(q, [SY - v, SX - u], order=1, mode='constant', cval=0.0).astype(np.float32)

def project(u, v):
    div = np.gradient(u, axis=1) + np.gradient(v, axis=0)
    p = idstn(dstn(div, type=1) / LAM, type=1).astype(np.float32)
    return u - np.gradient(p, axis=1), v - np.gradient(p, axis=0)

def down(a): return cv2.resize(a, (NX, NY), interpolation=cv2.INTER_AREA)

def simulate(S, seed=5):
    rng = np.random.default_rng(seed)
    d = np.zeros((NY, NX), np.float32); u = np.zeros_like(d); v = np.zeros_like(d); psi = np.zeros_like(d)
    mx, my = NX / 2, RIM_Y / 4 - 1.5
    src_mouth = np.exp(-((SX - mx) / 5.5) ** 2 - ((SY - my) / 2.0) ** 2).astype(np.float32)
    fsm = gaussian_filter(down(S['flask']) * (SY * 4 < FLOOR_Y - 10), 1.0); fgx, fgy = np.gradient(fsm, axis=1), np.gradient(fsm, axis=0)
    fedge = np.clip(np.hypot(fgx, fgy) * 2.5, 0, 1) * (SY * 4 > RIM_Y + 20)      # erlenin dış hattı
    PATCH = [gaussian_filter(rng.random((NY * 2, NX)).astype(np.float32), 4) for _ in range(2)]
    nd = down(S['ndis']); fl = down(S['flask']) * (SY * 4 < FLOOR_Y - 6)
    sil = down(S['sil']); sgx = np.gradient(sil, axis=1); sgy = np.gradient(sil, axis=0)
    sedge = gaussian_filter(np.clip(np.hypot(sgx, sgy) * 3, 0, 1), 1.5); nrm = np.hypot(sgx, sgy) + 1e-6
    tanx, tany = -sgy / nrm, sgx / nrm                     # dış hat boyunca teğet
    sil_in = cv2.erode(sil, np.ones((3, 3), np.uint8))
    Ds, PT = [], []
    parts = np.zeros((0, 7), np.float32)                   # x, y (px), yaş, ömür, boy, parlaklık, faz
    for f in range(NF):
        t = f / FPS
        # kaynaklar
        k_m = float(sm(T_SMOKE[0], T_SMOKE[1], t) * (1 - sm(T_SMOKE[2], T_SMOKE[3], t)))
        if k_m > 0:
            wob = 0.55 * math.sin(t * 5.3) + 0.35 * math.sin(t * 8.7 + 1.0)
            d += 0.38 * k_m * k_m * src_mouth
            v = v * (1 - src_mouth) + src_mouth * (-2.6 - 0.8 * k_m); u += src_mouth * wob * 1.8 * k_m
        k_w = float(sm(3.3, 3.8, t) * (1 - sm(4.3, 4.8, t)))
        if k_w > 0:                                         # erlenin dışında kıvrılan ince buhar
            o = int(f * 1.5) % NY; pat = np.clip(PATCH[1][o:o + NY] * 9 - 4.2, 0, 1)
            d += 0.012 * k_w * fedge * pat; v -= 0.9 * k_w * fedge; u += 0.5 * k_w * fedge * np.sign(SX - mx)
        tau = tau_dis(t)
        if T_DIS[0] <= t <= T_DIS[1] + 0.1:
            o = int(f * 2) % NY; pat = np.clip(PATCH[0][o:o + NY] * 9 - 3.8, 0, 1)
            e = np.exp(-((nd - tau) / 0.025) ** 2) * fl * pat
            d += 0.06 * e; v -= 1.7 * e; u += e * (0.7 * np.sign(SX - mx) + 1.4 * (rng.random(e.shape).astype(np.float32) - 0.5))
        k_s = float(sm(T_SIL[0], T_SIL[0] + 0.3, t) * (1 - sm(T_SIL[1] - 0.3, T_SIL[1], t)))
        if k_s > 0:
            o = int(f * 2.5) % NY; pat = np.clip(PATCH[1][o:o + NY] * 9 - 3.5, 0, 1)
            d += 0.03 * k_s * sedge * pat
            u += 1.6 * k_s * sedge * tanx; v += 1.6 * k_s * sedge * tany - 0.5 * k_s * sedge
        # kuvvetler
        v -= 0.12 * d
        w = np.gradient(v, axis=1) - np.gradient(u, axis=0); aw = np.abs(w)
        gx, gy = np.gradient(aw, axis=1), np.gradient(aw, axis=0); n = np.hypot(gx, gy) + 1e-5
        u += 0.42 * (gy / n) * w; v += -0.42 * (gx / n) * w
        psi = 0.92 * psi + 0.08 * gaussian_filter(rng.standard_normal((NY, NX)).astype(np.float32), 5) * 9
        u += 0.08 * np.gradient(psi, axis=0); v -= 0.08 * np.gradient(psi, axis=1)
        u *= 0.996; v *= 0.996
        u, v = advect(u, u, v), advect(v, u, v)
        u, v = project(u, v)
        diss = 0.991 - 0.06 * float(sm(*T_CLEAR, t))
        d = advect(d, u, v) * diss
        fill = float(sm(*T_FILL, t))
        if fill > 0: d *= 1 - 0.16 * fill * sil_in
        Ds.append(d.copy())
        # parıltılar
        new = []
        if k_m > 0.1 and rng.random() < 0.9:
            for _ in range(rng.poisson(3 * k_m)):
                new.append((CX + rng.normal(0, 14), RIM_Y - 4 + rng.normal(0, 3)))
        if T_DIS[0] <= t <= T_DIS[1]:
            ys, xs = np.nonzero(np.exp(-((nd - tau) / 0.03) ** 2) * fl > 0.5)
            if len(xs):
                for i in rng.choice(len(xs), size=min(len(xs), rng.poisson(7)), replace=False):
                    new.append((xs[i] * 4 + rng.random() * 4, ys[i] * 4 + rng.random() * 4))
        if k_s > 0.2:
            ys, xs = np.nonzero(sedge > 0.5)
            if len(xs):
                for i in rng.choice(len(xs), size=min(len(xs), rng.poisson(6 * k_s)), replace=False):
                    new.append((xs[i] * 4 + rng.random() * 4, ys[i] * 4 + rng.random() * 4))
        if new:
            nn = np.array(new, np.float32); m = len(nn)
            add = np.column_stack([nn, np.zeros(m), rng.uniform(0.8, 1.9, m), rng.uniform(0.7, 2.0, m),
                                   rng.uniform(0.5, 1.0, m), rng.uniform(0, 6.3, m)]).astype(np.float32)
            parts = np.vstack([parts, add])
        if len(parts):
            cxs, cys = parts[:, 0] / 4, parts[:, 1] / 4
            pu = map_coordinates(u, [cys, cxs], order=1, mode='nearest'); pv = map_coordinates(v, [cys, cxs], order=1, mode='nearest')
            parts[:, 0] += pu * 4 * 0.9; parts[:, 1] += pv * 4 * 0.9 - 0.25
            parts[:, 2] += 1 / FPS
            parts = parts[parts[:, 2] < parts[:, 3]]
        PT.append(parts.copy())
    return Ds, PT

# ---------------- duman ve parıltı çizimi ----------------
DET = None
def smoke_rgb(d, f):
    global DET
    if DET is None: DET = (fbm(H * 2, W, 12, ((10, .5), (24, .3), (56, .2))), fbm(H * 2, W, 13, ((14, .5), (32, .3), (70, .2))))
    big = np.clip(cv2.resize(d, (W, H), interpolation=cv2.INTER_CUBIC), 0, None)
    o1 = int(f * 3.2) % H; o2 = int(f * 5.1) % H
    det = 0.55 * DET[0][o1:o1 + H] + 0.45 * DET[1][o2:o2 + H]
    big *= 0.72 + 0.56 * det
    I = 1 - np.exp(-2.8 * big)
    return I[..., None] * np.array([1.0, 0.78, 0.42], np.float32) * 1.15 + (I * I)[..., None] * np.array([0.50, 0.40, 0.25], np.float32)

KER = {}
def sparkles(parts, f):
    acc = np.zeros((H, W), np.float32)
    for x, y, age, life, size, br, ph in parts:
        a = math.sin(math.pi * min(1.0, age / life)) * br * (0.55 + 0.45 * math.sin(ph + f * 0.9))
        sz = round(size * 2) / 2
        if sz not in KER:
            r = int(math.ceil(sz * 3)); g = np.arange(-r, r + 1, dtype=np.float32)
            KER[sz] = np.exp(-(g[None, :] ** 2 + g[:, None] ** 2) / (2 * (sz * 0.6) ** 2));
        k = KER[sz]; r = k.shape[0] // 2; xi, yi = int(round(x)), int(round(y))
        if xi - r < 0 or yi - r < 0 or xi + r >= W or yi + r >= H: continue
        acc[yi - r:yi + r + 1, xi - r:xi + r + 1] += k * a
    return acc

# ---------------- bölge yapıştırma ----------------
def feather(box, fe=14):
    x0, y0, x1, y1 = box; m = np.zeros((H, W), np.float32)
    lx = np.clip((XX[0] - x0) / fe, 0, 1) if x0 > 0 else (XX[0] >= x0).astype(np.float32)
    rx = np.clip((x1 - 1 - XX[0]) / fe, 0, 1) if x1 < W else (XX[0] < x1).astype(np.float32)
    ty = np.clip((YY[:, 0] - y0) / fe, 0, 1) if y0 > 0 else (YY[:, 0] >= y0).astype(np.float32)
    by = np.clip((y1 - 1 - YY[:, 0]) / fe, 0, 1) if y1 < H else (YY[:, 0] < y1).astype(np.float32)
    m = (ty * by)[:, None] * (lx * rx)[None, :]
    m[:y0] = 0; m[y1:] = 0; m[:, :x0] = 0; m[:, x1:] = 0
    return m[..., None]
FM = {k: feather(b) for k, b in REG.items()}

def region(name, f):
    p = f'{D}/{name}/{f:04d}.png'
    return ld(p) if os.path.exists(p) else None

def base_frame(S, f):
    b = S['plate'].copy()
    plan = []
    if f < FIRST_TOP: plan.append(('tip', min(f, P['F_IMPACT'] - 1)))
    if P['F_DETACH'] <= f <= P['F_IMPACT']: plan.append(('fall', f))
    if f >= FIRST_TOP: plan.append(('top', min(f, 100)))
    if f >= P['F_IMPACT']: plan.append(('liq', min(f, P['F_LAST'])))
    for name, ff in plan:
        im = region(name, ff)
        if im is not None: b = b * (1 - FM[name]) + im * FM[name]
    return b

# ---------------- kare ----------------
def compose(S, f, Ds, PT, smoke_only=False):
    t = f / FPS
    if smoke_only:
        img = np.zeros((H, W, 3), np.float32)
    else:
        img = base_frame(S, f)
        # sıvının parlaması artar
        g = 0.45 * float(sm(*T_GLOW, t))
        if g > 0:
            lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            amb = np.clip((img[..., 0] - img[..., 2]) * 1.6, 0, 1) * np.clip(lum * 1.8, 0, 1) * S['flask']
            img = np.clip(img * (1 + g * amb[..., None] * np.array([1.0, 0.82, 0.55], np.float32)), 0, 1)
        # erlen duman içinde çözülür
        tau = tau_dis(t)
        if t >= T_DIS[0] - 0.05:
            vis = sm(tau - 0.06, tau + 0.06, S['ndis'])[..., None]
            img = S['empty'] + (img - S['empty']) * vis
            edge = np.exp(-((S['ndis'] - tau) / 0.03) ** 2) * S['flask'] * (YY < FLOOR_Y + 8) * float(1 - sm(T_DIS[1] - 0.1, T_DIS[1] + 0.15, t))
            img = img + edge[..., None] * GOLD * 0.30
        # logo: önce hatlar ışıldar, sonra kenardan içe dolar
        ae = float(sm(T_EDGE[0], T_EDGE[1], t) * (1 - sm(T_EDGE[2], T_EDGE[3], t)))
        tf = tau_fill(t)
        m = sm(tf - 0.08, tf, S['rfill'])
        m = (1 - m) * S['sil'] if tf > -0.1 else np.zeros_like(S['sil'])
        if m.max() > 0 or ae > 0:
            img = img * (1 - m[..., None]) + S['logo'] * m[..., None]
            front = np.exp(-((S['rfill'] - tf) / 0.04) ** 2) * S['sil'] * float(sm(T_FILL[0], T_FILL[0] + 0.2, t) * (1 - sm(T_FILL[1] - 0.3, T_FILL[1] + 0.1, t)))
            img = img + (S['edges'] * ae + front * 0.55)[..., None] * GOLD
            # zeminde yansıma ve sıcak ışık
            ref_m = m[::-1]; ref = S['logo'][::-1]
            sh = int(2 * FLOOR_Y - H)
            refl = np.zeros_like(img); mm = np.zeros((H, W), np.float32)
            if sh >= 0:
                refl[sh:] = ref[:H - sh]; mm[sh:] = ref_m[:H - sh]
            else:
                refl[:H + sh] = ref[-sh:]; mm[:H + sh] = ref_m[-sh:]
            fade = (np.clip(1 - (YY - FLOOR_Y) / 230, 0, 1) ** 1.6 * (YY > FLOOR_Y))[..., None]
            refl = cv2.GaussianBlur(refl * mm[..., None] * fade * 0.38, (0, 0), 2.5)
            img = 1 - (1 - np.clip(img, 0, 1)) * (1 - refl)
            pool = np.exp(-((XX - CX) / 170) ** 2 - ((YY - FLOOR_Y - 6) / 22) ** 2) * float(m.max()) * 0.16
            img = img + pool[..., None] * GOLD
    sm_rgb = smoke_rgb(Ds[f], f)
    img = 1 - (1 - np.clip(img, 0, 1)) * (1 - np.clip(sm_rgb, 0, 1))
    sp = sparkles(PT[f], f)
    img = img + sp[..., None] * np.array([1.0, 0.86, 0.62], np.float32) * 0.9
    out = finish(Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)), seed=f)
    if f < 12:
        a = np.asarray(out).astype(np.float32) * float(sm(0, 12, f)); out = Image.fromarray(a.astype(np.uint8))
    return out

if __name__ == '__main__':
    mode = sys.argv[1]
    S = prep_static()
    Ds, PT = simulate(S)
    os.makedirs(OUT, exist_ok=True)
    if mode == 'smoke':
        for a in sys.argv[2:]:
            f = int(round(float(a) * FPS)); compose(S, f, Ds, PT, smoke_only=True).save(f'{OUT}/duman_{f:04d}.png')
    elif mode == 'frames':
        for a in sys.argv[2:]:
            f = int(a); compose(S, f, Ds, PT).save(f'{OUT}/k_{f:04d}.png')
    elif mode == 'all':
        for f in range(NF):
            compose(S, f, Ds, PT).save(f'{OUT}/{f:04d}.png')
            if f % 20 == 0: print('kare', f, flush=True)
    print('tamam', flush=True)
