"""Parfüm Lab açılışı · 3D animasyon kareleri.
Sabit plaka bir kez, değişen bölgeler kare kare render edilir; birleştirme comp.py'de.
  python anim.py plan              -> bölgeler ve önemli noktalar (frames/plan.json)
  python anim.py test 30:tip 58:liq -> seçilen kareler
  python anim.py all               -> plaka + boş plaka + tüm bölgeler (var olanları atlar)"""
import os, sys, math, json, time, random
os.environ['NO_RENDER'] = '1'
os.environ.setdefault('RX', '720'); os.environ.setdefault('RY', '1560')
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, 'scene.py'), encoding='utf-8').read())
import numpy as np
from bpy_extras.object_utils import world_to_camera_view

OUTDIR = os.path.join(HERE, 'frames')
FPS = 30; F_DETACH = 36; F_IMPACT = 52; F_LAST = 156
SPP_PLATE = 192; SPP_REG = int(os.environ.get('SPP_REG', 72))
O = bpy.data.objects
pip, pliq, hang, fall = O['pipet'], O['pipet_sivi'], O['asili_damla'], O['dusen_damla']
AX = Vector((math.sin(ANG), 0.0, math.cos(ANG)))
HANG_R0, FALL_R0 = 0.0017, 0.0021

def smooth(a, b, x):
    u = min(1.0, max(0.0, (x - a) / (b - a))); return u * u * (3 - 2 * u)

# ---------------- zamanlama ----------------
def pip_off(f): return AX * (0.17 * smooth(58, 100, f))

def hang_state(f):
    if f < F_DETACH:
        u = f / F_DETACH
        return 0.0007 + 0.0012 * u ** 1.3, 1.0 + 0.28 * u ** 3 + 0.18 * smooth(30, 36, f)
    u = smooth(F_DETACH, F_DETACH + 8, f)
    return 0.00064 + 0.0001 * u, 1.3 - 0.3 * u

Z0 = TIP.z - 0.0019 * 1.25
A_FALL = 2 * (Z0 - (ZL + 0.0006)) / ((F_IMPACT - F_DETACH) / FPS) ** 2

def fall_state(f):
    if f < F_DETACH or f > F_IMPACT: return None
    tt = (f - F_DETACH) / FPS; k = f - F_DETACH
    return Z0 - 0.5 * A_FALL * tt * tt, 1.0 + 0.11 * math.exp(-k / 7) * math.cos(k * 1.4)

# anahtar kareler (hareket bulanıklığı için)
for f in range(0, 220):
    off = pip_off(f)
    for ob in (pip, pliq):
        ob.location = TIP + off; ob.keyframe_insert('location', frame=f)
    r_, sz = hang_state(f); s_ = r_ / HANG_R0
    hang.location = TIP + off + Vector((0, 0, -r_ * sz * 0.72)); hang.scale = (s_, s_, s_ * sz)
    hang.keyframe_insert('location', frame=f); hang.keyframe_insert('scale', frame=f)
    st = fall_state(f)
    if st:
        z, sz = st; s_ = 0.0019 / FALL_R0
        fall.location = (0, 0, z); fall.scale = (s_ / math.sqrt(sz), s_ / math.sqrt(sz), s_ * sz)
    else:
        fall.location = (0, 0, Z0); fall.scale = (1e-4, 1e-4, 1e-4)
    fall.keyframe_insert('location', frame=f); fall.keyframe_insert('scale', frame=f)
for ob in (pip, pliq, hang, fall):
    ad = ob.animation_data
    if ad and ad.action:
        try:
            curves = ad.action.fcurves
        except Exception:
            curves = [fc for layer in ad.action.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]
        for fc in curves:
            for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'

# ---------------- sıvı yüzeyi: çukur, jet, halkalar ----------------
me = O['sivi'].data
BASE = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', BASE); BASE = BASE.reshape(-1, 3)
RR = np.hypot(BASE[:, 0], BASE[:, 1]); TOP = np.where(np.abs(BASE[:, 2] - ZL) < 1e-6)[0]; R0 = float(RR[TOP].max())

