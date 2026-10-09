import bpy, math, json
from mathutils import Vector
D=bpy.data; sc=bpy.context.scene
RAD={'thigh':.085,'calf':.06,'foot':.05,'ball':.04,'spine':.12,'pelvis':.13,'neck':.05,'Head':.10,'upperarm':.05,'lowerarm':.045,'hand':.05,'clavicle':.05}
def rad(b):
    for k,v in RAD.items():
        if b.startswith(k): return v
    return 0.025
solids=[o for o in D.objects if o.type=='MESH' and (o.name.startswith(('Desk_','TeacherDesk','Chair_')) or o.name=='Platform') and not o.hide_render]
def box_dist(o,p):
    q=o.matrix_world.inverted()@p; bb=[Vector(c) for c in o.bound_box]
    mn=Vector((min(c.x for c in bb),min(c.y for c in bb),min(c.z for c in bb))); mx=Vector((max(c.x for c in bb),max(c.y for c in bb),max(c.z for c in bb)))
    c=Vector((min(max(q.x,mn.x),mx.x),min(max(q.y,mn.y),mx.y),min(max(q.z,mn.z),mx.z)))
    return (o.matrix_world@c-p).length
chars=[o for o in D.objects if o.type=='ARMATURE' and o.name.startswith('CLS_') and not o.hide_render]
viol={}; minsep=9; stats=[]
for F in range(1,301,15):
    sc.frame_set(F); bpy.context.view_layer.update()
    pts={}
    for a in chars:
        P=[]
        for pb in a.pose.bones:
            r=rad(pb.name)*a.scale.z
            if pb.name.startswith(('index','middle','ring','pinky','thumb')): continue
            for t in (0,0.5,1.0): P.append((pb.name,a.matrix_world@(pb.head+(pb.tail-pb.head)*t),r))
        pts[a.name]=P
    for a in chars:
        own=a.name.replace('CLS_stu_','Chair_')
        for bn,p,r in pts[a.name]:
            if p.z<0.0-0.02: viol.setdefault((a.name,'floor'),[]).append(F)
            for o in solids:
                if o.name.startswith(own+'_') or (o.name.startswith('Platform') and a.name=='CLS_lecturer'): 
                    # own chair: only back/post vs spine/head handled below
                    if '_back' in o.name and bn.startswith(('spine','Head','neck','pelvis')):
                        d=box_dist(o,p)-r
                        if d<-0.01: viol.setdefault((a.name,o.name,bn[:6]),[]).append((F,round(d,3)))
                    continue
                d=box_dist(o,p)-r
                if d<-0.01 and not (a.name=='CLS_lecturer' and o.name.startswith('Platform')):
                    viol.setdefault((a.name,o.name,bn[:8]),[]).append((F,round(d,3)))
    names=list(pts)
    for i in range(len(names)):
        for j in range(i+1,len(names)):
            d=min(((p-q).length-r1-r2) for _,p,r1 in pts[names[i]] for _,q,r2 in pts[names[j]])
            minsep=min(minsep,d)
            if d<0: viol.setdefault((names[i],names[j],'mutual'),[]).append((F,round(d,3)))
# lecturer on platform: feet inside platform bounds
pl=D.objects['Platform']; 
print('characters',len(chars),'solids',len(solids),'min inter-character separation (m)',round(minsep,3))
print('violations (pen > 1cm):',len(viol))
for k,v in list(viol.items())[:30]: print(k,v[:3],len(v))
