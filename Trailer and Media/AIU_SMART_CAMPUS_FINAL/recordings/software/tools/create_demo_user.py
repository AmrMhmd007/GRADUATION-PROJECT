"""Create a TEST admin account in the ISOLATED simulation DB copy (never the real DB). Run with the backend venv python.
The password is generated here and stored only in recordings/software/.demo_credentials.json (local, not for sharing/committing)."""
import os, sys, json, secrets
SIM='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/simulated_occupancy_demo/sim_occupancy_demo.db'
REAL='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Source Code/backend/access_control.db'
os.environ['DATABASE_URL']=f'sqlite:///{SIM}'; os.environ['DISABLE_MQTT']='true'
sys.path.insert(0,'/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Source Code/backend')
from app.database import engine, SessionLocal
assert os.path.realpath(engine.url.database)==os.path.realpath(SIM) and os.path.realpath(engine.url.database)!=os.path.realpath(REAL)
from app import models, security
cred='/Users/amrmohamed/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL/recordings/software/.demo_credentials.json'
db=SessionLocal(); email='trailer.demo@example.edu'
old=db.query(models.User).filter(models.User.email=='trailer.demo@example.test').first()
if old is not None: db.delete(old); db.commit(); print('removed earlier .test demo row (my own, sim DB only)')
u=db.query(models.User).filter(models.User.email==email).first()
if os.path.exists(cred): pw=json.load(open(cred))['password']
else: pw=secrets.token_urlsafe(14)
if u is None:
    u=models.User(name='Demo Admin',email=email,role='admin',password_hash=security.hash_password(pw),must_change_password=False); db.add(u); db.commit(); print('created demo admin in SIM db only')
else:
    u.password_hash=security.hash_password(pw); u.must_change_password=False; db.commit(); print('updated demo admin password')
json.dump({'email':email,'password':pw},open(cred,'w')); os.chmod(cred,0o600); print('db',engine.url.database)