def surf_h(r, ti):
    h = np.zeros_like(r)
    if ti <= 0: return h
    if ti < 0.18:
        D = 0.004 * math.sin(math.pi * ti / 0.18)
        h += -D * np.exp(-(r / 0.0032) ** 2) + 0.28 * D * np.exp(-((r - 0.0048) / 0.0013) ** 2)
    if 0.12 < ti < 0.52:
        J = 0.014 * math.sin(math.pi * (ti - 0.12) / 0.40)
        sg = 0.0011 + 0.0005 * (ti - 0.12) / 0.40
        h += J * np.exp(-(r / sg) ** 2)
    for t0, A0 in ((0.04, 0.0007), (0.63, 0.00028)):
        tt = ti - t0
        if tt <= 0: continue
        A = A0 * math.exp(-tt / 0.45)
        for k in range(3):
            tk = tt - k * 0.045
            if tk <= 0: continue
            x = r - 0.10 * tk
            h += A * np.exp(-(x / 0.0026) ** 2) * np.cos(2 * math.pi * x / 0.0045) / (1 + r / 0.012)
    tp = np.clip((R0 - r) / 0.0025, 0, 1)
    return h * tp * tp * (3 - 2 * tp)

jet = sphere('jet_damla', 0.0012, Vector((0, 0, ZL)), mat=M_DROP, seg=32); jet.hide_render = True

def jet_z(ti):
    if not (0.30 <= ti <= 0.63): return None
    d = ti - 0.30
    return ZL + 0.0135 + 0.05 * d - 0.275 * d * d

# ---------------- kabarcıklar ----------------
random.seed(21)
BUBS = []
for i in range(10):                                     # çarpmayla içeri giren hava
    a = random.uniform(0, 2 * math.pi); rd = random.uniform(0, 0.004)
    BUBS.append(dict(t0=random.uniform(0.04, 0.16), x=rd * math.cos(a), y=rd * math.sin(a), z0=ZL - 0.003 - random.uniform(0, 0.007),
                     r=random.uniform(0.0003, 0.0008), v=random.uniform(0.012, 0.022), down=random.uniform(0.002, 0.005), ph=random.uniform(0, 6.3), fizz=False))
NUC = [(0.006, -0.010, 0.0064), (-0.011, -0.006, 0.0064), (0.016, -0.005, 0.0078), (-0.004, -0.017, 0.0066), (0.001, 0.004, 0.0064)]
for (nx, ny, nz) in NUC:                                 # dipten yükselen ince kabarcık dizileri
    t = 0.22 + random.uniform(0, 0.1)
    while t < (F_LAST - F_IMPACT) / FPS:
        BUBS.append(dict(t0=t, x=nx, y=ny, z0=nz, r=random.uniform(0.00022, 0.00045), v=random.uniform(0.028, 0.042), down=0.0, ph=random.uniform(0, 6.3), fizz=True))
        t += random.uniform(0.09, 0.16)
for i, b in enumerate(BUBS):
    b['ob'] = sphere(f'kb{i}', 1.0, Vector((0, 0, 0)), mat=M_BUB, seg=16); b['ob'].hide_render = True

def bub_pos(b, tau):
    if b['fizz']:
        z = b['z0'] + b['v'] * tau + 0.005 * tau * tau; w = 0.00015
    else:
        z = b['z0'] - b['down'] * math.sin(math.pi / 2 * min(tau / 0.12, 1.0)) + b['v'] * max(0.0, tau - 0.12); w = 0.0003
    x = b['x'] + w * math.sin(b['ph'] + tau * 17); y = b['y'] + w * math.cos(b['ph'] * 1.3 + tau * 13)
    grow = 1 + 0.35 * max(0.0, z - b['z0']) / 0.04
    return x, y, z, b['r'] * grow

def pose(f):
    sc.frame_set(f)
    ti = (f - F_IMPACT) / FPS
    co = BASE.copy(); co[TOP, 2] = ZL + surf_h(RR[TOP], ti)
    me.vertices.foreach_set('co', co.ravel()); me.update()
    jz = jet_z(ti)
    jet.hide_render = jz is None
    if jz is not None: jet.location = (0, 0, jz)
    for b in BUBS:
        tau = ti - b['t0']; ob = b['ob']
        if tau < 0: ob.hide_render = True; continue
        x, y, z, rad = bub_pos(b, tau)
        # yüzeye varınca 2 karede söner
        top = ZL - 0.0002 - rad
        if z > top:
            over = (z - top) / (b['v'] / FPS * 2 + 1e-9)
            if over >= 1: ob.hide_render = True; continue
            rad *= 1 - over; z = top
        if math.hypot(x, y) > r_inner(z) - rad - 0.0004: ob.hide_render = True; continue
        ob.hide_render = False; ob.location = (x, y, z); ob.scale = (rad, rad, rad)

