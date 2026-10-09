# Preview render settings
**Sandbox preview (what actually exists): `AIU_PROTOTYPE_REVEAL_PREVIEW.mp4`** — made by `make_prototype_preview.py` (Python/OpenCV/PIL + ffmpeg), NOT by After Effects.
- 1920×1080, 30 fps, 240 frames, 8.000 s, H.264 yuv420p, CRF 18. Source image scaled (≈117 % → 94 % of final), tiny perspective tilt only; no re-drawing.
- Highlights/labels are overlay graphics; the supplied image's own text, dimensions and AIU branding are untouched.

**After Effects render (not yet performed):** Render Queue → Best Settings, Resolution Full (or Half for a fast check), Output Module QuickTime/ProRes 422 or H.264 via Adobe Media Encoder; 1920×1080, 30 fps; Time span = work area 0–8 s.
