"""Master timeline for the narrated 115 s trailer. VO = supplied ElevenLabs file (105.33 s). Film time T = VO time + VO_OFF.
Anchors come from silence analysis of the VO (no speech recogniser available): +/-0.4 s on word positions inside a clause."""
VO_OFF=4.0; VO_LEN=105.33; TOTAL=115.0; XF=0.25
def T(vo): return round(vo+VO_OFF,3)
# Door scene (human_entry native frames 45..398): GRANT frame 225 is pinned to the words "...access is granted"
DOOR_GRANT_T=33.2
def door_T(f): return DOOR_GRANT_T+(f-225)/30.0
def door_f(t): return 225+(t-DOOR_GRANT_T)*30.0
# Segment boundaries (film time)
SEG=[('open',0.0,15.5),('doorA',15.5,18.0),('sw_access',18.0,29.7),('doorB',29.7,38.97),('sw_entry',38.97,43.36),
     ('classroom',43.36,46.2),('camera',46.2,57.2),('att_results',57.2,61.5),
     ('dash_home',61.5,66.7),('dash_rooms',66.7,70.3),('dash_occ',70.3,73.3),('dash_status',73.3,77.7),('dash_auto',77.7,82.2),('prototype',82.2,86.4),('arch',86.4,95.6),('montage',95.6,99.1),('sw_map',99.1,105.7),('closing',105.7,TOTAL)]
def seg(name): return next((a,b) for n,a,b in SEG if n==name)
if __name__=='__main__':
    for n,a,b in SEG: print(f'{n:12s} {a:7.2f} {b:7.2f} {b-a:6.2f}')
