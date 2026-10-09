"""Reusable 3D parts: people, corridor, classroom, HVAC, campus massing + 2D overlay helpers."""
import math
import numpy as np
import cairo
from r3d import *

NAVY = np.array([0.11, 0.10, 0.31]); NAVY2 = np.array([0.16, 0.15, 0.42]); RED = np.array([0.66, 0.10, 0.12])
WHITE = np.array([0.93, 0.94, 0.97]); GREY = np.array([0.72, 0.74, 0.79]); DGREY = np.array([0.18, 0.19, 0.24])
WOOD = np.array([0.60, 0.45, 0.32]); SKIN = np.array([0.80, 0.62, 0.50]); SKY = np.array([0.55, 0.72, 0.95])


def ss(x): x = min(max(x, 0.0), 1.0); return x * x * (3 - 2 * x)
def lerp(a, b, t): return np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t
def kf(keys, t):
    """keys: [(t, value)...] smoothstep interpolated."""
    if t <= keys[0][0]: return np.asarray(keys[0][1], float)
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1: return lerp(v0, v1, ss((t - t0) / (t1 - t0)))
    return np.asarray(keys[-1][1], float)


def seg(origin, theta, L, w, d, color, axis_rot=rotx):
    f = box((0, 0, -L / 2), (w, d, L), color, shadow=True)
    R = axis_rot(theta)
    return f.transform(R, origin), np.asarray(origin) + R @ np.array([0, 0, -L])


def person(pos, yaw=0.0, phase=0.0, walk=0.0, suit=NAVY, shirt=WHITE, pants=DGREY, skin=SKIN, hair=np.array([0.1, 0.08, 0.07]),
           seated=False, arm_r=None, anon=False, lod=1, scale=1.0, lanyard=False):
    f = Faces()
    if anon:
        suit = shirt = pants = skin = hair = np.array([0.60, 0.64, 0.72])
    hip = np.array([0, 0, 0.92])
    sw = math.sin(phase) * 0.55 * walk
    for side, sgn in ((-1, 1), (1, -1)):
        th = (sw * sgn) if not seated else math.pi / 2
        o = hip + np.array([side * 0.10, 0, 0])
        thigh, knee = seg(o, th, 0.45, 0.14, 0.15, pants)
        f.extend(thigh)
        bend = 0.0 if seated else -0.9 * max(0.0, math.sin(phase + (0 if sgn > 0 else math.pi) + 1.2)) * walk
        th2 = (th + bend) if not seated else 0.0
        shin, foot = seg(knee, th2, 0.45, 0.12, 0.13, pants)
        f.extend(shin)
        f.extend(box((foot[0], foot[1] + 0.05, foot[2] + 0.03), (0.11, 0.26, 0.07), np.array([0.07, 0.07, 0.09]), shadow=True))
    f.extend(box((0, 0, 1.18), (0.40, 0.23, 0.58), suit, shadow=True))
    f.extend(box((0, 0.121, 1.30), (0.12, 0.01, 0.30), shirt))         # shirt front V
    if lanyard: f.extend(box((0, 0.13, 1.25), (0.03, 0.01, 0.30), RED)); f.extend(box((0, 0.135, 1.08), (0.07, 0.01, 0.1), WHITE))
    f.extend(cyl((0, 0, 1.52), 0.055, 0.08, skin, n=8))
    nu, nv = (10, 6) if lod else (7, 4)
    f.extend(sphere((0, 0.01, 1.64), 0.11, skin, nu, nv, shadow=True))
    if not anon:
        f.extend(sphere((0, -0.012, 1.68), 0.108, hair, nu, nv))
    sh = np.array([0, 0, 1.43])
    for side, sgn in ((-1, 1), (1, -1)):
        o = sh + np.array([side * 0.25, 0, 0])
        if arm_r is not None and side == 1:
            th = arm_r; th2 = arm_r * 0.9
        else:
            th = (-sw * sgn * 0.8) if not seated else 0.5
            th2 = 0.15 if not seated else 1.1
        up, el = seg(o, th, 0.30, 0.09, 0.09, suit)
        f.extend(up)
        lo, hand = seg(el, th2, 0.28, 0.08, 0.08, suit)
        f.extend(lo)
        f.extend(sphere(hand, 0.045, skin, 6, 4))
    R = rotz(yaw) * scale
    return f.transform(R, pos)


