"""
AIU SMART CAMPUS — OCCUPANCY SCENE, STAGE 0 (EMPTY-ROOM TEST).  Blender 5.x, Cycles/Metal.
STATUS: written but NOT yet executed by the author (Blender cannot run in the authoring sandbox). Expect fix rounds.

* Self-contained, separate scene. Output .blend: blender/occupancy_scene/AIU_OCC_classroom_test.blend
* The approved door-access scene (blender/AIU_TEST01_corridor_door.blend) is only READ (appended copy). It is never saved over.
* NO people, mannequins or placeholder characters. NO occupancy count. The room is empty by design (people assets pending).
* The 3D scene contains no interface text. The "OCCUPANCY DEMO — PEOPLE ASSETS PENDING" panel is a separate transparent overlay.

Modes:  --mode build | review      (review = logic checks, then stills and preview;  --only logic|stills|preview|all)
Options: --out <dir>  --exposure -0.2  --preview-w 854 --preview-h 480 --preview-samples 12 --step 1
Timeline (30 fps, 450 frames = 15 s), hard cuts on 101 / 201 / 301 / 361:
  A   1-100  continue from the approved door scene's last camera pose, through the open doorway (50 mm, no zoom)
  B 101-200  establishing dolly down the side aisle (24 mm): desks, board, display, windows, ceiling lights
  C 201-300  reveal where the interior occupancy camera is mounted (35 mm)
  D 301-360  macro of the occupancy camera hardware (85 mm)
  E 361-450  coverage volume fades in; overlay panel (separate file) explains door camera vs interior camera
"""
import bpy, math, sys, os, json, random, traceback, glob, time
from mathutils import Vector

def P(*a): print(*a, flush=True)
argv = sys.argv; A = argv[argv.index('--') + 1:] if '--' in argv else []
def arg(n, d=None): return A[A.index(n) + 1] if n in A else d
MODE = arg('--mode', 'build')
ROOT = os.path.expanduser('~/Desktop/AIU_SMART_CAMPUS_FINAL/blender')
HERE = os.path.join(ROOT, 'occupancy_scene')
OUT = os.path.abspath(os.path.expanduser(arg('--out', os.path.join(HERE, 'renders', 'review_occ_v1'))))
APPROVED = os.path.join(ROOT, 'AIU_TEST01_corridor_door.blend')
BLEND = os.path.join(HERE, 'AIU_OCC_classroom_test.blend')
os.makedirs(OUT, exist_ok=True); random.seed(11)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene; scene.render.fps = 30; scene.frame_start = 1; scene.frame_end = 450
OCC = bpy.data.collections.new('OCC_Classroom'); scene.collection.children.link(OCC)

# ------------------------------------------------------------------ geometry constants (same world frame as the approved corridor)
HW, HERO, RH = 1.4, 9.0, 3.1                 # corridor wall x=1.4, door 3031 centred y=9.0, ceiling 3.1
X0, X1, Y0, Y1 = 1.5, 10.5, 4.5, 13.5        # classroom interior: 9 m x 9 m; corridor wall at X0, windows on X1, teaching wall at Y1

# ------------------------------------------------------------------ helpers
def setin(node, names, val):
    for n in ([names] if isinstance(names, str) else names):
        if n in node.inputs:
            try: node.inputs[n].default_value = val; return True
            except Exception: pass
    return False
