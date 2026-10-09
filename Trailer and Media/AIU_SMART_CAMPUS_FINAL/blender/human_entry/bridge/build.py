# builds the door-entry animation for ARM_Instructor. exec'd inside Blender via bridge.
import bpy, math, json, os
from mathutils import Quaternion, Vector, Matrix, Euler
exec(open(ROOT_H+'/bridge/lib.py').read())
exec(open(ROOT_H+'/bridge/pathlib_.py').read())
sc=bpy.context.scene
P=dict(arm='ARM_Student_F',F0=45,FEND=398,vmax=1.1,fB=296,reach0=230,reach1=244,release=268,STAND=(1.12,8.42))
P.update(PARAMS if 'PARAMS' in globals() else {})
arm=D.objects[P['arm']]
F0,FEND=P['F0'],P['FEND']
STRIDE=1.3   # m per 40-frame walk cycle (measured from UAL foot travel)
# ---------- lever: press DOWN (approved file lifts it); only in this working copy
act=D.actions['Lever_pivotAction']
if not act.get('aiu_flipped'):
    for fc in act.fcurves if hasattr(act,'fcurves') else [f for l in act.layers for s in l.strips for cb in s.channelbags for f in cb.fcurves]:
        if fc.data_path=='rotation_euler' and fc.array_index==0:
            for k in fc.keyframe_points:
                k.co[1]*=-1; k.handle_left[1]*=-1; k.handle_right[1]*=-1
    act['aiu_flipped']=True
hinge=D.objects['Door_Hinge']; lev=D.objects['Lever_pivot']
# ---------- sample door state
door={}
for F in range(1,FEND+1):
    sc.frame_set(F); bpy.context.view_layer.update()
    ang=hinge.rotation_euler.z
    grip=lev.matrix_world@Vector((-0.03,-0.075,0.0))
    leaf=hinge.matrix_world@Vector((-0.045,-0.80,1.07))
    door[F]=dict(ang=ang,grip=grip.copy(),leaf=leaf.copy(),hx=hinge.matrix_world.translation.copy())
def seg_d(p,a_,b_):
    ax,ay=a_;bx,by=b_;px,py=p; dx,dy=bx-ax,by-ay; L2=dx*dx+dy*dy
    t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L2)) if L2>0 else 0
    return math.hypot(px-(ax+t*dx),py-(ay+t*dy))
def rect_d(p,x0,x1,y0,y1):
    dx=max(x0-p[0],0,p[0]-x1); dy=max(y0-p[1],0,p[1]-y1); return math.hypot(dx,dy)
RECTS=[('latchjamb',1.335,1.465,8.44,8.50),('hingejamb',1.335,1.465,9.50,9.56),('wallS',1.4,1.5,0,8.44),('wallN',1.4,1.5,9.56,12),('chair',2.35,2.75,8.8,9.2),('chairS',2.35,2.75,7.2,7.6),('roomwallS',1.5,1.6,6.0,8.44)]
def door_clear(pos,F,r=0.20,detail=False):
    a=door[F]['ang']; hx,hy=1.4,9.495
    ex,ey=hx+0.96*math.sin(a),hy-0.96*math.cos(a)
    c={'leaf':seg_d(pos,(hx,hy),(ex,ey))-0.025}
    for n,*q in RECTS: c[n]=rect_d(pos,*q)
    k=min(c,key=c.get)
    return (c[k]-r,k) if detail else c[k]-r
# ---------- speed profiles
def ramp_profile(f0,S,vmax,up,down):
    def integ(fe):
        s=0.0; out={}
        f=f0
        while f<=fe+1:
            v=vmax*ss((f-f0)/up)*(ss((fe-f)/down) if down>0 else 1.0)
            out[f]=(s,v); s+=v/30.0; f+=1
        return out,s
    lo,hi=f0+20,f0+600
    for _ in range(50):
        mid=(lo+hi)/2; _,s=integ(mid)
        if s<S: lo=mid
        else: hi=mid
    out,s=integ(hi); return out,hi
STAND=P['STAND']
A=hermite((-0.35,5.0),dirv(80,3.0),STAND,dirv(-10,2.0)); sA=poly_arc(A); SA=sA[-1]
profA,feA=ramp_profile(F0,SA,P['vmax'],15,22)
ph0A=-(40*SA/STRIDE)%20
def mkB(pts):
    out=[]
    for i in range(len(pts)-1):
        (p0,h0),(p1,h1)=pts[i],pts[i+1]
        seg=hermite(p0,dirv(h0[0],h0[1]),p1,dirv(h1[0],h1[1]),120); out+= seg if i==0 else seg[1:]
    return out
B=mkB([(STAND,(80,0.7)),((1.08,8.86),(75,0.7)),((1.58,9.02),(5,0.8)),((1.82,8.75),(-55,0.7)),((2.0,7.7),(-90,1.2))]); sB=poly_arc(B); SB=sB[-1]
# ---------- build per-frame records
vB=0.85
def sB_at(f):
    if f<P['fB']: return 0.0,0.0
    s=0.0
    for g in range(P['fB'],f):
        s+=vB*ss((g-P['fB'])/22.0)/30.0
    return s, vB*ss((f-P['fB'])/22.0)
def unwrap(prev,a):
    while a-prev>math.pi: a-=2*math.pi
    while a-prev<-math.pi: a+=2*math.pi
    return a
