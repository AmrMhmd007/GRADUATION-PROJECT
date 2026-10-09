"""Prepare DEMONSTRATION data in the ISOLATED simulation DB copy only (never the real DB):
 1) anonymise the copied doctor row (shown by the real UI) -> 'Demo Doctor'
 2) create one temporary access window on Room A101 for that doctor through the real API (POST /api/access-windows) so the real
    'Check authorization now' feature has something to evaluate."""
import os, sys, json, datetime, urllib.request
SIM='/Users/amrmohamed/Desktop/AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/sim_occupancy_demo.db'
REAL='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Source Code/backend/access_control.db'
os.environ['DATABASE_URL']=f'sqlite:///{SIM}'; os.environ['DISABLE_MQTT']='true'
sys.path.insert(0,'/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Source Code/backend')
from app.database import engine, SessionLocal
assert os.path.realpath(engine.url.database)==os.path.realpath(SIM)!=os.path.realpath(REAL)
from app import models
db=SessionLocal(); u=db.get(models.User,2)
print('before:',u.role)
u.name='Demo Doctor'; u.email='demo.doctor@example.edu'; u.photo_url=None; u.phone=None; db.commit(); print('anonymised user 2 in SIM db')
c=json.load(open('/Users/amrmohamed/Desktop/AIU_SMART_CAMPUS_FINAL/recordings/software/.demo_credentials.json'))
def call(path,body=None,tok=None,method=None):
    req=urllib.request.Request('http://127.0.0.1:8001'+path,data=json.dumps(body).encode() if body is not None else None,method=method or ('POST' if body is not None else 'GET'),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+tok} if tok else {})})
    return json.load(urllib.request.urlopen(req))
tok=call('/api/auth/login',{'email':c['email'],'password':c['password']})['access_token']
wins=call('/api/access-windows',tok=tok)
if not any(w.get('door_id')==1 and w.get('user_id')==2 for w in wins):
    now=datetime.datetime.utcnow()
    w=call('/api/access-windows',{'door_id':1,'user_id':2,'recurring':False,'start_at':(now-datetime.timedelta(hours=1)).isoformat(),'end_at':(now+datetime.timedelta(days=120)).isoformat(),'reason':'DEMO window (simulation database)'},tok)
    print('created window',w.get('access_window_id'))
else: print('window exists')