# --------------------------------------------------------------- corridor
def corridor():
    f = Faces()
    f.extend(plane(-1.6, 1.6, 0, 26, 0, np.array([0.80, 0.82, 0.86]), tile=0.8, color2=np.array([0.75, 0.78, 0.84]), floor=True))
    ceil = plane(-1.6, 1.6, 0, 26, 3.1, np.array([0.90, 0.91, 0.95]), tile=1.3)
    ceil.P = [p[::-1] for p in ceil.P]; f.extend(ceil)
    f.extend(wall((1.6, 0), (1.6, 26), 0, 3.1, np.array([0.92, 0.93, 0.96]), tile=1.3, flip=True))
    f.extend(wall((-1.6, 0), (-1.6, 26), 0, 3.1, np.array([0.90, 0.91, 0.95]), tile=1.3, flip=False))
    f.extend(wall((-1.6, 26), (1.6, 26), 0, 3.1, np.array([0.88, 0.89, 0.93]), tile=1.3, flip=False))
    f.extend(box((1.57, 13, 0.07), (0.06, 26, 0.14), NAVY))                # skirting right
    f.extend(box((-1.57, 13, 0.07), (0.06, 26, 0.14), NAVY))
    f.extend(box((1.58, 13, 1.05), (0.03, 26, 0.04), NAVY2))               # accent line
    for y in np.arange(1.2, 26, 3.4):                                       # glazing bands
        f.add([(-1.585, y, 0.9), (-1.585, y + 2.6, 0.9), (-1.585, y + 2.6, 2.5), (-1.585, y, 2.5)][::-1], np.array([0.70, 0.84, 1.0]), emissive=True, decal=True)
    for y in np.arange(2.0, 26, 4.0):
        f.extend(box((0, y, 3.08), (0.35, 2.4, 0.03), np.array([1.0, 0.98, 0.94]), emissive=True))
    for y in (6.0, 12.0, 14.6, 20.0, 24.0):                                # doors (right wall)
        if y == 14.6: continue
        f.extend(box((1.56, y, 1.08), (0.07, 1.0, 2.16), WOOD))
        f.extend(box((1.545, y, 2.30), (0.02, 0.28, 0.1), NAVY))
    f.extend(box((1.56, 14.6, 2.24), (0.10, 1.2, 0.08), DGREY))             # target door frame
    f.extend(box((1.56, 14.6, 1.12), (0.10, 0.06, 2.24), DGREY).transform(None, (0, -0.57, 0)))
    f.extend(box((1.56, 14.6, 1.12), (0.10, 0.06, 2.24), DGREY).transform(None, (0, 0.57, 0)))
    f.extend(box((1.545, 14.6, 2.45), (0.02, 0.40, 0.14), NAVY))            # room plate
    # reader pod: camera + status LED (+Raspberry-Pi style enclosure)
    f.extend(box((1.53, 13.55, 1.50), (0.07, 0.16, 0.34), np.array([0.14, 0.15, 0.20]), shadow=True))
    f.extend(cyl((1.485, 13.55, 1.58), 0.035, 0.03, np.array([0.02, 0.02, 0.03]), axis='x', n=12))
    return f


def door_panel(angle):
    """Hinged door at y=14.1 (hinge), opening into the room (+x)."""
    d = box((0, 0.5, 0), (0.06, 1.0, 2.14), WOOD, shadow=True)
    d.extend(box((-0.04, 0.88, 0), (0.03, 0.04, 0.10), np.array([0.8, 0.8, 0.82])))
    return d.transform(rotz(-angle), (1.56, 14.1, 1.07))


def led(pos, color, on=True):
    f = Faces()
    f.extend(sphere(pos, 0.018, color if on else np.array([0.15, 0.15, 0.17]), 6, 4, emissive=on))
    return f


