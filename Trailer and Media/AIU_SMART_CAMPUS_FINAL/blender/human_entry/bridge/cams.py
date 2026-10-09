import bpy, math
from mathutils import Vector
D=bpy.data; sc=bpy.context.scene
male=D.objects['ARM_Instructor']
for o in list(D.objects):
    hide=False
    if o==male or o.parent==male or o.name=='ARM_UAL_source' or (o.parent and o.parent.name=='ARM_UAL_source'): hide=True
    for m in getattr(o,'modifiers',[]):
        if m.type=='ARMATURE' and m.object in (male,D.objects['ARM_UAL_source']): hide=True
    if hide: o.hide_render=True; o.hide_viewport=True
male.animation_data_clear()
fem=D.objects['ARM_Student_F']
# hide any male-only children: check names
print('hidden', [o.name for o in D.objects if o.hide_render and o.type in ('MESH','ARMATURE')])
def aim(cam,loc,tgt):
    d=Vector(tgt)-Vector(loc); return d.to_track_quat('-Z','Y').to_euler()
def mkcam(name,lens,f0,f1,l0,t0,l1,t1):
    for o in [o for o in D.objects if o.name==name]: D.objects.remove(o,do_unlink=True)
    cd=D.cameras.new(name); cd.lens=lens; cd.sensor_width=36; cd.dof.use_dof=False; cd.clip_start=0.05
    cam=D.objects.new(name,cd); sc.collection.objects.link(cam)
    for f,l,t in ((f0,l0,t0),(f1,l1,t1)):
        cam.location=l; cam.rotation_euler=aim(cam,l,t); cam.keyframe_insert('location',frame=f); cam.keyframe_insert('rotation_euler',frame=f)
    for fc in (cam.animation_data.action.fcurves if hasattr(cam.animation_data.action,'fcurves') else []):
        for k in fc.keyframe_points: k.interpolation='BEZIER'
    return cam
c1=mkcam('HCam_1_approach',30,45,148,(-1.2,2.8,1.55),(0.4,6.0,1.25),(-1.0,4.2,1.5),(0.9,8.2,1.3))
c2=mkcam('HCam_2_reader',36,149,224,(0.30,6.5,1.45),(1.15,8.35,1.36),(0.42,6.85,1.45),(1.2,8.4,1.38))
c3=mkcam('HCam_3_handle',50,225,295,(0.45,9.35,1.34),(1.25,8.55,1.12),(0.1,9.75,1.42),(1.35,8.7,1.12))
c4=mkcam('HCam_4_enter',26,296,398,(3.8,8.5,1.35),(1.5,8.9,1.3),(3.5,8.3,1.35),(1.7,8.5,1.25))
for m in list(sc.timeline_markers):
    if m.name.startswith('HCUT'): sc.timeline_markers.remove(m)
for cam,f in ((c1,45),(c2,149),(c3,225),(c4,296)):
    m=sc.timeline_markers.new('HCUT_'+cam.name,frame=f); m.camera=cam
sc.camera=c1
