"""Attendance-camera scene cameras. Run inside AIU_ATTENDANCE_SCENE.blend (copy of AIU_HUMAN_classroom_v1.blend; original untouched)."""
import bpy, math
from mathutils import Vector
D=bpy.data; sc=bpy.context.scene
for m in list(sc.timeline_markers): sc.timeline_markers.remove(m)
for o in [o for o in D.objects if o.name.startswith(('KCam_','AttCam_'))]: D.objects.remove(o,do_unlink=True)
def aim(l,t): return (Vector(t)-Vector(l)).to_track_quat('-Z','Y').to_euler()
def mk(name,lens,keys):
    cd=D.cameras.new(name); cd.lens=lens; cd.sensor_width=36; cd.dof.use_dof=False
    cam=D.objects.new(name,cd); sc.collection.objects.link(cam)
    for f,l,t in keys:
        cam.location=l; cam.rotation_euler=aim(l,t); cam.keyframe_insert('location',frame=f); cam.keyframe_insert('rotation_euler',frame=f)
    return cam
# SHOT 1 (1-90): camera reveal from the back of the room, slow push-in along the aisle
c1=mk('AttCam_1_reveal',35,[(1,(7.6,4.9,1.45),(6.0,13.3,2.3)),(90,(6.3,11.2,2.2),(6.0,13.38,2.7))])
c1.data.lens=35; c1.data.keyframe_insert('lens',frame=1); c1.data.lens=85; c1.data.keyframe_insert('lens',frame=90)
for fc in c1.data.animation_data.action.layers[0].strips[0].channelbags[0].fcurves: [setattr(k,'interpolation','BEZIER') for k in fc.keyframe_points]
# SHOT 2 (91-210): side view showing the monitored seating area (FOV volume visible)
c2=mk('AttCam_2_coverage',24,[(91,(10.25,4.9,2.65),(6.0,10.0,0.9)),(210,(10.25,8.6,2.75),(6.0,10.4,0.95))])
# SHOT 3 (211-300): the classroom camera's own point of view (render of the scene from the lens position)
c3=mk('AttCam_3_pov',20,[(211,(6.0,13.29,2.66),(6.0,9.0,0.9)),(300,(6.0,13.29,2.66),(6.0,9.0,0.9))])
for cam,f in zip((c1,c2,c3),(1,91,211)): sc.timeline_markers.new('A_'+cam.name,frame=f).camera=cam
sc.camera=c1; sc.frame_start=1; sc.frame_end=300
