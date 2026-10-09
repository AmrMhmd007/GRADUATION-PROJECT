exec(open('/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/blender/human_classroom/bridge_cls.py').read())
import json, os
sc=bpy.context.scene; col=D.collections['HUMANS_CLASS']
F0,F1=1,300
for a in [a for a in D.actions if a.name.startswith('CLS_')]: D.actions.remove(a)
for o in list(D.objects):
    if o.name.startswith('CLS_'): D.objects.remove(o,do_unlink=True)
for n in ('ARM_Instructor','ARM_Student_F'):
    for o in [D.objects[n]]+[k for k in D.objects if k.parent==D.objects[n]]: o.hide_render=True; o.hide_viewport=True   # templates stay hidden
W=lambda r,g,b:(r,g,b)
SEATS=[ # tag, who, shirt, hair, trousers, scale, phase, talking
 ('01','F',(0.16,0.20,0.36),(0.02,0.012,0.01),None,0.97,0,False),
 ('04','M',(0.45,0.52,0.60),(0.015,0.01,0.008),None,0.99,13,False),
 ('10','M',(0.30,0.05,0.07),(0.03,0.02,0.015),None,1.00,27,False),
 ('13','F',(0.82,0.80,0.76),(0.05,0.03,0.02),None,0.95,7,True),
 ('15','F',(0.20,0.33,0.28),(0.018,0.012,0.01),None,0.96,31,False),
 ('22','M',(0.60,0.62,0.64),(0.04,0.03,0.02),None,0.98,19,False),
 ('31','F',(0.55,0.20,0.24),(0.03,0.018,0.012),None,0.94,3,False),
 ('34','M',(0.12,0.14,0.20),(0.02,0.012,0.008),None,0.99,41,False),
 ('43','F',(0.75,0.72,0.60),(0.045,0.028,0.02),None,0.96,23,False)]
def mk_action(arm, name, frames, posefn):
    a=D.actions.new(name); sl=a.slots.new('OBJECT',arm.name); ly=a.layers.new('L'); st=ly.strips.new(type='KEYFRAME'); cb=st.channelbag(sl,ensure=True)
    ad=arm.animation_data_create(); ad.action=a; ad.action_slot=sl
    bones=[pb.name for pb in arm.pose.bones]
    fcs={}
    for b in bones:
        for i in range(4): fcs[(b,'q',i)]=cb.fcurves.new(f'pose.bones["{b}"].rotation_quaternion',index=i,group_name=b)
        if b in ('root','pelvis'):
            for i in range(3): fcs[(b,'l',i)]=cb.fcurves.new(f'pose.bones["{b}"].location',index=i,group_name=b)
    data={k:[] for k in fcs}
    for F in frames:
        pose=posefn(F)
        for b in bones:
            q,l=pose[b]
            for i in range(4): data[(b,'q',i)].append((F,q[i]))
            if b in ('root','pelvis'):
                for i in range(3): data[(b,'l',i)].append((F,l[i]))
    for k,fc in fcs.items():
        pts=data[k]; fc.keyframe_points.add(len(pts))
        fc.keyframe_points.foreach_set('co',[v for p in pts for v in p])
        fc.keyframe_points.foreach_set('interpolation',[1]*len(pts)); fc.update()
def head_motion(arm,pose,F,ph,amp_yaw,amp_pitch,bias_yaw=0.0):
    yaw=math.radians(bias_yaw)+math.radians(amp_yaw)*(0.6*math.sin(2*math.pi*(F+ph*7)/190)+0.4*math.sin(2*math.pi*(F+ph*3)/113+ph))
    pit=math.radians(amp_pitch)*math.sin(2*math.pi*(F+ph*5)/151+ph*0.7)
    for nm,fr in (('neck_01',0.4),('Head',0.6)):
        q=rot_arm(arm,nm,'Z',yaw*fr)@rot_arm(arm,nm,'X',pit*fr); q0,l0=pose[nm]; pose[nm]=(q@q0,l0)
    return pose
info=[]
for tag,who,shirt,hair,trs,sc_,ph,talk in SEATS:
    ch=D.objects[f'Chair_{tag}']; desk=D.objects[f'Desk_{tag}_top']
    src='ARM_Student_F' if who=='F' else 'ARM_Instructor'
    pre='F' if who=='F' else 'M'
    arm=clone_char(src,f'CLS_stu_{tag}',col,{f'{pre}_Shirt':shirt,f'{pre}_Hair':hair})
    for o in [arm]+[k for k in D.objects if k.parent==arm]: o.hide_render=False; o.hide_viewport=False
    rz=ch.rotation_euler.z+math.pi
    arm.rotation_mode='XYZ'; arm.rotation_euler=(0,0,rz)
    s=sc_*(0.90 if who=='M' else 1.0)
    arm.scale=(s*(0.92 if who=='M' else 0.98),s,s)
    # place pelvis (armature-local (0,0.324)) at chair centre +6cm forward
    fwd=Vector((math.sin(rz+math.pi)*-1,0,0))
    R=Matrix.Rotation(rz,3,'Z'); loc_pel=Vector((0,0.324*s,0));
    target=Vector((ch.location.x,ch.location.y,0))+Matrix.Rotation(ch.rotation_euler.z,3,'Z')@Vector((0,0.06,0))
    arm.location=target-R@loc_pel
    clip='Sitting_Talking_Loop' if talk else 'Sitting_Idle_Loop'; n=len(NS[clip])-1
    def pf(F,arm=arm,clip=clip,n=n,ph=ph,talk=talk):
        p=dict(clip_pose(clip,(F+ph*5)%n)); return head_motion(arm,p,F,ph,10 if not talk else 8,5,bias_yaw=0)
    mk_action(arm,f'CLS_{tag}_action',range(F0,F1+1),pf)
    info.append((tag,who,tuple(round(x,3) for x in arm.location)))
# lecturer
lec=clone_char('ARM_Instructor','CLS_lecturer',col,{'M_Shirt':(0.10,0.17,0.30),'M_Hair':(0.02,0.012,0.01)})
for o in [lec]+[k for k in D.objects if k.parent==lec]: o.hide_render=False; o.hide_viewport=False
lec.rotation_mode='XYZ'; lec.rotation_euler=(0,0,math.radians(22)); lec.scale=(0.86,0.92,0.93); lec.location=(5.0,12.55,0.12)
def lf(F):
    p=dict(blend_pose(clip_pose('Idle_Talking_Loop',F%88),clip_pose('Idle_Loop',(F*0.7)%75),0.25*(0.5+0.5*math.sin(F/45.0))))
    return head_motion(lec,p,F,5,16,4,bias_yaw=-8)
mk_action(lec,'CLS_lecturer_action',range(F0,F1+1),lf)
sc.frame_start=F0; sc.frame_end=F1
json.dump(info,open('/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/blender/human_classroom/seat_info.json','w'))
print('built',len(info),'students + lecturer')
