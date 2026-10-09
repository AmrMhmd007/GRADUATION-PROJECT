import math, sys, subprocess, os
import numpy as np
import cv2
from multiprocessing import Pool
from r3d import *
from parts import *

FPS = 30
_cache = {}
def cached(name, fn):
    if name not in _cache: _cache[name] = fn()
    return _cache[name]

def cap_alpha(t, a, b):
    return min(1.0, max(0.0, min((t - a) / 0.3, (b - t) / 0.25)))

# ============================================================ 1. MASSING (placeholder for real AIU establishing shot)
def massing_frame(t, dur=9.62):
    f = cached("mass", massing)
    p = t / dur
    cam = Camera(kf([(0, (0, -30, 26)), (dur, (3, 18, 15))], t), kf([(0, (0, 55, 4)), (dur, (0, 70, 6))], t), fov=48)
    def ov(ctx, cam):
        a = ss((t - 0.4) / 1.0) * (1 - ss((t - 6.0) / 0.5))
        text(ctx, "ALAMEIN INTERNATIONAL UNIVERSITY", 110, 150, 34, True, (1, 1, 1), a, spacing=3)
        text(ctx, "A SMARTER CAMPUS EXPERIENCE", 110, 198, 26, False, (0.82, 0.86, 1.0), a, spacing=2)
        ctx.set_source_rgba(0.66, 0.10, 0.12, a); ctx.rectangle(110, 214, 120, 3); ctx.fill()
        l1 = cap_alpha(t, 0.5, 6.0); l2 = cap_alpha(t, 6.2, dur)
        bottom_caption(ctx, "EVERY DAY, A MODERN CAMPUS MAKES THOUSANDS OF DECISIONS.", l1, H - 150)
        bottom_caption(ctx, "WHAT IF IT COULD THINK?", l2, H - 150)
        tag(ctx, "PLACEHOLDER · real AIU establishing footage not available — conceptual massing, NOT the AIU campus", x=W - 1230, y=H - 40)
    return render(f, cam, (0.10, 0.12, 0.30), (0.88, 0.62, 0.50), fog=(0.62, 0.55, 0.60), fog_density=0.006, ambient=0.5, key=0.75,
                  overlay=ov, light=np.array([-0.5, -0.3, 0.55]) / np.linalg.norm([-0.5, -0.3, 0.55]))

# ============================================================ 2/3. CORRIDOR (approach + access)
def _corridor_base():
    return corridor()

def doctor(pos, yaw, t_walk=None, walking=False, arm=None):
    return person(pos, yaw, phase=(t_walk or 0) * 5.2, walk=1.0 if walking else 0.0, lanyard=True, arm_r=arm)

def approach_frame(t, dur=8.73):
    base = cached("corr", _corridor_base)
    y = kf([(0.0, 3.0), (dur - 1.0, 13.0)], t)[()] if False else float(kf([(0.0, 3.0), (dur - 1.0, 13.0)], t))
    walking = t < dur - 1.0
    xdoc = float(kf([(0, 0.0), (dur - 1.0, 0.55)], t))
    yaw = float(kf([(dur - 2.2, 0.0), (dur - 0.6, -1.2)], t))
    f = Faces(); f.extend(base)
    f.extend(doctor((xdoc, y, 0), yaw, t, walking))
    f.extend(door_panel(0.0))
    f.extend(led((1.49, 13.55, 1.66), np.array([1.0, 0.72, 0.15])))
    camp = kf([(0, (-1.0, y - 5.0, 1.75)), (dur, (-0.7, y - 3.2, 1.65))], t) if False else np.array([-1.0 + 0.3 * t / dur, y - 4.6 + 1.2 * ss(t / dur), 1.7])
    cam = Camera(camp, (xdoc + 0.2, y + 2.5, 1.35), fov=44)
    def ov(ctx, cam):
        bottom_caption(ctx, "SEE.", cap_alpha(t, dur - 2.5, dur + 0.5))
        tag(ctx, "CONCEPTUAL ANIMATION · not real AIU footage")
    return render(f, cam, (0.1, 0.12, 0.25), (0.3, 0.35, 0.5), fog=(0.55, 0.6, 0.72), fog_density=0.018, ambient=0.55, key=0.55, overlay=ov, sky=True,
                  light=np.array([0.2, 0.1, 0.9]) / np.linalg.norm([0.2, 0.1, 0.9]))

