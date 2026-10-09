"""
AIU SMART CAMPUS — TEST 01: university corridor + access-control door (environment & hardware only)
Blender 4.2-4.5 (Cycles, Metal on Apple silicon).  NOT YET RUN BY THE AUTHOR — first run may need fixes.

Run (GUI):  Scripting workspace > Open this file > Run Script.  It builds the scene, saves the .blend and stops.
Run (CLI):  /Applications/Blender.app/Contents/MacOS/Blender -b -P aiu_test01_corridor_door.py -- --mode preview
Modes:  build (default) | still [--frame N] | preview | final [--frames A-B]
Other:  --out <folder>   (default ~/Desktop/AIU_SMART_CAMPUS_FINAL/blender/renders)

CONCEPTUAL: the door/lock hardware is not yet connected in the real project.  The lecturer is NOT modelled (live action pending).
Timeline (30 fps, 390 frames = 13 s):  A 1-150 tracking approach | B 151-240 reader macro | C 241-300 lock section macro | D 301-390 door opens
Logic frames:  verifying 170-222 | GRANT 225 (LED amber->green) | strike keeper retracts 228-240 | door opens 250-340
"""
import bpy, math, sys, os, json, random, traceback
def P(*a): print(*a, flush=True)
from mathutils import Vector

# ------------------------------------------------------------------ args
argv = sys.argv; A = argv[argv.index('--') + 1:] if '--' in argv else []
def arg(n, d=None): return A[A.index(n) + 1] if n in A else d
MODE = arg('--mode', 'build'); STILL = int(arg('--frame', 120))
OUT = os.path.expanduser(arg('--out', '~/Desktop/AIU_SMART_CAMPUS_FINAL/blender/renders'))
HERE = os.path.expanduser('~/Desktop/AIU_SMART_CAMPUS_FINAL/blender')
os.makedirs(OUT, exist_ok=True); os.makedirs(HERE, exist_ok=True)
random.seed(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = 30; scene.frame_start = 1; scene.frame_end = 390

# ------------------------------------------------------------------ helpers
def setin(node, names, val):
    if isinstance(names, str): names = [names]
    for n in names:
        if n in node.inputs:
            try: node.inputs[n].default_value = val; return True
            except Exception: pass
    return False

def new_mat(name, base=(0.8, 0.8, 0.8), rough=0.5, metal=0.0, **extra):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    setin(b, 'Base Color', (*base, 1)); setin(b, 'Roughness', rough); setin(b, 'Metallic', metal)
    for k, v in extra.items(): setin(b, k.replace('_', ' '), v)
    return m

def nodes_of(m): return m.node_tree.nodes, m.node_tree.links
def bsdf_of(m): return m.node_tree.nodes['Principled BSDF']

def procedural(m, kind):
    n, l = nodes_of(m); b = bsdf_of(m)
    tc = n.new('ShaderNodeTexCoord'); mp = n.new('ShaderNodeMapping')
    l.new(tc.outputs['Object'], mp.inputs['Vector'])
    if kind == 'tile':           # polished porcelain floor 0.6 m tiles, grout lines
        br = n.new('ShaderNodeTexBrick'); br.offset = 0.0
        for k, v in (('Color1', (0.64, 0.62, 0.58, 1)), ('Color2', (0.60, 0.58, 0.54, 1)), ('Mortar', (0.18, 0.18, 0.17, 1)),
                     ('Scale', 1.0), ('Mortar Size', 0.008), ('Brick Width', 0.6), ('Row Height', 0.6), ('Mortar Smooth', 0.1)):
            if k in br.inputs: br.inputs[k].default_value = v
        l.new(mp.outputs['Vector'], br.inputs['Vector']); l.new(br.outputs['Color'], b.inputs['Base Color'])
        nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 3.0
        l.new(mp.outputs['Vector'], nz.inputs['Vector'])
        cr = n.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color = (0.08, 0.08, 0.08, 1); cr.color_ramp.elements[1].color = (0.32, 0.32, 0.32, 1)
        l.new(nz.outputs['Fac'], cr.inputs['Fac']); l.new(cr.outputs['Color'], b.inputs['Roughness'])
        bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.4; bp.inputs['Distance'].default_value = 0.002
        l.new(br.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal'])
    elif kind == 'plaster':
        nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 250; nz.inputs['Detail'].default_value = 6
        l.new(mp.outputs['Vector'], nz.inputs['Vector'])
        bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.08; bp.inputs['Distance'].default_value = 0.0005
        l.new(nz.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal'])
        # --- subtle wear: low-frequency stains + darker, scuffed band toward the floor (walls are H tall, origin at mid-height)
        base = tuple(b.inputs['Base Color'].default_value)[:3]
        st = n.new('ShaderNodeTexNoise'); st.inputs['Scale'].default_value = 0.7; st.inputs['Detail'].default_value = 3
        l.new(mp.outputs['Vector'], st.inputs['Vector'])
        sr = n.new('ShaderNodeValToRGB'); sr.color_ramp.elements[0].color = (0.90, 0.90, 0.90, 1); sr.color_ramp.elements[1].color = (1, 1, 1, 1)
        l.new(st.outputs['Fac'], sr.inputs['Fac'])
        sp = n.new('ShaderNodeSeparateXYZ'); l.new(tc.outputs['Object'], sp.inputs['Vector'])
        gr = n.new('ShaderNodeMapRange'); gr.inputs['From Min'].default_value = -1.55; gr.inputs['From Max'].default_value = -0.7
        gr.inputs['To Min'].default_value = 0.62; gr.inputs['To Max'].default_value = 1.0
        l.new(sp.outputs['Z'], gr.inputs['Value'])
        scuff = n.new('ShaderNodeTexNoise'); scuff.inputs['Scale'].default_value = 14; scuff.inputs['Detail'].default_value = 8
        l.new(mp.outputs['Vector'], scuff.inputs['Vector'])
        sc2 = n.new('ShaderNodeMapRange'); sc2.inputs['From Min'].default_value = 0.35; sc2.inputs['From Max'].default_value = 0.7
        sc2.inputs['To Min'].default_value = 0.75; sc2.inputs['To Max'].default_value = 1.0; l.new(scuff.outputs['Fac'], sc2.inputs['Value'])
        def mixc():   # colour Mix node: use socket INDICES (6=A colour, 7=B colour, output 2=colour) — names are ambiguous
            mx = n.new('ShaderNodeMix'); mx.data_type = 'RGBA'; mx.blend_type = 'MULTIPLY'; mx.inputs[0].default_value = 1.0; return mx
        m1 = mixc(); m1.inputs[6].default_value = (*base, 1); l.new(sr.outputs['Color'], m1.inputs[7])
        m2 = mixc(); l.new(m1.outputs[2], m2.inputs[6]); l.new(gr.outputs['Result'], m2.inputs[7])
        m3 = mixc(); l.new(m2.outputs[2], m3.inputs[6]); l.new(sc2.outputs['Result'], m3.inputs[7])
        l.new(m3.outputs[2], b.inputs['Base Color'])
    elif kind == 'ceiling':      # 0.6 m grid tiles with dark T-bar lines
        br = n.new('ShaderNodeTexBrick'); br.offset = 0.0
        for k, v in (('Color1', (0.88, 0.88, 0.86, 1)), ('Color2', (0.84, 0.84, 0.82, 1)), ('Mortar', (0.55, 0.55, 0.56, 1)),
                     ('Scale', 1.0), ('Mortar Size', 0.012), ('Brick Width', 0.6), ('Row Height', 0.6)):
            if k in br.inputs: br.inputs[k].default_value = v
        l.new(mp.outputs['Vector'], br.inputs['Vector']); l.new(br.outputs['Color'], b.inputs['Base Color'])
        nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 90; nz.inputs['Detail'].default_value = 8
        l.new(mp.outputs['Vector'], nz.inputs['Vector'])
        bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.25; bp.inputs['Distance'].default_value = 0.001
        l.new(nz.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal'])
    elif kind in ('wood', 'doorwood'):
        # Fine straight veneer grain: bands ~7 mm apart, stretched ~8x along the grain direction so lines stay nearly straight.
        # 'doorwood' = grain runs along local Z (door height) in the coordinates of the hinge object (set later), so all leaf pieces match.
        # 'wood'     = grain runs along local Y (long axis of bench / desk tops).
        door = (kind == 'doorwood')
        mp.inputs['Scale'].default_value = (1.0, 1.0, 0.12) if door else (1.0, 0.12, 1.0)
        wv = n.new('ShaderNodeTexWave'); wv.wave_type = 'BANDS'; wv.bands_direction = 'Y' if door else 'X'
        wv.inputs['Scale'].default_value = 45; wv.inputs['Distortion'].default_value = 0.9; wv.inputs['Detail'].default_value = 2
        wv.inputs['Detail Scale'].default_value = 1.5; wv.inputs['Detail Roughness'].default_value = 0.6
        l.new(mp.outputs['Vector'], wv.inputs['Vector'])
        pl = n.new('ShaderNodeTexNoise'); pl.inputs['Scale'].default_value = 2.5; pl.inputs['Detail'].default_value = 2   # slow board-to-board tone drift
        l.new(mp.outputs['Vector'], pl.inputs['Vector'])
        tone = n.new('ShaderNodeMath'); tone.operation = 'MULTIPLY_ADD'; tone.inputs[1].default_value = 0.22; tone.inputs[2].default_value = 0.0
        l.new(wv.outputs['Fac'], tone.inputs[0])
        mix = n.new('ShaderNodeMath'); mix.operation = 'ADD'; l.new(tone.outputs[0], mix.inputs[0])
        pm = n.new('ShaderNodeMath'); pm.operation = 'MULTIPLY'; pm.inputs[1].default_value = 0.30; l.new(pl.outputs['Fac'], pm.inputs[0]); l.new(pm.outputs[0], mix.inputs[1])
        cr = n.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color = (0.30, 0.17, 0.085, 1); cr.color_ramp.elements[1].color = (0.45, 0.285, 0.15, 1)
        cr.color_ramp.elements[1].position = 0.55            # grain+drift signal spans ~0..0.55
        l.new(mix.outputs[0], cr.inputs['Fac']); l.new(cr.outputs['Color'], b.inputs['Base Color'])
        bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.08; bp.inputs['Distance'].default_value = 0.0004
        l.new(wv.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal'])
    elif kind == 'brushed':
        nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 600; nz.inputs['Detail'].default_value = 3
        mp.inputs['Scale'].default_value = (1, 1, 0.02)
        l.new(mp.outputs['Vector'], nz.inputs['Vector'])
        bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.05; bp.inputs['Distance'].default_value = 0.0003
        l.new(nz.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m

def emission_mat(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True; n, l = nodes_of(m)
    for x in list(n): n.remove(x)
    e = n.new('ShaderNodeEmission'); o = n.new('ShaderNodeOutputMaterial')
    e.inputs['Color'].default_value = (*color, 1); e.inputs['Strength'].default_value = strength
    l.new(e.outputs['Emission'], o.inputs['Surface']); return m, e

M = {}
M['tile'] = procedural(new_mat('Porcelain', (0.6, 0.58, 0.54), 0.15), 'tile')
M['plaster'] = procedural(new_mat('Plaster', (0.83, 0.80, 0.74), 0.85), 'plaster')
M['navy'] = procedural(new_mat('NavyPaint', (0.025, 0.03, 0.16), 0.38, coat_weight=0.2), 'plaster')
M['ceiling'] = procedural(new_mat('CeilingTile', (0.88, 0.88, 0.86), 0.9), 'ceiling')
M['wood'] = procedural(new_mat('BenchWood', (0.4, 0.22, 0.11), 0.5, coat_weight=0.1), 'wood')
M['doorwood'] = procedural(new_mat('DoorVeneer', (0.4, 0.22, 0.11), 0.45, coat_weight=0.12), 'doorwood')
M['frame'] = new_mat('FrameSteel', (0.05, 0.055, 0.075), 0.35, 0.6)
M['steel'] = procedural(new_mat('BrushedSteel', (0.72, 0.73, 0.75), 0.32, 1.0), 'brushed')
M['darksteel'] = new_mat('DarkSteel', (0.12, 0.12, 0.13), 0.4, 1.0)
M['black'] = new_mat('BlackPlastic', (0.015, 0.015, 0.018), 0.35)
M['blackglass'] = new_mat('BlackGlass', (0.004, 0.004, 0.006), 0.04, 0.0, coat_weight=1.0)
M['white'] = new_mat('WhiteABS', (0.88, 0.89, 0.9), 0.38)
M['glass'] = new_mat('Glass', (0.9, 0.95, 1.0), 0.02, 0.0, transmission_weight=1.0, transmission=1.0, ior=1.45)
M['ground'] = new_mat('Pavers', (0.62, 0.55, 0.44), 0.8)
M['room_floor'] = new_mat('RoomFloor', (0.35, 0.24, 0.16), 0.5)
M['room_wall'] = new_mat('RoomWall', (0.85, 0.85, 0.83), 0.8)
M['light'], _ = emission_mat('LED_Panel', (1.0, 0.97, 0.92), 5.0)        # was 9.0: panels clipped to flat white
M['daylight'], _ = emission_mat('Daylight', (0.85, 0.92, 1.0), 1.1)       # was 6.0: far-end opening was a blown white rectangle
M['warmroom'], _ = emission_mat('RoomWindow', (1.0, 0.93, 0.8), 5.0)
M['led'], LED = emission_mat('ReaderLED', (1.0, 0.55, 0.05), 6.0)       # animated
M['text'] = new_mat('SignText', (0.95, 0.95, 0.95), 0.5)

COL = scene.collection
def box(name, loc, size, mat=None, bevel=0.0, parent=None):
    sx, sy, sz = [s / 2 for s in size]
    v = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz), (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name); me.from_pydata(v, [], f); me.update()
    ob = bpy.data.objects.new(name, me); COL.objects.link(ob); ob.location = loc
    if mat: me.materials.append(mat)
    if bevel:
        bm = ob.modifiers.new('bevel', 'BEVEL'); bm.width = bevel; bm.segments = 2; bm.limit_method = 'ANGLE'
    if parent: ob.parent = parent
    return ob

def cyl(name, p0, p1, r, mat=None, verts=24, parent=None):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(p0 + p1) / 2)
    ob = bpy.context.active_object; ob.name = name
    ob.rotation_mode = 'QUATERNION'; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bpy.ops.object.shade_smooth()
    if mat: ob.data.materials.append(mat)
    if parent: ob.parent = parent
    return ob

def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None); COL.objects.link(e); e.location = loc
    if parent: e.parent = parent
    return e

def text(body, loc, size, mat, rot=(math.radians(90), 0, math.radians(-90))):
    bpy.ops.object.text_add(location=loc, rotation=rot)
    t = bpy.context.active_object; t.data.body = body; t.data.size = size; t.data.extrude = 0.0008
    t.data.align_x = 'CENTER'; t.data.align_y = 'CENTER'; t.data.materials.append(mat); return t

# ------------------------------------------------------------------ geometry: corridor shell
L, HW, H = 18.0, 1.4, 3.1
DOORS = [3.5, 9.0, 14.5]; HERO = 9.0
box('Floor', (0, L / 2, -0.05), (2 * HW + 0.2, L, 0.1), M['tile'])
box('Ceiling', (0, L / 2, H + 0.05), (2 * HW + 0.2, L, 0.1), M['ceiling'])
box('EndWall_Front', (0, -0.05, H / 2), (2 * HW + 0.2, 0.1, H), M['plaster'])
box('EndWall_Back', (0, L + 0.05, H / 2), (2 * HW + 0.2, 0.1, H), M['plaster'])
box('EndGlow', (0, L - 0.012, 1.15), (1.5, 0.004, 2.3), M['daylight'])
# the far end is a glazed stair/exit opening: frame + mullions so the bright area keeps architectural structure
for nm, loc, sz in (('EndFrame_L', (-0.78, L - 0.03, 1.15), (0.06, 0.05, 2.36)), ('EndFrame_R', (0.78, L - 0.03, 1.15), (0.06, 0.05, 2.36)),
                    ('EndFrame_T', (0, L - 0.03, 2.33), (1.62, 0.05, 0.06)), ('EndMullion_V', (0, L - 0.03, 1.15), (0.05, 0.05, 2.3)),
                    ('EndMullion_H', (0, L - 0.03, 1.4), (1.5, 0.05, 0.05)), ('EndSill', (0, L - 0.03, -0.0), (1.62, 0.05, 0.05))):
    box(nm, loc, sz, M['frame'], 0.002)
for k in range(6): box(f'LEDPanel{k}', (0, 1.5 + 3 * k, H - 0.012), (0.6, 1.2, 0.02), M['light'])
for k, y in enumerate((6.0, 12.0)):                       # corridor supply diffusers (continuity with the HVAC scene)
    box(f'Diffuser{k}', (0.7, y, H - 0.012), (0.6, 0.6, 0.02), M['white'], 0.003)
    for j in range(3): box(f'DiffSlat{k}{j}', (0.7, y, H - 0.025), (0.46 - 0.14 * j, 0.46 - 0.14 * j, 0.008), M['black'])

# right wall with door openings
segs = []; prev = 0.0
for d in DOORS: segs.append((prev, d - 0.5)); prev = d + 0.5
segs.append((prev, L))
for i, (a, b) in enumerate(segs):
    box(f'RWall{i}', (HW + 0.05, (a + b) / 2, H / 2), (0.1, b - a, H), M['plaster'])
    if b - a > 0.2:
        box(f'Wainscot{i}', (HW - 0.007, (a + b) / 2, 0.55 + 0.1), (0.014, b - a - 0.12, 1.0), M['navy'], 0.002)
        box(f'ChairRail{i}', (HW - 0.014, (a + b) / 2, 1.13), (0.03, b - a - 0.12, 0.03), M['steel'], 0.003)
        box(f'Skirt{i}', (HW - 0.01, (a + b) / 2, 0.05), (0.02, b - a - 0.12, 0.1), M['darksteel'])
for d in DOORS:
    box(f'Lintel{d}', (HW + 0.05, d, 2.6), (0.1, 1.0, 1.0), M['plaster'])
    box(f'FrameHead{d}', (HW - 0.0, d, 2.13), (0.13, 1.12, 0.06), M['frame'], 0.003)
    box(f'JambHinge{d}', (HW - 0.0, d + 0.53, 1.05), (0.13, 0.06, 2.1), M['frame'], 0.003)
    if d != HERO: box(f'JambLatch{d}', (HW - 0.0, d - 0.53, 1.05), (0.13, 0.06, 2.1), M['frame'], 0.003)
# hero latch-side jamb is split to expose the electric-strike section (z 0.93-1.07)
box('JambLatch_low', (HW, HERO - 0.53, 0.465), (0.13, 0.06, 0.93), M['frame'], 0.003)
box('JambLatch_high', (HW, HERO - 0.53, 1.57), (0.13, 0.06, 1.0 + 0.0), M['frame'], 0.003)

# left wall with six windows
WY = [2, 5, 8, 11, 14, 17]
box('LWall_low', (-HW - 0.05, L / 2, 0.45), (0.1, L, 0.9), M['plaster'])
box('LWall_high', (-HW - 0.05, L / 2, 2.75), (0.1, L, 0.7), M['plaster'])
edges = [0.0] + sum([[y - 0.85, y + 0.85] for y in WY], []) + [L]
for i in range(0, len(edges), 2):
    if edges[i + 1] - edges[i] > 0.01: box(f'Pier{i}', (-HW - 0.05, (edges[i] + edges[i + 1]) / 2, 1.65), (0.1, edges[i + 1] - edges[i], 1.5), M['plaster'])
for k, y in enumerate(WY):
    box(f'WinGlass{k}', (-HW - 0.05, y, 1.65), (0.012, 1.7, 1.5), M['glass'])
    for dy in (-0.85, 0.0, 0.85): box(f'WinMull{k}_{dy}', (-HW - 0.05, y + dy, 1.65), (0.07, 0.05, 1.5), M['frame'], 0.002)
    box(f'WinHead{k}', (-HW - 0.05, y, 2.4), (0.07, 1.75, 0.05), M['frame'], 0.002)
    box(f'WinSill{k}', (-HW + 0.03, y, 0.915), (0.2, 1.8, 0.03), M['white'], 0.003)
box('Skirt_L', (-HW + 0.01, L / 2, 0.05), (0.02, L, 0.1), M['darksteel'])
box('Ground', (-31.5, L / 2, -0.06), (60, 80, 0.1), M['ground'])
box('FarBuilding', (-45, L / 2, 6), (6, 60, 12), M['plaster'])

# ------------------------------------------------------------------ hero room (behind the access door)
RX = HW + 0.1
box('RoomFloor', (RX + 3.0, HERO, -0.05), (6.0, 6.0, 0.1), M['room_floor'])
box('RoomCeil', (RX + 3.0, HERO, H + 0.05), (6.0, 6.0, 0.1), M['room_wall'])
box('RoomBack', (RX + 6.05, HERO, H / 2), (0.1, 6.0, H), M['room_wall'])
box('RoomSideA', (RX + 3.0, HERO - 3.05, H / 2), (6.0, 0.1, H), M['room_wall'])
box('RoomSideB', (RX + 3.0, HERO + 3.05, H / 2), (6.0, 0.1, H), M['room_wall'])
box('RoomWindowGlow', (RX + 5.98, HERO, 1.7), (0.01, 4.2, 1.6), M['warmroom'])
for r in range(3):
    for c in range(3):
        x = RX + 1.6 + c * 1.5; y = HERO - 1.6 + r * 1.6
        box(f'Desk{r}{c}', (x, y, 0.74), (0.6, 1.2, 0.04), M['wood']); box(f'DeskLeg{r}{c}', (x, y, 0.37), (0.5, 1.1, 0.02), M['darksteel'])
        box(f'Chair{r}{c}', (x - 0.55, y, 0.45), (0.4, 0.4, 0.04), M['navy'])
for d in DOORS:
    if d != HERO: box(f'DarkRoom{d}', (RX + 0.2, d, 1.1), (0.1, 1.0, 2.2), M['black'])

# ------------------------------------------------------------------ hero door leaf (hinged), lever, latch section
hinge = empty('Door_Hinge', (HW, HERO + 0.495, 0.0))
LEAF = [('Leaf_main', (0, -0.30, 1.05), (0.045, 0.60, 2.1)), ('Leaf_low', (0, -0.78, 0.465), (0.045, 0.36, 0.93)),
        ('Leaf_high', (0, -0.78, 1.585), (0.045, 0.36, 1.03))]
for n_, loc, sz in LEAF: box(n_, loc, sz, M['doorwood'], 0.002, hinge)
for nd in M['doorwood'].node_tree.nodes:            # one shared coordinate space (the hinge) -> grain is continuous across the three leaf pieces and moves with the door
    if nd.bl_idname == 'ShaderNodeTexCoord': nd.object = hinge
# lock-set front plate: covers the open cut-out around the lever so it reads as a mortise lock case (hardware position unchanged)
box('Lock_frontplate', (-0.0245, -0.80, 1.0), (0.004, 0.30, 0.17), M['darksteel'], 0.002, hinge)
box('Leaf_backplate', (0.0205, -0.78, 1.0), (0.004, 0.36, 0.14), M['black'], 0, hinge)
box('LatchCase', (0.0, -0.80, 1.0), (0.03, 0.10, 0.045), M['darksteel'], 0.002, hinge)
bolt = box('LatchBolt', (0.0, -0.93, 1.0), (0.014, 0.08, 0.022), M['steel'], 0.002, hinge)
box('LatchFace', (0.0, -0.962, 1.0), (0.032, 0.004, 0.06), M['steel'], 0.001, hinge)
cyl('Lever_rose', (-0.0225, -0.86, 1.0), (-0.045, -0.86, 1.0), 0.026, M['steel'], parent=hinge)
lever = empty('Lever_pivot', (-0.045, -0.86, 1.0), hinge)
box('Lever_arm', (-0.03, -0.075, 0.0), (0.02, 0.15, 0.02), M['steel'], 0.004, lever)
cyl('Lever_hub', (-0.0, 0.0, 0.0), (-0.03, 0.0, 0.0), 0.011, M['steel'], parent=lever)
for z in (0.25, 1.0, 1.75): box(f'Hinge{z}', (0.0, 0.015, z), (0.05, 0.03, 0.1), M['steel'], 0.002, hinge)
# sign
box('SignPlate', (HW - 0.006, HERO + 0.98, 1.58), (0.012, 0.46, 0.22), M['navy'], 0.003)
text('3031', (HW - 0.014, HERO + 0.98, 1.625), 0.115, M['text'])
text('LECTURE ROOM', (HW - 0.014, HERO + 0.98, 1.53), 0.03, M['text'])

# ------------------------------------------------------------------ electric strike (section view) on the latch jamb
box('Strike_cavity', (HW + 0.0, HERO - 0.53, 1.0), (0.12, 0.05, 0.14), M['black'])
box('Strike_plate', (HW - 0.063, HERO - 0.53, 1.0), (0.004, 0.05, 0.14), M['steel'], 0.001)
keeper = box('Strike_keeper', (HW - 0.0, HERO - 0.505, 1.0), (0.03, 0.022, 0.05), M['steel'], 0.002)
box('Strike_solenoid', (HW + 0.045, HERO - 0.535, 1.0), (0.025, 0.03, 0.05), M['frame'], 0.002)
cyl('Strike_wire', (HW + 0.06, HERO - 0.535, 1.03), (HW + 0.06, HERO - 0.535, 2.1), 0.003, M['black'])

# ------------------------------------------------------------------ access reader + conduit
RY, RZ = HERO - 0.85, 1.30
box('Reader_plate', (HW - 0.005, RY, RZ), (0.01, 0.1, 0.22), M['darksteel'], 0.003)
box('Reader_body', (HW - 0.021, RY, RZ), (0.022, 0.085, 0.2), M['black'], 0.006)
box('Reader_glass', (HW - 0.0335, RY, RZ), (0.003, 0.075, 0.185), M['blackglass'], 0.002)
cyl('Reader_lens_ring', (HW - 0.034, RY, RZ + 0.055), (HW - 0.0375, RY, RZ + 0.055), 0.017, M['darksteel'])
cyl('Reader_lens', (HW - 0.0372, RY, RZ + 0.055), (HW - 0.0395, RY, RZ + 0.055), 0.011, M['blackglass'])
bpy.ops.mesh.primitive_torus_add(major_radius=0.02, minor_radius=0.0025, location=(HW - 0.0355, RY, RZ - 0.04), rotation=(0, math.radians(90), 0))
ring = bpy.context.active_object; ring.name = 'Reader_LED_ring'; ring.data.materials.append(M['led']); bpy.ops.object.shade_smooth()
for k in range(5): cyl(f'Reader_grille{k}', (HW - 0.0345, RY - 0.03 + 0.015 * k, RZ - 0.085), (HW - 0.0365, RY - 0.03 + 0.015 * k, RZ - 0.085), 0.0025, M['darksteel'], 12)
cyl('Conduit', (HW - 0.016, RY, H), (HW - 0.016, RY, RZ + 0.11), 0.011, M['steel'])
for z in (0.6 + RZ * 0 + 1.5, 2.0, 2.5, 2.95): box(f'Clip{z}', (HW - 0.012, RY, z), (0.012, 0.03, 0.012), M['steel'])
box('Conduit_box', (HW - 0.016, RY, RZ + 0.115), (0.03, 0.03, 0.02), M['darksteel'], 0.002)

# ------------------------------------------------------------------ SHOT-01 REFINEMENT: door, corridor and ceiling detail (reader above is unchanged)
for z in (0.25, 1.0, 1.75):   # hinge barrels + pins on the corridor side
    cyl(f'HingeBarrel{z}', (-0.012, 0.016, z - 0.05), (-0.012, 0.016, z + 0.05), 0.009, M['steel'], 16, hinge)
box('KickPlate', (-0.0245, -0.48, 0.15), (0.004, 0.86, 0.30), M['steel'], 0.001, hinge)
box('Door_edge_gasket', (HW - 0.066, HERO - 0.0, 2.09), (0.004, 0.96, 0.012), M['black'])
box('Gasket_latch', (HW - 0.066, HERO - 0.50, 1.05), (0.004, 0.008, 2.05), M['black'])
box('Gasket_hinge', (HW - 0.066, HERO + 0.50, 1.05), (0.004, 0.008, 2.05), M['black'])
box('Closer_body', (-0.058, -0.62, 2.04), (0.05, 0.24, 0.06), M['darksteel'], 0.005, hinge)
box('Closer_arm', (-0.075, -0.44, 2.075), (0.014, 0.40, 0.012), M['steel'], 0.002, hinge)
box('Threshold', (HW - 0.0, HERO, 0.006), (0.14, 1.0, 0.012), M['steel'], 0.002)
# ceiling: cable tray, smoke detector, sprinkler, exit sign, emergency luminaire
box('CableTray', (0.95, L / 2, H - 0.07), (0.22, L - 1.0, 0.06), M['darksteel'], 0.003)
for k in range(int(L - 1.0) * 3): box(f'TrayRung{k}', (0.95, 1.0 + k / 3.0, H - 0.1), (0.22, 0.012, 0.012), M['steel'])
cyl('SmokeDet', (-0.6, 7.3, H - 0.001), (-0.6, 7.3, H - 0.045), 0.055, M['white'], 32)
cyl('SmokeDetCap', (-0.6, 7.3, H - 0.045), (-0.6, 7.3, H - 0.055), 0.025, M['black'], 24)
cyl('SprinklerPipe', (-0.6, 10.6, H), (-0.6, 10.6, H - 0.03), 0.014, M['steel'], 16)
cyl('SprinklerDeflector', (-0.6, 10.6, H - 0.035), (-0.6, 10.6, H - 0.042), 0.02, M['steel'], 20)
box('ExitSign', (0.0, L - 0.15, 2.7), (0.4, 0.05, 0.16), M['white'], 0.004)
box('ExitSignGlow', (0.0, L - 0.178, 2.7), (0.34, 0.004, 0.1), emission_mat('ExitGreen', (0.15, 0.9, 0.35), 3.0)[0])
# wall furniture (restrained red only on the extinguisher)
box('NoticeBoard', (HW - 0.015, 6.2, 1.5), (0.03, 1.3, 0.9), M['navy'], 0.006)
box('NoticeFrame_t', (HW - 0.016, 6.2, 1.96), (0.034, 1.34, 0.03), M['steel'], 0.002)
box('NoticeFrame_b', (HW - 0.016, 6.2, 1.04), (0.034, 1.34, 0.03), M['steel'], 0.002)
for k, (dy, dz, w_, h_) in enumerate(((-0.4, 0.12, 0.28, 0.38), (0.0, -0.1, 0.34, 0.26), (0.38, 0.1, 0.3, 0.4))):
    box(f'Paper{k}', (HW - 0.034, 6.2 + dy, 1.5 + dz), (0.002, w_, h_), M['text'], 0.0)
cyl('Extinguisher', (HW - 0.09, 10.2, 0.25), (HW - 0.09, 10.2, 0.85), 0.07, new_mat('ExtRed', (0.45, 0.02, 0.02), 0.35, 0.3), 24)
cyl('ExtinguisherNeck', (HW - 0.09, 10.2, 0.85), (HW - 0.09, 10.2, 0.95), 0.025, M['darksteel'], 16)
box('Bench_seat', (HW - 0.25, 12.0, 0.45), (0.45, 1.5, 0.05), M['wood'], 0.006)
for dy in (-0.65, 0.65): box(f'Bench_leg{dy}', (HW - 0.25, 12.0 + dy, 0.22), (0.38, 0.04, 0.44), M['darksteel'], 0.003)

# ------------------------------------------------------------------ lighting
w = bpy.data.worlds.new('World'); scene.world = w; w.use_nodes = True
wn, wl = w.node_tree.nodes, w.node_tree.links
sky = wn.new('ShaderNodeTexSky')
for t in ('MULTIPLE_SCATTERING', 'NISHITA'):
    try: sky.sky_type = t; break
    except Exception: pass
try: sky.sun_elevation = math.radians(38); sky.sun_rotation = math.radians(70); sky.sun_disc = False
except Exception: pass
wl.new(sky.outputs['Color'], wn['Background'].inputs['Color']); wn['Background'].inputs['Strength'].default_value = 0.5
sun = bpy.data.lights.new('Sun', 'SUN'); sun.energy = 2.6; sun.angle = math.radians(0.6)
so = bpy.data.objects.new('Sun', sun); COL.objects.link(so)
so.rotation_mode = 'QUATERNION'; so.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(Vector((0.78, 0.3, -0.55)).normalized())
macro = bpy.data.lights.new('MacroKey', 'AREA'); macro.shape = 'RECTANGLE'; macro.size = 0.4; macro.size_y = 0.25; macro.color = (1.0, 0.96, 0.9)
mo = bpy.data.objects.new('MacroKey', macro); COL.objects.link(mo); mo.location = (0.45, HERO - 1.2, 1.9)
mo.rotation_euler = (math.radians(55), math.radians(20), math.radians(-100))
for f, e in ((1, 0), (149, 0), (151, 40), (299, 40), (301, 0), (390, 0)): macro.energy = e; macro.keyframe_insert('energy', frame=f)

# ------------------------------------------------------------------ cameras (markers switch them)
def make_cam(name, lens, fstop, focus):
    c = bpy.data.cameras.new(name); c.lens = lens; c.sensor_width = 36; c.dof.use_dof = True; c.dof.aperture_fstop = fstop; c.dof.focus_object = focus
    c.clip_start = 0.02; ob = bpy.data.objects.new(name, c); COL.objects.link(ob); ob.rotation_mode = 'XYZ'; return ob

def aim(cam, target_loc):
    d = Vector(target_loc) - Vector(cam.location); cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def key_cam(cam, keys):
    """keys: [(frame, (x,y,z), (tx,ty,tz))] with small hand-held jitter keyframes added between."""
    for f, p, t in keys:
        cam.location = p; aim(cam, t)
        cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f)

focusA = empty('FocusA', (HW, 8.4, 1.2)); focusB = empty('FocusB', (HW - 0.035, RY, RZ - 0.02)); focusC = empty('FocusC', (HW - 0.05, HERO - 0.5, 1.0))
focusD = empty('FocusD', (HW + 0.3, HERO, 1.1))
camA = make_cam('CamA_track', 35, 4.0, focusA); camB = make_cam('CamB_reader', 100, 2.8, focusB)
camC = make_cam('CamC_lock', 100, 3.2, focusC); camD = make_cam('CamD_door', 28, 5.6, focusD)
for f, y in ((1, 5.0), (150, 8.2)): focusA.location = (HW, y, 1.2); focusA.keyframe_insert('location', frame=f)
jit = lambda: (random.uniform(-0.004, 0.004), random.uniform(-0.004, 0.004), random.uniform(-0.003, 0.003))
def jitter(base_pts, f0, f1, tgt):
    out = []
    for i, (f, p) in enumerate(base_pts):
        j = jit(); out.append((f, (p[0] + j[0], p[1] + j[1], p[2] + j[2]), tgt(f)))
    return out
ptsA = [(1, (-0.40, 1.3, 1.55)), (30, (-0.37, 2.3, 1.56)), (60, (-0.31, 3.4, 1.55)), (90, (-0.20, 4.6, 1.54)), (120, (-0.05, 5.8, 1.52)), (150, (0.12, 6.9, 1.50))]
key_cam(camA, jitter(ptsA, 1, 150, lambda f: (HW, 2.0 + (f / 150.0) * 6.7, 1.15)))
key_cam(camB, [(151, (0.55, RY - 0.95, RZ + 0.08), (HW - 0.034, RY, RZ - 0.01)), (240, (0.50, RY - 0.72, RZ + 0.03), (HW - 0.034, RY, RZ - 0.025))])
key_cam(camC, [(241, (0.40, HERO - 0.78, 1.05), (HW - 0.01, HERO - 0.5, 1.0)), (300, (0.46, HERO - 0.62, 1.03), (HW - 0.01, HERO - 0.5, 1.0))])
key_cam(camD, [(301, (0.15, 6.5, 1.5), (HW + 0.3, HERO, 1.2)), (345, (0.45, 7.1, 1.48), (HW + 0.6, HERO, 1.2)), (390, (0.62, 7.6, 1.46), (HW + 1.0, HERO, 1.2))])
# (v1 animation cameras CamA..CamD are kept in the file for reference but are no longer bound to the timeline; v3 cameras below drive the move)

# --- SHOT 01 stills cameras (not on the animation timeline)
focusW = empty('FocusW', (HW, HERO - 0.3, 1.1)); focusM = empty('FocusM', (HW - 0.034, RY, RZ - 0.02))
# Geometry used (inspected from this script's own coordinates): corridor x -1.4..1.4, y 0..18, z 0..3.1; hero door 3031 centred y=9.0 in the
# RIGHT wall (x=+1.4), latch jamb y=8.47, reader y=8.15 z=1.30, lever y=8.64 z=1.0, hinge jamb y=9.5, sign y~10.0.
# Camera looks along +y with +x on the right, so higher-y objects sit LEFT of lower-y ones only for cameras that look toward +x.
# Wide: eye height 1.5 m, level horizon (no pitch), aimed slightly beyond the door so the corridor recedes on the left of frame.
camW = make_cam('CamWide_establishing', 24, 8.0, focusW); camW.location = (-1.0, 5.3, 1.5); aim(camW, (HW, 9.8, 1.5))
# Close-up: 50 mm, ~1.6 m, oblique ~45 deg, aimed between reader and latch jamb so frame + lever + leaf edge share the shot.
camM = make_cam('CamMacro_reader', 50, 5.6, focusM); camM.location = (0.25, 7.2, 1.38); aim(camM, (HW - 0.03, 8.4, 1.25))
GRANT_FRAME = 225

# ------------------------------------------------------------------ access logic animation (only after GRANT does the hardware respond)
# ---- NAMED EVENTS (frame numbers; 30 fps). Everything below is derived from this one table so timing can be reviewed in one place.
EV = {'CAM_WIDE_DOLLY_START': 1, 'CAM_WIDE_DOLLY_END': 150, 'CUT_TO_CLOSEUP': 151,
      'RING_IDLE_TO_AMBER_START': 165, 'RING_AMBER': 171,
      'EVT_IDENTITY': 172, 'EVT_ACCOUNT': 186, 'EVT_ROOM': 198, 'EVT_SCHEDULE': 208, 'EVT_BACKEND': 216,
      'EVT_GRANT': 225,                                   # backend GRANT: ring -> green on this frame
      'LOCK_RELEASE_START': 229, 'LOCK_RELEASED': 241,    # strike keeper retracts only AFTER grant
      'LEVER_PRESS_START': 246, 'LEVER_PRESSED': 254,     # lever turns only after the lock is released (placeholder for the lecturer's hand)
      'DOOR_OPEN_START': 256, 'DOOR_OPEN_END': 346,       # hinge rotation begins only after the lever is down
      'LEVER_RELEASE_START': 262, 'LEVER_RELEASED': 276, 'CAM_CLOSEUP_END': 390}
assert EV['EVT_BACKEND'] < EV['EVT_GRANT'] < EV['LOCK_RELEASE_START'] < EV['LOCK_RELEASED'] <= EV['LEVER_PRESS_START'] < EV['LEVER_PRESSED'] <= EV['DOOR_OPEN_START']
IDLE, AMBER, GREEN = (0.55, 0.68, 1.0), (1.0, 0.36, 0.02), (0.04, 0.95, 0.18)      # deeper orange/green so AgX does not wash them to cream
col_in, str_in = LED.inputs['Color'], LED.inputs['Strength']
def kled(f, color, s):
    col_in.default_value = (*color, 1); str_in.default_value = s
    col_in.keyframe_insert('default_value', frame=f); str_in.keyframe_insert('default_value', frame=f)
kled(1, IDLE, 0.5); kled(EV['RING_IDLE_TO_AMBER_START'], IDLE, 0.5)
kled(EV['RING_AMBER'], AMBER, 2.2); kled(EV['EVT_GRANT'] - 1, AMBER, 2.2)       # steady amber for the whole verification (no flashing)
kled(EV['EVT_GRANT'], GREEN, 2.2); kled(EV['CAM_CLOSEUP_END'], GREEN, 2.2)
K0, K1 = (HW, HERO - 0.505, 1.0), (HW, HERO - 0.54, 1.0)
keeper.location = K0; keeper.keyframe_insert('location', frame=1); keeper.keyframe_insert('location', frame=EV['LOCK_RELEASE_START'])
keeper.location = K1; keeper.keyframe_insert('location', frame=EV['LOCK_RELEASED']); keeper.keyframe_insert('location', frame=EV['CAM_CLOSEUP_END'])
LEV = math.radians(-28)
for f, a in ((1, 0), (EV['LEVER_PRESS_START'], 0), (EV['LEVER_PRESSED'], LEV), (EV['LEVER_RELEASE_START'], LEV), (EV['LEVER_RELEASED'], 0)):
    lever.rotation_euler = (a, 0, 0); lever.keyframe_insert('rotation_euler', frame=f)
for f, y in ((1, -0.93), (EV['LEVER_PRESS_START'], -0.93), (EV['LEVER_PRESSED'], -0.905), (EV['LEVER_RELEASE_START'], -0.905), (EV['LEVER_RELEASED'], -0.93)):
    bolt.location = (0.0, y, 1.0); bolt.keyframe_insert('location', frame=f)       # latch bolt retracts with the lever
for f, a in ((1, 0), (EV['DOOR_OPEN_START'], 0), (EV['DOOR_OPEN_END'], math.radians(92)), (EV['CAM_CLOSEUP_END'], math.radians(92))):
    hinge.rotation_euler = (0, 0, a); hinge.keyframe_insert('rotation_euler', frame=f)
for nm, f in EV.items():                                  # named, review-friendly markers on the timeline (no camera bound)
    scene.timeline_markers.new(nm, frame=f)

# ---- CAMERA MOVE: continuous wide dolly -> deliberate cut -> slow close-up pull-back. Separate animated cameras; the still cameras stay static.
def aimc(cam, target, prev=None):
    d = Vector(target) - Vector(cam.location); q = d.to_track_quat('-Z', 'Y')
    cam.rotation_euler = q.to_euler('XYZ', prev) if prev is not None else q.to_euler('XYZ')
def move(cam, keys):
    prev = None
    for f, p, t in keys:
        cam.location = p; aimc(cam, t, prev); prev = cam.rotation_euler.copy()
        cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f)
focusWA = empty('FocusWA', (HW, HERO - 0.3, 1.1)); focusMA = empty('FocusMA', (HW - 0.034, RY, RZ - 0.02))
camWA = make_cam('CamWide_dolly', 24, 8.0, focusWA); camMA = make_cam('CamCloseup_pull', 50, 5.6, focusMA)
# wide dolly: same start pose/aim as the approved still, travels 1.9 m toward the door at constant 24 mm (no zoom), eye height kept level
move(camWA, [(1, (-1.0, 5.3, 1.5), (HW, 9.8, 1.5)), (EV['CAM_WIDE_DOLLY_END'], (-0.45, 6.9, 1.46), (HW, 8.9, 1.38))])
# close-up: starts on the approved still pose, then a very slow pull-back/lateral move that reveals the door swinging open (constant 50 mm)
move(camMA, [(EV['CUT_TO_CLOSEUP'], (0.25, 7.2, 1.38), (HW - 0.03, 8.4, 1.25)), (EV['CAM_CLOSEUP_END'], (-0.05, 6.5, 1.42), (HW, 8.75, 1.2))])
for ob in (camWA, camMA):
    ob.data.dof.use_dof = True
mk = scene.timeline_markers.new('CAM_WIDE', frame=1); mk.camera = camWA
mk = scene.timeline_markers.new('CAM_CLOSEUP', frame=EV['CUT_TO_CLOSEUP']); mk.camera = camMA
scene.camera = camWA

timing = {'fps': 30, 'frames': 390, 'events': EV, 'seconds': {k: round(v / 30, 2) for k, v in EV.items()},
          'shots': {'wide_dolly': [1, 150], 'closeup_pullback': [151, 390]},
          'overlay_alignment': 'overlay frame N == Blender frame N; overlay step frames: IDENTITY 172, ACCOUNT 186, ROOM 198, SCHEDULE 208, BACKEND 216, GRANTED 225',
          'note': 'Conceptual: door/lock hardware not connected in the project. Lever press is a placeholder for the lecturer (live action pending).'}
json.dump(timing, open(os.path.join(HERE, 'AIU_TEST01_timing.json'), 'w'), indent=2)

# ------------------------------------------------------------------ render settings
def configure(res, samples):
    r = scene.render; r.engine = 'CYCLES'; r.resolution_x, r.resolution_y = res; r.resolution_percentage = 100
    cy = scene.cycles; cy.samples = samples; cy.use_denoising = True
    try: cy.denoiser = 'OPENIMAGEDENOISE'
    except Exception: pass
    cy.max_bounces = 8; cy.glossy_bounces = 6; cy.transmission_bounces = 8; cy.sample_clamp_indirect = 8.0
    r.use_motion_blur = False          # v3: no motion blur (slow camera + steady lights; blur added nothing)
    try:
        p = bpy.context.preferences.addons['cycles'].preferences; p.compute_device_type = 'METAL'; p.get_devices()
        for d in p.devices: d.use = (d.type != 'CPU')
        print('CYCLES DEVICES:', [(d.name, d.type, d.use) for d in p.devices]); cy.device = 'GPU'
    except Exception as e: print('GPU setup failed (CPU will be used):', e); cy.device = 'CPU'
    for vt in ('AgX', 'Filmic', 'Standard'):
        try: scene.view_settings.view_transform = vt; break
        except Exception: pass
    for lk in ('AgX - Medium High Contrast', 'Medium High Contrast', 'None'):
        try: scene.view_settings.look = lk; break
        except Exception: pass

blend = os.path.join(HERE, 'AIU_TEST01_corridor_door.blend')
# soft wall-wash above the hero door (keeps the reader wall readable without making the LED ring the only bright element)
wash = bpy.data.lights.new('DoorWash', 'AREA'); wash.shape = 'RECTANGLE'; wash.size = 1.4; wash.size_y = 0.5; wash.color = (1.0, 0.95, 0.88)
wash.energy = float(arg('--wash', 22)); wo = bpy.data.objects.new('DoorWash', wash); COL.objects.link(wo); wo.location = (0.55, HERO - 0.2, 2.95)
wo.rotation_euler = (0, math.radians(-70), 0)

def shot01(tag='v2', macro_frame=184, outdir=None):
    """Quality gate: one medium-wide still + one reader close-up. Same scene, same lights, only the camera differs."""
    samples = int(arg('--samples', 64)); exp = float(arg('--exposure', 0.0)); macro_exp = float(arg('--macro-exposure', -0.4))
    outdir = os.path.abspath(os.path.expanduser(outdir or arg('--out', os.path.join(OUT, f'review_{tag}')))); os.makedirs(outdir, exist_ok=True)
    configure((1920, 1080), samples)
    scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_depth = '16'
    jobs = [(f'AIU_SHOT01_wide_{tag}_f0001.png', camW, 1, exp), (f'AIU_SHOT01_reader_macro_{tag}_f{macro_frame:04d}.png', camM, macro_frame, macro_exp)]
    if '--only' in A and arg('--only') in ('wide', 'macro'): jobs = [j for j in jobs if arg('--only') in j[0]]
    bpy.ops.wm.save_as_mainfile(filepath=blend)
    # ROOT-CAUSE FIX: timeline markers carry camera bindings and frame_set() re-applies them, which silently replaced the requested camera
    # (log of the first run: scene.camera=CamA_track / CamB_reader). Unbind them for stills (restored afterwards for the animation preview).
    saved_marker_cams = [(mk, mk.camera) for mk in scene.timeline_markers]
    for mk, _ in saved_marker_cams: mk.camera = None
    def inspect(cam):
        from bpy_extras.object_utils import world_to_camera_view
        eul = [round(math.degrees(a), 2) for a in cam.matrix_world.to_euler()]
        P(f'    CAMERA {cam.name}: location={tuple(round(v, 3) for v in cam.matrix_world.translation)} rotation_deg(XYZ)={eul} '
          f'lens={cam.data.lens}mm sensor={cam.data.sensor_width}mm f/{cam.data.dof.aperture_fstop} clip={cam.data.clip_start}..{cam.data.clip_end} '
          f'focus_obj={cam.data.dof.focus_object.name if cam.data.dof.focus_object else None}')
        pts = {'door_centre': (HW, HERO, 1.05), 'door_head': (HW, HERO, 2.1), 'door_foot': (HW, HERO, 0.02), 'reader': (HW - 0.034, RY, RZ),
               'lever': (HW - 0.045, HERO - 0.365, 1.0), 'hinge_mid': (HW - 0.012, HERO + 0.511, 1.0), 'sign_3031': (HW - 0.014, HERO + 0.98, 1.625),
               'floor_ahead': (0.0, HERO + 2, 0.0), 'ceiling_panel': (0.0, 7.5, H)}
        for k, p in pts.items():
            v = world_to_camera_view(scene, cam, Vector(p)); ok = 0 <= v.x <= 1 and 0 <= v.y <= 1 and v.z > 0
            P(f'      {k:14s} frame_xy=({v.x:.2f},{v.y:.2f}) depth={v.z:.2f} m  {"IN FRAME" if ok else "** OUT OF FRAME **"}')
    log = {'engine': 'CYCLES', 'resolution': [1920, 1080], 'samples': samples, 'denoiser': 'OpenImageDenoise', 'exposure': exp,
           'view_transform': scene.view_settings.view_transform, 'look': scene.view_settings.look, 'device': scene.cycles.device,
           'blender': bpy.app.version_string, 'wash_energy_W': wash.energy, 'files': []}
    P(f'shot01: {len(jobs)} job(s) queued; engine={scene.render.engine} device={scene.cycles.device} samples={samples} '
      f'res={scene.render.resolution_x}x{scene.render.resolution_y} OUT={os.path.abspath(OUT)}')
    for fn, cam, fr, ex in jobs:
        path = os.path.abspath(os.path.join(outdir, fn))
        P(f'>>> START render: {fn} | camera={cam.name} | frame={fr} | -> {path}')
        try:
            scene.frame_set(fr); bpy.context.view_layer.update(); scene.camera = cam; scene.view_settings.exposure = ex; scene.render.filepath = path
            if scene.camera.name != cam.name: raise RuntimeError(f'active camera is {scene.camera.name}, expected {cam.name}')
            P(f'    scene.camera={scene.camera.name} frame_current={scene.frame_current} exposure={ex} '
              f'resolution={scene.render.resolution_x}x{scene.render.resolution_y}@{scene.render.resolution_percentage}% samples={scene.cycles.samples} output={scene.render.filepath}')
            inspect(cam)
            res = bpy.ops.render.render(write_still=True)
            P(f'    render operator returned {res}')
            if not os.path.exists(path):                        # operator finished but nothing on disk -> save the Render Result explicitly
                P('    WARNING: file missing after render; saving "Render Result" explicitly')
                bpy.data.images['Render Result'].save_render(path)
            if os.path.exists(path) and os.path.getsize(path) > 0: P(f'<<< DONE render: {path} ({os.path.getsize(path)} bytes) exists=True non-empty=True'); log['files'].append(path)
            else: P(f'<<< FAILED: missing or empty file at {path}')
        except Exception:
            P(f'<<< EXCEPTION while rendering {fn}:'); traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush()
    json.dump(log, open(os.path.join(outdir, f'AIU_SHOT01_{tag}_render_settings.json'), 'w'), indent=2)
    for mk, c in saved_marker_cams: mk.camera = c
    P(f'shot01 finished. files written: {log["files"]}')
    return log

def verify_animation():
    """Executes the timeline (no rendering) and checks the authorization ordering from the actual evaluated object states."""
    P('=== ANIMATION LOGIC CHECK (evaluated frame by frame, no rendering) ===')
    for nm, f in sorted(EV.items(), key=lambda kv: kv[1]): P(f'    EVENT {nm:26s} frame {f:3d}  t={f / 30:5.2f}s')
    k0 = Vector(K0); first = {'keeper_move': None, 'keeper_done': None, 'lever_move': None, 'door_move': None, 'led_green': None}
    clear = {'min_wall_dist': 9.0}
    for f in range(1, 391):
        scene.frame_set(f)
        if first['keeper_move'] is None and (keeper.location - k0).length > 1e-6: first['keeper_move'] = f
        if first['keeper_done'] is None and (keeper.location - Vector(K1)).length < 1e-6: first['keeper_done'] = f
        if first['lever_move'] is None and abs(lever.rotation_euler.x) > 1e-6: first['lever_move'] = f
        if first['door_move'] is None and abs(hinge.rotation_euler.z) > 1e-6: first['door_move'] = f
        if first['led_green'] is None and LED.inputs['Color'].default_value[1] > 0.8 and LED.inputs['Color'].default_value[0] < 0.3: first['led_green'] = f
        cp = scene.camera.matrix_world.translation if scene.camera else None
        if cp is not None: clear['min_wall_dist'] = min(clear['min_wall_dist'], HW - abs(cp.x) if abs(cp.x) < HW else -1)
        if f in (1, 75, 150, 151, 270, 390):
            c = scene.camera; P(f'    frame {f:3d}: active camera={c.name} loc={tuple(round(v, 3) for v in c.matrix_world.translation)} '
                                f'lens={c.data.lens}mm keeper_y={keeper.location.y:.4f} lever_deg={math.degrees(lever.rotation_euler.x):.1f} door_deg={math.degrees(hinge.rotation_euler.z):.1f}')
    P(f'    first frames: {first}   | min camera distance to corridor side walls: {clear["min_wall_dist"]:.2f} m')
    ok = True
    def need(cond, msg):
        nonlocal ok
        P(f'    [{"PASS" if cond else "FAIL"}] {msg}'); ok &= bool(cond)
    need(first['keeper_move'] is not None and first['keeper_move'] > EV['EVT_GRANT'], f'lock does not move before GRANT (GRANT {EV["EVT_GRANT"]}, first lock motion {first["keeper_move"]})')
    need(first['door_move'] is not None and first['keeper_done'] is not None and first['door_move'] > first['keeper_done'], f'door does not move before the lock is released (released {first["keeper_done"]}, door moves {first["door_move"]})')
    need(first['lever_move'] is not None and first['lever_move'] > first['keeper_done'], f'lever does not move before the lock is released (lever {first["lever_move"]})')
    if first['led_green'] is not None: need(first['led_green'] >= EV['EVT_GRANT'], f'ring is not green before GRANT (first green frame {first["led_green"]})')
    else: P('    [INFO] could not read ring colour from the evaluated node tree; ring timing is defined by keyframes 224=amber / 225=green')
    need(clear['min_wall_dist'] > 0.3, 'camera paths stay >0.3 m inside the corridor walls (no wall clipping on the path)')
    if not ok: raise RuntimeError('animation logic check failed')
    scene.frame_set(1)

def preview_animation(outdir):
    res = (int(arg('--preview-w', 960)), int(arg('--preview-h', 540))); samples = int(arg('--preview-samples', 16))
    configure(res, samples); scene.view_settings.exposure = float(arg('--exposure', 0.0)) - 0.2
    scene.frame_start, scene.frame_end = 1, 390
    base = os.path.join(outdir, 'AIU_SHOT01_v3_preview_')
    try:
        scene.render.image_settings.file_format = 'FFMPEG'; scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'; mode_ = 'mp4'
    except Exception:
        P('WARNING: FFMPEG output unavailable in this build, writing PNG sequence instead'); traceback.print_exc()
        scene.render.image_settings.file_format = 'PNG'; mode_ = 'png'
    scene.render.filepath = base
    import time; t0 = time.time()
    def on_post(sc, *a): P(f'    preview frame {sc.frame_current:3d}/390 done, camera={sc.camera.name}, elapsed {time.time() - t0:6.1f}s')
    bpy.app.handlers.render_post.append(on_post)
    P(f'=== PREVIEW ANIMATION: {res[0]}x{res[1]} samples={samples} frames 1-390 @30fps format={mode_} -> {base}* ===')
    try: bpy.ops.render.render(animation=True)
    finally: bpy.app.handlers.render_post.remove(on_post)
    import glob
    found = sorted(glob.glob(base + '*'))
    good = [p for p in found if os.path.getsize(p) > 0]
    P(f'preview outputs found: {len(good)} non-empty file(s); first={good[:1]} last={good[-1:]}')
    if not good: raise RuntimeError('preview produced no files')

def review3():
    outdir = os.path.abspath(os.path.expanduser(arg('--out', os.path.join(OUT, 'review_v3')))); os.makedirs(outdir, exist_ok=True)
    P(f'REVIEW_V3 output folder: {outdir}')
    verify_animation()
    which = arg('--only', 'all')
    if which in ('all', 'stills', 'wide', 'macro'):
        shot01(tag='v3', macro_frame=200, outdir=outdir)       # frame 200 = mid-verification, ring steady amber
    if which in ('all', 'preview'):
        for mk in scene.timeline_markers:                      # make sure the cut binding is active for the animation
            if mk.name == 'CAM_WIDE': mk.camera = camWA
            if mk.name == 'CAM_CLOSEUP': mk.camera = camMA
        preview_animation(outdir)
    P('REVIEW_V3 finished.')

P(f'SCRIPT {os.path.abspath(__file__)} | Blender {bpy.app.version_string} | argv-after-"--" = {A} | MODE = {MODE!r} | OUT = {os.path.abspath(OUT)}')
if MODE == 'shot01':
    try: shot01()
    except Exception: P('EXCEPTION in shot01():'); traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); sys.exit(1)
elif MODE == 'review3':
    try: review3()
    except Exception: P('EXCEPTION in review3():'); traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); sys.exit(1)
