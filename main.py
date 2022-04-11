"""
Code for generation of some weird landscapey things

This is the code that was used to generate renders, as well
as the 3D models.
This code is written in Python 3.8 (not tested on other versions),
and needs Blender to run. Blender is a free, open-source 3D graphics
software application with a good Python API, which this code uses.

To use this code, download Blender from blender.org and open the
scripting tab.

WARNING: SOME OF THIS CODE CAN BE QUITE COMPUTATIONAlLY EXPENSIVE
Blender may appear to crash / not respond

This code was tested on a pretty good rig, 3600X/3080, results may
be different for you.

You can mess about with the seed, but most values will produce horrific
landscapes / color-combinations anyways.

Thank you and have fun!


--- Some documentation ---

Broadly, this file is split into 3:
* Generating the important procedural values
* Rendering the images
* Creating the 3D model as stl (the 3D model is lower-quality)

The 3D model is an stl file
Render 1 is the "main" render, with a randomised camera position
Render 2 is the "secondary" render, with a fixed camera position
Render 3 is the top-down orthographic render

Any errors?
Check that you have Blender 3.0
Check that you have Python 3.8
Check that you have created the C://tmp directory (sorry Linux users, you will need to change the code) 

"""

from typing import *

import os
import hashlib
import colorsys

import bpy


# CONSTANTS FOR PROCEDURAL GENERATION
SEED = r"test2"
NUMBER = 0
NUMBER_PADDED = str(NUMBER).rjust(2, '0')


# CONSTANTS FOR QUALITY
DISPLACEMENT_MAP_DIMENSIONS = 4096, 4096  # You could change this, but it really wont do much
MODEL_SUBDIVISION_QUALITY = 10  # choose 10 for okay quality, and up to 12
MODEL_DECIMATE_RATIO = 0.25  # can go up to 1, but recommend 0.25


# CHANGE THESE FOR SAVE DESTINATIONS
STL_EXPORT_FILEPATH = f"C:\\tmp\\{NUMBER_PADDED}-model.stl"
RENDER_1_EXPORT_FILEPATH = f"C:\\tmp\\{NUMBER_PADDED}-render-1.png"
RENDER_2_EXPORT_FILEPATH = f"C:\\tmp\\{NUMBER_PADDED}-render-2.png"
RENDER_3_EXPORT_FILEPATH = f"C:\\tmp\\{NUMBER_PADDED}-render-3.png"


def gen_data_from_hash(
        key: str,
        num_values: int = 16
) -> List[float]:
    """Get data (list of float between 0 and 1) from a key"""
    hashed = hashlib.sha256(key.encode("utf-8")).digest()
    as_bytes = [hashed[i:i + 2] for i in range(0, len(hashed), 2)]
    data = [int.from_bytes(x, "big") for x in as_bytes]
    data = [x / 65536 for x in data][:num_values]
    return data


def gen_color_from_seed(
        seed: str
) -> Tuple[float, float, float]:
    """Generate color from seed"""
    hue, sat = gen_data_from_hash(seed)[:2]
    return colorsys.hsv_to_rgb(hue, sat, 255)


def gen_noise_value_from_seed(
        seed: str
) -> float:
    """Generate x and y coordinates for noise from seed"""
    x = gen_data_from_hash(seed)[2]
    return x * 1000


def displacement_scale_value_from_seed(
        seed: str
) -> float:
    """Generate displacement value from seed"""
    x = gen_data_from_hash(seed)[3]
    return 50 + (x * 25)


def adjacent_color(
        rgb_value: Tuple[float, float, float],
        seed: str,
        factor: float
) -> Tuple[float, float, float]:
    """Get adjacent color"""

    def constrain(x, y, z):
        """Constrain y between x and z"""
        return min(max(y, x), z)

    # Assumption: r, g, b in [0, 255]
    hue, sat, val = colorsys.rgb_to_hsv(*rgb_value)
    hue_change, sat_change, val_change = [
        x - 0.5 for x in gen_data_from_hash(seed, 3)]
    hue_change = hue_change * 0.1 * factor
    sat_change = sat_change * 0.1 * factor
    val_change = val_change * 32 * factor
    hue = hue + hue_change
    sat = sat + sat_change
    val = val + val_change
    hue = hue % 1
    sat = constrain(0, sat, 1)
    val = constrain(0, val, 255)
    return colorsys.hsv_to_rgb(hue, sat, val)


