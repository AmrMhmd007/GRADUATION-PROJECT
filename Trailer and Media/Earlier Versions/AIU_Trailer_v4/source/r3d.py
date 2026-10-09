"""Small software 3D renderer (perspective camera, lambert shading, soft floor
shadows, fog, bloom, vignette) built on numpy + pycairo + OpenCV. Used because
Blender is not installable in this environment. Scenes are CONCEPTUAL visualisations."""
import math
import numpy as np
import cairo
import cv2

W, H = 1920, 1080


def rotx(a): c, s = math.cos(a), math.sin(a); return np.array([[1,0,0],[0,c,-s],[0,s,c]])
def roty(a): c, s = math.cos(a), math.sin(a); return np.array([[c,0,s],[0,1,0],[-s,0,c]])
def rotz(a): c, s = math.cos(a), math.sin(a); return np.array([[c,-s,0],[s,c,0],[0,0,1]])


def hexc(h):
    h = h.lstrip('#'); return np.array([int(h[i:i+2], 16) / 255 for i in (0, 2, 4)])


class Faces:
    """Accumulates quads. Triangles are stored as degenerate quads."""
    def __init__(self):
        self.P = []; self.C = []; self.A = []; self.F = []   # F flags: bit0 emissive,1 two-sided,2 floor,3 shadow-caster
    def add(self, verts, color, alpha=1.0, emissive=False, two=False, floor=False, shadow=False, decal=False):
        v = np.asarray(verts, float)
        if len(v) == 3: v = np.vstack([v, v[2]])
        self.P.append(v); self.C.append(color if not isinstance(color, str) else hexc(color)); self.A.append(alpha)
        self.F.append(int(emissive) | int(two) << 1 | int(floor) << 2 | int(shadow) << 3 | int(decal) << 4)
    def extend(self, other):
        self.P += other.P; self.C += other.C; self.A += other.A; self.F += other.F
    def transform(self, R=None, t=(0, 0, 0)):
        out = Faces()
        R = np.eye(3) if R is None else R
        out.P = [p @ R.T + np.asarray(t) for p in self.P]
        out.C = list(self.C); out.A = list(self.A); out.F = list(self.F)
        return out
    def arrays(self):
        return (np.array(self.P) if self.P else np.zeros((0, 4, 3)), np.array(self.C), np.array(self.A), np.array(self.F))


