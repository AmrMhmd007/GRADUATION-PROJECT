import bpy
D=bpy.data
def hair_mat(name, col, strands=True):
    m=D.materials[name]; m.use_nodes=True; nt=m.node_tree; nt.nodes.clear()
    out=nt.nodes.new('ShaderNodeOutputMaterial'); b=nt.nodes.new('ShaderNodeBsdfPrincipled')
    tc=nt.nodes.new('ShaderNodeTexCoord'); mp=nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value=(60,60,60)
    wv=nt.nodes.new('ShaderNodeTexNoise'); wv.inputs['Scale'].default_value=1.0; wv.inputs['Detail'].default_value=6.0; wv.inputs['Roughness'].default_value=0.7
    mp2=nt.nodes.new('ShaderNodeMapping'); mp2.inputs['Scale'].default_value=(900,900,18)
    bump=nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value=0.55; bump.inputs['Distance'].default_value=0.01
    cr=nt.nodes.new('ShaderNodeValToRGB'); cr.color_ramp.elements[0].color=(col[0]*0.55,col[1]*0.55,col[2]*0.55,1); cr.color_ramp.elements[1].color=(col[0]*1.25,col[1]*1.25,col[2]*1.25,1)
    nt.links.new(tc.outputs['Object'],mp2.inputs['Vector']); nt.links.new(mp2.outputs['Vector'],wv.inputs['Vector'])
    nt.links.new(wv.outputs['Fac'],cr.inputs['Fac']); nt.links.new(cr.outputs['Color'],b.inputs['Base Color'])
    nt.links.new(wv.outputs['Fac'],bump.inputs['Height']); nt.links.new(bump.outputs['Normal'],b.inputs['Normal'])
    b.inputs['Roughness'].default_value=0.62; b.inputs['Specular IOR Level'].default_value=0.25; b.inputs['Metallic'].default_value=0.0
    try: b.inputs['Coat Weight'].default_value=0.0
    except: pass
    nt.links.new(b.outputs['BSDF'],out.inputs['Surface'])
hair_mat('HairMat_Chestnut',(0.026,0.014,0.010))
hair_mat('HairMat_Brown',(0.022,0.015,0.012))