def adjacent_colors(
        rgb_value: Tuple[float, float, float],
        seed: str,
        number: int,
        factor: float = 2
) -> List[Tuple[float, float, float]]:
    """Get adjacent colours"""
    colors = []
    for i in range(number):
        seed = str(gen_data_from_hash(str(seed), 4))
        colors.append(
            adjacent_color(rgb_value, seed, factor)
        )
    return colors


# ---------------------------------------
#                Main code
# ---------------------------------------


def setup():
    """Delete objects and set rendering settings"""
    # delete objects
    for obj in bpy.context.scene.objects:
        obj.select_set(True)
    bpy.ops.object.delete()

    # delete materials
    for material in bpy.data.materials:
        material.user_clear()
        bpy.data.materials.remove(material)

    # setup rendering stuff
    bpy.context.scene.render.engine = "CYCLES"
    bpy.context.scene.cycles.feature_set = "EXPERIMENTAL"

    # set the device type
    bpy.context.scene.cycles.device = "GPU"

    # set cuda rendering (you can change this to opengl)
    bpy.context.preferences.addons[
        "cycles"
    ].preferences.compute_device_type = "CUDA"


#  ------------------------------
#  |      Procedural stuff      |
#  ------------------------------


def generate_stl(
        seed: str
) -> None:
    """Generate just the stl file for the terrain"""
    # noise coordinates
    noise_value = gen_noise_value_from_seed(seed)
    displacement_scale_value = displacement_scale_value_from_seed(seed)

    # add the plane in
    bpy.ops.mesh.primitive_plane_add(location=[0, 0, 0], size=50)
    bpy.context.selected_objects[0].name = "terrain"

    # don't subdivide when baking displacement
    # bpy.ops.object.modifier_add(type="SUBSURF")
    # bpy.context.selected_objects[0].modifiers[0].levels = 6
    # bpy.context.selected_objects[0].modifiers[0].subdivision_type = "SIMPLE"
    # bpy.context.selected_objects[0].cycles.use_adaptive_subdivision = True

    # make material
    terrain_material = bpy.data.materials.new(name="TerrainMaterial")
    bpy.data.materials["TerrainMaterial"].use_nodes = True
    bpy.data.materials["TerrainMaterial"].cycles.displacement_method = "BOTH"

    nodes = terrain_material.node_tree.nodes
    node_tree = terrain_material.node_tree
    links = node_tree.links

    # terrain nodes
    bsdf_node = [x for x in nodes if isinstance(x, bpy.types.ShaderNodeBsdfPrincipled)][0]
    output_node = [x for x in nodes if isinstance(x, bpy.types.ShaderNodeOutputMaterial)][0]
    bsdf_node.location = 2000, 1000
    output_node.location = 2400, 0

    texture_coordinate_node = node_tree.nodes.new("ShaderNodeTexCoord")
    texture_coordinate_node.location = 200, 0

    shader_mapping_node = node_tree.nodes.new("ShaderNodeMapping")
    shader_mapping_node.location = 600, 0
    value_node_set_1_0 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_0.location = 400, -400
    value_node_set_1_0.outputs["Value"].default_value = noise_value

    musgrave_1_node = node_tree.nodes.new("ShaderNodeTexMusgrave")
    musgrave_1_node.location = 800, 0
    musgrave_1_node.musgrave_dimensions = "4D"
    musgrave_1_node.musgrave_type = "FBM"
    value_node_set_1_1 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_1.location = 600, -600
    value_node_set_1_1.outputs["Value"].default_value = 0.15
    value_node_set_1_2 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_2.location = 600, -800
    value_node_set_1_2.outputs["Value"].default_value = 16
    value_node_set_1_3 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_3.location = 600, -1000
    value_node_set_1_3.outputs["Value"].default_value = 0.95

    voronoi_1_node = node_tree.nodes.new("ShaderNodeTexVoronoi")
    voronoi_1_node.location = 1000, 0
    voronoi_1_node.feature = "SMOOTH_F1"
    value_node_set_1_4 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_4.location = 800, -400
    value_node_set_1_4.outputs["Value"].default_value = 0.3

    musgrave_2_node = node_tree.nodes.new("ShaderNodeTexMusgrave")
    musgrave_2_node.location = 1200, 0
    musgrave_2_node.musgrave_dimensions = "3D"
    musgrave_2_node.musgrave_type = "FBM"
    value_node_set_1_5 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_5.location = 1100, -600
    value_node_set_1_5.outputs["Value"].default_value = 9
    value_node_set_1_6 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_6.location = 1100, -800
    value_node_set_1_6.outputs["Value"].default_value = 14
    value_node_set_1_7 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_7.location = 1100, -1000
    value_node_set_1_7.outputs["Value"].default_value = 1.05

    # displacement_node = node_tree.nodes.new("ShaderNodeDisplacement")
    # displacement_node.location = 2200, 0
    # --!! IMPORTANT: REPLACE DISPLACEMENT WITH EMIT FOR BAKING !!--
    emission_node = node_tree.nodes.new("ShaderNodeEmission")
    emission_node.location = 2200, 0

    math_multiply_node_1 = node_tree.nodes.new("ShaderNodeMath")
    math_multiply_node_1.operation = "ADD"
    math_multiply_node_1.location = 1600, 0
    value_node_set_1_8 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_8.outputs["Value"].default_value = 0.75
    value_node_set_1_8.location = 1600, -400

    # not needed for making stl
    # value_node_set_1_9 = node_tree.nodes.new("ShaderNodeValue")
    # value_node_set_1_9.outputs["Value"].default_value = displacement_scale_value
    # value_node_set_1_9.location = 1800, -400

    links.new(texture_coordinate_node.outputs[0], shader_mapping_node.inputs[0])
    links.new(shader_mapping_node.outputs[0], musgrave_1_node.inputs[0])
    links.new(value_node_set_1_0.outputs[0], musgrave_1_node.inputs[1])
    links.new(value_node_set_1_1.outputs[0], musgrave_1_node.inputs[2])
    links.new(value_node_set_1_2.outputs[0], musgrave_1_node.inputs[3])
    links.new(value_node_set_1_3.outputs[0], musgrave_1_node.inputs[4])
    links.new(musgrave_1_node.outputs[0], voronoi_1_node.inputs[0])
    links.new(value_node_set_1_4.outputs[0], voronoi_1_node.inputs[2])
    links.new(voronoi_1_node.outputs[1], musgrave_2_node.inputs[0])
    links.new(value_node_set_1_5.outputs[0], musgrave_2_node.inputs[2])
    links.new(value_node_set_1_6.outputs[0], musgrave_2_node.inputs[3])
    links.new(value_node_set_1_7.outputs[0], musgrave_2_node.inputs[4])
    links.new(musgrave_2_node.outputs[0], math_multiply_node_1.inputs[0])
    links.new(value_node_set_1_8.outputs[0], math_multiply_node_1.inputs[1])
    # links.new(math_multiply_node_1.outputs[0], displacement_node.inputs[0])
    links.new(math_multiply_node_1.outputs[0], emission_node.inputs[0])
    # links.new(value_node_set_1_9.outputs[0], displacement_node.inputs[2])
    # links.new(value_node_set_1_9.outputs[0], emission_node.inputs[2])
    # links.new(displacement_node.outputs[0], output_node.inputs[2])
    links.new(emission_node.outputs[0], output_node.inputs[0])

    # assign material to terrain
    bpy.context.active_object.data.materials.append(terrain_material)

    # setup things for baking displacement
    bpy.context.scene.cycles.samples = 1

    image_node = node_tree.nodes.new("ShaderNodeTexImage")
    image_node.location = 2000, -400
    baked_image = bpy.data.images.new(
        "BakedDisplacement",
        width=DISPLACEMENT_MAP_DIMENSIONS[0],
        height=DISPLACEMENT_MAP_DIMENSIONS[1],
        float_buffer=True,
        alpha=True
    )
    image_node.image = bpy.data.images[baked_image.name]
    nodes.active = image_node

    # bake displacement
    bpy.ops.object.bake(type="EMIT")

    # time to make the final 3d model
    # yeet everything out
    for x in bpy.context.scene.objects:
        x.select_set(True)
    bpy.ops.object.delete()

    # add a plane (sound familiar?)
    bpy.ops.mesh.primitive_plane_add(location=[0, 0, 0], size=50)
    bpy.context.selected_objects[0].name = "terrain"

    # subdivide it
    bpy.ops.object.modifier_add(type="SUBSURF")
    bpy.context.selected_objects[0].modifiers[0].name = "SUBSURF"
    bpy.context.selected_objects[0].modifiers[0].levels = MODEL_SUBDIVISION_QUALITY
    bpy.context.selected_objects[0].modifiers[0].subdivision_type = "SIMPLE"
    bpy.ops.object.modifier_apply(modifier="SUBSURF")

    # add texture
    texture = bpy.data.textures.new(name="DisplacementMap", type="IMAGE")
    texture.image = bpy.data.images[baked_image.name]

    # add displacement modifier
    bpy.ops.object.modifier_add(type="DISPLACE")
    bpy.context.selected_objects[0].modifiers[0].name = "DISPLACE"
    bpy.context.selected_objects[0].modifiers[0].strength = displacement_scale_value
    bpy.context.selected_objects[0].modifiers[0].mid_level = 0
    bpy.context.selected_objects[0].modifiers[0].texture_coords = "UV"
    bpy.context.selected_objects[0].modifiers[0].texture = texture
    bpy.ops.object.modifier_apply(modifier="DISPLACE")

    # get rid of outermost vertices (they make a weird rim)
    # make an object to use with boolean modifier
    terrain_obj = bpy.context.object
    bpy.ops.mesh.primitive_cube_add(location=[0, 0, 0], size=49.8)
    bpy.context.selected_objects[-1].name = "boolean_mask"
    boolean_mask = bpy.context.selected_objects[-1]
    bpy.ops.transform.resize(value=[1, 1, 10])
    bpy.context.view_layer.objects.active = terrain_obj
    for obj in bpy.context.scene.objects:
        if obj.name == "terrain":
            obj.select_set(True)
        else:
            obj.select_set(False)

    # add boolean modifier
    bpy.ops.object.modifier_add(type="BOOLEAN")
    bpy.context.selected_objects[0].modifiers[0].name = "BOOLEAN"
    bpy.context.selected_objects[0].modifiers[0].object = boolean_mask
    bpy.context.selected_objects[0].modifiers[0].operation = "INTERSECT"
    bpy.ops.object.modifier_apply(modifier="BOOLEAN")

    # delete boolean mask
    for obj in bpy.context.scene.objects:
        if obj.name == "boolean_mask":
            obj.select_set(True)
        else:
            obj.select_set(False)
    bpy.ops.object.delete()
    for obj in bpy.context.scene.objects:
        obj.select_set(True)

    # add decimate modifier
    bpy.ops.object.modifier_add(type="DECIMATE")
    bpy.context.selected_objects[0].modifiers[0].name = "DECIMATE"
    bpy.context.selected_objects[0].modifiers[0].decimate_type = "COLLAPSE"
    bpy.context.selected_objects[0].modifiers[0].ratio = MODEL_DECIMATE_RATIO
    bpy.ops.object.modifier_apply(modifier="DECIMATE")

    # export to stl file
    for x in bpy.context.scene.objects:
        x.select_set(True)
    if os.path.exists(STL_EXPORT_FILEPATH):
        os.remove(STL_EXPORT_FILEPATH)
    open(STL_EXPORT_FILEPATH, "x")

    bpy.ops.export_mesh.stl(
        filepath=STL_EXPORT_FILEPATH,
        use_selection=True
    )