# --------------------------------------------------------------- classroom
def classroom_static(with_desks=True):
    f = Faces()
    f.extend(plane(-6, 6, 0, 10, 0, np.array([0.70, 0.62, 0.52]), tile=1.0, color2=np.array([0.67, 0.59, 0.49]), floor=True))
    ceil = plane(-6, 6, 0, 10, 3.2, np.array([0.92, 0.93, 0.96]), tile=1.0)
    ceil.P = [p[::-1] for p in ceil.P]; f.extend(ceil)
    f.extend(wall((-6, 0), (6, 0), 0, 3.2, np.array([0.93, 0.94, 0.97]), tile=1.5, flip=True))          # front
    f.extend(wall((-6, 10), (6, 10), 0, 3.2, np.array([0.90, 0.91, 0.95]), tile=1.5, flip=False))         # rear
    f.extend(wall((-6, 0), (-6, 10), 0, 3.2, np.array([0.92, 0.93, 0.96]), tile=1.5, flip=False))         # left
    f.extend(wall((6, 0), (6, 10), 0, 3.2, np.array([0.92, 0.93, 0.96]), tile=1.5, flip=True))          # right
    for y in (1.5, 4.5, 7.5):
        f.add([(-5.985, y, 1.0), (-5.985, y + 2.4, 1.0), (-5.985, y + 2.4, 2.6), (-5.985, y, 2.6)][::-1], np.array([0.72, 0.86, 1.0]), emissive=True, decal=True)
    f.extend(box((0, 0.03, 1.9), (3.4, 0.04, 1.9), np.array([0.20, 0.22, 0.30])))                         # screen (dark when off)
    f.extend(box((-4.2, 0.03, 1.5), (2.2, 0.04, 1.2), np.array([0.95, 0.96, 0.98])))                       # whiteboard
    f.extend(box((0, 0.2, 3.17), (11.6, 0.35, 0.05), NAVY))                                                # navy header trim
    for x in (-3.0, 3.0):
        for y in (2.5, 6.5):
            f.extend(box((x, y, 3.19), (0.6, 0.6, 0.02), np.array([0.60, 0.62, 0.68])))                  # ceiling vent grills
            for k in range(-2, 3):
                f.extend(box((x, y + k * 0.1, 3.185), (0.55, 0.012, 0.01), np.array([0.3, 0.32, 0.38])))
    for x in (-3.5, 0, 3.5):
        for y in (3.0, 7.0):
            f.extend(box((x, y, 3.19), (1.4, 0.35, 0.02), np.array([1.0, 0.98, 0.94]), emissive=True))
    f.extend(box((2.4, 1.2, 0.5), (0.9, 0.5, 1.0), WOOD, shadow=True))                                      # podium
    f.extend(box((2.4, 1.2, 1.02), (0.9, 0.5, 0.04), np.array([0.2, 0.2, 0.25]), shadow=True))
    if with_desks:
        for r, y in enumerate((3.6, 4.8, 6.0, 7.2, 8.4)):
            for c, x in enumerate(np.arange(-4.2, 4.3, 1.2)):
                f.extend(box((x, y, 0.72), (0.95, 0.5, 0.04), np.array([0.85, 0.82, 0.76]), shadow=True))
                for lx in (-0.42, 0.42):
                    f.extend(box((x + lx, y, 0.36), (0.04, 0.44, 0.72), DGREY, shadow=True))
                f.extend(box((x, y + 0.55, 0.45), (0.42, 0.40, 0.04), NAVY2, shadow=True))
                f.extend(box((x, y + 0.75, 0.70), (0.42, 0.04, 0.4), NAVY2, shadow=True))
    return f


def seat_positions():
    out = []
    for y in (3.6, 4.8, 6.0, 7.2, 8.4):
        for x in np.arange(-4.2, 4.3, 1.2):
            out.append((x, y))
    return out


def projector(on_beam=None):
    f = Faces()
    f.extend(box((0, 5.2, 3.10), (0.04, 0.04, 0.2), DGREY))
    f.extend(box((0, 5.2, 2.94), (0.46, 0.34, 0.13), np.array([0.90, 0.91, 0.94]), shadow=True))
    f.extend(cyl((0, 5.03, 2.94), 0.06, 0.04, np.array([0.02, 0.02, 0.03]), axis='y', n=12))
    return f