def access_frame(t, dur=11.75):
    base = cached("corr", _corridor_base)
    f = Faces(); f.extend(base)
    grant_t = 7.2; open_a = float(kf([(grant_t + 0.4, 0.0), (grant_t + 2.0, 1.25)], t))
    walkin = float(kf([(grant_t + 1.2, 0.0), (dur, 1.0)], t))
    docx = 0.55 + 1.2 * walkin; docy = 13.2 + 1.3 * walkin
    yaw = -1.2 - 0.1 * walkin if walkin < 0.01 else float(kf([(grant_t + 1.2, -1.2), (grant_t + 2.2, -1.0)], t))
    f.extend(doctor((docx, docy, 0), yaw, t, walking=walkin > 0.02 and walkin < 1.0))
    f.extend(door_panel(open_a))
    green = t >= grant_t
    f.extend(led((1.49, 13.55, 1.66), np.array([0.2, 0.95, 0.5]) if green else (np.array([1.0, 0.72, 0.15]) if t > 1.0 else np.array([0.5, 0.5, 0.55])), on=True))
    cam = Camera(kf([(0, (-0.5, 10.6, 1.65)), (6, (0.0, 11.3, 1.62)), (dur, (0.4, 12.2, 1.7))], t), kf([(0, (1.0, 13.6, 1.5)), (dur, (1.4, 14.2, 1.3))], t), fov=40)
    def ov(ctx, cam):
        # face-scan brackets around the head (no facial detail is drawn; this is a schematic frame)
        hx, hy, _ = project(cam, (docx, docy, 1.64))
        if 1.0 < t < grant_t + 0.8:
            s = 96 + 6 * math.sin(t * 6); a = ss((t - 1.0) / 0.4)
            col = (0.4, 0.85, 0.65) if t > 2.4 else (0.9, 0.9, 1.0)
            ctx.set_source_rgba(*col, a); ctx.set_line_width(3)
            for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                cx, cy = hx + sx * s, hy + sy * s * 1.15
                ctx.move_to(cx, cy - sy * 28); ctx.line_to(cx, cy); ctx.line_to(cx - sx * 28, cy); ctx.stroke()
            if t < 2.4:
                yy = hy - s * 1.1 + ((t * 1.2) % 1.0) * s * 2.2
                ctx.set_source_rgba(0.6, 0.8, 1, 0.8); ctx.rectangle(hx - s, yy, 2 * s, 2); ctx.fill()
        # backend decision panel
        px, py, pw, ph = W - 640, 150, 560, 470
        a = ss((t - 1.6) / 0.5)
        if a > 0:
            card(ctx, px, py, pw, ph, 0.84 * a)
            text(ctx, "ACCESS DECISION · BACKEND", px + 28, py + 46, 22, True, (0.75, 0.8, 1), a, spacing=2)
            steps = [("FACE VERIFIED", 2.4), ("ACCOUNT ACTIVE · ROLE: DOCTOR", 3.4), ("ROOM AUTHORIZED", 4.4), ("SCHEDULE VALID", 5.4), ("ACCESS WINDOW VALID", 6.3)]
            for i, (lab, ts) in enumerate(steps):
                yy = py + 100 + i * 58; sa = ss((t - ts) / 0.3)
                ctx.new_path(); ctx.set_source_rgba(0.6, 0.65, 0.9, 0.35 * a); ctx.arc(px + 40, yy - 8, 12, 0, 6.3); ctx.set_line_width(2); ctx.stroke()
                if sa > 0: check(ctx, px + 31, yy - 8, 18, alpha=sa)
                text(ctx, lab, px + 70, yy, 21, False, (0.92, 0.94, 1), 0.35 * a + 0.65 * sa * a)
            ga = ss((t - grant_t) / 0.3)
            if ga > 0:
                chip(ctx, px + 28, py + ph - 76, "DECISION: GRANT", (0.12, 0.55, 0.38), 28, ga)
        # evidence / event chip
        ea = ss((t - 8.2) / 0.4)
        if ea > 0:
            card(ctx, 90, H - 270, 640, 100, 0.84 * ea)
            text(ctx, "ACCESS EVENT RECORDED · EVIDENCE PRESERVED", 120, H - 218, 22, True, (0.9, 0.93, 1), ea, spacing=1)
            text(ctx, "identity · room · schedule · decision · timestamp", 120, H - 184, 19, False, (0.7, 0.75, 0.95), ea)
        bottom_caption(ctx, "SECURITY.", cap_alpha(t, 0.0, 2.18))
        bottom_caption(ctx, "IDENTITY. AUTHORIZATION. SCHEDULE.", cap_alpha(t, 2.2, 7.99))
        bottom_caption(ctx, "EVIDENCE.", cap_alpha(t, 8.0, dur + 1))
        tag(ctx, "CONCEPTUAL ANIMATION · prototype hardware not shown as installed")
    return render(f, cam, (0.1, 0.12, 0.25), (0.3, 0.35, 0.5), fog=(0.55, 0.6, 0.72), fog_density=0.018, ambient=0.55, key=0.55, overlay=ov,
                  light=np.array([0.2, 0.1, 0.9]) / np.linalg.norm([0.2, 0.1, 0.9]))

