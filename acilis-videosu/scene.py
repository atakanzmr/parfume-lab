"""Parfüm Lab açılışı · 3D sahne (Blender/Cycles).
Erlen + amber sıvı + cam pipet + damla, koyu parlak zemin, ürün fotoğrafı ışığı.
Ortam değişkenleri: RX, RY, SPP, OUT, DROP_Z (düşen damlanın yüksekliği, m)."""
import bpy, bmesh, math, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
from mathutils import Vector

RX = int(os.environ.get('RX', 360)); RY = int(os.environ.get('RY', 780))
SPP = int(os.environ.get('SPP', 96)); OUT = os.environ.get('OUT', os.path.join(HERE, 'test.png'))
DROP_Z = float(os.environ.get('DROP_Z', 0.178))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---------------- yardımcılar ----------------
def V2(x, y): return Vector((x, y))

def isect(p1, d1, p2, d2):
    p1, d1, p2, d2 = V2(*p1), V2(*d1), V2(*p2), V2(*d2)
    den = d1.x * d2.y - d1.y * d2.x
    s = ((p2.x - p1.x) * d2.y - (p2.y - p1.y) * d2.x) / den
    q = p1 + d1 * s
    return (q.x, q.y)

def fillet(poly, radii, seg=12, maxlen=0.0025):
    """Köşeleri yay ile yuvarlatılmış yoğun profil; düz kısımlar da bölünür."""
    P = [V2(*p) for p in poly]
    pts = [P[0].copy()]
    for i in range(1, len(P) - 1):
        r = radii.get(i, 0)
        a, b, c = P[i - 1], P[i], P[i + 1]
        d1 = (b - a).normalized(); d2 = (c - b).normalized()
        th = math.acos(max(-1.0, min(1.0, d1.dot(d2))))
        if r <= 0 or th < 1e-4:
            pts.append(b.copy()); continue
        L = r * math.tan(th / 2)
        A = b - d1 * L; B = b + d2 * L
        cr = d1.x * d2.y - d1.y * d2.x
        n = V2(-d1.y, d1.x) if cr > 0 else V2(d1.y, -d1.x)
        C = A + n * r
        a0 = math.atan2(A.y - C.y, A.x - C.x); a1 = math.atan2(B.y - C.y, B.x - C.x)
        da = a1 - a0
        while da > math.pi: da -= 2 * math.pi
        while da < -math.pi: da += 2 * math.pi
        k_n = max(3, int(seg * th / (math.pi / 2)) + 2)
        for k in range(k_n + 1):
            t = a0 + da * k / k_n
            pts.append(V2(C.x + r * math.cos(t), C.y + r * math.sin(t)))
    pts.append(P[-1].copy())
    out = [pts[0]]
    for q in pts[1:]:
        p0 = out[-1]; n = int((q - p0).length / maxlen)
        for k in range(1, n + 1):
            out.append(p0.lerp(q, k / (n + 1)))
        if (q - out[-1]).length > 1e-7:
            out.append(q)
    return [(v.x, v.y) for v in out]

def revolve(name, prof, steps=128, closed_profile=True):
    """(r, z) profilini Z ekseni etrafında döndürür; eksendeki noktalar birleşir."""
    bm = bmesh.new()
    verts = [bm.verts.new((r, 0.0, z)) for r, z in prof]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    if closed_profile:
        edges.append(bm.edges.new((verts[-1], verts[0])))
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(0, 0, 1),
                   angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    # eksen üzerindeki dejenere yüzleri temizle
    bad = [f for f in bm.faces if f.calc_area() < 1e-14]
    if bad: bmesh.ops.delete(bm, geom=bad, context='FACES')
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    return ob

def node_mat(name):
    m = bpy.data.materials.new(name)
    try: m.use_nodes = True
    except Exception: pass
    return m, m.node_tree.nodes, m.node_tree.links

def glass_mat(name, ior=1.47, rough=0.0, tint=(1, 1, 1)):
    m, N, L = node_mat(name)
    b = N.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*tint, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['IOR'].default_value = ior
    b.inputs['Transmission Weight'].default_value = 1.0
    return m

def liquid_mat(name, color, density, ior=1.36):
    m = glass_mat(name, ior=ior)
    N, L = m.node_tree.nodes, m.node_tree.links
    va = N.new('ShaderNodeVolumeAbsorption')
    va.inputs['Color'].default_value = (*color, 1); va.inputs['Density'].default_value = density
    L.new(va.outputs[0], N['Material Output'].inputs['Volume'])
    return m

def no_shadow(ob):
    ob.visible_shadow = False

