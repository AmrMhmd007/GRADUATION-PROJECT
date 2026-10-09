import bpy, math
from mathutils import Vector
D=bpy.data; sc=bpy.context.scene
for o in D.objects:
    if o.name.startswith('FOV_'): o.hide_render=True; o.hide_viewport=True
for m in list(sc.timeline_markers): sc.timeline_markers.remove(m)
for o in [o for o in D.objects if o.name.startswith('KCam_')]: D.objects.remove(o,do_unlink=True)
def aim(l,t): return (Vector(t)-Vector(l)).to_track_quat('-Z','Y').to_euler()
def mk(name,lens,f0,f1,l0,t0,l1,t1):
    cd=D.cameras.new(name); cd.lens=lens; cd.sensor_width=36; cd.dof.use_dof=False
    cam=D.objects.new(name,cd); sc.collection.objects.link(cam)
    for f,l,t in ((f0,l0,t0),(f1,l1,t1)):
        cam.location=l; cam.rotation_euler=aim(l,t); cam.keyframe_insert('location',frame=f); cam.keyframe_insert('rotation_euler',frame=f)
    return cam
cams=[mk('KCam_1_wide',24,1,75,(2.2,5.0,1.78),(6.5,12.0,1.2),(2.9,5.5,1.72),(6.4,12.0,1.2)),
      mk('KCam_2_aisle',32,76,150,(6.5,5.2,1.5),(5.0,12.5,1.4),(6.5,7.6,1.5),(5.0,12.5,1.4)),
      mk('KCam_3_students',38,151,225,(6.5,10.6,1.15),(4.4,7.0,0.98),(6.8,10.9,1.2),(4.6,7.0,1.0)),
      mk('KCam_4_lecturer',34,226,300,(9.8,9.0,1.45),(4.8,12.4,1.4),(8.8,10.2,1.45),(4.9,12.4,1.4))]
for cam,f in zip(cams,(1,76,151,226)): sc.timeline_markers.new('K_'+cam.name,frame=f).camera=cam
sc.camera=cams[0]; sc.frame_start=1; sc.frame_end=300
