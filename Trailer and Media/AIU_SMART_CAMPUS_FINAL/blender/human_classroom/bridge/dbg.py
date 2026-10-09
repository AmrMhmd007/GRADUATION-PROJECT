import bpy, math, os
from mathutils import Vector
def dbg_render(name, cam_loc, target, lens=35, frame=None, res=(640,360), samples=16, hide_chars=()):
    sc=bpy.context.scene; D=bpy.data
    cam=D.objects.get('DBG_cam')
    if cam is None:
        cd=D.cameras.new('DBG_cam'); cam=D.objects.new('DBG_cam',cd); sc.collection.objects.link(cam)
    cam.data.lens=lens; cam.data.dof.use_dof=False
    cam.location=cam_loc
    d=Vector(target)-Vector(cam_loc); cam.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
    saved=(sc.camera,sc.render.resolution_x,sc.render.resolution_y,sc.render.resolution_percentage,sc.render.filepath,sc.render.image_settings.file_format)
    mk=[(m,m.camera) for m in sc.timeline_markers]
    for m,_ in mk: m.camera=None
    sc.camera=cam
    sc.render.resolution_x,sc.render.resolution_y=res; sc.render.resolution_percentage=100
    eng=sc.render.engine
    if eng=='CYCLES':
        s0=sc.cycles.samples; sc.cycles.samples=samples
    if frame is not None: sc.frame_set(frame)
    out=os.path.expanduser('~/Desktop/AIU_SMART_CAMPUS_FINAL/blender/human_entry/renders/'+name)
    sc.render.filepath=out; sc.render.image_settings.file_format='PNG'
    bpy.ops.render.render(write_still=True)
    if eng=='CYCLES': sc.cycles.samples=s0
    for m,c in mk: m.camera=c
    sc.camera,sc.render.resolution_x,sc.render.resolution_y,sc.render.resolution_percentage,sc.render.filepath,sc.render.image_settings.file_format=saved
    print('dbg render',name,'engine',eng)