# ---------------- erlen ----------------
O0 = (0.0, 0.0020); K = (0.0436, 0.0000); S = (0.0170, 0.1130)
cone_d = (S[0] - K[0], S[1] - K[1]); cl = math.hypot(*cone_d); cone_u = (cone_d[0] / cl, cone_d[1] / cl)
nrm = (-cone_u[1], cone_u[0])                              # sola dik: eksene ve aşağıya doğru
if nrm[0] > 0: nrm = (-nrm[0], -nrm[1])
TW = 0.0016
Kc_in = (K[0] + nrm[0] * TW, K[1] + nrm[1] * TW)           # iç koni çizgisi üzerinde bir nokta
bot_d = (K[0] - O0[0], K[1] - O0[1])
I0 = (0.0, 0.0052)
Kp = isect(I0, bot_d, Kc_in, cone_d)
Sp = isect((0.0153, 0.0), (0, 1), Kc_in, cone_d)
outer_inner = [O0, K, S, (0.0170, 0.1400), (0.0181, 0.1414), (0.0181, 0.1466), (0.0171, 0.1486),
               (0.0155, 0.1486), (0.0153, 0.1474), Sp, Kp, I0]
radii = {1: 0.0060, 2: 0.0085, 3: 0.0012, 4: 0.0010, 5: 0.0012, 6: 0.0008, 7: 0.0005, 8: 0.0003, 9: 0.0068, 10: 0.0045}
flask_prof = fillet(outer_inner, radii, seg=14)
flask = revolve('erlen', flask_prof, steps=160)
M_GLASS = glass_mat('cam', ior=1.47)
flask.data.materials.append(M_GLASS); no_shadow(flask)

def r_inner(z):  # iç koni yarıçapı
    s = (z - Kc_in[1]) / cone_d[1]
    return Kc_in[0] + s * cone_d[0]

def r_outer(z):
    s = (z - K[1]) / cone_d[1]
    return K[0] + s * cone_d[0]

# ---------------- sıvı ----------------
ZL = 0.050
def liquid_profile(level, gap=0.00006, ring=0.0004):
    inner = fillet([I0, Kp, (r_inner(level + 0.004), level + 0.004)], {1: 0.0045}, seg=14, maxlen=0.002)
    pts = []
    for (r, z) in inner:
        if z > level + 0.0010: break
        pts.append((max(0.0, r - gap * 1.4), z + gap))
    rw = r_inner(level + 0.0012) - gap * 1.4
    for k in range(0, 9):                                   # menisküs
        u = k / 8
        pts.append((rw - 0.0032 * u, level + 0.0012 * (1 - u) ** 2.6))
    r0 = rw - 0.0032
    r = r0
    while r > 0.0052:
        r -= ring; pts.append((r, level))
    while r > 0.00012:
        r -= 0.00012; pts.append((max(r, 0.0), level))
    if pts[-1][0] > 0: pts.append((0.0, level))
    return pts

liquid = revolve('sivi', liquid_profile(ZL), steps=160)
M_LIQ = liquid_mat('sivi', (0.95, 0.72, 0.20), 30.0)
def add_glow(m, center, radius, e0, e1, color):
    """Sıvının içinden gelen altın parıltı: dipte güçlü, kenara doğru söner (hacim ışıması)."""
    N, L = m.node_tree.nodes, m.node_tree.links
    out = N['Material Output']; va = [n for n in N if n.type == 'VOLUME_ABSORPTION'][0]
    tc = N.new('ShaderNodeTexCoord'); dist = N.new('ShaderNodeVectorMath'); dist.operation = 'DISTANCE'
    dist.inputs[1].default_value = center
    mr = N.new('ShaderNodeMapRange'); mr.inputs['From Min'].default_value = 0.0; mr.inputs['From Max'].default_value = radius
    mr.inputs['To Min'].default_value = 1.0; mr.inputs['To Max'].default_value = 0.0
    pw = N.new('ShaderNodeMath'); pw.operation = 'POWER'; pw.inputs[1].default_value = 1.6
    mu = N.new('ShaderNodeMath'); mu.operation = 'MULTIPLY_ADD'; mu.inputs[1].default_value = e0; mu.inputs[2].default_value = e1
    em = N.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (*color, 1)
    ad = N.new('ShaderNodeAddShader')
    L.new(tc.outputs['Object'], dist.inputs[0]); L.new(dist.outputs['Value'], mr.inputs['Value'])
    L.new(mr.outputs['Result'], pw.inputs[0]); L.new(pw.outputs[0], mu.inputs[0]); L.new(mu.outputs[0], em.inputs['Strength'])
    L.new(va.outputs[0], ad.inputs[0]); L.new(em.outputs[0], ad.inputs[1]); L.new(ad.outputs[0], out.inputs['Volume'])
    return m
