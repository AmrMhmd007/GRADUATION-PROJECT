"""AIU SMART CAMPUS v5 — scene functions + renderer.  Usage: python3 v5.py <scene> [still <t>...]"""
import sys, os, math, subprocess
import numpy as np, cv2, cairo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from multiprocessing import Pool
import scenes
from r3d import *
from parts import *
import parts as _p

FPS = 30
BASE = "/sessions/great-sleepy-rubin/mnt/Desktop/TOP PR/GRADUATION PROJECT/Trailer and Media/AIU_SMART_CAMPUS_FINAL"
PROTO = f"{BASE}/assets/prototype_original.jpg"
APPDIR = f"{BASE}/application_recordings"
CLIPS = "/tmp/work/v5/clips"
PAD = 0.5

# ---- anonymous silhouettes instead of mannequin characters
SIL = np.array([0.12, 0.13, 0.20])
def _sil(*a, **k):
    k.update(suit=SIL, shirt=SIL, pants=SIL, skin=SIL, hair=SIL, lanyard=False); k.pop("anon", None)
    return _p.person(*a, **k)
scenes.person = _sil

# absolute timeline (seconds in the 152.92 s voice-over) — boundaries sit inside narration pauses
TL = {"A": (0.0, 21.0), "B": (21.0, 40.2), "C": (40.2, 58.7), "D": (58.7, 73.6), "E": (73.6, 88.0),
      "F": (88.0, 107.3), "G": (107.3, 125.7), "H": (125.7, 146.1), "I": (146.1, 152.92)}
CHAP = {"B": ("02", "CAMPUS INTELLIGENCE"), "C": ("03", "ACCESS · VERIFIED BEFORE IT UNLOCKS"), "D": ("04", "ANONYMOUS OCCUPANCY COUNT"),
        "E": ("05", "SENSE · COMPARE · ALERT"), "F": ("06", "CENTRAL HVAC")}

_cache = {}
def cached(k, fn):
    if k not in _cache: _cache[k] = fn()
    return _cache[k]

