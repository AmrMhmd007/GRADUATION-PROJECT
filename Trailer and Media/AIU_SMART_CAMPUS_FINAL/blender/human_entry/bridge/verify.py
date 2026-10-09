import bpy, json, math
from mathutils import Vector
D=bpy.data; sc=bpy.context.scene
arm=D.objects[VARM]
F0,F1=VRANGE
tgt=D.objects['IK_L_target_'+arm.name]
cons=arm.pose.bones['hand_l'].constraints['AIU_IK']
rows=[]; prev=None
for F in range(F0,F1+1):
    sc.frame_set(F); bpy.context.view_layer.update()
    mw=arm.matrix_world
    hand=mw@arm.pose.bones['hand_l'].tail
    t=tgt.matrix_world.translation
    fl=mw@arm.pose.bones['foot_l'].head; fr=mw@arm.pose.bones['foot_r'].head
    bl=mw@arm.pose.bones['ball_l'].head; br=mw@arm.pose.bones['ball_r'].head
    rows.append(dict(F=F,infl=cons.influence,herr=(hand-t).length,fl=tuple(fl),fr=tuple(fr),bl=tuple(bl),br=tuple(br),
        minz=min(bl.z,br.z),pel=(mw@arm.pose.bones['pelvis'].head).z,hand=tuple(hand)))
json.dump(rows,open(ROOT_H+'/analysis/verify_'+arm.name+'.json','w'))
# summary
he=[r for r in rows if r['infl']>0.95]
print('hand contact frames',len(he),'max err (m)',round(max(r['herr'] for r in he),4) if he else None,'mean',round(sum(r['herr'] for r in he)/max(1,len(he)),4) if he else None)
bad=[(r['F'],round(r['herr'],3)) for r in he if r['herr']>0.02]; print('frames with hand err>2cm',bad[:40],len(bad))
# foot planting: ankle z < 0.11 => planted; slide = horizontal speed
sl=[]
for a,b in zip(rows,rows[1:]):
    for k in ('fl','fr'):
        pa,pb=a[k],b[k]
        if pa[2]<0.105 and pb[2]<0.105:
            sl.append((math.hypot(pb[0]-pa[0],pb[1]-pa[1])*100,b['F'],k))
sl.sort(reverse=True)
print('planted foot horizontal motion cm/frame top8',[(round(x,2),f,k) for x,f,k in sl[:8]])
walk=[x for x,f,k in sl if 70<f<150];
print('planted-foot slide during A-walk 70..150: median',round(sorted(walk)[len(walk)//2],2) if walk else None,'cm/frame (clip stance speed incl. body motion 3.3cm/f expected = body translation, planted foot should be ~0 world motion)')
print('min foot-ball z',round(min(r['minz'] for r in rows),3),'max ',round(max(r['minz'] for r in rows),3))