# ============================================================ 4. OCCUPANCY COUNTING
def _class_base(): return classroom_static(True)
def occupancy_frame(t, dur=11.75):
    base = cached("class", _class_base)
    seats = seat_positions(); n_target = 37
    f = Faces(); f.extend(base)
    shown = 0
    rng = np.random.default_rng(3)
    skip = set(rng.choice(len(seats), len(seats) - n_target, replace=False).tolist())
    order = [i for i in range(len(seats)) if i not in skip]
    for k, i in enumerate(order):
        st = 1.0 + k * 0.17
        if t >= st:
            x, y = seats[i]; shown += 1
            f.extend(person((x, y + 0.36, 0.47 - 0.92), math.pi, seated=True, anon=True, lod=0, arm_r=None))
    # independent counting camera node (rear ceiling) + translucent field of view
    f.extend(box((0, 9.8, 3.02), (0.22, 0.12, 0.10), np.array([0.95, 0.95, 0.97]), shadow=True))
    f.extend(cyl((0, 9.72, 3.02), 0.035, 0.03, np.array([0.02, 0.02, 0.03]), axis='y', n=12))
    f.extend(box((0, 9.99, 3.05), (0.10, 0.04, 0.10), np.array([0.2, 0.2, 0.24])))
    apex = (0, 9.7, 3.02)
    base_pts = [(-5.2, 3.2, 0.0), (5.2, 3.2, 0.0), (5.2, 3.2, 2.1), (-5.2, 3.2, 2.1)]
    f.extend(cone_frustum(apex, base_pts, np.array([0.45, 0.65, 1.0]), 0.07))
    cam = Camera(kf([(0, (-5.2, 9.2, 2.7)), (dur, (3.8, 8.6, 2.3))], t), kf([(0, (1.5, 3.5, 1.1)), (dur, (-1.0, 3.0, 1.2))], t), fov=52)
    def ov(ctx, cam):
        for k, i in enumerate(order[:shown]):
            x, y = seats[i]; sx, sy, z = project(cam, (x, y + 0.36, 1.12))
            if z < 0.5: continue
            age = t - (1.0 + k * 0.17)
            r = 8 + 14 * max(0, 1 - age / 0.6)
            ctx.new_path(); ctx.set_source_rgba(1.0, 1.0, 1.0, 0.85 * max(0.25, 1 - age / 2.5)); ctx.set_line_width(2.2); ctx.arc(sx, sy, r, 0, 6.3); ctx.stroke()
        card(ctx, 90, H - 330, 700, 210, 0.85)
        text(ctx, "ROOM OCCUPANCY · COUNT ONLY", 122, H - 282, 21, True, (0.75, 0.8, 1), 1, spacing=2)
        text(ctx, str(shown), 122, H - 190, 96, True, (1, 1, 1))
        text(ctx, "/ 50 capacity", 122 + 150 + (30 if shown > 9 else 0), H - 196, 28, False, (0.8, 0.85, 1))
        text(ctx, "No faces stored · No identities · No attendance records", 122, H - 142, 20, False, (0.95, 0.85, 0.6))
        bottom_caption(ctx, "SEEING ISN'T ENOUGH.", cap_alpha(t, 0.0, 4.22))
        tag(ctx, "CONCEPTUAL ANIMATION · anonymous figures · not AIU footage")
    return render(f, cam, (0.1, 0.12, 0.25), (0.3, 0.35, 0.5), fog=(0.6, 0.62, 0.7), fog_density=0.0, ambient=0.5, key=0.5, overlay=ov, sky=True,
                  light=np.array([0.1, 0.1, 1.0]) / np.linalg.norm([0.1, 0.1, 1.0]), shadow_strength=0.3)