# --------------------------------------------------------------- HVAC section
def hvac_static():
    f = Faces()
    f.extend(plane(-11, 9, -3.5, 5.5, 0, np.array([0.78, 0.80, 0.85]), tile=1.0, color2=np.array([0.75, 0.77, 0.83]), floor=True))
    # plant room floor slab/back wall
    f.extend(wall((-11, 5.5), (9, 5.5), 0, 4.6, np.array([0.88, 0.89, 0.94]), tile=1.5, flip=False))
    # rooms (open towards camera at y=-3.5)
    for k, x0 in enumerate((-4.2, 0.1, 4.4)):
        x1 = x0 + 4.0
        f.extend(plane(x0, x1, 0, 5.4, 0.01, np.array([0.72, 0.64, 0.54]), tile=1.0))
        f.extend(wall((x0, 5.4), (x1, 5.4), 0, 3.2, np.array([0.93, 0.94, 0.97]), tile=1.3, flip=False))
        f.extend(wall((x0, 0), (x0, 5.4), 0, 3.2, np.array([0.90, 0.91, 0.95]), tile=1.3, flip=False, alpha=0.55, two=True))
        f.extend(wall((x1, 0), (x1, 5.4), 0, 3.2, np.array([0.90, 0.91, 0.95]), tile=1.3, flip=True, alpha=0.55, two=True))
        ceil = plane(x0, x1, 0, 5.4, 3.2, np.array([0.92, 0.93, 0.96]), tile=1.3, alpha=0.5, two=True)
        f.extend(ceil)
        f.extend(box((x0 + 2, 5.35, 1.9), (2.4, 0.04, 1.3), np.array([0.2, 0.22, 0.3])))
        for r in (1.3, 2.5, 3.7):
            for c in (-1.2, -0.4, 0.4, 1.2):
                f.extend(box((x0 + 2 + c, r, 0.72), (0.6, 0.35, 0.04), np.array([0.85, 0.82, 0.76]), shadow=True))
                f.extend(box((x0 + 2 + c, r, 0.36), (0.04, 0.3, 0.72), DGREY, shadow=True))
        f.extend(box((x0 + 2, 2.7, 3.19), (0.7, 0.7, 0.02), np.array([0.6, 0.62, 0.68])))          # vent grill
        for kk in range(-3, 4):
            f.extend(box((x0 + 2, 2.7 + kk * 0.09, 3.185), (0.66, 0.012, 0.01), np.array([0.28, 0.3, 0.36])))
    # main supply duct above the rooms (rectangular), z 3.9-4.5
    f.extend(box((-1.0, 2.7, 4.2), (16.0, 0.9, 0.6), np.array([0.78, 0.8, 0.85]), shadow=True))
    f.extend(box((-1.0, 2.7, 4.2), (16.0, 0.92, 0.04), NAVY2))
    for x0 in (-4.2, 0.1, 4.4):                                                                   # branch ducts to vents
        f.extend(box((x0 + 2, 2.7, 3.7), (0.55, 0.55, 1.0), np.array([0.80, 0.82, 0.87]), shadow=True))
    # central HVAC unit + blower housing
    f.extend(box((-8.6, 2.7, 1.3), (3.6, 2.2, 2.6), np.array([0.82, 0.84, 0.88]), shadow=True))
    f.extend(box((-8.6, 1.58, 1.3), (3.2, 0.03, 2.2), NAVY))
    f.extend(box((-8.6, 1.56, 2.45), (1.6, 0.02, 0.18), RED))
    f.extend(box((-6.55, 2.7, 3.15), (0.5, 0.9, 0.9), np.array([0.8, 0.82, 0.87]), shadow=True))     # plenum to duct
    f.extend(box((-6.95, 2.7, 2.2), (0.04, 0.04, 0.04), WHITE))
    return f


def blower_fan(t):
    f = Faces()
    f.extend(cyl((-8.6, 1.55, 1.2), 0.82, 0.12, np.array([0.30, 0.32, 0.38]), axis='y', n=24))
    for k in range(6):
        a = t * 8 + k * math.pi / 3
        pts = [(-8.6 + 0.12 * math.cos(a), 1.50, 1.2 + 0.12 * math.sin(a)),
               (-8.6 + 0.74 * math.cos(a - 0.35), 1.50, 1.2 + 0.74 * math.sin(a - 0.35)),
               (-8.6 + 0.74 * math.cos(a + 0.12), 1.50, 1.2 + 0.74 * math.sin(a + 0.12))]
        f.add(pts, np.array([0.85, 0.87, 0.92]), two=True)
    f.extend(cyl((-8.6, 1.50, 1.2), 0.13, 0.08, DGREY, axis='y', n=12))
    return f


