# Prototype Reveal — report
**Directory:** `AIU_SMART_CAMPUS_FINAL/after_effects/prototype_reveal/` (door and classroom scenes untouched).
## Actually done and tested
- Source image confirmed accessible: 1280×853 RGB; identical (mean diff 0.38, JPEG vs PNG) to `assets/prototype_original.jpg`; copied here as `prototype_reference.jpg`, unaltered.
- Rendered the sandbox preview `AIU_PROTOTYPE_REVEAL_PREVIEW.mp4` (ffprobe: 1920×1080, 30 fps, 240 frames, 8.0 s). I inspected 12 sample frames (stills only; did not watch it in motion).
- Fixed after the first inspection: highlight boxes mis-registered under the tilt (now exact homography), top-left tag overlapped the image's own title (removed), final frame clipped at top (re-framed).
## Written, NOT executed
- `AIU_Prototype_Reveal.jsx` — **never run in After Effects**; may need small fixes (e.g. camera zoom/distance, label positions, text-animator and render-queue lines). No .aep exists yet.
## Limitations
- Source is only 1280 px wide, shown at ~1.17× then ~0.9×: no close-up pushes; fine details in the small bottom panels stay small (≈ unreadable at 1080p in places).
- Highlight rectangles are estimated by eye from the 1280×853 image; the unconfirmed alignment in AE needs a visual check.
- The image is a presentation render of the model; "Real Components Used" does not prove every part is assembled/operational — no claim is made in the shot.
- Sandbox preview has no depth-of-field/light sweep; "2.5D" there is a slight perspective tilt + push only.
## To run (your Mac)
File ▸ Scripts ▸ Run Script File… ▸ `AIU_Prototype_Reveal.jsx`; tell me any error text and I'll fix it. **Ready for review:** the preview MP4 only, not an AE render.
