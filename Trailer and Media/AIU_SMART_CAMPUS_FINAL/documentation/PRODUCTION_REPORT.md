# AIU SMART CAMPUS — final production report (v6)

**Final video:** `AIU_SMART_CAMPUS_FINAL_TRAILER.mp4` — 1920×1080, 30 fps, 152.93 s, H.264 + AAC 48 kHz, ~86 MB, −16.3 LUFS. Also: `AIU_SMART_CAMPUS_PREVIEW.mp4` (48.9 s: title, access, prototype, app, finale).

## What was verified (and how)
| Check | Result |
|---|---|
| File: codec, size, fps, duration | ffprobe: 1920×1080, 30 fps, 152.933 s video / 152.920 s audio |
| Black frames / frozen frames | blackdetect + freezedetect: none |
| Loudness | −16.3 LUFS integrated, peak −2.4 dBFS (checked on the earlier identical mix) |
| Visual continuity | Frame sheets at every scene and at the start of all 37 speech segments (`SYNC_REVIEW_SHEET_all_37_segments.jpg`) were inspected |
| Event sync | Title appears at 9.93 s (segment 4); SEE/UNDERSTAND/DECIDE/ACT appear at 149.30/150.17/151.28/152.32 s, matching the four one-word segments; door-release SFX at 54.25 s coincides with the GRANT/unlock |
| Application footage | Real dashboard (localhost:5173, live backend) opened in Chrome, no console errors, 7 screens captured 2× |
| **Not verified** | **Whether each picture matches the *meaning* of the Arabic/English speech.** No speech-recognition model is available, so I cannot hear/transcribe. Scene cuts sit in measured pauses, but the meaning-to-picture mapping follows the earlier script order. I did not "watch" the video in real time; I inspected frames and measurements. |

## Honest state of each scene
A: real AIU photographs (2 stills, logo-verified, licence unconfirmed). B–F: conceptual/simulated 3D, flat-shaded, silhouettes, labelled on screen. G: your prototype image, crop/zoom only, labels untouched. H: real app captures, stills with camera motion (no hardware connected, so the app shows OFFLINE/Unavailable, and the data shown is the development database). I: title reveal.
The SENSE→…→MONITOR strip and the SENSORS›BACKEND›INFRASTRUCTURE›DASHBOARD chain are explanatory overlays, not narration-derived. No scene shows a failed physical action as successful; no hardware success is claimed.

## Limitations
- Not photorealistic (no Blender/GPU/human assets here).
- Official AIU gallery/maps pages were unreachable; only your supplied photos were used (see AIU_FOOTAGE_SOURCES.md). The glass-facade photo was not used because no AIU mark is visible.
- App section is stills with camera motion; the browser tools can't record video. For true video: Cmd+Shift+5 on your Mac, send the .mov, and I'll replace scene H.
- Photos (≤860 px) and the prototype image (1280 px) are upscaled, so they look soft at full-screen zoom.
- The HVAC scene is a conceptual cutaway; the app has no live HVAC readings to show.
- `animation/` and `renders/` hold large intermediates; delete if space is needed.
