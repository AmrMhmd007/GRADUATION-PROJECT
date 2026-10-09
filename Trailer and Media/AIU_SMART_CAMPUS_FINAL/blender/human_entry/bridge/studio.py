import bpy, math
D=bpy.data
R='/Users/amrmohamed/Desktop/AIU_SMART_CAMPUS_FINAL/blender/human_entry/renders'
def studio(out, cam_loc, cam_rot_deg, lens=50, res=(1280,640), samples=24, frame=None):
    sc=bpy.context.scene
    for m in sc.timeline_markers:
        if m.camera: m.camera=None
    hid=[]
    for o in D.objects:
        if o.users_collection and o.users_collection[0].name!='HUMANS' and o.type in ('MESH','LIGHT','CURVE','FONT') and not o.name.startswith('TMP'):
            hid.append((o,o.hide_render)); o.hide_render=True
    bpy.ops.object.light_add(type='SUN', location=(0,-6,5)); sun=bpy.context.object; sun.name='TMP_sun'; sun.data.energy=2.2; sun.rotation_euler=(math.radians(50),0,math.radians(20))
    bpy.ops.mesh.primitive_plane_add(size=30, location=(4,-3,0)); fl=bpy.context.object; fl.name='TMP_floor'
    cam=D.objects.new('TMP_cam', D.cameras.new('TMP_cam')); sc.collection.objects.link(cam); cam.data.lens=lens
    cam.location=cam_loc; cam.rotation_euler=tuple(math.radians(a) for a in cam_rot_deg)
    old=sc.camera; sc.camera=cam; r=sc.render; r.resolution_x,r.resolution_y=res; sc.cycles.samples=samples
    ow=sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value if sc.world and sc.world.use_nodes else None
    if frame is not None: sc.frame_set(frame)
    sc.render.filepath=R+'/'+out
    try: bpy.ops.render.render(write_still=True)
    finally:
        for o,h in hid: o.hide_render=h
        for n in ('TMP_sun','TMP_floor','TMP_cam'): D.objects.remove(D.objects[n], do_unlink=True)
        sc.camera=old
    print('studio render ->',out)
