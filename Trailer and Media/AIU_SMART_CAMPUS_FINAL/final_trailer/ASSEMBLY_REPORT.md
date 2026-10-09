# Trailer assembly — report (updated; previous preview kept unchanged)
## Current review cut: `AIU_TRAILER_REVIEW_FINAL.mp4`
1920×1080, 30 fps, H.264 yuv420p CRF 18, 32.5 s (975 frames), silent (no audio track). Built by `assemble_review.py` (0.5 s xfades). Previous `AIU_TRAILER_ASSEMBLY_PREVIEW.mp4` untouched (md5 694f34bc…).
| Shot | Source | Seg |
|---|---|---|
| 1 Access | review_v3 MP4 (960×540, upscaled) + verification overlay | 10 s |
| 2 Classroom | occupancy preview MP4 (1280×720, upscaled), 9–15 s | 6 s |
| 3 Dashboard | `recordings/AIU_OCCUPANCY_DASHBOARD_PROVISIONAL.mp4` | 8 s |
| 4 Prototype + title | after_effects/prototype_reveal preview + 2 s hold | 10 s |
## Dashboard — what it is and is not
**NOT a screen recording.** `recordings/AIU_OCCUPANCY_DASHBOARD_RAW.mov` does NOT exist. QuickTime/Cmd+Shift+5 capture was blocked: QuickTime has no controllable menu here and your Terminal windows overlap the dashboard; Chrome shows a debugging banner.
The clip is real pixels captured from the running app (Chrome tool, localhost:5174 → sim backend 8001, Occupancy tab, your logged-in session), shown with a slow push-in. Only edit: the mouse-cursor patch (~40×44 px) was replaced with the same area from an earlier cursor-free capture. Amber caption added by me under the app: "SIMULATED DATA — NOT LIVE CAMERA OR SENSOR TELEMETRY". Sources in `recordings/source_frames/`; script `make_dashboard_clip.py`.
## Verified
- Isolation: your login row went to the sim DB; real DB 55 audit rows, 0 occupancy readings (only the pre-existing 11:33 UTC login differs from baseline); MQTT disabled; nothing written to the real DB by this work.
- Page (read from the live DOM text + screenshot): A101 31/40, A102 18/30, Smart Lab 301 11/24, Lecture Hall 101 74/120; Server Room, Section Room 204, Hall B Unavailable/UNKNOWN/UNAVAILABLE; amber SIMULATED banner; ONLINE 0, SIMULATED 4; sensor column "No hardware (simulated)".
- Video: decodes fully (ffmpeg null decode), 1920×1080/30, 0 black segments ≥0.2 s (blackdetect), 9 sample frames inspected. I did NOT watch it in motion.
## Limitations
- Dashboard is a push-in on a still capture, not live motion; UI table styling is the app's own (some columns look unstyled).
- Campus Map tab (not shown) still shows DEGRADED for simulated rooms; Room Intel/Staff Today also not corrected — don't show them.
- Door/classroom footage upscaled and soft; door v3 had known review notes. Classroom has no people/count.
- After Effects: `AIU_Prototype_Reveal.jsx` never run; no .aep exists. Prototype shot is the sandbox render.
- Not committed or pushed to GitHub.
## To replace with a true recording (shortest action for you)
Close/hide the two Terminal windows, press Cmd+Shift+5 → Record Selected Portion over the Chrome page → ~12 s → save as `recordings/AIU_OCCUPANCY_DASHBOARD_RAW.mov`; I'll swap it into `assemble_review.py` (variable `DASH`).

