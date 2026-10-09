"""Synth primitives (original, procedural). Copied from audio_v4/make_audio.py; no third-party audio."""
"""ORIGINAL procedural music + SFX for AIU SMART CAMPUS review cut v4. No third-party audio is used.
Everything is synthesised here with numpy/scipy (sine/triangle/saw oscillators, filtered noise, convolution reverb). No voice."""
import numpy as np, wave, sys, json
from scipy import signal
SR=48000; rng=np.random.default_rng(7)
def t_(d): return np.arange(int(d*SR))/SR
def env(n,a=0.005,d=0.2,pw=3):
    t=np.arange(n)/SR; e=np.exp(-t/d)**pw if False else np.exp(-t/d); e*=np.minimum(1,t/max(a,1e-4)); return e
def place(buf,x,at,gain=1.0,pan=0.0):
    i=int(at*SR);
    if i>=len(buf) or i+len(x)<0: return
    x=x[:max(0,len(buf)-i)]; l=gain*np.sqrt(0.5*(1-pan)); r=gain*np.sqrt(0.5*(1+pan))
    buf[i:i+len(x),0]+=x*l; buf[i:i+len(x),1]+=x*r
def lp(x,fc,o=2): return signal.sosfilt(signal.butter(o,fc/(SR/2),'low',output='sos'),x)
def hp(x,fc,o=2): return signal.sosfilt(signal.butter(o,fc/(SR/2),'high',output='sos'),x)
def bp(x,f0,f1,o=2): return signal.sosfilt(signal.butter(o,[f0/(SR/2),f1/(SR/2)],'band',output='sos'),x)
def sine(f,d,ph=0): t=t_(d); return np.sin(2*np.pi*f*t+ph)
def glide(f0,f1,d): t=t_(d); f=f0*(f1/f0)**(t/d); return np.sin(2*np.pi*np.cumsum(f)/SR)
def noise(d): return rng.standard_normal(int(d*SR))
def fade(x,a=0.01,b=0.02):
    n=len(x); x=x.copy(); na=int(a*SR); nb=int(b*SR); x[:na]*=np.linspace(0,1,na); x[-nb:]*=np.linspace(1,0,nb); return x
# ---------- SFX ----------
def tick(f=1900,d=0.05): return fade(sine(f,d)*env(int(d*SR),0.001,0.012))
def blip(f=880,d=0.12): return fade(sine(f,d)*env(int(d*SR),0.004,0.05))
def chime(f=784,d=0.9): x=sine(f,d)+0.4*sine(f*1.5,d)+0.2*sine(f*2,d); return fade(x*env(len(x),0.004,0.28)*0.5,0.002,0.05)
def hollow(f=440,d=0.5): t=t_(d); x=signal.sawtooth(2*np.pi*f*t,0.5)*0.5; x=lp(x,1100); x*= (0.6+0.4*np.sin(2*np.pi*6*t)); return fade(x*env(len(x),0.01,0.18),0.005,0.05)
def boom(d=2.8): x=glide(78,34,d)*env(int(d*SR),0.004,0.7)+0.5*lp(noise(d),240)*env(int(d*SR),0.002,0.35); return fade(x,0.001,0.1)
def whoosh(d=1.0,f0=300,f1=3000,up=True):
    n=noise(d); t=np.linspace(0,1,len(n)); out=np.zeros_like(n)
    fc=np.geomspace(f0,f1,len(n)) if up else np.geomspace(f1,f0,len(n))
    # swept bandpass via block processing
    B=2048
    for i in range(0,len(n),B):
        f=fc[min(i,len(n)-1)]; out[i:i+B]=bp(n[i:i+B+0],max(60,f*0.6),min(f*1.6,SR/2-100),1) if False else out[i:i+B]
    # simpler: amplitude-swelled filtered noise
    x=bp(n,f0,f1); sh=np.sin(np.pi*t)**2; return fade(x*sh,0.01,0.05)
def lock_release():
    c1=hp(noise(0.03),2500)*env(int(0.03*SR),0.0005,0.006); th=sine(118,0.18)*env(int(0.18*SR),0.001,0.045)
    x=np.zeros(int(0.5*SR)); x[:len(c1)]+=c1*0.9; x[int(0.012*SR):int(0.012*SR)+len(th)]+=th*0.9
    c2=hp(noise(0.02),3500)*env(int(0.02*SR),0.0005,0.004); x[int(0.17*SR):int(0.17*SR)+len(c2)]+=c2*0.7; return x
def handle():
    c=bp(noise(0.05),1800,5200)*env(int(0.05*SR),0.0005,0.012); cl=sine(210,0.14)*env(int(0.14*SR),0.001,0.03)
    x=np.zeros(int(0.45*SR)); x[:len(c)]+=c; x[:len(cl)]+=0.7*cl
    c2=bp(noise(0.03),1500,4500)*env(int(0.03*SR),0.0005,0.008); x[int(0.3*SR):int(0.3*SR)+len(c2)]+=0.6*c2; return x
def door_open(d=2.6):
    n=noise(d); t=t_(d); sw=np.sin(np.pi*np.minimum(1,t/d))**1.5
    air=bp(n,150,900)*sw*0.5; hinge=bp(noise(d),520,780)*(sw**3)*0.25*(0.7+0.3*np.sin(2*np.pi*3.5*t))
    return fade(air+hinge,0.05,0.4)
def sweep(d=1.5):
    t=t_(d); x=glide(280,1500,d)*0.5*np.sin(np.pi*np.minimum(1,t/d)*0.5+0.0)**2
    return fade(x*0.8+0.25*bp(noise(d),1500,6000)*(t/d)**2,0.02,0.15)
def room_tone(d): return lp(noise(d),420,2)*0.035+bp(noise(d),120,260)*0.03
# ---------- music ----------
BPM=96; BEAT=60/BPM; BAR=4*BEAT
NOTE={'D':146.83,'Bb':116.54,'F':87.31,'C':130.81,'A':110.0,'Gm':98.0}
def mtof(m): return 440*2**((m-69)/12)
CH=[('Dm',[50,53,57,62]),('Bb',[46,53,58,62]),('F',[53,57,60,65]),('C',[48,55,60,64])]
def pad(notes,d,gain=1.0):
    n=int(d*SR); t=np.arange(n)/SR; x=np.zeros(n)
    for m in notes:
        for det in (-0.07,0.0,0.06):
            f=mtof(m)*2**(det/12); x+=signal.sawtooth(2*np.pi*f*t)*0.12+np.sin(2*np.pi*f*t)*0.08
    x=lp(x,1500+900*np.sin(t*0.4)) if False else lp(x,1700)
    a=np.minimum(1,t/1.2)*np.minimum(1,(d-t)/1.2); return x*a*gain
def pluck(m,d=0.5):
    t=t_(d); f=mtof(m); x=(np.sin(2*np.pi*f*t)+0.3*np.sin(4*np.pi*f*t)+0.15*np.sin(6*np.pi*f*t))*np.exp(-t/0.14); return fade(x*0.5,0.002,0.05)
