import math
def hermite(p0,t0,p1,t1,n=400):
    pts=[]
    for i in range(n+1):
        u=i/n; h00=2*u**3-3*u**2+1; h10=u**3-2*u**2+u; h01=-2*u**3+3*u**2; h11=u**3-u**2
        pts.append((h00*p0[0]+h10*t0[0]+h01*p1[0]+h11*t1[0], h00*p0[1]+h10*t0[1]+h01*p1[1]+h11*t1[1]))
    return pts
def poly_arc(pts):
    s=[0.0]
    for a,b in zip(pts,pts[1:]): s.append(s[-1]+math.hypot(b[0]-a[0],b[1]-a[1]))
    return s
def at(pts,s,d):
    if d<=0: i=0
    elif d>=s[-1]: i=len(pts)-2
    else:
        lo,hi=0,len(s)-1
        while hi-lo>1:
            m=(lo+hi)//2
            if s[m]<=d: lo=m
            else: hi=m
        i=lo
    seg=s[i+1]-s[i] or 1e-9; u=min(max((d-s[i])/seg,0),1)
    a,b=pts[i],pts[i+1]
    return (a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u), math.atan2(b[1]-a[1],b[0]-a[0])
def dirv(deg,m): return (m*math.cos(math.radians(deg)), m*math.sin(math.radians(deg)))