---
## Update — After Effects, desktop recording, motion check
**After Effects (actually executed, 15:15–15:17 local):** the original script had failed part-way earlier (stopped after the first label: `comp.markers` does not exist in the AE API). Fixed (marker line removed, camera zoom/distance set to 2666 for 1:1 scale, text-tracking animator + easing wrapped in try/catch, global error alert); original kept as `AIU_Prototype_Reveal_v1_ORIGINAL.jsx`. Run through File ▸ Scripts ▸ Run Script File in After Effects 2026: it completed ("Built AIU_Prototype_Reveal"), saved `after_effects/prototype_reveal/AIU_Prototype_Reveal.aep` (valid RIFX file, ~500 KB, folders 01–07 + comp + camera + control null + highlight/label layers + markers), and rendered `AE_PREVIEW_PROTOTYPE_REVEAL.mp4` with AE's own H.264 (1920×1080, 30 fps, 240 frames, 8.0 s; first render kept as `_v1.mp4`).
**Quality of the AE render: not good enough to use.** I inspected stills: the image, camera move and title work, but the room labels are left-aligned at their anchor (clipped/overlapping, e.g. "ROOM 3031 — LE…") and the highlight boxes sit above-right of the door signs. The trailer therefore still uses the cleaner sandbox-rendered prototype preview. Fixing = centre point-text justification and re-measure highlight coordinates in AE (not done).
**Desktop recording:** attempted via QuickTime/Chrome; not achievable cleanly (your Terminal windows share the screen, Terminal can't be hidden at click tier, Chrome shows a debugger banner). Dashboard shot therefore remains a still-based shot built from real app captures (see above). Not claimed as a recording.
**"In motion" inspection:** I cannot play video. I checked decoding, black-frame detection and many sampled stills only.
**Audio:** none (silent review cut), as requested.
**Unchanged:** `AIU_TRAILER_REVIEW_FINAL.mp4` (32.5 s) is still the current review cut; no new export was made this round because no shot changed.


---
## REVIEW v2 (humans) — `final_trailer/AIU_TRAILER_REVIEW_v2_HUMANS.mp4`  (previous cut untouched, md5 d7c824ff… / 694f34bc…)
Built by `final_trailer/assemble_review_v2_humans.py` (work files in `work_v2/`). 1920×1080, 30 fps, H.264 High yuv420p, 42.33 s (1270 frames), **no audio track**, 0.5 s crossfades.
| # | Segment | Source | Length |
|---|---|---|---|
| 0 | Opening title card | generated | 3.0 s |
| 1 | Access control: approach, verify, enter | `blender/human_entry/renders/preview_v2` (960×540 render, upscaled) + overlay "VERIFYING IDENTITY..." → "ACCESS GRANTED" at 1080p | 11.8 s |
| 2 | Classroom with lecturer + 9 seated students | `blender/human_classroom/renders/preview_v1` (960×540, upscaled) | 10.0 s |
| 3 | Dashboard (provisional, still-based, SIMULATED labelled) | `recordings/AIU_OCCUPANCY_DASHBOARD_PROVISIONAL.mp4` first 9 s | 9.0 s |
| 4 | Engineering prototype reveal | `after_effects/prototype_reveal/AIU_PROTOTYPE_REVEAL_PREVIEW.mp4` first 6.5 s | 6.5 s |
| 5 | Closing card: AIU SMART CAMPUS / Alamein International University | generated | 4.5 s |
Uniform light grade (contrast/saturation/vignette) on the two Blender segments; chapter labels in Carlito; classroom carries "CONCEPT VISUALISATION · ANIMATED PEOPLE · NO OCCUPANCY DATA SHOWN" (no count shown in the classroom).
**Technical verification:** full decode OK (ffmpeg null decode); ffprobe 1920×1080, 30/1 fps, 1270 frames, 42.33 s, 0 audio streams; blackdetect: only the intentional first 0.17 s fade-in from black; freezedetect: only the static closing card. Representative stills inspected (14-frame contact sheet + detail frames). **I did not watch it in motion.**
**Classroom checks (Blender, 20 sampled frames, bone-capsule vs desk/chair/teacher-desk boxes):** 0 penetrations >1 cm; min inter-character separation 0.77 m; seated pelvis/thighs rest on seats (intended contact); hands clear of desk tops (≥1.6 cm). Lecturer stands on the platform.
**Dashboard:** no verified screen recording exists (only stills in `application_recordings/`), so the provisional still-based clip is kept and labelled SIMULATED DATA — NOT LIVE HARDWARE TELEMETRY.
**Remaining limitations (not final):** door/classroom renders are 960×540 upscaled and soft (re-render at 1080p for a final); characters stylized with simplified hair, male students still athletic-looking; brief foot slide at walk start; dashboard is a push-in on captures; prototype shot's labels overlap the image's own labels (AE render not used); no music/VO; classroom segment doesn't continue the door-scene character; the Standard asset pack limits realism.
**Paths:** classroom blend `blender/human_classroom/AIU_HUMAN_classroom_v1.blend`; classroom preview `blender/human_classroom/renders/AIU_HUMAN_CLASSROOM_PREVIEW_v1.mp4`; door `blender/human_entry/AIU_HUMAN_door_entry_v1.blend` + `renders/AIU_HUMAN_DOOR_ENTRY_PREVIEW_v1.mp4`; reports `blender/human_entry/HUMAN_ENTRY_REPORT.md`.

---
## REVIEW v3 (native 1080p) — `final_trailer/AIU_TRAILER_REVIEW_v3_NATIVE.mp4`
Previous cuts untouched (`AIU_TRAILER_REVIEW_v2_HUMANS.mp4`, `AIU_TRAILER_REVIEW_FINAL.mp4`, `AIU_TRAILER_ASSEMBLY_PREVIEW.mp4`). Built by `final_trailer/assemble_review_v3_native.py` (work files `work_v3/`). 1920×1080, 30 fps, H.264 High yuv420p, 42.33 s (1270 frames), no audio track, same segment order/transitions/labels as v2.
**Native renders (not upscaled):**
- Door: `blender/human_entry/AIU_HUMAN_door_entry_v2.blend` (new file; v1 kept) → `blender/human_entry/renders/native_1080/f_0045…f_0398.png`, 354 frames 1920×1080. Verification overlay composited at native 1080p.
- Classroom: `blender/human_classroom/AIU_HUMAN_classroom_v1.blend` → `blender/human_classroom/renders/native_1080/f_0001…f_0300.png`, 300 frames.
- Settings (both): Cycles GPU (Metal), 24 samples, adaptive threshold 0.01, OpenImageDenoise, persistent data, AgX unchanged. Test stills first (4 per scene, ~12–15 s/frame): 100%-crops showed no visible noise or softness. Full render ≈ 13 s/frame (door ≈ 80 min, classroom ≈ 70 min).
- Checks: all frames 1920×1080; per-frame mean-luma jump analysis shows jumps only at the intended hard cuts (door 150/225/296; classroom 76/151/226) — no flicker; contact sheets inspected (still frames).
**Door animation fix (v2):** walk-start now begins in the passing pose and the body pre-turns toward the doorway before walking; max planted-foot motion at walk start 5.4 → 2.9 cm/frame (other planted-foot spikes ≤ ~4.8 cm/frame are ordinary swing starts). Sequence unchanged: verifying → access granted (f225) → lock release → handle (hand contact error mean 2.5 mm, max 27 mm at release frame) → door opens → she walks through (body clearance min +8 mm).
**Prototype labels fixed:** `after_effects/prototype_reveal/make_prototype_preview_v2.py` → `AIU_PROTOTYPE_REVEAL_PREVIEW_v2.mp4` (1920×1080, 30 fps, 240 frames; v1 preview kept). Per-component text callouts that collided with the image's own printed labels were removed; highlights are now plain boxes and one caption chip per step sits in a reserved band below the image. The trailer uses the first 6.5 s (before the shot's own end title, since the closing card follows). Stills inspected: no overlaps, everything inside the frame.
**Technical verification of v3:** ffprobe as above; full decode OK (ffmpeg null decode) for the final file and each of the 6 segment files; blackdetect: only the intentional first 0.17 s fade-in; freezedetect: only the static closing card (38.6–41.57 s, intentional). 16-frame contact sheet inspected. **I did not watch the video in motion.**
**Still-limitations:** dashboard remains a still-based push-in on real app captures labelled "SIMULATED DATA — NOT LIVE CAMERA OR SENSOR TELEMETRY" (no verified screen recording exists); characters are stylized Quaternius CC0 models with simplified hair, male students remain athletic-looking; a few frames of body-turn foot slide remain (≈2–3 cm/frame); classroom segment does not continue the door-scene character; no music/VO; not a final until reviewed in motion.

---
## Narrated final cut (2026-10-09)
`final_trailer/AIU_SMART_CAMPUS_FINAL_TRAILER.mp4` (narrated, 115.000 s, 1920×1080, 30 fps, H.264 + AAC 48 kHz stereo, −16.1 LUFS) and `AIU_SMART_CAMPUS_FINAL_SILENT.mp4`. Production files, scripts, clips, mix, sync test and reports are in `final_trailer/voiceover_final/` (timeline: `timeline_vo.py`; build: `assemble_final_vo.py`; mix: `make_mix_vo.py`). Attendance scene: `blender/attendance_scene/AIU_ATTENDANCE_SCENE.blend`, preview `renders/AIU_ATTENDANCE_PREVIEW.mp4` (integrated camera segment). Segment table: see `VOICEOVER_SYNC_REPORT.md`; data classes: `DATA_SOURCE_AUTHENTICITY_REPORT.md`.
Verified: decode, duration, no freeze ≥1.5 s, loudness, key frames. Not verified: watching/listening in motion. Known: 0.2 s dark flash at 95.6 s; 115 s total because the VO is 105.3 s.