# ---------------- bölgeler ----------------
def px(p):
    v = world_to_camera_view(sc, cam, Vector(p)); return v.x * RX, (1 - v.y) * RY

def bbox(ob):
    vs = ob.data.vertices; pts = [px(ob.matrix_world @ vs[i].co) for i in range(0, len(vs), 7)]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

sc.frame_set(0)
tipx, tipy = px(TIP); sx, sy = px((0, 0, ZL)); jx, jy = px((0, 0, ZL + 0.020)); rimx, rimy = px((0, 0, 0.1486))
fb = bbox(O['erlen'])
cl = lambda v, hi: int(max(0, min(hi, round(v))))
REG = {
    'tip': (cl(tipx - 60, RX), cl(tipy - 60, RY), cl(tipx + 70, RX), cl(tipy + 80, RY)),
    'fall': (cl(tipx - 32, RX), cl(tipy - 10, RY), cl(tipx + 32, RX), cl(sy + 24, RY)),
    'top': (cl(tipx - 70, RX), 0, RX, cl(tipy + 90, RY)),
    'liq': (cl(fb[0] - 14, RX), cl(jy - 20, RY), cl(fb[2] + 14, RX), cl(fb[3] + 30, RY)),
}
PLAN = dict(RX=RX, RY=RY, FPS=FPS, F_DETACH=F_DETACH, F_IMPACT=F_IMPACT, F_LAST=F_LAST, regions=REG,
            tip=(tipx, tipy), surface=(sx, sy), rim=(rimx, rimy), flask_bbox=fb, floor_y=px((0, 0, 0))[1],
            floor_front_y=px((0, -0.0436, 0))[1])
SCHED = {'tip': range(0, F_IMPACT), 'fall': range(F_DETACH, F_IMPACT + 1), 'top': range(58, 101), 'liq': range(F_IMPACT, F_LAST + 1)}

def render(path, box=None, spp=SPP_REG, blur=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if box:
        x0, y0, x1, y1 = box
        r.use_border = True; r.use_crop_to_border = False
        r.border_min_x, r.border_max_x = x0 / RX, x1 / RX
        r.border_min_y, r.border_max_y = 1 - y1 / RY, 1 - y0 / RY
    else:
        r.use_border = False
    r.use_motion_blur = blur; r.motion_blur_shutter = 0.5
    cy.samples = spp; r.filepath = path
    bpy.ops.render.render(write_still=True)

FLASKY = ('erlen', 'sivi', 'cizgi', 'ara', 'sayi', 'pipet', 'asili_damla', 'dusen_damla', 'kab', 'kb', 'jet_damla')
r.use_persistent_data = True

def run(jobs):
    t_all = time.time()
    for f, name in jobs:
        path = f'{OUTDIR}/{name}/{f:04d}.png'
        if os.path.exists(path): continue
        t0 = time.time(); pose(f)
        blur = (name == 'fall' and F_DETACH < f < F_IMPACT) or (name == 'top' and 58 < f < 100)
        render(path, REG[name], SPP_REG, blur)
        print(f'KARE {name} {f} {time.time() - t0:.1f}s', flush=True)
    print(f'BITTI {time.time() - t_all:.0f}s', flush=True)

mode = sys.argv[1] if len(sys.argv) > 1 else 'plan'
os.makedirs(OUTDIR, exist_ok=True)
json.dump(PLAN, open(f'{OUTDIR}/plan.json', 'w'), indent=1)
print('PLAN', json.dumps(REG), 'tip', (round(tipx), round(tipy)), 'yuzey', round(sy), 'agiz', round(rimy), 'erlen', [round(v) for v in fb], flush=True)
if mode == 'test':
    run([(int(a.split(':')[0]), a.split(':')[1]) for a in sys.argv[2:]])
elif mode == 'all':
    if not os.path.exists(f'{OUTDIR}/plate.png'):
        t0 = time.time(); pose(0); render(f'{OUTDIR}/plate.png', None, SPP_PLATE); print(f'PLAKA {time.time() - t0:.0f}s', flush=True)
    if not os.path.exists(f'{OUTDIR}/empty.png'):
        hid = [o for o in sc.objects if o.name.startswith(FLASKY) and not o.hide_render]
        for o in hid: o.hide_render = True
        render(f'{OUTDIR}/empty.png', None, 64)
        for o in hid: o.hide_render = False
        print('BOS PLAKA', flush=True)
    jobs = [(f, n) for n in ('tip', 'fall', 'top', 'liq') for f in SCHED[n]]
    run(jobs)
