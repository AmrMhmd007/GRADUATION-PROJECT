# sample clips into driver_namespace
import bpy
from mathutils import Quaternion, Vector
NS=bpy.app.driver_namespace
def sample_clip(arm, act, n):
    set_action(arm, act); out=[]
    sc=bpy.context.scene
    for f in range(n+1):
        sc.frame_set(f); bpy.context.view_layer.update()
        out.append({pb.name:(Quaternion(pb.rotation_quaternion), Vector(pb.location)) for pb in arm.pose.bones})
    return out