def generate_terrain(
        seed: str
) -> None:
    """Generate just the stl file for the terrain"""
    # noise coordinates
    noise_value = gen_noise_value_from_seed(seed)
    displacement_scale_value = displacement_scale_value_from_seed(seed)

    # add the plane in
    bpy.ops.mesh.primitive_plane_add(location=[0, 0, 0], size=50)
    bpy.context.selected_objects[0].name = "terrain"

    # subdivide it
    bpy.ops.object.modifier_add(type="SUBSURF")
    bpy.context.selected_objects[0].modifiers[0].name = "SUBSURF"
    bpy.context.selected_objects[0].modifiers[0].levels = 8
    bpy.context.selected_objects[0].modifiers[0].subdivision_type = "SIMPLE"

    # other stuff
    bpy.context.selected_objects[0].cycles.use_adaptive_subdivision = True

    # make material
    terrain_material = bpy.data.materials.new(name="TerrainMaterial")
    bpy.data.materials["TerrainMaterial"].use_nodes = True
    bpy.data.materials["TerrainMaterial"].cycles.displacement_method = "BOTH"

    nodes = terrain_material.node_tree.nodes
    node_tree = terrain_material.node_tree
    links = node_tree.links

    # terrain nodes
    bsdf_node = [x for x in nodes if isinstance(x, bpy.types.ShaderNodeBsdfPrincipled)][0]
    output_node = [x for x in nodes if isinstance(x, bpy.types.ShaderNodeOutputMaterial)][0]
    bsdf_node.location = 2000, 1000
    output_node.location = 2400, 0

    texture_coordinate_node = node_tree.nodes.new("ShaderNodeTexCoord")
    texture_coordinate_node.location = 200, 0

    shader_mapping_node = node_tree.nodes.new("ShaderNodeMapping")
    shader_mapping_node.location = 600, 0
    value_node_set_1_0 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_0.location = 400, -400
    value_node_set_1_0.outputs["Value"].default_value = noise_value

    musgrave_1_node = node_tree.nodes.new("ShaderNodeTexMusgrave")
    musgrave_1_node.location = 800, 0
    musgrave_1_node.musgrave_dimensions = "4D"
    musgrave_1_node.musgrave_type = "FBM"
    value_node_set_1_1 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_1.location = 600, -600
    value_node_set_1_1.outputs["Value"].default_value = 0.15
    value_node_set_1_2 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_2.location = 600, -800
    value_node_set_1_2.outputs["Value"].default_value = 16
    value_node_set_1_3 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_3.location = 600, -1000
    value_node_set_1_3.outputs["Value"].default_value = 0.95

    voronoi_1_node = node_tree.nodes.new("ShaderNodeTexVoronoi")
    voronoi_1_node.location = 1000, 0
    voronoi_1_node.feature = "SMOOTH_F1"
    value_node_set_1_4 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_4.location = 800, -400
    value_node_set_1_4.outputs["Value"].default_value = 0.3

    musgrave_2_node = node_tree.nodes.new("ShaderNodeTexMusgrave")
    musgrave_2_node.location = 1200, 0
    musgrave_2_node.musgrave_dimensions = "3D"
    musgrave_2_node.musgrave_type = "FBM"
    value_node_set_1_5 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_5.location = 1100, -600
    value_node_set_1_5.outputs["Value"].default_value = 9
    value_node_set_1_6 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_6.location = 1100, -800
    value_node_set_1_6.outputs["Value"].default_value = 14
    value_node_set_1_7 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_7.location = 1100, -1000
    value_node_set_1_7.outputs["Value"].default_value = 1.05

    displacement_node = node_tree.nodes.new("ShaderNodeDisplacement")
    displacement_node.location = 2200, 0

    math_multiply_node_1 = node_tree.nodes.new("ShaderNodeMath")
    math_multiply_node_1.operation = "ADD"
    math_multiply_node_1.location = 1600, 0
    value_node_set_1_8 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_8.outputs["Value"].default_value = 0.75
    value_node_set_1_8.location = 1600, -400

    value_node_set_1_9 = node_tree.nodes.new("ShaderNodeValue")
    value_node_set_1_9.outputs["Value"].default_value = displacement_scale_value
    value_node_set_1_9.location = 1800, -400

    links.new(texture_coordinate_node.outputs[0], shader_mapping_node.inputs[0])
    links.new(shader_mapping_node.outputs[0], musgrave_1_node.inputs[0])
    links.new(value_node_set_1_0.outputs[0], musgrave_1_node.inputs[1])
    links.new(value_node_set_1_1.outputs[0], musgrave_1_node.inputs[2])
    links.new(value_node_set_1_2.outputs[0], musgrave_1_node.inputs[3])
    links.new(value_node_set_1_3.outputs[0], musgrave_1_node.inputs[4])
    links.new(musgrave_1_node.outputs[0], voronoi_1_node.inputs[0])
    links.new(value_node_set_1_4.outputs[0], voronoi_1_node.inputs[2])
    links.new(voronoi_1_node.outputs[1], musgrave_2_node.inputs[0])
    links.new(value_node_set_1_5.outputs[0], musgrave_2_node.inputs[2])
    links.new(value_node_set_1_6.outputs[0], musgrave_2_node.inputs[3])
    links.new(value_node_set_1_7.outputs[0], musgrave_2_node.inputs[4])
    links.new(musgrave_2_node.outputs[0], math_multiply_node_1.inputs[0])
    links.new(value_node_set_1_8.outputs[0], math_multiply_node_1.inputs[1])
    links.new(math_multiply_node_1.outputs[0], displacement_node.inputs[0])
    links.new(value_node_set_1_9.outputs[0], displacement_node.inputs[2])
    links.new(displacement_node.outputs[0], output_node.inputs[2])

    # assign material to terrain
    bpy.context.active_object.data.materials.append(terrain_material)


setup()
generate_terrain(SEED)
