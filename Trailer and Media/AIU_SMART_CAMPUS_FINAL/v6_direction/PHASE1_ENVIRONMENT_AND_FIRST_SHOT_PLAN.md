# Phase 1 — Environment check (your Mac) and first-shot plan

Nothing was installed or changed. I only read System Settings > General > About and the installed-application list the system gave me.

## What I verified on your Mac
| Item | Finding | How verified |
|---|---|---|
| Model / chip | MacBook Pro 14" (Nov 2024), **Apple M4** (arm64) | System Settings > About |
| RAM | **16 GB** unified memory | About |
| Storage | 994.66 GB disk, **606.2 GB free** | About |
| OS | macOS 27.0 "Golden Gate" (27.0.1 update pending; not touched) | About / Software Update |
| GPU / Metal | M4 integrated GPU — Metal is supported by hardware; Blender's Metal backend works on Apple silicon. Not yet exercised because Blender isn't installed | Inferred from chip (not tested) |
| **Blender** | **Not installed** (absent from the installed-apps list) | App list |
| **After Effects** | **Not installed** | App list |
| **Premiere Pro** | **Not installed** | App list |
| Available instead | **Final Cut Pro** (edit, colour, titles, export), iMovie, GarageBand (music/SFX), QuickTime Player (screen recording), Terminal, VS Code, Cursor, Keynote, Preview | App list |
| Project files | `AIU_SMART_CAMPUS_FINAL` on your Desktop: prototype image, 7 real 2× dashboard captures, AIU photographs, voice-over, source code | My file access |

Limits of this check: I cannot see folders outside Desktop/Documents/Downloads, so a Blender copy in an unusual location would be missed; and I cannot run Terminal commands on your Mac (Terminal is click-only for me).

## Pipeline adapted to what exists
| Role | Planned | Reality |
|---|---|---|
| 3D, materials, lighting, cameras | **Blender 4.x (free, blender.org)** with Metal GPU, Cycles | **Needs your approval to install** |
| Compositing / motion graphics / tracking | After Effects | Not installed. Replacement: overlays pre-rendered by me as transparent ProRes 4444 clips, assembled in Final Cut Pro; Blender's compositor for 3D passes. (No AE-style planar tracking — avoid shots that need it, or install an AE/DaVinci Resolve trial if you choose) |
| Edit, music, SFX, export | Premiere Pro | **Final Cut Pro** (installed) |
| Humans | Licensed rigged characters, or live action | Neither is in place yet (see below) |
| Real app footage | Your screen recordings | **You record** with Cmd+Shift+5 (1080p/60) while the app runs |

## Why I am stopping before the first shot
Your rule: if the character or environment can't meet the quality bar, stop and explain what is missing. Missing right now:
1. **Blender** (not installed) — I cannot render the corridor, door hardware or HVAC without it, and I cannot run it for you.
2. **A human**: no licensed rigged character with walking animation is present, and I cannot download one.
3. **Corridor/door/hardware assets** (optional; I can model simple hardware parametrically, but quality depends on texture/HDRI/model packs).
Making any "first shot" now would repeat the rejected blockout, so none was made. **No test render exists.**

## Recommended hybrid (most likely to look real)
- **Human shots = live action.** Film a real adult (classmate/lecturer) walking along a real corridor and opening a classroom door with an iPhone on a gimbal or steady hold: 4K, 30 fps, locked exposure, shot at AIU if permitted. This avoids synthetic humans entirely and is the only route to natural movement here.
- **Blender = what cameras cannot film:** the access reader and lock macro, the back-of-door bolt, ceiling occupancy camera, projector mount/sensor, and the **central HVAC cutaway**. Blender scenes use CC0 materials/HDRIs (Poly Haven, ambientCG — check each licence) and my parametric models.
- **Final Cut Pro** edits live action + Blender renders + real app recordings + the prototype image, with my overlays and sound.
- Backend logic on screen follows the project: identity check → backend authorization (account, room, schedule, window) → GRANT/DENY → only then bolt/door; labelled "conceptual — door hardware not yet connected".

## First proof-of-quality shot (10–15 s) — spec, ready to execute once approved
"Corridor to grant": 5 s tracking shot (live action, 35 mm eq., gimbal, subject left-to-right) → 3 s macro of the reader (Blender, 100 mm, rack focus camera → LED) with restrained overlay IDENTITY › ACCOUNT › ROOM › SCHEDULE › BACKEND → 2 s GRANT chip → 2 s macro of bolt retracting (Blender) → 3 s door opens and subject enters (live action, matched direction). Lighting: window key from the left; navy/white grade; one red status LED only. Sound: footsteps, reader beep, relay click, latch, door swing, room tone.

## What I need from you (approvals / supply)
1. **Approve installing Blender** from blender.org (free; ~400 MB) — or tell me you will install it. I will not install anything myself.
2. Choose the human route: **(A) film live action** (recommended), **(B) download a licensed rigged character + walk cycle** (e.g. Mixamo with your Adobe ID — you must accept its terms; I cannot), or **(C) both**.
3. Confirm whether you can film inside AIU, and send the clips (or a corridor/door photo for reference).
4. Record the real app with Cmd+Shift+5 when the demo database is in the state you want (tell me if you want a clearly labelled demo dataset instead of the current mostly-empty one).
5. After Blender is installed I will write the scene scripts (corridor hardware, HVAC cutaway, camera paths) for you to run; I cannot test Blender scripts here, so the first run may need a round of fixes.

Until you reply with 1–2 I will not begin any render.