def new_mat(name, base, rough=0.5, metal=0.0, extra=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes['Principled BSDF']
    setin(b, 'Base Color', (*base, 1)); setin(b, 'Roughness', rough); setin(b, 'Metallic', metal)
    for k, v in (extra or {}).items(): setin(b, k, v)
    return m
def bump(m, scale, strength, dist, mapscale=None, fac_from=None):
    n, l = m.node_tree.nodes, m.node_tree.links; b = n['Principled BSDF']
    tc = n.new('ShaderNodeTexCoord'); mp = n.new('ShaderNodeMapping'); l.new(tc.outputs['Object'], mp.inputs['Vector'])
    if mapscale: mp.inputs['Scale'].default_value = mapscale
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = scale; nz.inputs['Detail'].default_value = 6
    l.new(mp.outputs['Vector'], nz.inputs['Vector'])
    bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = strength; bp.inputs['Distance'].default_value = dist
    l.new(nz.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal'])
    return m
def tile_mat(name, c1, c2, mortar, size=0.6):
    m = new_mat(name, c1, 0.2); n, l = m.node_tree.nodes, m.node_tree.links; b = n['Principled BSDF']
    tc = n.new('ShaderNodeTexCoord'); mp = n.new('ShaderNodeMapping'); l.new(tc.outputs['Object'], mp.inputs['Vector'])
    br = n.new('ShaderNodeTexBrick'); br.offset = 0.0
    for k, v in (('Color1', (*c1, 1)), ('Color2', (*c2, 1)), ('Mortar', (*mortar, 1)), ('Scale', 1.0), ('Mortar Size', 0.006),
                 ('Brick Width', size), ('Row Height', size), ('Mortar Smooth', 0.1)):
        if k in br.inputs: br.inputs[k].default_value = v
    l.new(mp.outputs['Vector'], br.inputs['Vector']); l.new(br.outputs['Color'], b.inputs['Base Color'])
    nz = n.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 3.0; l.new(mp.outputs['Vector'], nz.inputs['Vector'])
    cr = n.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color = (0.10, 0.10, 0.10, 1); cr.color_ramp.elements[1].color = (0.30, 0.30, 0.30, 1)
    l.new(nz.outputs['Fac'], cr.inputs['Fac']); l.new(cr.outputs['Color'], b.inputs['Roughness'])
    bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.35; bp.inputs['Distance'].default_value = 0.002
    l.new(br.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal']); return m
def grain_mat(name, light, dark, axis_dir='X', stretch=(1, 0.12, 1), rough=0.45):
    m = new_mat(name, light, rough, 0.0, {'Coat Weight': 0.08}); n, l = m.node_tree.nodes, m.node_tree.links; b = n['Principled BSDF']
    tc = n.new('ShaderNodeTexCoord'); mp = n.new('ShaderNodeMapping'); l.new(tc.outputs['Object'], mp.inputs['Vector']); mp.inputs['Scale'].default_value = stretch
    wv = n.new('ShaderNodeTexWave'); wv.wave_type = 'BANDS'; wv.bands_direction = axis_dir
    wv.inputs['Scale'].default_value = 45; wv.inputs['Distortion'].default_value = 0.9; wv.inputs['Detail'].default_value = 2
    l.new(mp.outputs['Vector'], wv.inputs['Vector'])
    cr = n.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color = (*dark, 1); cr.color_ramp.elements[1].color = (*light, 1)
    l.new(wv.outputs['Fac'], cr.inputs['Fac']); l.new(cr.outputs['Color'], b.inputs['Base Color'])
    bp = n.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.06; bp.inputs['Distance'].default_value = 0.0004
    l.new(wv.outputs['Fac'], bp.inputs['Height']); l.new(bp.outputs['Normal'], b.inputs['Normal']); return m
def emission_mat(name, color, strength):
    m = bpy.data.materials.new(name); m.use_nodes = True; n, l = m.node_tree.nodes, m.node_tree.links
    for x in list(n): n.remove(x)
    e = n.new('ShaderNodeEmission'); o = n.new('ShaderNodeOutputMaterial'); e.inputs['Color'].default_value = (*color, 1); e.inputs['Strength'].default_value = strength
    l.new(e.outputs['Emission'], o.inputs['Surface']); return m, e
def fade_mat(name, color, strength, fac):
    m = bpy.data.materials.new(name); m.use_nodes = True; n, l = m.node_tree.nodes, m.node_tree.links
    for x in list(n): n.remove(x)
    e = n.new('ShaderNodeEmission'); t = n.new('ShaderNodeBsdfTransparent'); mx = n.new('ShaderNodeMixShader'); o = n.new('ShaderNodeOutputMaterial')
    e.inputs['Color'].default_value = (*color, 1); e.inputs['Strength'].default_value = strength; mx.inputs['Fac'].default_value = fac
    l.new(t.outputs['BSDF'], mx.inputs[1]); l.new(e.outputs['Emission'], mx.inputs[2]); l.new(mx.outputs['Shader'], o.inputs['Surface']); return m, mx, e

M = {}
M['floor'] = tile_mat('VinylTile', (0.34, 0.37, 0.42), (0.31, 0.34, 0.39), (0.12, 0.12, 0.13))
M['wall'] = bump(new_mat('WallPaint', (0.80, 0.79, 0.75), 0.82), 220, 0.05, 0.0004)
M['navy'] = bump(new_mat('NavyPaint', (0.025, 0.03, 0.16), 0.4, 0.0, {'Coat Weight': 0.15}), 220, 0.04, 0.0004)
M['ceiling'] = bump(new_mat('CeilingTile', (0.88, 0.88, 0.86), 0.92), 90, 0.2, 0.001)
M['desk'] = grain_mat('DeskLaminate', (0.66, 0.54, 0.40), (0.58, 0.46, 0.33), 'X', (1.0, 0.12, 1.0))
M['wood'] = grain_mat('TeachingPlatform', (0.50, 0.33, 0.18), (0.40, 0.25, 0.13), 'X', (1.0, 0.12, 1.0), 0.4)
M['steel'] = bump(new_mat('BrushedSteel', (0.72, 0.73, 0.75), 0.32, 1.0), 600, 0.04, 0.0003, (1, 1, 0.02))
M['darksteel'] = new_mat('DarkSteel', (0.12, 0.12, 0.13), 0.4, 1.0)
M['alu'] = bump(new_mat('Aluminium', (0.80, 0.81, 0.83), 0.3, 1.0), 500, 0.04, 0.0003, (1, 1, 0.02))
M['black'] = new_mat('BlackPlastic', (0.015, 0.015, 0.018), 0.35)
M['blackglass'] = new_mat('BlackGlass', (0.004, 0.004, 0.006), 0.04, 0.0, {'Coat Weight': 1.0})
M['white'] = new_mat('WhiteABS', (0.88, 0.89, 0.90), 0.38)
M['fabric'] = bump(new_mat('NavyFabric', (0.03, 0.04, 0.17), 0.85), 900, 0.35, 0.0006)
M['chairplastic'] = new_mat('ChairShell', (0.04, 0.05, 0.20), 0.45)
M['board'] = new_mat('Whiteboard', (0.88, 0.89, 0.89), 0.18, 0.0, {'Coat Weight': 0.2})
M['glass'] = new_mat('Glass', (0.9, 0.95, 1.0), 0.02, 0.0, {'Transmission Weight': 1.0, 'IOR': 1.45})
M['blind'] = new_mat('BlindSlat', (0.86, 0.86, 0.84), 0.45, 0.6)
M['wall_ext'] = new_mat('ExteriorGround', (0.52, 0.47, 0.38), 0.85)
M['panel'], _ = emission_mat('LED_Panel', (1.0, 0.97, 0.92), 5.0)
M['display'], _ = emission_mat('DisplayStandby', (0.03, 0.05, 0.13), 0.7)
M['occled'], OCCLED = emission_mat('OccCamStatus', (0.55, 0.78, 1.0), 1.4)
M['fovfill'], FOVMIX, _e = fade_mat('FOV_Fill', (0.62, 0.78, 1.0), 1.0, 0.0)
M['fovline'], FOVLINE = emission_mat('FOV_Line', (0.75, 0.88, 1.0), 0.0)

def link(ob, col=None): (col or OCC).objects.link(ob); return ob
def box(name, loc, size, mat=None, bevel=0.0, parent=None, rot=None):
    sx, sy, sz = [s / 2 for s in size]
    v = [(-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz), (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    me = bpy.data.meshes.new(name); me.from_pydata(v, [], f); me.update()
    ob = bpy.data.objects.new(name, me); link(ob); ob.location = loc
    if mat: me.materials.append(mat)
    if bevel:
        bm = ob.modifiers.new('bevel', 'BEVEL'); bm.width = bevel; bm.segments = 2; bm.limit_method = 'ANGLE'
    if rot: ob.rotation_euler = rot
    if parent: ob.parent = parent
    return ob
def cyl(name, p0, p1, r, mat=None, verts=24, parent=None):
    p0, p1 = Vector(p0), Vector(p1); d = p1 - p0
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=d.length, location=(p0 + p1) / 2)
    ob = bpy.context.active_object; ob.name = name
    for c in list(ob.users_collection): c.objects.unlink(ob)
    link(ob); ob.rotation_mode = 'QUATERNION'; ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
    bpy.ops.object.shade_smooth()
    if mat: ob.data.materials.append(mat)
    if parent: ob.parent = parent
    return ob
def empty(name, loc, parent=None):
    e = bpy.data.objects.new(name, None); link(e); e.location = loc
    if parent: e.parent = parent
    return e

# ------------------------------------------------------------------ 1) bring in the approved corridor + door (READ-ONLY copy; the file on disk is never written)
APPENDED = False
def bring_in_approved():
    global APPENDED
    if not os.path.exists(APPROVED): P('WARNING: approved .blend not found -> classroom only (no corridor)'); return
    with bpy.data.libraries.load(APPROVED, link=False) as (src, dst):
        dst.objects = list(src.objects); dst.worlds = list(src.worlds)
    drop_prefix = ('Room', 'Desk', 'Chair')           # the approved scene's placeholder 6x6 room (only removed from THIS copy)
    for ob in dst.objects:
        if ob is None: continue
        if ob.type == 'CAMERA' or ob.name in ('MacroKey',) or ob.name.startswith(drop_prefix):
            bpy.data.objects.remove(ob, do_unlink=True); continue
        scene.collection.objects.link(ob)             # corridor objects stay in the scene root collection
    if dst.worlds and dst.worlds[0]: scene.world = dst.worlds[0]
    for nm, setter in (('Door_Hinge', lambda o: setattr(o, 'rotation_euler', (0, 0, math.radians(92)))),   # approved END state: door open,
                       ('Lever_pivot', lambda o: setattr(o, 'rotation_euler', (0, 0, 0))),                   # lever released,
                       ('Strike_keeper', lambda o: setattr(o, 'location', (HW, HERO - 0.54, 1.0))),         # lock released,
                       ('LatchBolt', lambda o: setattr(o, 'location', (0.0, -0.93, 1.0)))):
        o = bpy.data.objects.get(nm)
        if o: o.animation_data_clear(); setter(o)
    led = bpy.data.materials.get('ReaderLED')                                                              # ring green (GRANTED)
    if led and led.node_tree:
        led.node_tree.animation_data_clear()
        for nd in led.node_tree.nodes:
            if nd.bl_idname == 'ShaderNodeEmission':
                nd.inputs['Color'].default_value = (0.04, 0.95, 0.18, 1); nd.inputs['Strength'].default_value = 2.2
    APPENDED = True; P(f'approved corridor appended (read-only copy): {len([o for o in dst.objects if o])} objects')
bring_in_approved()
if not scene.world:
    w = bpy.data.worlds.new('World'); w.use_nodes = True; scene.world = w; w.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5

# ------------------------------------------------------------------ 2) room shell
cx, cy = (X0 + X1) / 2, (Y0 + Y1) / 2
box('OCC_Floor', (cx, cy, -0.05), (X1 - X0 + 0.2, Y1 - Y0 + 0.2, 0.1), M['floor'])
box('OCC_Ceiling', (cx, cy, RH + 0.05), (X1 - X0 + 0.2, Y1 - Y0 + 0.2, 0.1), M['ceiling'])
box('OCC_BackWall', (cx, Y0 - 0.05, RH / 2), (X1 - X0 + 0.2, 0.1, RH), M['wall'])
box('OCC_FrontWall', (cx, Y1 + 0.05, RH / 2), (X1 - X0 + 0.2, 0.1, RH), M['wall'])
box('OCC_NavyPanel', (6.0, Y1 - 0.015, RH / 2), (3.4, 0.03, RH), M['navy'])
for nm, (a, b) in {'Skirt_Back': ((cx, Y0 + 0.01, 0.05), (X1 - X0, 0.02, 0.1)), 'Skirt_Front': ((cx, Y1 - 0.01, 0.05), (X1 - X0, 0.02, 0.1))}.items():
    box(nm, a, b, M['darksteel'])
box('Skirt_Corridor', (X0 + 0.01, cy, 0.05), (0.02, Y1 - Y0, 0.1), M['darksteel'])
box('Dado_Corridor', (X0 + 0.01, cy, 0.55), (0.02, Y1 - Y0 - 0.02, 1.0), M['navy'], 0.002)
box('DadoRail_Corridor', (X0 + 0.018, cy, 1.06), (0.036, Y1 - Y0 - 0.02, 0.03), M['alu'], 0.003)
# window wall (exterior) with four windows
WIN = [(5.4, 7.0), (7.4, 9.0), (9.4, 11.0), (11.4, 13.0)]
box('Win_LowWall', (X1 + 0.05, cy, 0.45), (0.1, Y1 - Y0, 0.9), M['wall']); box('Win_HighWall', (X1 + 0.05, cy, 2.75), (0.1, Y1 - Y0, 0.7), M['wall'])
edges = [Y0] + [v for w in WIN for v in w] + [Y1]
for i in range(0, len(edges), 2):
    if edges[i + 1] - edges[i] > 0.01: box(f'Win_Pier{i}', (X1 + 0.05, (edges[i] + edges[i + 1]) / 2, 1.65), (0.1, edges[i + 1] - edges[i], 1.5), M['wall'])
for k, (a, b) in enumerate(WIN):
    yc = (a + b) / 2
    box(f'WinGlass{k}', (X1 + 0.05, yc, 1.65), (0.012, b - a, 1.5), M['glass'])
    for yy in (a, yc, b): box(f'WinMull{k}_{yy:.1f}', (X1 + 0.05, yy, 1.65), (0.07, 0.05, 1.5), M['darksteel'], 0.002)
    box(f'WinHead{k}', (X1 + 0.05, yc, 2.4), (0.07, b - a + 0.05, 0.05), M['darksteel'], 0.002)
    box(f'WinSill{k}', (X1 - 0.08, yc, 0.915), (0.2, b - a + 0.12, 0.03), M['white'], 0.003)
    box(f'BlindHead{k}', (X1 - 0.03, yc, 2.34), (0.05, b - a - 0.06, 0.05), M['alu'], 0.003)
    for s in range(14):                                         # venetian blind, lowered ~0.7 m, slats tilted
        box(f'BlindSlat{k}_{s}', (X1 - 0.03, yc, 2.28 - s * 0.05), (0.05, b - a - 0.08, 0.008), M['blind'], 0.0, rot=(0, math.radians(32), 0))
box('Outside_Ground', (X1 + 30.0, cy, -0.06), (60.0, 80.0, 0.1), M['wall_ext'])
# interior casing of the approved door opening (room side)
for nm, loc, sz in (('Casing_L', (X0 + 0.02, HERO - 0.53, 1.05), (0.04, 0.06, 2.1)), ('Casing_R', (X0 + 0.02, HERO + 0.53, 1.05), (0.04, 0.06, 2.1)),
                    ('Casing_T', (X0 + 0.02, HERO, 2.13), (0.04, 1.12, 0.06))):
    box(nm, loc, sz, M['darksteel'], 0.002)

# ------------------------------------------------------------------ 3) ceiling: LED panels, HVAC diffusers, life-safety
for xi, xp in enumerate((3.5, 6.0, 8.5)):
    for yi, yp in enumerate((6.5, 9.0, 11.5)):
        box(f'LEDPanel{xi}{yi}', (xp, yp, RH - 0.012), (1.2, 0.6, 0.02), M['panel'])
for xi, xp in enumerate((4.75, 7.25)):
    for yi, yp in enumerate((7.75, 10.25)):
        box(f'Diffuser{xi}{yi}', (xp, yp, RH - 0.012), (0.6, 0.6, 0.02), M['white'], 0.003)
        for j in range(3): box(f'DiffSlat{xi}{yi}{j}', (xp, yp, RH - 0.025), (0.46 - 0.14 * j, 0.46 - 0.14 * j, 0.008), M['black'])
box('ReturnGrille', (9.2, 5.3, RH - 0.012), (0.6, 0.3, 0.02), M['white'], 0.003)
for j in range(5): box(f'ReturnBar{j}', (9.2, 5.3 - 0.1 + j * 0.05, RH - 0.025), (0.54, 0.012, 0.008), M['black'])
cyl('SmokeDet', (3.5, 8.0, RH - 0.001), (3.5, 8.0, RH - 0.045), 0.055, M['white'], 32)
for k, (sx, sy) in enumerate(((5.0, 5.8), (8.0, 8.0), (5.0, 11.0))):
    cyl(f'SprinklerPipe{k}', (sx, sy, RH), (sx, sy, RH - 0.03), 0.014, M['steel'], 16); cyl(f'SprinklerDef{k}', (sx, sy, RH - 0.035), (sx, sy, RH - 0.042), 0.02, M['steel'], 20)

# ------------------------------------------------------------------ 4) teaching wall: platform, boards, display, teacher desk
box('Platform', (6.0, Y1 - 0.6, 0.06), (X1 - X0, 1.2, 0.12), M['wood'], 0.004)
for nm, xc in (('BoardL', 3.2), ('BoardR', 8.8)):
    box(nm, (xc, Y1 - 0.02, 1.55), (2.6, 0.02, 1.2), M['board'], 0.002)
    for tag, (dl, sz) in {'T': ((0, 0.6 + 0.0), (2.64, 0.03, 0.03)), 'B': ((0, -0.6), (2.64, 0.03, 0.03))}.items():
        box(f'{nm}_Frame{tag}', (xc, Y1 - 0.03, 1.55 + (0.615 if tag == 'T' else -0.615)), sz, M['alu'], 0.003)
    for tag, dx in (('L', -1.31), ('R', 1.31)): box(f'{nm}_Frame{tag}', (xc + dx, Y1 - 0.03, 1.55), (0.03, 0.03, 1.26), M['alu'], 0.003)
    box(f'{nm}_Tray', (xc, Y1 - 0.06, 0.93), (2.2, 0.07, 0.03), M['alu'], 0.004)
box('Display_Bezel', (6.0, Y1 - 0.05, 1.65), (2.4, 0.06, 1.4), M['black'], 0.006)
box('Display_Screen', (6.0, Y1 - 0.082, 1.65), (2.3, 0.004, 1.3), M['display'])
box('Display_Mount', (6.0, Y1 - 0.015, 1.65), (0.6, 0.03, 0.4), M['darksteel'])
box('TeacherDesk_Top', (3.4, Y1 - 0.9, 0.76), (1.6, 0.7, 0.04), M['desk'], 0.004)
for dx in (-0.74, 0.74): box(f'TeacherDesk_Side{dx}', (3.4 + dx, Y1 - 0.9, 0.37), (0.04, 0.62, 0.74), M['desk'])
box('TeacherDesk_Modesty', (3.4, Y1 - 0.62, 0.45), (1.4, 0.02, 0.5), M['desk'])

# ------------------------------------------------------------------ 5) student desks and chairs (30 seats, EMPTY)
COLS = [3.3, 4.4, 5.5, 7.5, 8.6, 9.7]; ROWS = [6.4, 7.6, 8.8, 10.0, 11.2]
def desk(x, y, tag):
    box(f'Desk_{tag}_top', (x, y, 0.745), (1.0, 0.55, 0.03), M['desk'], 0.004)
    for dx in (-0.45, 0.45):
        for dy in (-0.22, 0.22): box(f'Desk_{tag}_leg{dx}{dy}', (x + dx, y + dy, 0.365), (0.04, 0.04, 0.73), M['darksteel'])
        box(f'Desk_{tag}_rail{dx}', (x + dx, y, 0.6), (0.03, 0.44, 0.03), M['darksteel'])
    box(f'Desk_{tag}_modesty', (x, y + 0.24, 0.5), (0.9, 0.015, 0.34), M['desk'])
def chair(x, y, tag, jx, jy, rz):
    root = empty(f'Chair_{tag}', (x + jx, y - 0.55 + jy, 0.0)); root.rotation_euler = (0, 0, rz)
    box(f'Chair_{tag}_seat', (0, 0, 0.45), (0.42, 0.42, 0.045), M['fabric'], 0.01, root)
    box(f'Chair_{tag}_back', (0, -0.2, 0.74), (0.40, 0.03, 0.30), M['chairplastic'], 0.01, root)
    for dx in (-0.17, 0.17): box(f'Chair_{tag}_post{dx}', (dx, -0.2, 0.55), (0.025, 0.025, 0.2), M['darksteel'], 0, root)
    for dx in (-0.18, 0.18):
        for dy in (-0.18, 0.18): box(f'Chair_{tag}_leg{dx}{dy}', (dx, dy, 0.215), (0.025, 0.025, 0.43), M['darksteel'], 0, root)
n_seats = 0
for ri, yy in enumerate(ROWS):
    for ci, xx in enumerate(COLS):
        tag = f'{ri}{ci}'; desk(xx, yy, tag); chair(xx, yy, tag, random.uniform(-0.04, 0.04), random.uniform(-0.05, 0.06), random.uniform(-0.07, 0.07)); n_seats += 1

# ------------------------------------------------------------------ 6) INTERIOR OCCUPANCY CAMERA (white housing + navy band; distinct from the black door reader)
OCC_MOUNT = Vector((6.0, Y1 - 0.02, 2.72))
piv = empty('OccCam_Pivot', OCC_MOUNT); piv.rotation_euler = (math.radians(20), 0, 0)      # faces -Y (into the room), tilted down 20 deg
box('OccCam_WallPlate', (6.0, Y1 - 0.01, 2.72), (0.18, 0.02, 0.14), M['darksteel'], 0.004)
box('OccCam_Arm', (0, -0.035, 0.0), (0.05, 0.06, 0.05), M['darksteel'], 0.004, piv)
box('OccCam_Housing', (0, -0.115, -0.005), (0.15, 0.10, 0.075), M['white'], 0.012, piv)
box('OccCam_Band', (0, -0.115, 0.0), (0.152, 0.102, 0.012), M['navy'], 0.003, piv)
box('OccCam_FrontGlass', (0, -0.166, -0.005), (0.11, 0.004, 0.052), M['blackglass'], 0.003, piv)
cyl('OccCam_LensRing', (0, -0.166, -0.005), (0, -0.176, -0.005), 0.024, M['darksteel'], 32, piv)
cyl('OccCam_Lens', (0, -0.175, -0.005), (0, -0.181, -0.005), 0.016, M['blackglass'], 32, piv)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0035, location=(0.058, -0.168, 0.026)); led = bpy.context.active_object; led.name = 'OccCam_StatusLED'
for c in list(led.users_collection): c.objects.unlink(led)
link(led); led.parent = piv; led.data.materials.append(M['occled'])
box('OccCam_Cable', (0, -0.035, 0.07), (0.012, 0.012, 0.09), M['black'], 0.002, piv)

# ------------------------------------------------------------------ 7) coverage volume (concept visual; visible to camera only, does not light the room)
apex = Vector((6.0, Y1 - 0.2, 2.62))
BASE = [Vector((2.8, 5.0, 0.02)), Vector((9.2, 5.0, 0.02)), Vector((9.2, 11.8, 0.02)), Vector((2.8, 11.8, 0.02))]
vs = [apex] + BASE; fs = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1)]
me = bpy.data.meshes.new('FOV_Mesh'); me.from_pydata([tuple(v) for v in vs], [], fs); me.update(); me.materials.append(M['fovfill'])
fov = bpy.data.objects.new('FOV_Volume', me); link(fov)
fov_parts = [fov]
for i, b in enumerate(BASE):
    fov_parts.append(cyl(f'FOV_Edge{i}', apex, b, 0.005, M['fovline'], 8)); fov_parts.append(cyl(f'FOV_Base{i}', b, BASE[(i + 1) % 4], 0.005, M['fovline'], 8))
for ob in fov_parts:
    for attr in ('visible_diffuse', 'visible_glossy', 'visible_shadow', 'visible_transmission', 'visible_volume_scatter'):
        try: setattr(ob, attr, False)
        except Exception: pass

# ------------------------------------------------------------------ 8) lighting (all constant; nothing is keyed except the coverage-volume fade)
sunr = bpy.data.lights.new('Sun_Room', 'SUN'); sunr.energy = 2.2; sunr.angle = math.radians(0.7)
so = bpy.data.objects.new('Sun_Room', sunr); link(so)
so.rotation_mode = 'QUATERNION'; so.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(Vector((-0.8, 0.25, -0.5)).normalized())   # from the window side
rf = bpy.data.lights.new('RoomFill', 'AREA'); rf.shape = 'RECTANGLE'; rf.size = 6.0; rf.size_y = 5.0; rf.energy = 60.0; rf.color = (1.0, 0.97, 0.92)
rfo = bpy.data.objects.new('RoomFill', rf); link(rfo); rfo.location = (6.0, 9.0, RH - 0.15); rfo.rotation_euler = (0, 0, 0)          # points straight down, soft ceiling bounce stand-in

# ------------------------------------------------------------------ 9) cameras + choreography
def make_cam(name, lens, fstop, focus):
    c = bpy.data.cameras.new(name); c.lens = lens; c.sensor_width = 36; c.dof.use_dof = True; c.dof.aperture_fstop = fstop; c.dof.focus_object = focus
    c.clip_start = 0.02; ob = bpy.data.objects.new(name, c); link(ob); return ob
def aimc(cam, target, prev=None):
    q = (Vector(target) - Vector(cam.location)).to_track_quat('-Z', 'Y'); cam.rotation_euler = q.to_euler('XYZ', prev) if prev is not None else q.to_euler('XYZ')
def move(cam, keys, focus=None):
    prev = None
    for f, p, t in keys:
        cam.location = p; aimc(cam, t, prev); prev = cam.rotation_euler.copy()
        cam.keyframe_insert('location', frame=f); cam.keyframe_insert('rotation_euler', frame=f)
        if focus: focus.location = t; focus.keyframe_insert('location', frame=f)
EV = {'CUT_A_TRANSITION': 1, 'CUT_B_ESTABLISH': 101, 'CUT_C_REVEAL': 201, 'CUT_D_MACRO': 301, 'CUT_E_COVERAGE': 361,
      'FOV_FADE_START': 355, 'FOV_FADE_END': 395, 'OVERLAY_PANEL_START': 375, 'END': 450}
fA, fB, fC, fD, fE = (empty(n, (0, 0, 0)) for n in ('FocusA', 'FocusB', 'FocusC', 'FocusD', 'FocusE'))
cA = make_cam('OccCam_A_transition', 50, 8.0, fA); cB = make_cam('OccCam_B_establish', 24, 8.0, fB); cC = make_cam('OccCam_C_reveal', 35, 6.3, fC)
cD = make_cam('OccCam_D_macro', 85, 4.0, fD); cE = make_cam('OccCam_E_coverage', 24, 8.0, fE)
# A: starts on the approved scene's final close-up pose (-0.05,6.5,1.42 -> door) and glides through the doorway (door y 8.5..9.5), 50 mm throughout
move(cA, [(1, (-0.05, 6.5, 1.42), (HW, 8.75, 1.2)), (35, (0.15, 7.9, 1.48), (2.4, 8.95, 1.4)), (70, (1.0, 8.95, 1.5), (3.8, 9.3, 1.4)), (100, (2.0, 8.9, 1.5), (4.6, 10.2, 1.35))], fA)
move(cB, [(101, (2.1, 5.0, 1.62), (6.5, 13.0, 1.5)), (200, (2.4, 8.2, 1.65), (7.0, 13.2, 1.6))], fB)
move(cC, [(201, (9.4, 5.0, 1.95), (6.0, 12.6, 2.3)), (250, (7.9, 6.8, 2.15), (6.0, 13.0, 2.5)), (300, (6.2, 10.8, 2.3), (6.0, 13.4, 2.7))], fC)
move(cD, [(301, (5.3, 11.9, 2.45), (6.0, 13.35, 2.69)), (360, (5.55, 12.1, 2.5), (6.0, 13.35, 2.69))], fD)
move(cE, [(361, (2.8, 5.2, 2.1), (6.0, 11.0, 1.0)), (450, (4.2, 5.0, 2.2), (6.0, 11.5, 1.0))], fE)
for nm, cam, fr in (('CAM_A', cA, 1), ('CAM_B', cB, 101), ('CAM_C', cC, 201), ('CAM_D', cD, 301), ('CAM_E', cE, 361)):
    scene.timeline_markers.new(nm, frame=fr).camera = cam
for nm, f in EV.items(): scene.timeline_markers.new(nm, frame=f)
scene.camera = cA
# coverage-volume fade (the only animated look element)
for f, fac, st in ((EV['FOV_FADE_START'], 0.0, 0.0), (EV['FOV_FADE_END'], 0.06, 1.2)):
    FOVMIX.inputs['Fac'].default_value = fac; FOVMIX.inputs['Fac'].keyframe_insert('default_value', frame=f)
    FOVLINE.inputs['Strength'].default_value = st; FOVLINE.inputs['Strength'].keyframe_insert('default_value', frame=f)
json.dump({'fps': 30, 'frames': 450, 'events': EV, 'seats_modelled': n_seats, 'people_modelled': 0, 'approved_corridor_appended': APPENDED,
           'note': 'Empty-room test. No people, no count. Overlay (separate file) carries the OCCUPANCY DEMO - PEOPLE ASSETS PENDING label.'},
          open(os.path.join(HERE, 'AIU_OCC_timing.json'), 'w'), indent=2)

# ------------------------------------------------------------------ 10) render config
def configure(res, samples):
    r = scene.render; r.engine = 'CYCLES'; r.resolution_x, r.resolution_y = res; r.resolution_percentage = 100; r.use_motion_blur = False
    cy = scene.cycles; cy.samples = samples; cy.use_denoising = True
    try: cy.denoiser = 'OPENIMAGEDENOISE'
    except Exception: pass
    cy.max_bounces = 8; cy.glossy_bounces = 6; cy.transmission_bounces = 8; cy.sample_clamp_indirect = 8.0
    try:
        p = bpy.context.preferences.addons['cycles'].preferences; p.compute_device_type = 'METAL'; p.get_devices()
        for d in p.devices: d.use = (d.type != 'CPU')
        P('CYCLES DEVICES:', [(d.name, d.type, d.use) for d in p.devices]); cy.device = 'GPU'
    except Exception as e: P('GPU setup failed (CPU will be used):', e); cy.device = 'CPU'
    for vt in ('AgX', 'Filmic', 'Standard'):
        try: scene.view_settings.view_transform = vt; break
        except Exception: pass
    for lk in ('AgX - Medium High Contrast', 'Medium High Contrast', 'None'):
        try: scene.view_settings.look = lk; break
        except Exception: pass
    scene.view_settings.exposure = float(arg('--exposure', -0.2))      # constant for the whole sequence

# ------------------------------------------------------------------ 11) validation
def static_boxes():
    out = []
    for ob in bpy.data.objects:
        if ob.type != 'MESH' or ob.parent is not None or any(abs(a) > 1e-6 for a in ob.rotation_euler) or ob.name.startswith(('FOV_', 'Outside', 'Ground', 'FarBuilding', 'BlindSlat')): continue
        if ob.rotation_mode == 'QUATERNION': continue
        cs = [ob.matrix_world @ Vector(c) for c in ob.bound_box]; out.append((ob.name, Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs))), Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))))
    return out