def post(img, fn):
    arr = np.ascontiguousarray(np.dstack([img[..., 2], img[..., 1], img[..., 0], np.full(img.shape[:2], 255, np.uint8)]))
    sf = cairo.ImageSurface.create_for_data(arr, cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(sf); fn(ctx); sf.flush()
    return np.ascontiguousarray(arr[..., [2, 1, 0]])

def chap_hdr_br(ctx, n, s, a):
    if a <= 0: return
    x0 = W - 90 - 24 * len(s) - 90
    ctx.set_source_rgba(0, 0, 0, 0.70 * a); rrect(ctx, x0 - 20, H - 150, W - 70 - x0 + 20, 64, 8); ctx.fill()
    ctx.set_source_rgba(0.72, 0.10, 0.13, a); ctx.rectangle(x0, H - 138, 5, 40); ctx.fill()
    text(ctx, n, x0 + 24, H - 108, 26, True, (0.85, 0.88, 1.0), a, spacing=2)
    text(ctx, s, x0 + 78, H - 108, 26, True, (1, 1, 1), a, spacing=3)

def chap_hdr(ctx, n, s, a):
    if a <= 0: return
    ctx.set_source_rgba(0, 0, 0, 0.30 * a); rrect(ctx, 56, 52, 120 + 21 * len(s), 64, 8); ctx.fill()
    ctx.set_source_rgba(0.72, 0.10, 0.13, a); ctx.rectangle(72, 64, 5, 40); ctx.fill()
    text(ctx, n, 96, 94, 26, True, (0.85, 0.88, 1.0), a, spacing=2)
    text(ctx, s, 150, 94, 26, True, (1, 1, 1), a, spacing=3)

def chapter(ctx, t, L, key):
    if key not in CHAP: return
    a = min(ss((t - 0.3) / 0.5), 1 - ss((t - (L - 0.5)) / 0.5))
    chap_hdr(ctx, *CHAP[key], a)

def title_A(ctx, t):
    fo = 1 - ss((t - 20.3) / 0.6)
    a1 = ss((t - 9.9) / 0.7) * fo; a2 = ss((t - 11.7) / 0.7) * fo; a3 = ss((t - 18.0) / 0.7) * fo
    if a1 <= 0: return
    g = cairo.RadialGradient(W / 2, H * 0.48, 80, W / 2, H * 0.48, 900)
    g.add_color_stop_rgba(0, 0.03, 0.03, 0.12, 0.62 * a1); g.add_color_stop_rgba(1, 0.03, 0.03, 0.12, 0.0)
    ctx.set_source(g); ctx.rectangle(0, 0, W, H); ctx.fill()
    text(ctx, "AIU SMART CAMPUS", W / 2, H * 0.47, 104, True, (1, 1, 1), a1, "c", spacing=6)
    ctx.set_source_rgba(0.72, 0.10, 0.13, a2); ctx.rectangle(W / 2 - 90, H * 0.47 + 28, 180, 5); ctx.fill()
    text(ctx, "CYBER-PHYSICAL CONTROL SYSTEM", W / 2, H * 0.47 + 92, 38, True, (0.86, 0.9, 1), a2, "c", spacing=9)
    text(ctx, "Designed for Alamein International University", W / 2, H * 0.47 + 160, 30, False, (0.8, 0.85, 1), a3, "c", spacing=2)

# ------------------------------------------------------------------ view helpers (crop/zoom/pan only — no distortion)
def navy_bg():
    y = np.linspace(0, 1, H)[:, None, None]; x = np.linspace(-1, 1, W)[None, :, None]
    bg = np.array([16, 18, 52]) * (1 - y) + np.array([6, 7, 24]) * y
    bg = bg * (1 - 0.35 * x ** 2)
    return np.broadcast_to(bg, (H, W, 3)).astype(np.float32).copy()

def blurred_cover(img, dim=0.30):
    h, w = img.shape[:2]; s = max(W / w, H / h) * 1.12
    r = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    y0 = (r.shape[0] - H) // 2; x0 = (r.shape[1] - W) // 2
    c = cv2.GaussianBlur(r[y0:y0 + H, x0:x0 + W].astype(np.float32), (0, 0), 28)
    return c * dim + np.array([10, 12, 40], np.float32) * (1 - dim) * 0.6

def view(img, pre, cx, cy, w, bg, oy=0):
    s = W / w
    M = np.float32([[s / pre, 0, W / 2 - cx * s], [0, s / pre, H / 2 + oy - cy * s]])
    fg = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    m = cv2.warpAffine(np.ones(img.shape[:2], np.float32), M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)
    m = cv2.GaussianBlur(m, (0, 0), 1.2)
    shadow = cv2.GaussianBlur(np.roll(m, 16, 0), (0, 0), 32) * 0.55
    out = bg * (1 - shadow[..., None])
    out = out * (1 - m[..., None]) + fg.astype(np.float32) * m[..., None]
    return out, s, m

def sweep(out, m, t, speed=120, strength=0.06):
    xx = cached("xx", lambda: np.tile(np.arange(W, dtype=np.float32), (H, 1)) + np.arange(H, dtype=np.float32)[:, None] * 0.35)
    pos = (t * speed) % (W + 800) - 400
    g = np.exp(-((xx - pos) / 240.0) ** 2) * strength
    return out + (g * m)[..., None] * 255

def finish(out, t):
    v = cached("vig", lambda: (1 - 0.22 * (np.linspace(-1, 1, W)[None, :] ** 2 + np.linspace(-1, 1, H)[:, None] ** 2) ** 1.1).astype(np.float32))
    out = out * v[..., None]
    rng = np.random.default_rng(int(t * 30) + 7)
    out = out + rng.normal(0, 2.2, out.shape[:2])[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ operational-flow overlays
STAGES = ["SENSE", "ANALYZE", "VERIFY", "DECIDE", "ACT", "MONITOR"]
SCHED = {  # absolute seconds; None = stage not exercised in that scene
    "C": [(40.2, 47.0), (47.0, 49.6), (49.6, 53.0), (53.0, 54.25), (54.25, 56.5), (56.5, 58.7)],
    "D": [(58.7, 63.0), (63.0, 69.0), None, None, None, (69.0, 73.6)],
    "E": [(73.6, 77.0), (77.0, 80.1), (80.1, 82.0), (82.0, 83.5), (83.5, 85.5), (85.5, 88.0)],
    "F": [None, None, None, None, (88.0, 102.2), (102.2, 107.3)],
    "H": [(0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (125.7, 146.1)],
}
def stage_strip(ctx, t, key, L):
    ta = TL[key][0] + t
    a = min(ss((t - 0.6) / 0.5), 1 - ss((t - (L - 0.4)) / 0.4))
    if a <= 0: return
    pw, gap = 148, 8; x0 = W - 60 - 6 * pw - 5 * gap
    for i, (nm, sc) in enumerate(zip(STAGES, SCHED[key])):
        x = x0 + i * (pw + gap)
        if sc is None: st = "na"
        elif ta >= sc[1]: st = "done"
        elif ta >= sc[0]: st = "act"
        else: st = "next"
        col = {"na": (0.1, 0.1, 0.2, 0.35), "next": (0.1, 0.1, 0.3, 0.55), "done": (0.16, 0.17, 0.42, 0.85), "act": (0.72, 0.10, 0.13, 0.95)}[st]
        ctx.set_source_rgba(col[0], col[1], col[2], col[3] * a); rrect(ctx, x, 52, pw, 44, 22); ctx.fill()
        tc = {"na": 0.35, "next": 0.6, "done": 0.9, "act": 1.0}[st]
        text(ctx, nm, x + pw / 2, 81, 18, True, (1, 1, 1), tc * a, "c", spacing=2)

CHAIN = ["SENSORS", "BACKEND", "INFRASTRUCTURE", "DASHBOARD"]
def chain_strip_dash(ctx, t, L):
    pass

def chain_strip(ctx, t, L, act):
    a = min(ss((t - 0.8) / 0.5), 1 - ss((t - (L - 0.4)) / 0.4))
    if a <= 0: return
    pw, gap = 205, 36; x0 = W - 60 - 4 * pw - 3 * gap
    for i, nm in enumerate(CHAIN):
        x = x0 + i * (pw + gap); on = (act == i) or act == 9
        ctx.set_source_rgba(*((0.72, 0.10, 0.13, 0.95) if on else (0.1, 0.1, 0.3, 0.6)), ) if False else ctx.set_source_rgba(0.72 if on else 0.1, 0.10 if on else 0.1, 0.13 if on else 0.3, (0.95 if on else 0.6) * a)
        rrect(ctx, x, 52, pw, 44, 22); ctx.fill()
        text(ctx, nm, x + pw / 2, 81, 17, True, (1, 1, 1), (1.0 if on else 0.6) * a, "c", spacing=2)
        if i < 3: text(ctx, "›", x + pw + gap / 2, 83, 26, True, (0.85, 0.88, 1), 0.8 * a, "c")

# ------------------------------------------------------------------ G: prototype image
def _proto():
    im = cv2.cvtColor(cv2.imread(PROTO), cv2.COLOR_BGR2RGB)
    big = cv2.resize(im, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
    big = cv2.addWeighted(big, 1.25, cv2.GaussianBlur(big, (0, 0), 2.0), -0.25, 0)
    return im, big, blurred_cover(im)

PV = [(0.0, 640, 428, 1640), (1.9, 640, 428, 1560), (3.5, 640, 330, 1340), (4.6, 640, 320, 1300),
      (6.0, 250, 335, 600), (8.3, 262, 335, 580), (9.1, 580, 335, 580), (11.2, 592, 335, 560),
      (11.9, 892, 335, 560), (13.7, 880, 335, 560), (14.6, 560, 245, 900), (16.1, 580, 240, 860),
      (16.8, 1075, 270, 440), (17.6, 1075, 265, 420), (18.4, 640, 428, 1500)]
PR = [(2.6, 5.4, (45, 90, 1190, 400), "01", "PHYSICAL PROTOTYPE MODEL", "120 × 80 × 25 cm cyber-physical campus building"),
      (6.0, 8.8, (50, 232, 350, 215), "02", "ROOM 3031 · LECTURE ROOM", "Door access panel + occupancy camera, as drawn"),
      (9.1, 11.6, (400, 232, 340, 215), "03", "ROOM 3032 · SMART LAB", "Ceiling vent fed by the central HVAC"),
      (11.9, 14.1, (742, 232, 300, 215), "04", "ROOM 3033 · OFFICE / ADMIN", "Occupancy camera · same access pattern"),
      (14.6, 16.5, (195, 112, 760, 150), "05", "CENTRAL HVAC", "Central unit › main duct › branch ducts › ceiling vents"),
      (16.8, 18.0, (972, 158, 195, 235), "06", "TECHNICAL COMPARTMENT", "Raspberry Pi · network · power (as labelled)")]
def proto_frame(t, L=18.4):
    im, big, bgc = cached("proto", _proto)
    u = t * 18.4 / L
    cx, cy, w = kf([(a, np.array([b, c, d], float)) for a, b, c, d in PV], u)
    cx += 5 * math.sin(u * 0.9); cy += 3 * math.cos(u * 0.7)
    bg = navy_bg() * 0.5 + np.roll(bgc, int(-(cx - 640) * 0.12), 1) * 0.9
    out, s, m = view(big, 2, cx, cy, w, bg)
    out = finish(sweep(out, m, t) * ss(t / 0.9), t)
    def ov(ctx):
        for (a, b, (x, y, rw, rh), n, ti, su) in PR:
            ta = min(ss((u - a) / 0.4), 1 - ss((u - (b - 0.35)) / 0.4))
            if ta <= 0: continue
            sx, sy = s * (x - cx) + W / 2, s * (y - cy) + H / 2
            ctx.set_source_rgba(0.80, 0.16, 0.20, 0.95 * ta); ctx.set_line_width(3); rrect(ctx, sx, sy, rw * s, rh * s, 10); ctx.stroke()
            ctx.set_source_rgba(0.80, 0.16, 0.20, 0.10 * ta); rrect(ctx, sx, sy, rw * s, rh * s, 10); ctx.fill()
            card(ctx, 70, H - 190, 800, 120, 0.90 * ta)
            text(ctx, n, 98, H - 128, 34, True, (0.88, 0.2, 0.25), ta)
            text(ctx, ti, 154, H - 134, 32, True, (1, 1, 1), ta, spacing=1.5)
            text(ctx, su, 154, H - 98, 21, False, (0.78, 0.83, 1), ta)
        a = ss((t - 0.4) / 0.6) * (1 - ss((t - (L - 0.4)) / 0.4))
        chap_hdr_br(ctx, "07", "PHYSICAL PROTOTYPE DESIGN", a)
        act = -1 if u < 6.0 else 0 if u < 14.4 else 2 if u < 16.6 else 1 if u < 18.0 else 9
        chain_strip(ctx, t, L, act)
        tag(ctx, "SUPPLIED PROTOTYPE DESIGN IMAGE · shown unaltered (crop/zoom only) · no installed-hardware claim", x=W - 1300, y=H - 40)
    return post(out, ov)

# ------------------------------------------------------------------ H: real application captures
APP_SHOTS = [
    ("app2x_01_home.png", (960, 458, 1620), (930, 400, 1280), "COMMAND HUB", "8 doors · 2 buildings · 1 college — read live from the backend"),
    ("app2x_02_command.png", (960, 458, 1620), (1300, 300, 1100), "COMMAND CENTER", "Nominal state · locked / unlocked doors · anomaly indicators"),
    ("app2x_03_smart_building.png", (960, 458, 1620), (900, 560, 1240), "SMART BUILDING", "7 zones monitored · closing sequence verifies before any shutdown"),
    ("app2x_04_access_events.png", (960, 458, 1620), (1200, 520, 1180), "ACCESS EVENTS", "Every decision persisted — door, method, result, investigation"),
    ("app2x_05_campus_map.png", (960, 458, 1620), (900, 330, 1100), "CAMPUS MAP", "Room health shown honestly: OFFLINE / DEGRADED, never invented"),
    ("app2x_06_occupancy.png", (960, 458, 1620), (1100, 320, 1140), "OCCUPANCY", "Count only — “Unavailable” when no sensor reports"),
    ("app2x_07_device_faults.png", (960, 458, 1620), (900, 300, 1100), "DEVICE FAULTS", "No fault recorded · unmonitored devices are not guessed")]
def _app():
    return [cv2.resize(cv2.cvtColor(cv2.imread(f"{APPDIR}/{f}"), cv2.COLOR_BGR2RGB), (2880, 1376), interpolation=cv2.INTER_AREA) for f, *_ in APP_SHOTS]
def app_frame(t, L=20.4):
    imgs = cached("app", _app); n = len(APP_SHOTS); d = L / n; X = 0.5
    bg = cached("navybg", navy_bg)
    def shot(i):
        f, k0, k1, ti, su = APP_SHOTS[i]
        p = float(np.clip((t - i * d + X / 2) / (d + X), 0, 1)); p = ss(p) * 0.85 + p * 0.15
        cx, cy, w = [k0[j] + (k1[j] - k0[j]) * p for j in range(3)]
        h = w * 9 / 16; cx = min(max(cx, w / 2), 1920 - w / 2); cy = min(max(cy, h / 2 - 20), 917 - h / 2 + 20)
        return view(imgs[i], 1.5, cx, cy, w, bg, oy=-40)[0]
    idx = min(int(t / d), n - 1)
    out = shot(idx)
    # dissolve with neighbour near boundaries
    if idx < n - 1 and t > (idx + 1) * d - X / 2:
        w_ = ss((t - ((idx + 1) * d - X / 2)) / X); out = out * (1 - w_) + shot(idx + 1) * w_
    elif idx > 0 and t < idx * d + X / 2:
        w_ = ss((t - (idx * d - X / 2)) / X); out = shot(idx - 1) * (1 - w_) + out * w_
    out = finish(out * ss(t / 0.5), t)
    ti, su = APP_SHOTS[idx][3], APP_SHOTS[idx][4]
    lt = t - idx * d
    la = min(ss((lt - 0.15) / 0.35), 1 - ss((lt - (d - 0.35)) / 0.3)) if idx < n - 1 else min(ss((lt - 0.15) / 0.35), 1 - ss((t - (L - 0.4)) / 0.4))
    def ov(ctx):
        a = ss((t - 0.3) / 0.5) * (1 - ss((t - (L - 0.4)) / 0.4))
        chap_hdr_br(ctx, "08", "THE REAL APPLICATION", a)
        stage_strip(ctx, t, "H", L); chain_strip_dash(ctx, t, L)
        card(ctx, 70, H - 150, 1000, 84, 0.94 * la)
        text(ctx, ti, 100, H - 105, 26, True, (1, 1, 1), la, spacing=2.5)
        text(ctx, su, 100, H - 78, 19, False, (0.78, 0.83, 1), la)
        tag(ctx, "ACTUAL APPLICATION · stills captured from the running dashboard + backend (dev database, no hardware connected)", x=W - 1330, y=H - 40)
    return post(out, ov)

# ------------------------------------------------------------------ I: final reveal
def final_frame(t, L=6.82):
    im, big, bgc = cached("proto", _proto)
    bg = navy_bg() * 0.55 + bgc * 0.8
    out = finish(bg * ss(t / 0.5), t); ta = 146.1
    def ov(ctx):
        g = cairo.RadialGradient(W / 2, H * 0.42, 60, W / 2, H * 0.42, 880)
        g.add_color_stop_rgba(0, 0.03, 0.03, 0.12, 0.55); g.add_color_stop_rgba(1, 0.03, 0.03, 0.12, 0.0)
        ctx.set_source(g); ctx.rectangle(0, 0, W, H); ctx.fill()
        a1 = ss((t - 0.4) / 0.7); a2 = ss((t - 1.2) / 0.7); a3 = ss((t - 2.0) / 0.7)
        text(ctx, "AIU SMART CAMPUS", W / 2, H * 0.40, 100, True, (1, 1, 1), a1, "c", spacing=6)
        ctx.set_source_rgba(0.72, 0.10, 0.13, a2); ctx.rectangle(W / 2 - 90, H * 0.40 + 26, 180, 5); ctx.fill()
        text(ctx, "CYBER-PHYSICAL CONTROL SYSTEM", W / 2, H * 0.40 + 88, 38, True, (0.86, 0.9, 1), a2, "c", spacing=9)
        for (wd, tw), x in zip([("SEE.", 149.3), ("UNDERSTAND.", 150.17), ("DECIDE.", 151.28), ("ACT.", 152.32)], [W * 0.20, W * 0.40, W * 0.62, W * 0.80]):
            a = ss((t - (tw - ta) + 0.05) / 0.25)
            text(ctx, wd, x, H * 0.64, 54, True, (0.95, 0.30, 0.34) if wd == "ACT." else (1, 1, 1), a, "c", spacing=4)
        text(ctx, "Designed for Alamein International University", W / 2, H * 0.80, 30, False, (0.8, 0.85, 1), a3, "c", spacing=2)
    return post(out, ov)

# ------------------------------------------------------------------ 3D scene wrappers
def _massing_b(t, L):
    f = scenes.cached("mass", massing)
    cam = Camera(kf([(0, (3, 18, 15)), (L, (-17, 9, 8.5))], t), kf([(0, (0, 70, 6)), (L, (-3, 62, 5))], t), fov=48)
    def ov(ctx, cam):
        tag(ctx, "CONCEPTUAL MASSING · not the AIU campus · not real footage", x=W - 1230, y=H - 40)
    return render(f, cam, (0.10, 0.12, 0.30), (0.88, 0.62, 0.50), fog=(0.62, 0.55, 0.60), fog_density=0.006, ambient=0.5, key=0.75,
                  overlay=ov, light=np.array([-0.5, -0.3, 0.55]) / np.linalg.norm([-0.5, -0.3, 0.55]))

AIU_PHOTOS = [("aiu_exterior_01_shield_logo.png", (430, 290, 1.30), (520, 262, 1.02)),
              ("aiu_exterior_03_flags_logo.png", (358, 206, 1.30), (300, 200, 1.02))]
def _aiu():
    out = []
    for f, *_ in AIU_PHOTOS:
        im = cv2.cvtColor(cv2.imread(f"{BASE}/assets/collected_references/{f}"), cv2.COLOR_BGR2RGB)
        big = cv2.resize(im, None, fx=3, fy=3, interpolation=cv2.INTER_LANCZOS4)
        big = cv2.addWeighted(big, 1.2, cv2.GaussianBlur(big, (0, 0), 2.0), -0.2, 0)
        out.append((im, big, blurred_cover(im, 0.55)))
    return out
def A_fn(t, L):
    ph = cached("aiu", _aiu); d = L / 2; X = 0.7
    def shot(i):
        im, big, bgc = ph[i]; f, k0, k1 = AIU_PHOTOS[i]
        p = float(np.clip((t - i * d + X / 2) / (d + X), 0, 1)); p = ss(p)
        cx = k0[0] + (k1[0] - k0[0]) * p; cy = k0[1] + (k1[1] - k0[1]) * p
        w = im.shape[1] * (k0[2] + (k1[2] - k0[2]) * p)
        bg = navy_bg() * 0.35 + bgc
        return view(big, 3, cx, cy, w, bg)[0]
    idx = 0 if t < d else 1
    out = shot(idx)
    if idx == 0 and t > d - X / 2: w_ = ss((t - (d - X / 2)) / X); out = out * (1 - w_) + shot(1) * w_
    elif idx == 1 and t < d + X / 2: w_ = ss((t - (d - X / 2)) / X); out = shot(0) * (1 - w_) + out * w_
    out = finish(out * ss(t / 0.8), t)
    def ov(ctx):
        a = min(ss((t - 0.4) / 0.6), 1 - ss((t - 20.3) / 0.6))
        chap_hdr(ctx, "01", "ALAMEIN INTERNATIONAL UNIVERSITY", a)
        ctx.set_source_rgba(0, 0, 0, 0.28 * ss((t - 9.6) / 0.6) * (1 - ss((t - 20.3) / 0.6))); ctx.rectangle(0, 0, W, H); ctx.fill()
        title_A(ctx, t)
        tag(ctx, "AUTHENTIC AIU CAMPUS PHOTOGRAPHS (stills, supplied by the project team) · licence to be confirmed", x=W - 1330, y=H - 40)
    return post(out, ov)
def B_fn(t, L): return post(_massing_b(t, L), lambda c: chapter(c, t, L, "B"))
def C_fn(t, L):
    s = 7.0
    img = scenes.approach_frame(t * 8.73 / s, 8.73) if t < s else scenes.access_frame((t - s) * 11.75 / (L - s), 11.75)
    return post(img, lambda c: (chapter(c, t, L, "C"), stage_strip(c, t, "C", L)))
def D_fn(t, L): return post(scenes.occupancy_frame(t * 11.75 / L, 11.75), lambda c: (chapter(c, t, L, "D"), stage_strip(c, t, "D", L)))
def E_fn(t, L): return post(scenes.projector_frame(t * 7.9 / L, 7.9), lambda c: (chapter(c, t, L, "E"), stage_strip(c, t, "E", L)))
def F_fn(t, L): return post(scenes.hvac_frame(t * 9.4 / L, 9.4), lambda c: (chapter(c, t, L, "F"), stage_strip(c, t, "F", L)))
FN = dict(A=A_fn, B=B_fn, C=C_fn, D=D_fn, E=E_fn, F=F_fn, G=proto_frame, H=app_frame, I=final_frame)

def L_of(k): a, b = TL[k]; return b - a
def _work(args):
    k, i = args
    return i, FN[k](i / FPS, L_of(k))

def render_scene(k, procs=4):
    os.makedirs(CLIPS, exist_ok=True)
    n = int(round((L_of(k) + (PAD if k != "I" else 0)) * FPS))
    out = f"{CLIPS}/{k}.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                          "-i", "-", "-c:v", "libx264", "-crf", "15", "-preset", "medium", "-pix_fmt", "yuv420p", "-g", "30", out], stdin=subprocess.PIPE)
    with Pool(procs) as pool:
        for i, img in pool.imap(_work, [(k, i) for i in range(n)], chunksize=2):
            p.stdin.write(np.ascontiguousarray(img).tobytes())
    p.stdin.close(); p.wait()
    return out

if __name__ == "__main__":
    k = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "still":
        ims = [cv2.resize(FN[k](float(t), L_of(k))[..., ::-1], (960, 540)) for t in sys.argv[3:]]
        while len(ims) % 2: ims.append(ims[-1] * 0)
        cv2.imwrite(f"/sessions/great-sleepy-rubin/mnt/outputs/_preview/v5_{k}.jpg", np.vstack([np.hstack(ims[i:i + 2]) for i in range(0, len(ims), 2)]))
    else:
        render_scene(k)