# ============================================================ 5. PROJECTOR FAULT
def projector_frame(t, dur=7.9):
    base = cached("class_nodesks", lambda: classroom_static(False))
    f = Faces(); f.extend(base); f.extend(projector())
    press = 1.9
    # sensor node clamped to projector power drop
    f.extend(box((0.25, 5.2, 3.0), (0.14, 0.10, 0.07), np.array([0.14, 0.2, 0.55]), shadow=True))
    f.extend(cyl((0.12, 5.2, 3.0), 0.05, 0.05, DGREY, axis='x', n=10))
    f.extend(led((0.25, 5.2 - 0.056, 3.0), np.array([0.3, 0.9, 0.55])))
    arm = float(kf([(1.0, 0.0), (1.7, 1.45), (2.3, 1.45), (2.9, 0.0)], t))
    f.extend(person((1.0, 1.0, 0), math.pi, arm_r=arm, lanyard=True))
    f.extend(box((0.9, 0.06, 1.25), (0.14, 0.03, 0.2), np.array([0.2, 0.2, 0.25])))                       # wall control panel
    f.extend(led((0.9, 0.08, 1.3), np.array([1.0, 0.7, 0.2]) if t > press else np.array([0.3, 0.3, 0.35])))
    f.extend(led((0.0, 5.0, 2.94), np.array([1.0, 0.7, 0.2]) if t > press + 0.2 else np.array([0.25, 0.25, 0.3])))   # projector standby/commanded LED
    cam = Camera(kf([(0, (-3.6, 7.8, 1.9)), (dur, (-1.8, 6.6, 1.8))], t), kf([(0, (0.4, 2.0, 2.0)), (dur, (0.5, 1.5, 2.0))], t), fov=52)
    words = [("SENSE", 0.0), ("ANALYZE", 0.94), ("VERIFY", 1.83), ("DECIDE", 2.72), ("ACT", 3.68), ("MONITOR", 4.44)]
    def ov(ctx, cam):
        px, py, pw, ph = W - 600, 120, 520, 430
        card(ctx, px, py, pw, ph, 0.86)
        text(ctx, "PROJECTOR · CURRENT SENSOR", px + 26, py + 44, 21, True, (0.75, 0.8, 1), 1, spacing=1.5)
        exp = "—" if t < press else "ON (manual start)"
        text(ctx, "EXPECTED", px + 26, py + 100, 17, False, (0.7, 0.75, 0.95)); text(ctx, exp, px + 26, py + 134, 28, True, (1, 1, 1))
        pw_ = "0.0 W" if t < press else "0.4 W"
        text(ctx, "OBSERVED POWER", px + 26, py + 192, 17, False, (0.7, 0.75, 0.95)); text(ctx, pw_, px + 26, py + 228, 34, True, (1, 0.85, 0.5) if t > press + 1 else (1, 1, 1))
        text(ctx, "SENSOR: ONLINE", px + 300, py + 134, 20, True, (0.45, 0.9, 0.65))
        if t > 3.6:
            a = ss((t - 3.6) / 0.4)
            text(ctx, "EXPECTED ≠ OBSERVED", px + 26, py + 290, 22, True, (1, 0.8, 0.5), a)
            chip(ctx, px + 26, py + 312, "SEVERITY: HIGH", (0.82, 0.38, 0.1), 24, a)
        if t > 5.1:
            a = ss((t - 5.1) / 0.4)
            card(ctx, 90, H - 360, 880, 170, 0.88 * a, (0.9, 0.5, 0.3))
            text(ctx, "ROOM 3032  ·  PROJECTOR ISSUE", 126, H - 304, 32, True, (1, 1, 1), a)
            text(ctx, "Alert persisted · evidence: sensor reading, timestamp, expected vs observed", 126, H - 266, 19, False, (0.8, 0.85, 1), a)
            chip(ctx, 126, H - 244, "Retry Check", (0.2, 0.2, 0.5), 20, a); chip(ctx, 300, H - 244, "Report Issue", (0.5, 0.12, 0.15), 20, a)
        # pipeline strip
        xs = [W * (i + 0.5) / len(words) for i in range(len(words))]
        for (w_, ts), x in zip(words, xs):
            on = t >= ts
            text(ctx, w_, x, 90, 36, True, (1, 1, 1) if on else (0.5, 0.55, 0.75), 1.0 if on else 0.45, "c", spacing=2)
        tag(ctx, "CONCEPTUAL SIMULATION · no real AIU device fault is depicted", y=H - 40, x=W - 760)
    return render(f, cam, (0.1, 0.12, 0.25), (0.3, 0.35, 0.5), fog_density=0.0, ambient=0.48, key=0.5, overlay=ov,
                  light=np.array([0.1, 0.1, 1.0]) / np.linalg.norm([0.1, 0.1, 1.0]), shadow_strength=0.3)

