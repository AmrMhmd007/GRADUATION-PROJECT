import bpy, math
from mathutils import Quaternion, Vector, Matrix
NS=bpy.app.driver_namespace
D=bpy.data
def ss(x): x=min(max(x,0.0),1.0); return x*x*(3-2*x)
def apply_pose(arm, pose):
    for pb in arm.pose.bones:
        q,l=pose[pb.name]; pb.rotation_quaternion=q; pb.location=l
def blend_pose(pa,pb_,w):
    out={}
    for k,(qa,la) in pa.items():
        qb,lb=pb_[k]; out[k]=(qa.slerp(qb,w), la.lerp(lb,w))
    return out
def clip_pose(name, t):
    S=NS[name]; n=len(S)-1; t=t%n; i=int(t); u=t-i
    return blend_pose(S[i],S[(i+1)%n if i+1>n else i+1],u) if u>1e-6 else S[i]
def place(arm,pos,heading):
    arm.rotation_mode='XYZ'; arm.location=(pos[0],pos[1],0.0); arm.rotation_euler=(0,0,heading+math.pi/2)
def ensure_ik(arm):
    sfx='_'+arm.name
    for nm in ('IK_L_target'+sfx,'IK_L_pole'+sfx):
        if nm not in D.objects:
            e=D.objects.new(nm,None); e.empty_display_type='SPHERE'; e.empty_display_size=0.03
            bpy.context.scene.collection.objects.link(e)
    pb=arm.pose.bones['hand_l']
    c=pb.constraints.get('AIU_IK') or pb.constraints.new('IK'); c.name='AIU_IK'
    c.target=D.objects['IK_L_target'+sfx]; c.pole_target=D.objects['IK_L_pole'+sfx]; c.pole_angle=math.radians(-90)
    c.chain_count=3; c.use_tail=True; c.use_stretch=False; c.iterations=200; c.influence=1.0
    return c
