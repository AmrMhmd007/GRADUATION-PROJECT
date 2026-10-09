# AIU SMART CAMPUS — Final Trailer: Production Report

Deliverable: `AIU_SMART_CAMPUS_FINAL_TRAILER.mp4` — 1920×1080, 30 fps, H.264 + AAC, 2:22.9 (matches the voice-over, 142.9 s).

## What was completed
- Six conceptual 3D scenes rendered with a custom Python 3D renderer (perspective camera, shading, soft shadows, camera moves). **Blender could not be installed here** (no `bpy` for the sandbox's Python 3.10), so this is a hybrid: custom 3D + ffmpeg motion graphics. It is clean "technical visualisation", not photoreal.
- Real application screenshots from the project dashboard for the digital-system scenes.
- Recorded voice-over, sidechain-ducked procedural music and transition sounds, re-timed to the new scenes.
- Checks run: ffmpeg black-frame / freeze detection, audio level check (peak −0.2 dB, no clipping), contact-sheet review of frames from every scene. I did **not** watch the video in real time or listen to it; sync was checked by construction (scene captions are timed to the recorded VO timestamps) and by frames.

## Scene timeline (time → content → type)
| Time | Scene | Type |
|---|---|---|
| 0:00–0:09 | Opening — **placeholder** for real AIU establishing shot: conceptual campus massing with title lines | CONCEPTUAL ANIMATION (placeholder; labelled "NOT the AIU campus") |
| 0:09–0:17 | AIU SMART CAMPUS title reveal over the darkened massing | MOTION GRAPHICS |
| 0:17–0:25 | Doctor walks down a corridor toward a lecture room | CONCEPTUAL 3D |
| 0:25–0:30 | Smart Building overview | **ACTUAL APP SCREENSHOT** |
| 0:30–0:42 | Independent ceiling camera counts occupants; anonymous figures, no faces/identities/attendance | CONCEPTUAL 3D |
| 0:42–0:49 | Doctor manually starts a projector; current sensor shows 0.4 W vs expected ON → HIGH alert; SENSE→MONITOR strip | CONCEPTUAL 3D simulation |
| 0:49–0:59 | Smart Lab 301 detail, zones | **ACTUAL APP SCREENSHOT** |
| 0:59–1:08 | Central HVAC → main duct → branch ducts → ceiling vents, airflow particles | CONCEPTUAL 3D (prototype concept) |
| 1:08–1:17 | Automation log | **ACTUAL APP SCREENSHOT** |
| 1:17–1:29 | Face verification → backend checks (active, role, room, schedule, access window) → GRANT → door opens → evidence | CONCEPTUAL 3D |
| 1:29–1:47 | Access events, GRANTED/DENIED/UNUSUAL/INVESTIGATED, investigation + evidence | **ACTUAL APP SCREENSHOTS** |
| 1:47–2:09 | Command Center | **ACTUAL APP SCREENSHOT** |
| 2:09–2:13 | "THE CAMPUS CAN SEE. UNDERSTAND. DECIDE. ACT." | MOTION GRAPHICS |
| 2:13–2:23 | Final title: AIU SMART CAMPUS · CYBER-PHYSICAL CONTROL SYSTEM · Designed for Alamein International University | MOTION GRAPHICS |

## Real footage vs application vs conceptual
- **Real AIU footage:** none (see AIU_FOOTAGE_SOURCES.md).
- **Actual application:** 10 screenshots of the project's own dashboard (screenshots, not screen recordings; no interface was invented). Note the face-door, occupancy-count and device-fault screens are not shown from the app in this cut — those capabilities appear only as conceptual 3D scenes.
- **Conceptual animation:** campus massing, corridor, access sequence, classroom occupancy, projector fault, central HVAC. Each carries an on-screen "CONCEPTUAL" tag. None depicts installed AIU hardware, a real AIU room, a real AIU device failure, or an inspected AIU HVAC system.

## Assets requiring permission
All six candidate AIU sources in AIU_FOOTAGE_SOURCES.md. Nothing from them is included.

## Missing requested shots (not sourced)
Scene 1 exterior/aerial; Scene 2 real building/corridor; Scene 4 real lecture hall/lab; Scene 6 building-exterior transition; Scene 8 closing campus shot. Each is a placeholder or replaced by the conceptual scene.

## Voice-over
The only human voice available is your existing recording (`AIU_trailer_voiceover_recorded.mp3`, script in `AIU_trailer_voiceover_script.txt`). I cannot record a human voice, so the new scene-1 line from your brief ("Every day, a modern campus brings together people, spaces, technology, and thousands of decisions.") was **not** recorded; the existing line "Every day, a modern campus makes thousands of decisions." is used. To use your new line, record it and swap it into the first seconds; re-time with `source/build_audio_v2.py` / `build_final.py`.

## Remaining limitations
1. No real AIU footage (permission + file access).
2. Visual style is stylised 3D, not Blender-quality; characters are simple mannequins.
3. App scenes are screenshots with pan/zoom, not live screen recordings; the newer features (Face ID, occupancy, device faults, central HVAC) were not captured from the running dashboard.
4. Scene lengths follow the existing 142.9 s voice-over, not the 1:50 outline in your brief.
5. The ElevenLabs voice's commercial terms are for you to confirm.

## Rebuild
`source/scenes.py <scene>` renders a 3D scene; `source/build_final.py` assembles; `source/build_audio_v2.py` mixes audio. Needs numpy, pycairo, opencv, ffmpeg, Poppins font.
