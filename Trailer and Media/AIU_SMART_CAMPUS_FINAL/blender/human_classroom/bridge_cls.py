import bpy, math, random
from mathutils import Quaternion, Vector, Matrix
D=bpy.data; NS=bpy.app.driver_namespace
def set_action(arm, name):
    ad=arm.animation_data or arm.animation_data_create(); a=D.actions[name]; ad.action=a
    try: ad.action_slot=a.slots[0]
    except Exception as e: pass
def sample_clip(arm, act, n):
    set_action(arm, act); out=[]; sc=bpy.context.scene
    for f in range(n+1):
        sc.frame_set(f); bpy.context.view_layer.update()
        out.append({pb.name:(Quaternion(pb.rotation_quaternion), Vector(pb.location)) for pb in arm.pose.bones})
    return out
def ss(x): x=min(max(x,0.0),1.0); return x*x*(3-2*x)
def blend_pose(pa,pb_,w): return {k:(qa.slerp(pb_[k][0],w), la.lerp(pb_[k][1],w)) for k,(qa,la) in pa.items()}
def clip_pose(name,t):
    S=NS[name]; n=len(S)-1; t=t%n; i=int(t); u=t-i
    return blend_pose(S[i],S[i+1],u) if u>1e-6 else S[i]
def apply_pose(arm,pose):
    for pb in arm.pose.bones:
        q,l=pose[pb.name]; pb.rotation_quaternion=q; pb.location=l
def rot_arm(arm,bname,axis,ang):
    Rb=arm.data.bones[bname].matrix_local.to_3x3(); Rz=Matrix.Rotation(ang,3,axis)
    return (Rb.inverted()@Rz@Rb).to_quaternion()
def clone_char(src_name, new_name, col, tint=None):
    src=D.objects[src_name]; kids=[o for o in D.objects if o.parent==src]
    na=src.copy(); na.name=new_name; na.animation_data_clear(); col.objects.link(na)
    for k in kids:
        nk=k.copy(); nk.name=f'{new_name}__{k.name}'; col.objects.link(nk)
        nk.parent=na; nk.matrix_parent_inverse=k.matrix_parent_inverse.copy()
        for m in nk.modifiers:
            if m.type=='ARMATURE': m.object=na
        if tint and k.name in tint:
            nk.data=k.data.copy()
            for i,s in enumerate(nk.material_slots):
                m=s.material.copy(); m.name=f'{new_name}_{k.name}_mat'; s.material=m
                for nd in m.node_tree.nodes:
                    if nd.type=='BSDF_PRINCIPLED' and tint[k.name] is not None:
                        # tint: multiply existing base colour by given rgb via simple replace when no link
                        if not nd.inputs['Base Color'].is_linked: nd.inputs['Base Color'].default_value=(*tint[k.name],1)
                    if nd.type=='VALTORGB' and tint[k.name] is not None:
                        c=tint[k.name]; nd.color_ramp.elements[0].color=(c[0]*.55,c[1]*.55,c[2]*.55,1); nd.color_ramp.elements[1].color=(c[0]*1.25,c[1]*1.25,c[2]*1.25,1)
    return na
