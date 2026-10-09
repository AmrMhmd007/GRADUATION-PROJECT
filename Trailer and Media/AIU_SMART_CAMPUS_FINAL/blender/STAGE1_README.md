# AIU SMART CAMPUS — Stage 1: Blender corridor + access-door test

**Status (honest):** Blender is NOT confirmed installed. `aiu_test01_corridor_door.py` has NOT been run by anyone (Blender cannot run in my sandbox). Expect one or two fix rounds. Nothing here is a render result.

## A. Install and verify (you do this; I change nothing on your Mac)
1. Open https://www.blender.org/download/ and download the **macOS Apple Silicon (.dmg)** of the current stable release (4.2 LTS or newer; the script targets 4.2–4.5).
2. Open the .dmg, drag **Blender** into **Applications**. First launch: right-click > Open if macOS warns.
3. Verify GPU/Metal. In Terminal (one line):
   `/Applications/Blender.app/Contents/MacOS/Blender -b -P "$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/verify_gpu.py"`
   Expected: a `DEVICE:` line with "Apple M4" and type METAL, and `Metal GPU found: True`.
4. Send me the full printed output. Only then do I treat Blender/Metal as verified.

## B. Scene script
`aiu_test01_corridor_door.py` — 18 m corridor, tile floor, grid ceiling with LED panels and diffusers, six windows, navy wainscot, three doors, hero door 3031 with room behind, access reader (IDENTITY indicator ring), electric-strike section, latch/lever, hinged door. No human model (live-action lecturer is the missing component). Hardware is conceptual.

Story/timing (30 fps, 390 frames = 13 s): A 1–150 tracking approach · B 151–240 reader macro, amber "verifying" pulse, GREEN at frame 225 (GRANT) · C 241–300 strike keeper retracts, lever turns · D 301–390 door swings open. Nothing physical moves before frame 225.
The on-screen UI chain (IDENTITY › ACCOUNT › ROOM › SCHEDULE › BACKEND › GRANT) is NOT in Blender: I will deliver it as transparent overlay clips for Final Cut Pro, timed with `AIU_TEST01_timing.json`.

## C. Run
1. Quick check (builds and saves the scene only):
   `/Applications/Blender.app/Contents/MacOS/Blender -b -P "$HOME/Desktop/AIU_SMART_CAMPUS_FINAL/blender/aiu_test01_corridor_door.py"`
   Expect `SCENE BUILT AND SAVED`. Report any red error text verbatim.
2. One still (1080p, ~1–5 min), frames 60 / 200 / 270 / 340 to check each shot:
   `... Blender -b -P ...aiu_test01_corridor_door.py -- --mode still --frame 200`
3. Preview video (540p, 48 samples):
   `... -- --mode preview`
4. Only after you and I review stills + preview: full quality
   `... -- --mode final` (or `--frames 1-150` to split into sessions).

## D. Outputs and settings
Folder: `AIU_SMART_CAMPUS_FINAL/blender/renders/`
- `AIU_TEST01_still_f0200.png` (stills) · `AIU_TEST01_preview_540p_0001-0390.mp4` · `AIU_TEST01_1080p_0001.png … 0390.png` (final sequence)
- Scene file: `blender/AIU_TEST01_corridor_door.blend` · timing: `blender/AIU_TEST01_timing.json`
Settings: Cycles, Metal GPU, 1920×1080, 30 fps, 128 samples + OpenImageDenoise, 8 bounces, motion blur 0.4 shutter, AgX view transform, 16:9. Final: PNG sequence → import into Final Cut Pro (or I give you an ffmpeg-free route: File > Import > the PNG sequence as stills, or encode in Blender VSE). Estimated time per 1080p frame on M4: unknown until measured — your still tells us the real number; do not assume.

## E. Troubleshooting
- "Blender can't be opened": right-click > Open, or System Settings > Privacy & Security > Open Anyway (your choice).
- Script error: send the last 20 lines of Terminal output; likely causes are Blender-version socket names (Principled BSDF / brick inputs) — I patch them.
- No METAL device: update Blender; send verify_gpu output; fall back to CPU (`cy.device='CPU'`, slower).
- Black/noisy/too dark image: send the still; I adjust light energy/exposure.
- Memory pressure: use `--frames` chunks, close other apps, lower samples to 64.
- Render too slow: tell me seconds per still; I lower samples/resolution for tests, keep 128 for final.
- Door/hardware hits wrong place: send the still; geometry is parametric.