GLOW = [float(x) for x in os.environ.get('GLOW', '12,2.5').split(',')]
GLOWC = tuple(float(x) for x in os.environ.get('GLOWC', '1.0,0.55,0.12').split(','))
add_glow(M_LIQ, (0.0, 0.0, 0.008), 0.058, GLOW[0], GLOW[1], GLOWC)
liquid.data.materials.append(M_LIQ); no_shadow(liquid)

# ---------------- ölçek çizgileri ve rakamlar ----------------
M_PRINT, Np, Lp = node_mat('baski')
bp = Np.get('Principled BSDF'); bp.inputs['Base Color'].default_value = (0.92, 0.92, 0.9, 1)
bp.inputs['Roughness'].default_value = 0.6
bp.inputs['Emission Color'].default_value = (1, 1, 1, 1); bp.inputs['Emission Strength'].default_value = 0.22

def cone_strip(name, z, h, arc0, arc_len, off=0.00012, n=10):
    bm = bmesh.new(); rows = []
    for zz in (z, z + h):
        r = r_outer(zz) + off; row = []
        for k in range(n + 1):
            th = (arc0 + arc_len * k / n) / r
            row.append(bm.verts.new((r * math.cos(th), r * math.sin(th), zz)))
        rows.append(row)
    for k in range(n):
        bm.faces.new((rows[0][k], rows[0][k + 1], rows[1][k + 1], rows[1][k]))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); ob.data.materials.append(M_PRINT)
    return ob

def cone_text(name, body, z, arc0, size=0.0038, off=0.00012):
    """Yazıyı koninin dış yüzeyine sarar; arc0 = yazının başladığı yay konumu (θ·r)."""
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = size; cu.align_x = 'LEFT'; cu.align_y = 'CENTER'
    tmp = bpy.data.objects.new(name + '_t', cu); sc.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp); bpy.data.curves.remove(cu)
    for v in me.vertices:
        x, y = v.co.x, v.co.y
        zz = z + y; r = r_outer(zz) + off; th = (arc0 + x) / r
        v.co = (r * math.cos(th), r * math.sin(th), zz)
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob); ob.data.materials.append(M_PRINT)
    return ob

FRONT = -math.pi / 2                                   # kameraya bakan yüz
def arc_at(z, ang): return ang * (r_outer(z) + 0.00012)

for i, (z, lab) in enumerate([(0.028, '50'), (0.048, '100'), (0.068, '150'), (0.088, '200')]):
    a0 = arc_at(z, FRONT - 0.30)
    cone_strip(f'cizgi{i}', z, 0.00055, a0, 0.0062)
    cone_text(f'sayi{i}', lab, z + 0.00028, a0 + 0.0075)
    zz = z + 0.010
    if zz < 0.098:
        cone_strip(f'ara{i}', zz, 0.00045, arc_at(zz, FRONT - 0.30), 0.0036)

# ---------------- pipet ----------------
pip_out = [(0.00105, 0.0), (0.00125, 0.045), (0.00140, 0.060), (0.0041, 0.094), (0.0041, 0.33),
           (0.0032, 0.33), (0.0032, 0.095), (0.00078, 0.061), (0.00066, 0.045), (0.00056, 0.0)]
pip_prof = fillet(pip_out, {3: 0.010, 6: 0.008, 2: 0.010, 7: 0.010, 9: 0.00012, 1: 0, 4: 0.0003, 5: 0.0003}, seg=10, maxlen=0.003)
pip = revolve('pipet', pip_prof, steps=48)
pip.data.materials.append(M_GLASS); no_shadow(pip)
TIP = Vector((0.0, 0.0, 0.212)); ANG = math.radians(32)
pip.rotation_euler = (0, ANG, 0); pip.location = TIP

M_DROP = liquid_mat('damla', (0.92, 0.60, 0.10), 120.0)
def add_const_glow(m, strength, color):
    N, L = m.node_tree.nodes, m.node_tree.links
    va = [n for n in N if n.type == 'VOLUME_ABSORPTION'][0]
    em = N.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (*color, 1); em.inputs['Strength'].default_value = strength
    ad = N.new('ShaderNodeAddShader'); L.new(va.outputs[0], ad.inputs[0]); L.new(em.outputs[0], ad.inputs[1])
    L.new(ad.outputs[0], N['Material Output'].inputs['Volume'])
