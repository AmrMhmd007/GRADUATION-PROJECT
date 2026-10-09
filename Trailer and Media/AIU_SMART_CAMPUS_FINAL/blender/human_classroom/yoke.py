import bpy, bmesh
from mathutils import Vector
D=bpy.data
def add_yoke(shirt_name, body_name, zlo, zhi, xmax, off=0.016):
    sh=D.objects[shirt_name]; body=D.objects[body_name]
    if sh.get('yoke'): print('already'); return
    b=bmesh.new(); b.from_mesh(body.data)
    for v in b.verts: pass
    b.normal_update()
    keep=[v for v in b.verts if zlo<=v.co.z<=zhi and abs(v.co.x)<=xmax]
    ks=set(keep)
    # keep only faces whose verts are all kept
    faces=[f for f in b.faces if all(v in ks for v in f.verts)]
    geom_del=[f for f in b.faces if f not in set(faces)]
    bmesh.ops.delete(b,geom=geom_del,context='FACES')
    bmesh.ops.delete(b,geom=[v for v in b.verts if not v.link_faces],context='VERTS')
    b.normal_update()
    for v in b.verts: v.co=v.co+v.normal*off
    for f in b.faces: f.material_index=0
    tmp=D.meshes.new('yoke_tmp'); b.to_mesh(tmp); b.free()
    sb=bmesh.new(); sb.from_mesh(sh.data); n0=len(sb.verts)
    sb.from_mesh(tmp); sb.to_mesh(sh.data); sb.free(); sh.data.update(); D.meshes.remove(tmp)
    sh['yoke']=True
    print('yoke added to',shirt_name,'verts',n0,'->',len(sh.data.vertices))
add_yoke('M_Shirt','SuperHero_Male',1.38,1.545,0.30)