# ============================================================ 6. CENTRAL HVAC
def hvac_frame(t, dur=9.4):
    base = cached("hvac", hvac_static)
    f = Faces(); f.extend(base); f.extend(blower_fan(t))
    cam = Camera(kf([(0, (-14, -17, 7.5)), (dur, (3, -19, 5.5))], t), kf([(0, (-3, 2.5, 2.2)), (dur, (0, 2.7, 2.6))], t), fov=42)
    path = [(-8.6, 2.7, 2.9), (-6.7, 2.7, 3.15), (-6.0, 2.7, 4.2)]
    def ov(ctx, cam):
        # airflow particles: along duct, down branches, spreading under vents
        for k in range(48):
            u = (t * 0.35 + k / 48.0) % 1.0
            if u < 0.30:
                x = -6.7 + (u / 0.30) * 14.0; y, z = 2.7, 4.2
                col = (0.55, 0.8, 1.0)
            else:
                b = k % 3; vx = (-2.2, 2.1, 6.4)[b]; v = (u - 0.30) / 0.70
                x, y = vx + (math.sin(k) * 0.25 * v), 2.7 + math.cos(k * 1.7) * 0.25 * v; z = 4.2 - v * 1.9
                if k % 3 != (0 + 0): pass
                col = (0.65, 0.88, 1.0)
            sx, sy, zz = project(cam, (x, y, z))
            ctx.new_path(); ctx.set_source_rgba(*col, 0.85); ctx.arc(sx, sy, 3.5, 0, 6.3); ctx.fill()
        labels = [("CENTRAL HVAC / BLOWER", (-8.6, 1.5, 2.7), 0.8), ("MAIN SUPPLY DUCT", (-1.0, 2.7, 4.55), 2.6),
                  ("BRANCH DUCTS", (2.1, 2.7, 3.7), 4.3), ("CEILING VENTS", (2.1, 2.7, 3.2), 6.0)]
        for lab, p, ts in labels:
            a = ss((t - ts) / 0.4)
            if a <= 0: continue
            sx, sy, z = project(cam, p)
            ctx.new_path(); ctx.set_source_rgba(1, 1, 1, 0.8 * a); ctx.set_line_width(2); ctx.move_to(sx, sy); ctx.line_to(sx, sy - 80); ctx.stroke()
            ctx.new_path(); ctx.arc(sx, sy, 5, 0, 6.3); ctx.fill()
            chip(ctx, sx - 20, sy - 130, lab, (0.12, 0.12, 0.38), 20, a)
        if t > 6.9:
            a = ss((t - 6.9) / 0.4)
            card(ctx, 90, H - 250, 760, 120, 0.86 * a)
            text(ctx, "ZONE CONDITIONS: shown only when a sensor reports them", 120, H - 200, 22, True, (0.9, 0.93, 1), a)
            text(ctx, "temperature · airflow · otherwise “unavailable” — never assumed", 120, H - 164, 19, False, (0.7, 0.75, 0.95), a)
        bottom_caption(ctx, "IT VERIFIES BEFORE IT ACTS.", cap_alpha(t, 0.0, 6.9))
        tag(ctx, "CONCEPTUAL · prototype uses a small blower, ducts and vents · not an inspected AIU installation")
    return render(f, cam, (0.1, 0.12, 0.25), (0.28, 0.33, 0.5), fog_density=0.0, ambient=0.5, key=0.55, overlay=ov,
                  light=np.array([0.3, -0.4, 0.8]) / np.linalg.norm([0.3, -0.4, 0.8]), shadow_strength=0.3)

SCENES = {"massing": (massing_frame, 9.62), "approach": (approach_frame, 8.73), "access": (access_frame, 11.75),
          "occupancy": (occupancy_frame, 11.75), "projector": (projector_frame, 7.9), "hvac": (hvac_frame, 9.4)}

def _work(args):
    name, k = args
    fn, dur = SCENES[name]
    return k, fn(k / FPS)

def render_scene(name, out, procs=4, limit=None):
    fn, dur = SCENES[name]
    n = int(round(dur * FPS)) if limit is None else limit
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(procs) as pool:
        for k, img in pool.imap(_work, [(name, k) for k in range(n)], chunksize=2):
            p.stdin.write(np.ascontiguousarray(img).tobytes())
    p.stdin.close(); p.wait()

if __name__ == "__main__":
    name = sys.argv[1]
    if len(sys.argv) > 2 and sys.argv[2] == "still":
        t = float(sys.argv[3]); fn, d = SCENES[name]
        img = fn(t); cv2.imwrite(f"/sessions/great-sleepy-rubin/mnt/outputs/_preview/{name}_{t}.png", cv2.resize(img[..., ::-1], (960, 540)))
    else:
        render_scene(name, f"/tmp/work/trailer/{name}.mp4")