add_const_glow(M_DROP, float(os.environ.get('DGLOW', 80)), (1.0, 0.56, 0.14))
pl = revolve('pipet_sivi', [(0.0, 0.0002), (0.00052, 0.0002), (0.00054, 0.028), (0.00038, 0.0292), (0.0, 0.0296)], steps=24)
pl.data.materials.append(M_DROP); no_shadow(pl); pl.rotation_euler = (0, ANG, 0); pl.location = TIP

def sphere(name, r, loc, scale=(1, 1, 1), mat=None, seg=48):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    ob.location = loc; ob.scale = scale
    if mat: ob.data.materials.append(mat)
    no_shadow(ob); return ob

hang = sphere('asili_damla', 0.0017, TIP + Vector((0, 0, -0.0012)), (1, 1, 1.12), M_DROP)
fall = sphere('dusen_damla', 0.0021, Vector((0.0, 0.0, DROP_Z)), (1, 1, 1.14), M_DROP)

# kabarcıklar
M_BUB = glass_mat('kabarcik', ior=1 / 1.36)
import random
random.seed(7)
for i in range(26):
    z = random.uniform(0.008, ZL - 0.003) if i % 3 else random.uniform(ZL - 0.008, ZL - 0.0025); rr = r_inner(z) - 0.0018 - random.uniform(0, 0.016)
    th = random.uniform(-math.pi * 0.95, -math.pi * 0.05)
    sphere(f'kab{i}', random.uniform(0.0004, 0.0014), Vector((rr * math.cos(th), rr * math.sin(th), z)), mat=M_BUB, seg=16)

# zemindeki damlacıklar
M_SPILL = glass_mat('zemin_damla', ior=1.36)
random.seed(11)
for i in range(18):
    ang = random.uniform(0, 2 * math.pi); d = random.uniform(0.07, 0.30)
    x, y = d * math.cos(ang), d * math.sin(ang) * (1.6 if math.sin(ang) > 0 else 0.9)
    rr = random.uniform(0.0006, 0.0016)
    sphere(f'zd{i}', rr, Vector((x, y, rr * 0.35)), (1, 1, 0.45), M_SPILL, seg=16)
# ---------------- zemin ----------------
bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3.0)
me = bpy.data.meshes.new('zemin'); bm.to_mesh(me); bm.free()
floor = bpy.data.objects.new('zemin', me); sc.collection.objects.link(floor)
M_FL, Nf, Lf = node_mat('zemin')
bf = Nf.get('Principled BSDF')
bf.inputs['Base Color'].default_value = (0.0025, 0.0025, 0.0028, 1)
bf.inputs['Specular IOR Level'].default_value = 0.55
noise = Nf.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 18.0; noise.inputs['Detail'].default_value = 6.0
mr = Nf.new('ShaderNodeMapRange'); mr.inputs['To Min'].default_value = 0.05; mr.inputs['To Max'].default_value = 0.13
Lf.new(noise.outputs['Fac'], mr.inputs['Value']); Lf.new(mr.outputs['Result'], bf.inputs['Roughness'])
bump = Nf.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.02
n2 = Nf.new('ShaderNodeTexNoise'); n2.inputs['Scale'].default_value = 140.0
Lf.new(n2.outputs['Fac'], bump.inputs['Height']); Lf.new(bump.outputs['Normal'], bf.inputs['Normal'])
floor.data.materials.append(M_FL)

# ---------------- ışıklar ----------------
def area(name, size, loc, target, power, color=(1, 1, 1), shape='RECTANGLE', size_y=None, spread=None):
    ld = bpy.data.lights.new(name, 'AREA'); ld.shape = shape; ld.size = size
    if size_y is not None: ld.size_y = size_y
    ld.energy = power; ld.color = color
    if spread is not None: ld.spread = spread
    ob = bpy.data.objects.new(name, ld); sc.collection.objects.link(ob); ob.location = loc
    d = Vector(target) - Vector(loc); ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    ob.visible_camera = False
    return ob

SPREAD = math.radians(55)
L1 = area('sol_serit', 0.045, (-0.30, 0.32, 0.24), (0, 0, 0.11), 13.0, (1.0, 0.97, 0.93), size_y=0.80, spread=SPREAD)
L2 = area('sag_serit', 0.045, (0.30, 0.32, 0.24), (0, 0, 0.11), 13.0, (1.0, 0.97, 0.93), size_y=0.80, spread=SPREAD)
L3 = area('ust', 0.30, (0.0, 0.05, 0.62), (0, 0, 0.12), 4.0, (1.0, 0.96, 0.9), size_y=0.30, spread=math.radians(40))
# bu ışıklar zemine vurmasın: zemin yalnızca sıvının altın ışığını ve camın yansımasını alsın
ZC = bpy.data.collections.new('zemin_haric'); ZC.objects.link(floor)
for co in ZC.collection_objects: co.light_linking.link_state = 'EXCLUDE'
for _L in (L1, L2, L3): _L.light_linking.receiver_collection = ZC