elif MODE == 'still':
    configure((1920, 1080), 128); scene.frame_set(STILL)
    scene.render.image_settings.file_format = 'PNG'; scene.render.filepath = os.path.join(OUT, f'AIU_TEST01_still_f{STILL:04d}.png')
    bpy.ops.wm.save_as_mainfile(filepath=blend); bpy.ops.render.render(write_still=True)
elif MODE == 'preview':
    configure((960, 540), 48)
    scene.render.image_settings.file_format = 'FFMPEG'; scene.render.ffmpeg.format = 'MPEG4'; scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'; scene.render.filepath = os.path.join(OUT, 'AIU_TEST01_preview_540p_')
    bpy.ops.wm.save_as_mainfile(filepath=blend); bpy.ops.render.render(animation=True)
elif MODE == 'final':
    configure((1920, 1080), 128)
    if arg('--frames'): a, b = arg('--frames').split('-'); scene.frame_start, scene.frame_end = int(a), int(b)
    scene.render.image_settings.file_format = 'PNG'; scene.render.filepath = os.path.join(OUT, 'AIU_TEST01_1080p_')
    scene.render.use_overwrite = False
    bpy.ops.wm.save_as_mainfile(filepath=blend); bpy.ops.render.render(animation=True)
else:
    P(f'NOTE: MODE {MODE!r} is not a render mode (shot01 | still | preview | final) -> building and saving the scene only, NO render.')
    configure((1920, 1080), 128); bpy.ops.wm.save_as_mainfile(filepath=blend)
    print('SCENE BUILT AND SAVED:', blend)
