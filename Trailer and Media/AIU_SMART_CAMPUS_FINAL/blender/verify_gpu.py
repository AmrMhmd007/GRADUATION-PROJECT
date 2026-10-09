"""Prints Blender version and Cycles compute devices. Does not change any setting on your Mac."""
import bpy
print("BLENDER VERSION:", bpy.app.version_string)
p = bpy.context.preferences.addons['cycles'].preferences
p.compute_device_type = 'METAL'
p.get_devices()
for d in p.devices:
    print("DEVICE:", d.name, "| type:", d.type, "| id:", d.id)
print("Metal GPU found:", any(d.type == 'METAL' for d in p.devices))
