/* AIU SMART CAMPUS — Physical Prototype Reveal (ExtendScript for After Effects).
   STATUS: written in a Linux sandbox. NOT YET EXECUTED IN AFTER EFFECTS. First run may need small fixes.
   Run: File > Scripts > Run Script File… (allow "Scripts to Write Files and Access Network" if prompted).
   Creates AIU_Prototype_Reveal.aep next to this script. Uses prototype_reference.jpg unaltered. 1920x1080, 30 fps, 8 s.
   Highlight rectangles are in SOURCE-IMAGE pixels (1280x853) — edit the HL table to nudge them. */
(function () { try {
    var HERE = File($.fileName).parent;
    var IMG = File(HERE.fsName + "/prototype_reference.jpg");
    if (!IMG.exists) { alert("Missing " + IMG.fsName); return; }
    var W = 1920, H = 1080, FPS = 30, DUR = 8;
    var NAVY = [8/255, 13/255, 26/255], WHITE = [0.96, 0.97, 0.99], BLUE = [0.47, 0.75, 1], GREEN = [0.2, 0.85, 0.5];
    var HL = [ // [group, x0, y0, x1, y1, label, startSec]
        ["room", 170, 335, 300, 365, "ROOM 3031 — LECTURE ROOM", 1.9], ["room", 520, 335, 650, 365, "ROOM 3032 — SMART LAB", 2.12], ["room", 840, 335, 970, 365, "ROOM 3033 — OFFICE / ADMIN", 2.34],
        ["hvac", 370, 120, 500, 205, "CENTRAL HVAC UNIT", 3.6], ["hvac", 200, 140, 365, 245, "MAIN DUCTS", 3.82],
        ["cam", 145, 235, 185, 270, "OCCUPANCY CAMERA", 4.0], ["cam", 435, 235, 475, 270, "OCCUPANCY CAMERA", 4.22], ["cam", 780, 235, 820, 270, "OCCUPANCY CAMERA", 4.44],
        ["tech", 975, 160, 1260, 395, "TECHNICAL COMPARTMENT", 4.6]
    ];
    app.beginUndoGroup("AIU Prototype Reveal");
    var proj = app.newProject();
    var fOut = proj.items.addFolder("01_COMPOSITIONS"), fFoot = proj.items.addFolder("02_FOOTAGE"), fPre = proj.items.addFolder("03_PRECOMPS"), fGfx = proj.items.addFolder("04_GRAPHICS");
    proj.items.addFolder("05_AUDIO"); proj.items.addFolder("06_EXPORTS"); proj.items.addFolder("07_SCRIPTS");
    var footage = proj.importFile(new ImportOptions(IMG)); footage.parentFolder = fFoot;
    var comp = proj.items.addComp("AIU_Prototype_Reveal", W, H, 1, DUR, FPS); comp.parentFolder = fOut; comp.bgColor = NAVY;

    // ---- background
    var bg = comp.layers.addSolid(NAVY, "BG_Navy", W, H, 1); bg.moveToEnd();
    var vig = comp.layers.addSolid([0.12, 0.2, 0.38], "BG_Glow", W, H, 1);
    var m = vig.Masks.addProperty("Mask"); var sh = new Shape(); sh.vertices = [[200,100],[W-200,100],[W-200,H-100],[200,H-100]]; sh.closed = true; m.maskShape.setValue(sh);
    m.maskFeather.setValue([700, 700]); vig.transparency = false; vig.property("Opacity").setValue(35);
    vig.moveAfter(bg);

    // ---- camera + control null
    var ctrl = comp.layers.addNull(DUR); ctrl.name = "CTRL_Camera"; ctrl.threeDLayer = true; ctrl.property("Position").setValue([W/2, H/2, 0]);
    var cam = comp.layers.addCamera("Camera 1", [W/2, H/2]); cam.parent = ctrl; cam.property("Zoom").setValue(2666); cam.property("Position").setValue([0, 0, -2666]); // 50mm-equivalent: distance = zoom -> 1:1 scale
    // ---- prototype image (2.5D). Scale so width = 1500 px
    var img = comp.layers.add(footage); img.name = "PROTOTYPE_IMAGE"; img.threeDLayer = true;
    var s0 = 1500 / 1280 * 100;
    img.property("Position").setValue([W/2, H/2, 0]);
    img.property("Scale").setValue([s0, s0, s0]);
    img.property("Opacity").setValueAtTime(0, 0); img.property("Opacity").setValueAtTime(1.6, 100);
    // very small Y rotation drift, then settle flat for the final frame
    var ry = img.property("Orientation"); ry.setValueAtTime(0, [0, 3, 0]); ry.setValueAtTime(5.6, [0, -3, 0]); ry.setValueAtTime(6.6, [0, 0, 0]);
    // push-in then pull back to a smaller framing (room for title)
    var sc = img.property("Scale"); sc.setValueAtTime(0, [s0*0.97, s0*0.97, s0*0.97]); sc.setValueAtTime(5.6, [s0*1.02, s0*1.02, s0*1.02]); sc.setValueAtTime(6.6, [s0*0.76, s0*0.76, s0*0.76]);
    var ps = img.property("Position"); ps.setValueAtTime(5.6, [W/2, H/2, 0]); ps.setValueAtTime(6.6, [W/2, H/2 - 165, 0]);
    for (var k = 1; k <= ps.numKeys; k++) { ps.setInterpolationTypeAtKey(k, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER); }
    // soft shadow

    // ---- highlight layers: parented to the image so they follow every camera/scale move
    function px(sx, sy) { return [sx - 640, sy - 426.5]; } // source px -> layer-local offset from image centre (anchor is centre)
    img.property("Anchor Point").setValue([640, 426.5, 0]);
    var gi = 0;
    for (var i = 0; i < HL.length; i++) {
        var h = HL[i], t0 = h[6], dur = (h[0]=="room")?1.6:(h[0]=="hvac")?1.4:(h[0]=="cam")?1.4:1.0;
        var L = comp.layers.addShape(); L.name = "HL_" + h[0] + "_" + (i+1); L.threeDLayer = true; L.parent = img;
        L.property("Position").setValue([640, 426.5, 0]); L.property("Anchor Point").setValue([640, 426.5, 0]);
        var cont = L.property("Contents"); var g = cont.addProperty("ADBE Vector Group");
        var rect = g.property("Contents").addProperty("ADBE Vector Shape - Rect");
        rect.property("Position").setValue([(h[1]+h[3])/2, (h[2]+h[4])/2]); rect.property("Size").setValue([h[3]-h[1], h[4]-h[2]]);
        var st = g.property("Contents").addProperty("ADBE Vector Graphic - Stroke"); st.property("Color").setValue(BLUE); st.property("Stroke Width").setValue(3.5);
        var fl = g.property("Contents").addProperty("ADBE Vector Graphic - Fill"); fl.property("Color").setValue(BLUE); fl.property("Opacity").setValue(18);
        var op = L.property("Opacity"); op.setValueAtTime(t0, 0); op.setValueAtTime(t0 + 0.4, 100); op.setValueAtTime(t0 + dur, 100); op.setValueAtTime(t0 + dur + 0.4, 0);
        // label (editable text layer, in comp space, parented to image so it tracks)
        var T = comp.layers.addText(h[5]); T.name = "LBL_" + h[0] + "_" + (i+1); T.threeDLayer = true; T.parent = img;
        var td = T.property("Source Text").value; td.fontSize = 22; td.fillColor = WHITE; td.font = "Arial-BoldMT"; td.applyFill = true; td.applyStroke = true; td.strokeColor = NAVY; td.strokeWidth = 5; td.strokeOverFill = false; td.justification = ParagraphJustification.CENTER_JUSTIFY; T.property("Source Text").setValue(td);
        var below = !(h[0]=="hvac" && h[5]=="CENTRAL HVAC UNIT");
        T.property("Position").setValue([(h[1]+h[3])/2 - 0, below ? h[4] + 24 : h[2] - 14, 0]);
        T.property("Anchor Point").setValue([0, 0, 0]);
        T.property("Scale").setValue([100, 100, 100]);
        var to = T.property("Opacity"); to.setValueAtTime(t0, 0); to.setValueAtTime(t0 + 0.4, 100); to.setValueAtTime(t0 + dur, 100); to.setValueAtTime(t0 + dur + 0.4, 0);
    }
    // text positioning note: anchor [0,0,0] + centre justification places the text centred on the x position.

    // ---- end title (Layer-space comp coords, 2D on top)
    function title(txt, y, size, col, delay, bold) {
        var T = comp.layers.addText(txt); T.name = "TITLE_" + txt.split(" ")[0];
        var td = T.property("Source Text").value; td.fontSize = size; td.fillColor = col; td.font = bold ? "Arial-BoldMT" : "ArialMT"; td.justification = ParagraphJustification.CENTER_JUSTIFY; T.property("Source Text").setValue(td);
        T.property("Position").setValue([W/2, y]);
        var o = T.property("Opacity"); o.setValueAtTime(6.2 + delay, 0); o.setValueAtTime(7.0 + delay, 100);
        var p = T.property("Position"); p.setValueAtTime(6.2 + delay, [W/2, y + 14]); p.setValueAtTime(7.0 + delay, [W/2, y]);
        try { for (var k = 1; k <= 2; k++) { p.setTemporalEaseAtKey(k, [new KeyframeEase(0, 80)], [new KeyframeEase(0, 80)]); } } catch (e) {}
        return T;
    }
    title("AIU SMART CAMPUS", 930, 64, WHITE, 0, true);
    var sub = title("CYBER-PHYSICAL CONTROL SYSTEM", 988, 26, BLUE, 0.12, true); try { var an = sub.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator"); an.property("ADBE Text Animator Properties").addProperty("ADBE Text Tracking Amount").setValue(14); } catch (e) {}
    title("ALAMEIN INTERNATIONAL UNIVERSITY", 1030, 22, [0.9, 0.93, 0.97], 0.24, false);

    // ---- markers (animation beats)
    var beats = [[0, "Reveal"], [1.9, "Rooms"], [3.6, "HVAC"], [4.0, "Cameras"], [4.6, "Technical compartment"], [5.6, "Pull back"], [6.2, "Title"]];
    for (var b = 0; b < beats.length; b++) { var mk = new MarkerValue(beats[b][1]); comp.markerProperty.setValueAtTime(beats[b][0], mk); }
    // ---- output module template note + render queue (preview, H.264 requires AME in recent AE; falls back to default template)
    var rq = proj.renderQueue.items.add(comp);
    try { rq.outputModule(1).file = new File(HERE.fsName + "/AE_PREVIEW_PROTOTYPE_REVEAL.mov"); } catch (e) {}
    proj.save(new File(HERE.fsName + "/AIU_Prototype_Reveal.aep"));
    app.endUndoGroup();
    alert("Built AIU_Prototype_Reveal. Check: highlight alignment, label positions, camera. Render via the Render Queue.");
} catch (err) { alert('AIU script ERROR line ' + err.line + ': ' + err.toString()); }
})();