recs={}
yaw=None
head_stand=math.atan2(0,1)
for F in range(F0,FEND+1):
    r={}
    if F<=feA and F in profA and F<P['reach0']:
        s,v=profA[F]; s=min(s,SA); pos,hd=at(A,sA,s)
        # smooth heading: look ahead 0.3m
        _,hd=at(A,sA,min(s+0.35,SA)) if s<SA-0.01 else (None,hd)
        phase=ph0A+40*s/STRIDE; mode='A'
    elif F<P['fB']:
        pos,_=at(A,sA,SA); v=0.0; phase=0; mode='stand'
        _,hd=at(A,sA,SA)
        hd=math.radians(-10)
        if F>=P['reach0']:
            hd=math.radians(-10)+(math.radians(40)-math.radians(-10))*ss((F-(P['reach0']))/20.0)
        if F>=P['release']:
            hd=math.radians(40)+(math.radians(78)-math.radians(40))*ss((F-P['release'])/30.0)
    else:
        s,v=sB_at(F); pos,hd=at(B,sB,min(s,SB-1e-6)); phase=10+40*s/STRIDE; mode='B'
        _,hd=at(B,sB,min(s+0.3,SB-1e-6))
    hd=unwrap(yaw if yaw is not None else hd,hd)
    yaw=hd if yaw is None else yaw+(hd-yaw)*(0.35 if F<P['reach0'] else 0.14)
    r.update(pos=pos,yaw=yaw,v=v,phase=phase,mode=mode,w=ss(v/0.75))
    recs[F]=r
# ---------- clearance search is done by caller; compute body clearance now
minclear=(9,None)
for F,r in recs.items():
    if F>=240:
        c=door_clear(r['pos'],F)
        if c<minclear[0]: minclear=(c,F)
print('min body-door clearance',round(minclear[0],3),'at frame',minclear[1],'fB',P['fB'],'feA',round(feA,1),'SA',round(SA,2),'SB',round(SB,2))
# ---------- pose composition
def rest3(bname):
    return arm.data.bones[bname].matrix_local.to_3x3()
def rot_arm(bname, axis, ang):
    Rb=rest3(bname); Rz=Matrix.Rotation(ang,3,axis)
    return (Rb.inverted()@Rz@Rb).to_quaternion()
def smooth_hold(F,a,b,c,d):   # 0 before a, ramp a..b, 1 until c, ramp down c..d
    return ss((F-a)/(b-a))*(1-ss((F-c)/(d-c)))
IKP={'start':P['reach0'],'full':P['reach1'],'release':P['release']}
ad=arm.animation_data or arm.animation_data_create()
ad.action=None
newact=D.actions.new('HUMAN_'+arm.name+'_DoorEntry_v1'); ad.action=newact
cons=ensure_ik(arm); tgt=D.objects['IK_L_target_'+arm.name]; pole=D.objects['IK_L_pole_'+arm.name]
for o in (tgt,pole):
    o.animation_data_clear()
arm.animation_data_clear(); ad=arm.animation_data_create(); ad.action=newact
arm.rotation_mode='XYZ'
log=[]
first=True
for F in range(F0,FEND+1):
    r=recs[F]
    sc.frame_set(F)   # evaluates door (not the character: action is empty so far)
    pose=blend_pose(clip_pose('Idle_Loop',(F-F0)%75), clip_pose('Walk_Formal_Loop',r['phase']%40), r['w'])
    # head look at reader (before/while verifying), then back to door
    look=smooth_hold(F,150,166,226,238)
    g=math.radians(26)*look
    if g>1e-4:
        for nm,fr in (('neck_01',0.4),('Head',0.6)):
            q=rot_arm(nm,'Z',-g*fr); q0,l0=pose[nm]; pose[nm]=(q@q0,l0)
        for nm,fr in (('neck_01',0.4),('Head',0.6)):
            q=rot_arm(nm,'X',math.radians(3.5)*look*fr); q0,l0=pose[nm]; pose[nm]=(q@q0,l0)
    apply_pose(arm,pose)
    arm.location=(r['pos'][0],r['pos'][1],0.0); arm.rotation_euler=(0,0,r['yaw']+math.pi/2)
    # IK influence + targets
    infl=smooth_hold(F,IKP['start'],IKP['full'],IKP['release'],IKP['release']+10)
    d=door[F]
    t=d['grip']+Vector((0,0,0.022))+Vector((0,0,0.06))*(1-ss((F-236)/9.0))
    if F>=P['release']: t=t+Vector((-0.03,0,0.10))*ss((F-P['release'])/8.0)
    tgt.location=t
    fw=Vector((math.cos(r['yaw']),math.sin(r['yaw']),0)); lf=Vector((-fw.y,fw.x,0))
    pole.location=Vector((r['pos'][0],r['pos'][1],0.0))+lf*0.9+fw*(-0.35)+Vector((0,0,0.95))
    cons.influence=infl
    # keys
    for pb in arm.pose.bones:
        pb.keyframe_insert('rotation_quaternion',frame=F)
        if pb.name in ('root','pelvis'): pb.keyframe_insert('location',frame=F)
    arm.keyframe_insert('location',frame=F); arm.keyframe_insert('rotation_euler',frame=F)
    cons.keyframe_insert('influence',frame=F)
    tgt.keyframe_insert('location',frame=F); pole.keyframe_insert('location',frame=F)
    log.append(dict(F=F,pos=list(r['pos']),yaw=r['yaw'],v=r['v'],w=r['w'],infl=infl,mode=r['mode'],ang=d['ang'],tgt=list(t),clear=door_clear(r['pos'],F)))
os.makedirs(ROOT_H+'/analysis',exist_ok=True)
json.dump(log,open(ROOT_H+'/analysis/entry_records.json','w'),indent=0)
print('baked frames',F0,FEND)