def logic_check():
    from bpy_extras.object_utils import world_to_camera_view
    P('=== OCCUPANCY TEST LOGIC CHECK (no rendering) ===')
    ok = True
    def need(c, m):
        nonlocal ok; P(f'    [{"PASS" if c else "FAIL"}] {m}'); ok &= bool(c)
    need(sum(1 for o in bpy.data.objects if o.name.startswith('Chair_') and o.type == 'EMPTY') == 30, '30 chairs modelled, 30 desks, 0 people objects')
    need(not any(('person' in o.name.lower() or 'human' in o.name.lower() or 'student' in o.name.lower()) for o in bpy.data.objects), 'no human/placeholder-character objects exist in the file')
    bxs = static_boxes(); hits = {}; near = {}; seen = {}
    for f in range(1, 451):
        scene.frame_set(f); cam = scene.camera; p = cam.matrix_world.translation
        seen[f] = cam.name
        for nm, mn, mx in bxs:
            if all(mn[i] + 0.002 < p[i] < mx[i] - 0.002 for i in range(3)): hits.setdefault(nm, []).append(f)
            else:
                d = max(max(mn[i] - p[i], 0, p[i] - mx[i]) for i in range(3)) if True else 9
                dist = Vector((max(mn.x - p.x, 0, p.x - mx.x), max(mn.y - p.y, 0, p.y - mx.y), max(mn.z - p.z, 0, p.z - mx.z))).length
                if dist < 0.15: near.setdefault(nm, []).append(f)
        if 1.2 < p.x < 1.6 and not (8.55 < p.y < 9.45): hits.setdefault('DOORWAY_JAMB(path)', []).append(f)
    need(not hits, f'no camera is ever inside solid geometry or the door jambs {dict((k, (v[0], v[-1])) for k, v in hits.items()) if hits else ""}')
    P(f'    [INFO] camera passes within 15 cm of: {dict((k, (v[0], v[-1])) for k, v in near.items()) if near else "nothing"}')
    cut = {1: 'OccCam_A_transition', 101: 'OccCam_B_establish', 201: 'OccCam_C_reveal', 301: 'OccCam_D_macro', 361: 'OccCam_E_coverage'}
    for f, n in cut.items(): scene.frame_set(f); need(scene.camera.name == n, f'frame {f}: active camera is {scene.camera.name} (expected {n})')
    for f in (60, 150, 250, 330, 420):
        scene.frame_set(f); cam = scene.camera
        for lab, loc in (('occupancy camera', OCC_MOUNT), ('door 3031 opening', Vector((HW, HERO, 1.2))), ('board/display wall', Vector((6.0, Y1, 1.6)))):
            v = world_to_camera_view(scene, cam, loc); inn = 0 <= v.x <= 1 and 0 <= v.y <= 1 and v.z > 0
            P(f'      f{f} {cam.name:22s} lens={cam.data.lens:>4.0f}mm  {lab:20s} frame_xy=({v.x:.2f},{v.y:.2f}) {"IN" if inn else "out"}')
    for f in (355, 375, 395): scene.frame_set(f); P(f'      f{f}: FOV fade fac={FOVMIX.inputs["Fac"].default_value:.3f} line={FOVLINE.inputs["Strength"].default_value:.2f}')
    scene.frame_set(1)
    if not ok: raise RuntimeError('occupancy logic check failed')

