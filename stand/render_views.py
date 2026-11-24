"""
いろいろな角度のプレビュー画像を出力する（build_stand.py の形状をそのまま使う）。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender -b -P stand/render_views.py
"""
import os, math
import bpy, bmesh
from mathutils import Vector, Matrix

__file__ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_stand.py")
_src = open(__file__, encoding="utf-8").read().replace("\nmain()\n", "\n")
exec(compile(_src, __file__, "exec"))

PREV = os.path.join(HERE, "preview")
os.makedirs(PREV, exist_ok=True)


def build():
    clear()
    cap = make_cap()
    cap.matrix_world = local_to_world()
    apply_tf(cap)
    s_inv = s_to_world().inverted()
    if min((s_inv @ v.co).z for v in cap.data.vertices) < BOTTOM_Z:
        boolean(cap, plane_cutter(True), "DIFFERENCE", "FAST")
    body = make_body()
    base = make_base()
    boolean(base, make_plug_relief(), "DIFFERENCE")
    dial = import_dial()
    # 公式モデルには画面のガラスがないので、黒いガラス板を足して見た目を実物に近づける
    zf = ZS + PANEL_T + DIAL_SHOULDER_Z + 17.32  # ノブ前面（ローカル z）
    glass = cyl(17.2, zf - 1.6, zf - 1.1)
    glass.matrix_world = local_to_world()
    apply_tf(glass)
    glass.name = "glass"
    return cap, body, base, dial, glass


def scene_setup(table_z):
    setup_render()
    sc = bpy.context.scene
    sc.render.resolution_x = 1400
    sc.render.resolution_y = 1100
    sc.display.shading.show_shadows = False
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = "BOTH"
    sc.world.color = (0.94, 0.94, 0.95)
    bpy.ops.mesh.primitive_plane_add(size=2000, location=(0, 0, table_z))
    floor = bpy.context.object
    floor.name = "floor"
    floor.data.materials.append(mat("floor", (0.90, 0.89, 0.87)))
    return floor


def colorize(cap, body, base, dial, glass):
    cap.data.materials.append(mat("cap", (0.10, 0.10, 0.11)))
    body.data.materials.append(mat("body", (0.13, 0.13, 0.14)))
    base.data.materials.append(mat("base", (0.17, 0.17, 0.18)))
    dial.data.materials.append(mat("dial", (0.93, 0.47, 0.13)))
    glass.data.materials.append(mat("glass", (0.02, 0.02, 0.03)))


def shot(name, loc, target, lens=55):
    camera(loc, target, lens)
    render(os.path.join(PREV, name))


def main_views():
    cap, body, base, dial, glass = build()
    table = base_table_z()
    floor = scene_setup(table)
    colorize(cap, body, base, dial, glass)
    tgt = Vector((0, 0, (R + table) / 2 - 3))

    shot("5_front.png", (0, -360, 10), tgt, 60)
    shot("6_side.png", (-360, 0, 5), tgt, 60)
    shot("7_desk_view.png", (-70, -260, 150), tgt, 55)          # 机の前に座ったときの目線
    shot("8_back.png", (190, 250, 70), tgt, 55)
    shot("9_low_angle.png", (-150, -230, -40), tgt, 50)

    # 前カバー + M5Dial を裏から（ナットの締め付けと差し込みリングの D カット）
    for o in (body, base, floor):
        o.hide_render = True
    ax = local_to_world().to_3x3() @ Vector((0, 0, 1))
    c = ax * ZS
    back = c - ax * 190 + Vector((80, 0, 90))
    shot("10_cap_back_with_nut.png", back, c - ax * 5, 50)
    for o in (body, base, floor):
        o.hide_render = False

    # 本体の中（前カバーを外した状態で正面から）
    cap.hide_render = dial.hide_render = glass.hide_render = True
    shot("11_body_inside.png", (-60, -300, 40), Vector((0, 0, -15)), 55)
    cap.hide_render = dial.hide_render = glass.hide_render = False
    return cap, body, base


def print_layout(cap, body, base):
    """印刷する向きで 3 パーツを並べた図"""
    for o in list(bpy.data.objects):
        if o.type == "MESH" and o.name not in ("cap", "body", "base"):
            o.hide_render = True
    # 印刷向きへの変換（build_stand.py の export と同じ）
    cp = dup(cap, "cap_p")
    cp.matrix_world = Matrix.Translation((-120, 0, ZF)) @ Matrix.Rotation(math.pi, 4, "X") @ local_to_world().inverted()
    apply_tf(cp)
    bp = dup(body, "body_p")
    bp.matrix_world = Matrix.Translation((0, 0, -BOTTOM_Z)) @ s_to_world().inverted()
    apply_tf(bp)
    sp = dup(base, "base_p")
    sp.location = (120, 0, -base_table_z())
    apply_tf(sp)
    for o in (cap, body, base):
        o.hide_render = True
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    bed = bpy.context.object
    bed.scale = (340, 150, 1)
    apply_tf(bed)
    bed.data.materials.append(mat("bed", (0.30, 0.32, 0.35)))
    bpy.data.objects["floor"].hide_render = True
    shot("12_print_layout.png", (-40, -380, 300), Vector((0, 0, 15)), 38)


cap, body, base = main_views()
print_layout(cap, body, base)
print("DONE")