def box(c, s, color, **kw):
    f = Faces(); cx, cy, cz = c; sx, sy, sz = [x / 2 for x in s]
    v = np.array([[cx+a*sx, cy+b*sy, cz+d*sz] for d in (-1, 1) for b in (-1, 1) for a in (-1, 1)])
    # indices: 0..3 bottom (z-), 4..7 top
    quads = [(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
    ctr = np.array(c, float)
    if min(s) <= 0.1 and not kw.get('shadow') and 'decal' not in kw: kw['decal'] = True
    for q in quads:
        qv = v[list(q)]
        n = np.cross(qv[1] - qv[0], qv[2] - qv[0])
        if np.dot(n, qv.mean(axis=0) - ctr) < 0: qv = qv[::-1]
        f.add(qv, color, **kw)
    return f


def plane(x0, x1, y0, y1, z, color, tile=1.0, color2=None, **kw):
    """Horizontal plane subdivided into tiles (so perspective clipping is safe)."""
    f = Faces(); nx = max(1, int(round((x1-x0)/tile))); ny = max(1, int(round((y1-y0)/tile)))
    xs = np.linspace(x0, x1, nx+1); ys = np.linspace(y0, y1, ny+1)
    for i in range(nx):
        for j in range(ny):
            col = color if (color2 is None or (i + j) % 2 == 0) else color2
            f.add([(xs[i],ys[j],z),(xs[i+1],ys[j],z),(xs[i+1],ys[j+1],z),(xs[i],ys[j+1],z)], col, **kw)
    return f


def wall(p0, p1, z0, z1, color, tile=1.0, flip=False, **kw):
    """Vertical wall between two XY points."""
    f = Faces(); p0 = np.array(p0, float); p1 = np.array(p1, float)
    L = np.linalg.norm(p1 - p0); n = max(1, int(round(L / tile))); m = max(1, int(round((z1-z0)/tile)))
    for i in range(n):
        a = p0 + (p1-p0) * i/n; b = p0 + (p1-p0) * (i+1)/n
        for j in range(m):
            za = z0 + (z1-z0)*j/m; zb = z0 + (z1-z0)*(j+1)/m
            q = [(a[0],a[1],za),(b[0],b[1],za),(b[0],b[1],zb),(a[0],a[1],zb)]
            f.add(q[::-1] if flip else q, color, **kw)
    return f


def cyl(c, r, h, color, axis='z', n=14, **kw):
    f = Faces(); cx, cy, cz = c
    ang = np.linspace(0, 2*math.pi, n, endpoint=False)
    def pt(a, d):
        u, v = r*math.cos(a), r*math.sin(a)
        if axis == 'z': return (cx+u, cy+v, cz+d)
        if axis == 'x': return (cx+d, cy+u, cz+v)
        return (cx+u, cy+d, cz+v)
    for i in range(n):
        a, b = ang[i], ang[(i+1) % n]
        f.add([pt(a,-h/2), pt(b,-h/2), pt(b,h/2), pt(a,h/2)], color, **kw)
    cap_t = [pt(a, h/2) for a in ang]; cap_b = [pt(a, -h/2) for a in ang][::-1]
    for i in range(1, n-1):
        f.add([cap_t[0], cap_t[i], cap_t[i+1]], color, **kw)
        f.add([cap_b[0], cap_b[i], cap_b[i+1]], color, **kw)
    return f


def sphere(c, r, color, nu=10, nv=6, **kw):
    f = Faces(); cx, cy, cz = c
    for j in range(nv):
        t0 = math.pi*j/nv; t1 = math.pi*(j+1)/nv
        for i in range(nu):
            p0 = 2*math.pi*i/nu; p1 = 2*math.pi*(i+1)/nu
            def P(t, p): return (cx+r*math.sin(t)*math.cos(p), cy+r*math.sin(t)*math.sin(p), cz+r*math.cos(t))
            f.add([P(t0,p0), P(t0,p1), P(t1,p1), P(t1,p0)][::-1], color, **kw)
    return f


def cone_frustum(apex, base_pts, color, alpha, **kw):
    f = Faces(); n = len(base_pts)
    for i in range(n):
        f.add([apex, base_pts[i], base_pts[(i+1) % n]], color, alpha=alpha, two=True, **kw)
    return f


class Camera:
    def __init__(self, pos, target, fov=42, up=(0, 0, 1)):
        self.pos = np.array(pos, float); self.target = np.array(target, float); self.fov = fov; self.up = np.array(up, float)
        f = self.target - self.pos; f /= np.linalg.norm(f)
        r = np.cross(f, self.up); r /= np.linalg.norm(r)
        u = np.cross(r, f)
        self.R = np.vstack([r, u, f])   # world -> view (x right, y up, z forward)
        self.fx = (H / 2) / math.tan(math.radians(fov) / 2)
    def to_view(self, P):
        return (P - self.pos) @ self.R.T
    def proj(self, V):
        z = np.maximum(V[..., 2], 1e-3)
        return np.stack([W/2 + self.fx * V[..., 0] / z, H/2 - self.fx * V[..., 1] / z], axis=-1)


LIGHT = np.array([0.45, -0.35, 0.82]); LIGHT /= np.linalg.norm(LIGHT)
FILL = np.array([-0.6, 0.5, 0.35]); FILL /= np.linalg.norm(FILL)

_vig = None
def _vignette():
    global _vig
    if _vig is None:
        y, x = np.mgrid[0:H, 0:W]
        d = np.sqrt(((x - W/2) / (W/2))**2 + ((y - H/2) / (H/2))**2)
        _vig = np.clip(1.0 - 0.28 * d**2.2, 0.55, 1.0)[..., None].astype(np.float32)
    return _vig


def render(faces: Faces, cam: Camera, bg_top, bg_bot, fog=(0.04, 0.05, 0.1), fog_density=0.0, ambient=0.42, key=0.7,
           fillk=0.22, floor_z=0.0, shadow_strength=0.38, overlay=None, bloom=0.35, sky=True, light=None):
    """Returns HxWx3 uint8 RGB."""
    P, C, A, F = faces.arrays()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    if sky:
        g = cairo.LinearGradient(0, 0, 0, H)
        g.add_color_stop_rgb(0, *bg_top); g.add_color_stop_rgb(1, *bg_bot)
        ctx.set_source(g); ctx.paint()
    L = LIGHT if light is None else light
    if len(P):
        V = cam.to_view(P)                      # N,4,3
        cen = P.mean(axis=1)
        nrm = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
        ln = np.linalg.norm(nrm, axis=1, keepdims=True); ln[ln == 0] = 1; nrm /= ln
        to_cam = cam.pos - cen
        facing = (nrm * to_cam).sum(axis=1)
        two = (F >> 1) & 1 == 1
        flip = (facing < 0) & two
        nrm[flip] *= -1
        vis = ((facing > 0) | two) & (V[:, :, 2].min(axis=1) > 0.15)
        emi = (F & 1) == 1
        lam = np.clip(nrm @ L, 0, 1); lam2 = np.clip(nrm @ FILL, 0, 1)
        hemi = 0.5 + 0.5 * nrm[:, 2]
        shade = ambient * (0.75 + 0.25 * hemi) + key * lam + fillk * lam2
        col = C * shade[:, None]
        depth = V[:, :, 2].mean(axis=1)
        depth = depth - 0.8 * ((F >> 4) & 1)
        if fog_density > 0:
            f = 1 - np.exp(-fog_density * depth)
            col = col * (1 - f[:, None]) + np.array(fog) * f[:, None]
        col[emi] = C[emi]
        col = np.clip(col, 0, 1)
        S = cam.proj(V)
        order = np.argsort(-depth)
        floor_idx = [i for i in order if vis[i] and (F[i] >> 2) & 1]
        rest_idx = [i for i in order if vis[i] and not (F[i] >> 2) & 1]

        def draw(idx_list):
            for i in idx_list:
                s = S[i]
                ctx.move_to(*s[0]); ctx.line_to(*s[1]); ctx.line_to(*s[2]); ctx.line_to(*s[3]); ctx.close_path()
                r, g_, b = col[i]
                ctx.set_source_rgba(r, g_, b, A[i]); ctx.fill_preserve()
                if A[i] >= 0.99:
                    ctx.set_line_width(0.8); ctx.stroke()
                else:
                    ctx.new_path()
        draw(floor_idx)
        # soft shadows on the floor plane from caster faces
        casters = np.where((F >> 3) & 1 == 1)[0]
        if len(casters) and shadow_strength > 0:
            sm = cairo.ImageSurface(cairo.FORMAT_A8, W // 2, H // 2); sc = cairo.Context(sm)
            Ls = L
            for i in casters:
                p = P[i]
                sp = p - Ls * ((p[:, 2] - floor_z) / Ls[2])[:, None]
                v = cam.to_view(sp)
                if v[:, 2].min() < 0.15: continue
                q = cam.proj(v) / 2
                sc.move_to(*q[0]); [sc.line_to(*q[k]) for k in (1, 2, 3)]; sc.close_path(); sc.set_source_rgba(0, 0, 0, 1); sc.fill()
            sm.flush()
            m = np.frombuffer(sm.get_data(), np.uint8).reshape(H // 2, sm.get_stride())[:, :W // 2].astype(np.float32) / 255
            m = cv2.GaussianBlur(m, (0, 0), 9)
            m = cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)
            surf.flush()
            buf = np.frombuffer(surf.get_data(), np.uint8).reshape(H, surf.get_stride() // 4, 4)[:, :W, :].astype(np.float32)
            # only darken where something was drawn (floor), keep alpha
            buf[..., :3] *= (1 - shadow_strength * m)[..., None]
            tmp = np.ascontiguousarray(buf.astype(np.uint8))
            surf.flush()
            data = surf.get_data()
            full = np.frombuffer(data, np.uint8).reshape(H, surf.get_stride() // 4, 4)
            full[:, :W, :] = tmp
            surf.mark_dirty()
        draw(rest_idx)
    if overlay is not None:
        overlay(ctx, cam)
    surf.flush()
    img = np.frombuffer(surf.get_data(), np.uint8).reshape(H, surf.get_stride() // 4, 4)[:, :W, :3][..., ::-1].astype(np.float32) / 255
    # bloom on bright pixels
    if bloom > 0:
        br = np.clip(img - 0.78, 0, 1)
        sm = cv2.resize(br, (W // 4, H // 4)); sm = cv2.GaussianBlur(sm, (0, 0), 9)
        img = img + bloom * cv2.resize(sm, (W, H))
    img = img * _vignette()
    # subtle filmic grade: lift navy shadows, soft contrast
    img = np.clip(img, 0, 1)
    img = img ** 0.97
    img = img * np.array([0.98, 1.0, 1.04], np.float32)
    noise = np.random.default_rng(int(np.sum(cam.pos * 1000) % 10000)).normal(0, 0.006, (H // 2, W // 2, 1)).astype(np.float32)
    img += cv2.resize(noise, (W, H))[..., None]
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)   # BGR order after [::-1]? returned as RGB below