def render_stills():
    configure((1280, 720), int(arg('--samples', 32))); scene.render.image_settings.file_format = 'PNG'
    for f in (60, 150, 250, 330, 420):
        scene.frame_set(f); path = os.path.join(OUT, f'AIU_OCC_still_f{f:04d}.png'); scene.render.filepath = path
        c = scene.camera; P(f'>>> still f{f} camera={c.name} loc={tuple(round(v, 3) for v in c.matrix_world.translation)} lens={c.data.lens}mm res=1280x720 -> {path}')
        bpy.ops.render.render(write_still=True); P(f'<<< {"DONE" if os.path.exists(path) and os.path.getsize(path) > 0 else "FAILED"}: {path}')
def render_preview():
    res = (int(arg('--preview-w', 854)), int(arg('--preview-h', 480))); configure(res, int(arg('--preview-samples', 12)))
    scene.frame_start, scene.frame_end, scene.frame_step = 1, 450, int(arg('--step', 1)); scene.render.image_settings.file_format = 'PNG'
    d = os.path.join(OUT, 'preview_frames'); os.makedirs(d, exist_ok=True); scene.render.filepath = os.path.join(d, 'AIU_OCC_preview_')
    t0 = time.time()
    def on_post(sc, *a): P(f'    preview frame {sc.frame_current:3d}/450 camera={sc.camera.name} elapsed {time.time() - t0:6.1f}s')
    bpy.app.handlers.render_post.append(on_post)
    P(f'=== PREVIEW {res[0]}x{res[1]} spp={scene.cycles.samples} step={scene.frame_step} -> {d} ===')
    try: bpy.ops.render.render(animation=True)
    finally: bpy.app.handlers.render_post.remove(on_post)
    n = len([p for p in glob.glob(os.path.join(d, '*.png')) if os.path.getsize(p) > 0]); P(f'preview PNG frames written (non-empty): {n}')

P(f'SCRIPT {os.path.abspath(__file__)} | Blender {bpy.app.version_string} | MODE={MODE!r} | OUT={OUT} | approved corridor appended={APPENDED}')
try:
    if MODE == 'review':
        configure((1280, 720), 32); bpy.ops.wm.save_as_mainfile(filepath=BLEND); P('saved', BLEND)
        which = arg('--only', 'all')
        if which in ('all', 'logic'): logic_check()
        if which in ('all', 'stills'): render_stills()
        if which in ('all', 'preview'): render_preview()
        P('REVIEW finished.')
    else:
        configure((1280, 720), 32); bpy.ops.wm.save_as_mainfile(filepath=BLEND); P('SCENE BUILT AND SAVED:', BLEND, '(no render in build mode)')
except Exception:
    P('EXCEPTION:'); traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); sys.exit(1)