# --------------------------------------------------------------- campus massing (CONCEPTUAL, not AIU)
def massing():
    f = Faces()
    f.extend(plane(-60, 60, -20, 100, 0, np.array([0.64, 0.60, 0.52]), tile=10, color2=np.array([0.61, 0.57, 0.50]), floor=True))
    f.extend(plane(-6, 6, -20, 100, 0.02, np.array([0.78, 0.75, 0.70]), tile=6, floor=True))        # central walkway
    blocks = [(-26, 30, 18, 12, 9), (26, 36, 18, 14, 12), (-28, 62, 22, 12, 8), (28, 68, 20, 14, 10), (0, 96, 30, 12, 14),
              (-40, 10, 12, 10, 7), (42, 12, 12, 10, 7)]
    for (x, y, w, d, h) in blocks:
        f.extend(box((x, y, h / 2), (w, d, h), np.array([0.90, 0.86, 0.78]), shadow=True))
        f.extend(box((x, y, h + 0.4), (w + 0.6, d + 0.6, 0.8), NAVY, shadow=True))
        side = -1 if x > 0 else 1
        for fl in range(int(h // 3)):
            f.add([(x + side * (w / 2 + 0.02), y - d / 2 + 1, 1.2 + fl * 3), (x + side * (w / 2 + 0.02), y + d / 2 - 1, 1.2 + fl * 3),
                   (x + side * (w / 2 + 0.02), y + d / 2 - 1, 2.6 + fl * 3), (x + side * (w / 2 + 0.02), y - d / 2 + 1, 2.6 + fl * 3)][::(1 if side < 0 else -1)],
                  np.array([0.45, 0.62, 0.82]) if fl % 2 == 0 else np.array([0.5, 0.68, 0.88]), emissive=False)
    for i in range(26):
        x = (-1) ** i * (9 + (i * 7) % 11); y = 8 + i * 3.6
        f.extend(cyl((x, y, 1.0), 0.18, 2.0, np.array([0.35, 0.25, 0.18]), n=6))
        f.extend(sphere((x, y, 2.6), 1.3, np.array([0.28, 0.48, 0.30]), 8, 5, shadow=True))
    return f


# --------------------------------------------------------------- 2D overlay helpers (cairo)
def font(ctx, size, bold=True, family="Poppins"):
    ctx.select_font_face(family, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)


def text(ctx, s, x, y, size=28, bold=True, color=(1, 1, 1), alpha=1.0, anchor="l", spacing=0.0):
    ctx.new_path(); font(ctx, size, bold)
    if spacing:
        widths = [ctx.text_extents(ch).x_advance + spacing for ch in s]; tw = sum(widths) - spacing
    else:
        tw = ctx.text_extents(s).x_advance
    if anchor == "c": x -= tw / 2
    elif anchor == "r": x -= tw
    ctx.set_source_rgba(color[0], color[1], color[2], alpha)
    if spacing:
        cx = x
        for ch, w in zip(s, widths):
            ctx.move_to(cx, y); ctx.show_text(ch); cx += w
    else:
        ctx.move_to(x, y); ctx.show_text(s)
    return tw


def rrect(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0); ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi); ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2); ctx.close_path()


def card(ctx, x, y, w, h, alpha=0.82, border=(0.45, 0.5, 0.75)):
    rrect(ctx, x, y, w, h, 14); ctx.set_source_rgba(0.05, 0.05, 0.16, alpha); ctx.fill_preserve()
    ctx.set_source_rgba(border[0], border[1], border[2], 0.55); ctx.set_line_width(1.5); ctx.stroke()


def chip(ctx, x, y, label, color, size=22, alpha=1.0):
    ctx.new_path()
    font(ctx, size, True); tw = ctx.text_extents(label).x_advance
    rrect(ctx, x, y, tw + 34, size + 20, 10); ctx.set_source_rgba(color[0], color[1], color[2], 0.92 * alpha); ctx.fill()
    ctx.set_source_rgba(1, 1, 1, alpha); ctx.move_to(x + 17, y + size + 5); ctx.show_text(label)
    return tw + 34


def check(ctx, x, y, s=22, color=(0.35, 0.85, 0.6), alpha=1.0):
    ctx.new_path()
    ctx.set_source_rgba(color[0], color[1], color[2], alpha); ctx.set_line_width(4); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.move_to(x, y); ctx.line_to(x + s * 0.38, y + s * 0.4); ctx.line_to(x + s, y - s * 0.55); ctx.stroke()


def tag(ctx, label, x=None, y=None):
    ctx.new_path()
    font(ctx, 17, False); tw = ctx.text_extents(label).x_advance
    x = W - tw - 60 if x is None else x; y = 46 if y is None else y
    rrect(ctx, x - 14, y - 22, tw + 28, 34, 8); ctx.set_source_rgba(0.04, 0.04, 0.14, 0.7); ctx.fill()
    ctx.set_source_rgba(0.95, 0.85, 0.55, 0.95); ctx.move_to(x, y); ctx.show_text(label)


def bottom_caption(ctx, s, a=1.0, y=H - 96):
    if a <= 0: return
    font(ctx, 40, True); tw = ctx.text_extents(s).x_advance
    ctx.set_source_rgba(0, 0, 0, 0.42 * a); rrect(ctx, W / 2 - tw / 2 - 28, y - 46, tw + 56, 72, 10); ctx.fill()
    text(ctx, s, W / 2, y, 40, True, (0.96, 0.97, 1.0), a, "c")


def project(cam, p):
    v = cam.to_view(np.asarray(p, float)); s = cam.proj(v); return float(s[0]), float(s[1]), float(v[2])
