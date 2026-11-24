"""
いろいろな角度のプレビュー画像を出力する（build_stand.py の形状をそのまま使う）。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender -b -P stand/render_views.py              # Ø84 版
  VARIANT=100 /Applications/Blender.app/Contents/MacOS/Blender -b -P stand/render_views.py  # Ø100 版
"""
import os, math
import bpy, bmesh
from mathutils import Vector, Matrix

__file__ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_stand.py")
_src = open(__file__, encoding="utf-8").read().replace("\nmain()\n", "\n")
exec(compile(_src, __file__, "exec"))

PREV = PREV_DIR
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


def rear_notch():
    """台座の後ろの切り欠きと、ケーブルの通し方の目安"""
    cap, body, base, dial, glass = build()
    dial.hide_render = glass.hide_render = True
    setup_render()
    cap.data.materials.append(mat("a", (0.11, 0.11, 0.12)))
    body.data.materials.append(mat("b", (0.16, 0.16, 0.17)))
    base.data.materials.append(mat("c", (0.20, 0.20, 0.21)))
    # ケーブル: プラグの先から台座の中で後ろへ曲げ、切り欠きを通って外へ
    tip = local_to_world() @ Vector((0, -22.5 - PLUG_LEN, plug_zc()))
    z0 = base_table_z() + BASE_FLOOR + 2.3
    cy = (s_to_world() @ Vector((0, 0, BOTTOM_Z))).y
    pts = [(0, tip.y, tip.z + 2), (0, (tip.y + cy) / 2, z0 + 3), (0, cy, z0), (0, cy + RB + 40, z0)]
    cu = bpy.data.curves.new("cable", "CURVE")
    cu.dimensions = "3D"; cu.bevel_depth = 2.2; cu.bevel_resolution = 4
    sp = cu.splines.new("BEZIER"); sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p; bp.handle_left_type = bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("cable", cu)
    bpy.context.collection.objects.link(ob)
    ob.data.materials.append(mat("cab", (0.2, 0.5, 0.95)))
    t = base_table_z()
    shot("4_rear_cable_notch.png", (120, 240, t + 50), Vector((0, 0, t + 15)), 60)
    bpy.data.objects.remove(ob, do_unlink=True)


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


rear_notch()
cap, body, base = main_views()
print_layout(cap, body, base)
print("DONE")
