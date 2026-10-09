import bpy, math, mathutils
D=bpy.data
exec(open('/Users/amrmohamed/Desktop/AIU_SMART_CAMPUS_FINAL/blender/human_entry/bridge/studio.py').read())
def set_action(arm, action_name):
    ad=arm.animation_data or arm.animation_data_create()
    a=D.actions[action_name]; ad.action=a
    try:
        ad.action_slot = a.slots[0]
    except Exception as e: print('slot warn',e)
    return a
def look_at(obj, target):
    d=mathutils.Vector(target)-obj.location; obj.rotation_euler=d.to_track_quat('-Z','Y').to_euler()
