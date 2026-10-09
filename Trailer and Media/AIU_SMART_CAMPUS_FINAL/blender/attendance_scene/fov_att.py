"""Illustrative coverage frustum (approximate, NOT a measured field of view) + status LED. Concept visualisation only."""
import bpy, bmesh
from mathutils import Vector
D=bpy.data; sc=bpy.context.scene
for o in D.objects:
    if o.name.startswith('FOV_'): o.hide_render=True; o.hide_viewport=True
for n in [o.name for o in D.objects if o.name.startswith('ATT_')]: D.objects.remove(D.objects[n],do_unlink=True)
apex=Vector((6.0,13.29,2.66)); fl=[(2.7,5.0),(9.3,5.0),(9.3,11.5),(2.7,11.5)]
def mat(name,col,strength,alpha):
    m=D.materials.get(name) or D.materials.new(name); m.use_nodes=True; nt=m.node_tree; nt.nodes.clear()
    out=nt.nodes.new('ShaderNodeOutputMaterial'); em=nt.nodes.new('ShaderNodeEmission'); em.inputs[0].default_value=col+(1,); em.inputs[1].default_value=strength
    if alpha<1:
        tr=nt.nodes.new('ShaderNodeBsdfTransparent'); mx=nt.nodes.new('ShaderNodeMixShader'); mx.inputs[0].default_value=alpha
        nt.links.new(tr.outputs[0],mx.inputs[1]); nt.links.new(em.outputs[0],mx.inputs[2]); nt.links.new(mx.outputs[0],out.inputs[0])
    else: nt.links.new(em.outputs[0],out.inputs[0])
    return m
mfill=mat('ATT_Fill',(0.35,0.62,1.0),1.2,0.10); mline=mat('ATT_Line',(0.55,0.8,1.0),6.0,1.0); mflo=mat('ATT_Floor',(0.35,0.62,1.0),1.0,0.18)
def mesh(name,verts,faces,m,origin):
    me=D.meshes.new(name); me.from_pydata([tuple(Vector(v)-origin) for v in verts],[],faces); me.update(); me.materials.append(m)
    o=D.objects.new(name,me); o.location=origin; sc.collection.objects.link(o); o.visible_shadow=False; return o
V=[apex]+[Vector((x,y,0.03)) for x,y in fl]
vol=mesh('ATT_FOV_Volume',V,[(0,1,2),(0,2,3),(0,3,4),(0,4,1)],mfill,apex)
flo=mesh('ATT_FOV_Floor',V[1:],[(0,1,2,3)],mflo,apex)
edges=[]
def bar(a,b,r=0.006):
    a,b=Vector(a),Vector(b); d=b-a
    bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=r,depth=d.length,location=(a+b)/2); o=bpy.context.object
    o.rotation_euler=d.to_track_quat('Z','Y').to_euler(); o.data.materials.append(mline); o.visible_shadow=False; edges.append(o); return o
for i in range(1,5): bar(apex,V[i]); bar(V[i],V[i%4+1])
for o in edges: o.name='ATT_FOV_Edge'; o.parent=vol; o.matrix_parent_inverse=vol.matrix_world.inverted()
# reveal animation: grows out of the lens between frames 100 and 135; visible only in shot 2
for o in (vol,flo):
    o.scale=(0.001,0.001,0.001); o.keyframe_insert('scale',frame=91); o.scale=(1,1,1); o.keyframe_insert('scale',frame=135)
    o.hide_render=False; o.keyframe_insert('hide_render',frame=91)
    o.hide_render=True; o.keyframe_insert('hide_render',frame=211); o.hide_render=False
    o.hide_render=True; o.keyframe_insert('hide_render',frame=1); o.keyframe_insert('hide_render',frame=90)
    o.hide_render=False; o.keyframe_insert('hide_render',frame=91); o.keyframe_insert('hide_render',frame=210)
    o.hide_render=True; o.keyframe_insert('hide_render',frame=211)
for e in edges:  # edges follow parent scale but need their own visibility
    e.hide_render=True; e.keyframe_insert('hide_render',frame=1); e.keyframe_insert('hide_render',frame=90)
    e.hide_render=False; e.keyframe_insert('hide_render',frame=91); e.keyframe_insert('hide_render',frame=210)
    e.hide_render=True; e.keyframe_insert('hide_render',frame=211)
# make constant interpolation for visibility keys
def const(o):
    ad=o.animation_data
    if ad and ad.action:
        for fc in ad.action.layers[0].strips[0].channelbags[0].fcurves:
            if fc.data_path=='hide_render':
                for k in fc.keyframe_points: k.interpolation='CONSTANT'
for o in [vol,flo]+edges: const(o)
# status LED: steady cyan glow (it is only a rendered prop)
led=D.objects['OccCam_StatusLED']
if led.data.materials:
    m=led.data.materials[0]
    if m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type=='EMISSION': n.inputs[0].default_value=(0.2,0.8,1.0,1); n.inputs[1].default_value=30
            if n.type=='BSDF_PRINCIPLED':
                n.inputs['Emission Color'].default_value=(0.2,0.8,1.0,1); n.inputs['Emission Strength'].default_value=30