def glow_card(name, w, h, loc, strength, color):
    """Yalnızca camın içinden görünen, ortası parlak yumuşak ışık kartı."""
    bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    ob.scale = (w, h, 1); ob.rotation_euler = (math.pi / 2, 0, 0); ob.location = loc
    m, N, L = node_mat(name)
    for n in list(N): N.remove(n)
    out = N.new('ShaderNodeOutputMaterial'); em = N.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (*color, 1)
    tc = N.new('ShaderNodeTexCoord'); gr = N.new('ShaderNodeTexGradient'); gr.gradient_type = 'SPHERICAL'
    mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (2.0, 2.0, 2.0)
    cr = N.new('ShaderNodeMath'); cr.operation = 'POWER'; cr.inputs[1].default_value = 1.0
    mul = N.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = strength
    L.new(tc.outputs['Object'], mp.inputs['Vector']); L.new(mp.outputs['Vector'], gr.inputs['Vector'])
    L.new(gr.outputs['Fac'], cr.inputs[0]); L.new(cr.outputs[0], mul.inputs[0]); L.new(mul.outputs[0], em.inputs['Strength'])
    L.new(em.outputs[0], out.inputs['Surface']); ob.data.materials.append(m)
    ob.visible_camera = False; ob.visible_glossy = False; ob.visible_diffuse = False; ob.visible_shadow = False
    return ob

glow_card('damla_karti', 0.05, 0.085, (0.012, 0.09, 0.2175), 1.6, (1.0, 0.78, 0.45))  # damlayı arkadan aydınlatır

# ---------------- dünya, kamera ----------------
w = bpy.data.worlds.new('dunya'); sc.world = w
try: w.use_nodes = True
except Exception: pass
w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.0

cam_d = bpy.data.cameras.new('kamera'); cam_d.lens = 70; cam_d.sensor_width = 36; cam_d.sensor_fit = 'AUTO'
cam = bpy.data.objects.new('kamera', cam_d); sc.collection.objects.link(cam); sc.camera = cam
cam.location = (0.0, -0.74, 0.16)
LOOK = Vector((0.0, 0.0, 0.076))
cam.rotation_euler = (LOOK - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam_d.dof.use_dof = True; cam_d.dof.focus_distance = (Vector((0, 0, 0.075)) - cam.location).length; cam_d.dof.aperture_fstop = 5.6

for _n in filter(None, os.environ.get('DISABLE', '').split(',')):
    if _n in bpy.data.objects: bpy.data.objects[_n].hide_render = True
# ---------------- render ----------------
r = sc.render; r.engine = 'CYCLES'; r.resolution_x = RX; r.resolution_y = RY; r.resolution_percentage = 100
r.threads_mode = 'FIXED'; r.threads = 2
cy = sc.cycles; cy.device = 'CPU'; cy.samples = SPP; cy.use_adaptive_sampling = True; cy.adaptive_threshold = 0.012
cy.use_denoising = True
try: cy.denoiser = 'OPENIMAGEDENOISE'
except Exception: pass
cy.max_bounces = 32; cy.transmission_bounces = 32; cy.glossy_bounces = 8; cy.diffuse_bounces = 2
cy.transparent_max_bounces = 8; cy.volume_bounces = 0
cy.caustics_reflective = False; cy.caustics_refractive = False; cy.blur_glossy = 0.4
cy.sample_clamp_indirect = 6.0
vs = sc.view_settings
for vt, look in (('AgX', 'AgX - Medium High Contrast'), ('AgX', 'Medium High Contrast'), ('AgX', 'None')):
    try:
        vs.view_transform = vt; vs.look = look; break
    except Exception: continue
vs.exposure = float(os.environ.get('EXPO', 0.0))
r.image_settings.file_format = 'PNG'; r.filepath = OUT
if os.environ.get('BORDER'):
    bx0, bx1, by0, by1 = (float(v) for v in os.environ['BORDER'].split(','))
    r.use_border = True; r.use_crop_to_border = False
    r.border_min_x, r.border_max_x, r.border_min_y, r.border_max_y = bx0, bx1, by0, by1

if not os.environ.get('NO_RENDER'):
    t0 = time.time(); bpy.ops.render.render(write_still=True)
    print('RENDER', round(time.time() - t0, 1), 's', OUT, vs.view_transform, vs.look)
