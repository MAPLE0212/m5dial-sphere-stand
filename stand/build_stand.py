"""
M5Dial 球体スタンド（前後2分割・パネル挟み込み式）
Blender ヘッドレスで STL とプレビュー画像を生成する。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender -b -P stand/build_stand.py

単位: mm（Blender の 1 unit = 1 mm として STL 出力）

ローカル座標（cap/body の設計座標）: +Z = ダイヤルの正面方向, +Y = 上, 球の中心 = 原点
球の座標 S: ローカルを X 軸まわり 90° 回したもの（-Y = 正面, +Z = 上）。球の底はこの座標で水平に切る
ワールド座標（出力）: S を TILT だけ後ろへ傾けたもの。台座は机に垂直で、上面が斜め（くさび形）
  → USB プラグは球に対して常に真下を向くので、傾けても球の内側に当たらない
"""
import bpy, bmesh, math, os
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
DIAL_STL = os.path.join(HERE, "..", "reference", "Dial.stl")
if not os.path.exists(DIAL_STL):
    raise SystemExit(
        "reference/Dial.stl がありません。M5Stack 公式の 3D モデルを取得してください:\n"
        "  curl -L -o reference/Dial.stl https://raw.githubusercontent.com/m5stack/M5_Hardware/"
        "master/Products/K130_Dial/Structures/Dial.stl")

# ---------------- パラメータ ----------------
R = 50.0            # 球の外半径（直径100mm）
T = 2.6             # 球殻の厚み
FACE_R = 33.0       # 正面の平らな面の半径
PANEL_T = 3.0       # M5Dial が挟むパネル厚（付属ナットで締める。STL実測: 標準隙間1.8mm、ねじは後ろへ約7mm続く）
RECESS = 3.6        # ダイヤル周りのすり鉢状のくぼみ深さ（45°）
HOLE_D = 45.4       # 取付穴径（公式 45mm + 印刷公差）
KNOB_CLR_R = 26.0   # くぼみ底の半径（ノブ Ø49.6 + 隙間）
SPIGOT_H = 4.0      # 前カバーの差し込みリング長さ（USBプラグに当たらない長さ）
SPIGOT_W = 2.0      # 差し込みリング肉厚
RIM_W = 1.6         # 本体の縁の肉厚
FIT = 0.15          # はめ合いクリアランス（片側）。きつければ 0.2〜0.25 に
DFLAT = 2.5         # 回り止めの D カット量（上側）
TILT = float(os.environ.get("TILT", 15.0))         # 画面の上向き角度（°）。球ごと後ろへ傾ける
BOTTOM_Z = float(os.environ.get("BOTTOM_Z", -37.0))  # 球の底を切る位置（球の座標で中心から）。高いほど底の穴が広い
BEND_ROOM = float(os.environ.get("BEND_ROOM", 11.0))  # プラグの先から台座の底板までの余裕（ケーブルを曲げる）
BASE_BACK_MIN = 8.0 # 台座の後ろ側の最低の高さ
PLUG_LEN = 32.0     # USB-C プラグの長さ（根元のブーツ込み）
PLUG_RELIEF = 1.5   # プラグ通路の逃げ（本体・台座の内側を削る量）
RELIEF_FRONT = float(os.environ.get("RELIEF_FRONT", 1.2))  # プラグ前面側の逃げ
BASE_FLOOR = 2.0    # 台座の底板（中に重りを入れられる）
BASE_WALL = 2.4     # 台座の肉厚
SEG = 192           # 円の分割数

ZF = math.sqrt(R**2 - FACE_R**2)          # 正面の平面
ZS = ZF - RECESS - PANEL_T                # 分割面 = パネル裏面
RC = math.sqrt(R**2 - ZS**2) - RIM_W      # 本体側の受け穴半径
RB = math.sqrt(R**2 - BOTTOM_Z**2)        # 台座の外半径（球の底の平面と一致）
RBI = math.sqrt((R - T)**2 - BOTTOM_Z**2) # 球の底の開口半径

# M5Dial（公式STL）の座標: -Z が正面, 肩（パネル当たり面）が z=-2.7, 標準ナット前面 z=-0.9（隙間1.8mm）, USB-C は -Y 側 z≈9.2
DIAL_SHOULDER_Z = -2.7


# ---------------- ヘルパー ----------------
def clear():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)


def apply_tf(o):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def sphere(r):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=SEG, ring_count=SEG // 2, radius=r)
    return bpy.context.object


def cyl(r, z0, z1, verts=SEG):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=z1 - z0,
                                        location=(0, 0, (z0 + z1) / 2))
    return apply_tf(bpy.context.object)


def cone(r0, z0, r1, z1):
    bpy.ops.mesh.primitive_cone_add(vertices=SEG, radius1=r0, radius2=r1, depth=z1 - z0,
                                    location=(0, 0, (z0 + z1) / 2))
    return apply_tf(bpy.context.object)


def box(x0, x1, y0, y1, z0, z1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    o = bpy.context.object
    o.scale = (x1 - x0, y1 - y0, z1 - z0)
    return apply_tf(o)


def boolean(a, b, op, solver="EXACT"):
    m = a.modifiers.new("bool", "BOOLEAN")
    m.operation = op
    m.object = b
    m.solver = solver
    bpy.context.view_layer.objects.active = a
    bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.data.objects.remove(b, do_unlink=True)
    return a


def ring(ro, ri, z0, z1):
    o = cyl(ro, z0, z1)
    return boolean(o, cyl(ri, z0 - 1, z1 + 1), "DIFFERENCE")


def local_to_world():
    # ローカル +Z(正面) → ワールド (0,-cos t, sin t)
    return Matrix.Rotation(math.radians(90 - TILT), 4, "X")


def join(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    return bpy.context.object


# ---------------- 部品 ----------------
def s_to_world():
    """球の座標 S → ワールド（TILT だけ後ろへ傾ける）"""
    return Matrix.Rotation(math.radians(-TILT), 4, "X")


def plane_cutter(below):
    """球の底の平面（S で z = BOTTOM_Z）で切るためのカッター"""
    c = box(-120, 120, -120, 120, -120, BOTTOM_Z) if below else box(-120, 120, -120, 120, BOTTOM_Z, 120)
    c.matrix_world = s_to_world()
    return apply_tf(c)


def plane_cut(o, co, no):
    """平面で切って、normal 側を捨て、切り口を面で閉じる（boolean より確実に閉じた形になる）"""
    bm = bmesh.new(); bm.from_mesh(o.data)
    r = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                               plane_co=co, plane_no=no, clear_outer=True)
    edges = [e for e in r["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=edges)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(o.data); bm.free()
    return o


def ell_cyl(rx, ry, z0, z1, cx, cy):
    o = cyl(rx, z0, z1)
    o.scale = (1, ry / rx, 1)
    o.location = (cx, cy, 0)
    return apply_tf(o)


def plug_zc():
    return ZS + PANEL_T - (9.2 - DIAL_SHOULDER_Z)


def base_table_z():
    """台座の底（机の面）の高さ。プラグの先の下に BEND_ROOM を確保する"""
    zc = plug_zc()
    m = local_to_world()
    low = min((m @ Vector((x, -22.5 - PLUG_LEN, z))).z for x in (-6.15, 6.15) for z in (zc - 3.25, zc + 3.25))
    back_top = BOTTOM_Z * math.cos(math.radians(TILT)) - RB * math.sin(math.radians(TILT))
    return min(low - BEND_ROOM - BASE_FLOOR, back_top - BASE_BACK_MIN)


def make_cap():
    """前カバー: 取付穴のあるパネル + 本体に差し込むリング"""
    cap = sphere(R)
    boolean(cap, box(-100, 100, -100, 100, ZS, ZF), "INTERSECT")
    # すり鉢状のくぼみ（45°）
    top = ZF + 1
    boolean(cap, cone(KNOB_CLR_R, ZS + PANEL_T, KNOB_CLR_R + (top - (ZS + PANEL_T)), top), "DIFFERENCE")
    boolean(cap, cyl(HOLE_D / 2, ZS - 1, ZF + 1), "DIFFERENCE")
    # 差し込みリング（上側を D カットして回り止め）
    sp = ring(RC - FIT, RC - FIT - SPIGOT_W, ZS - SPIGOT_H, ZS + 0.5)
    boolean(sp, box(-100, 100, RC - DFLAT - FIT, 100, -100, 100), "DIFFERENCE")
    boolean(cap, sp, "UNION")
    cap.name = "cap"
    return cap


def make_body():
    """本体: 球の後ろ側。底を平らに切り、台座に載せる"""
    body = sphere(R)
    boolean(body, sphere(R - T), "DIFFERENCE")
    # 差し込みリングを受けるカラー
    # 外側は円すい台にして殻の内側にだけ肉を足す（球同士の重なりを避ける）
    zc0 = ZS - SPIGOT_H - 0.3
    collar = cone(math.sqrt((R - 0.8)**2 - zc0**2), zc0, math.sqrt((R - 0.8)**2 - ZS**2), ZS)
    boolean(collar, cyl(RC, zc0 - 1, ZS + 1), "DIFFERENCE")
    body = boolean(body, collar, "UNION")
    boolean(body, box(-100, 100, -100, 100, -100, ZS), "INTERSECT")
    # D カット付き受け穴
    hole = cyl(RC, ZS - SPIGOT_H - 0.3, ZS + 1)
    boolean(hole, box(-100, 100, RC - DFLAT, 100, -100, 100), "DIFFERENCE")
    boolean(body, hole, "DIFFERENCE")
    # USB プラグの通り道（内側だけ削る）と底の平面カット。傾ける前のローカル座標で行う
    # （ローカルでは球の底は y = BOTTOM_Z の平面）
    boolean(body, make_plug_relief(local=True), "DIFFERENCE", "FAST")
    plane_cut(body, (0, BOTTOM_Z, 0), (0, -1, 0))
    body.matrix_world = local_to_world()
    apply_tf(body)
    body.name = "body"
    return body


def make_base():
    """台座: 机に垂直な楕円筒で、上面は球の底に合わせて斜め（くさび形）。
    上板 + 位置決めの C 字リング、後ろにケーブル用の切り欠き"""
    t = math.radians(TILT)
    C = s_to_world() @ Vector((0, 0, BOTTOM_Z))   # 球の底の円の中心
    table = base_table_z()
    top = C.z + RB * math.sin(t) + 5
    # 斜めの平面で切ったとき、ちょうど半径 RB の円になる楕円筒
    base = ell_cyl(RB, RB * math.cos(t), table, top, C.x, C.y)
    plane_cut(base, C, s_to_world().to_3x3() @ Vector((0, 0, 1)))
    boolean(base, ell_cyl(RB - BASE_WALL, RB * math.cos(t) - BASE_WALL, table + BASE_FLOOR, top + 1, C.x, C.y),
            "DIFFERENCE")
    # 上板（下面は円すいにしてサポートなしで印刷できるように）と C 字リング。球の座標で作って傾ける
    ri = RBI - FIT - 2.0
    plate = cone(RB - 0.6, BOTTOM_Z - 7, RB - 0.6, BOTTOM_Z)
    boolean(plate, cone(RB - 0.6, BOTTOM_Z - 7.01, ri, BOTTOM_Z + 0.01), "DIFFERENCE")
    loc = ring(RBI - FIT, ri, BOTTOM_Z - 0.5, BOTTOM_Z + 4.0)
    # 前側 120° は USB プラグの通り道として開ける（C 字）
    boolean(loc, box(-100, 100, -100, -RBI * 0.5, -100, 100), "DIFFERENCE")
    boolean(plate, loc, "UNION")
    plate.matrix_world = s_to_world()
    apply_tf(plate)
    boolean(base, plate, "UNION")
    # 後ろのケーブル切り欠き（下から開いているので、ケーブルを上から落とし込める）
    boolean(base, box(-3.0, 3.0, C.y, 100, table - 1, table + BASE_FLOOR + 5), "DIFFERENCE")
    # 飾りの通気穴（写真の台座のイメージ）
    hv = table + BASE_FLOOR + 4 + 0.5 * (C.z - RB * math.sin(t) - (table + BASE_FLOOR + 4))
    holes = []
    n = 36
    for i in range(n):
        a = 2 * math.pi * i / n
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=1.3, depth=10,
                                            location=(C.x + math.cos(a) * RB, C.y + math.sin(a) * RB * math.cos(t), hv),
                                            rotation=(0, math.pi / 2, a))
        holes.append(apply_tf(bpy.context.object))
    boolean(base, join(holes), "DIFFERENCE")
    base.name = "base"
    return base


def import_dial():
    """公式 STL を読み込み、取付位置に配置（パネル厚に合わせてナットも移動）"""
    bpy.ops.wm.stl_import(filepath=DIAL_STL)
    d = bpy.context.object
    bm = bmesh.new()
    bm.from_mesh(d.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x < -30], context="VERTS")  # 重複コピー除去
    # ナット（z -0.9〜4.1, r>21.2 の部品）をパネル厚の分だけ後ろへ
    nut_shift = PANEL_T - 1.8
    for v in bm.verts:
        r = math.hypot(v.co.x, v.co.y)
        if -0.95 <= v.co.z <= 4.15 and r >= 21.25:
            v.co.z += nut_shift
    bm.to_mesh(d.data)
    bm.free()
    # ダイヤル座標 → ローカル: z' = (ZS+PANEL_T) - (z - SHOULDER), x' = -x（Y軸まわり180°）
    m = Matrix.Translation((0, 0, ZS + PANEL_T + DIAL_SHOULDER_Z)) @ Matrix.Rotation(math.pi, 4, "Y")
    d.matrix_world = local_to_world() @ m
    apply_tf(d)
    d.name = "M5Dial"
    return d


def make_plug(straight):
    """USB-C プラグの目安。ストレート: 12.3x6.5 長さ30。L字: 頭 13mm + 後ろへ伸びるケーブル Ø4.5"""
    zc = plug_zc()
    if straight:
        p = box(-6.15, 6.15, -22.5 - PLUG_LEN, -22.5, zc - 3.25, zc + 3.25)
    else:
        p = box(-6.15, 6.15, -22.5 - 13, -22.5, zc - 3.25, zc + 3.25)
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=2.25, depth=14,
                                            location=(0, -22.5 - 9, zc - 3.25 - 7))
        c = apply_tf(bpy.context.object)
        p = join([p, c])
    p.matrix_world = local_to_world()
    apply_tf(p)
    p.name = "usb_straight" if straight else "usb_L"
    return p


def make_plug_relief(front=None, local=False):
    """プラグの通り道を本体・台座の内側から逃がすカッター（外側の見た目は変わらない）"""
    zc = plug_zc()
    e = PLUG_RELIEF
    f = RELIEF_FRONT if front is None else front
    c = box(-6.15 - e, 6.15 + e, -22.5 - PLUG_LEN - 3, -30.0, zc - 3.25 - e, zc + 3.25 + f)  # 底板は貫通させない
    if local:
        return c
    c.matrix_world = local_to_world()
    return apply_tf(c)


def bvh(o):
    dg = bpy.context.evaluated_depsgraph_get()
    return BVHTree.FromObject(o, dg)


# ---------------- 描画 ----------------
def mat(name, rgb):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    return m


def setup_render():
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "MATERIAL"
    sc.display.shading.show_cavity = True
    sc.display.shading.show_shadows = False
    sc.render.resolution_x = 1200
    sc.render.resolution_y = 1000
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("w") if sc.world is None else sc.world
    sc.display.shading.background_type = "WORLD"
    sc.world.color = (0.85, 0.85, 0.86)
    sc.view_settings.view_transform = "Standard"


def camera(loc, target, lens=50):
    if "cam" in bpy.data.objects:
        c = bpy.data.objects["cam"]
    else:
        bpy.ops.object.camera_add()
        c = bpy.context.object
        c.name = "cam"
    c.location = loc
    d = Vector(target) - Vector(loc)
    c.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    c.data.lens = lens
    c.data.clip_end = 5000
    bpy.context.scene.camera = c


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def dup(o, name):
    n = o.copy()
    n.data = o.data.copy()
    n.name = name
    bpy.context.collection.objects.link(n)
    return n


def export(o, path):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, ascii_format=False)


# ---------------- メイン ----------------
def main():
    clear()
    print(f"ZF={ZF:.2f} ZS={ZS:.2f} RC={RC:.2f} RB={RB:.2f} RBI={RBI:.2f}")
    cap = make_cap()
    cap.matrix_world = local_to_world()
    apply_tf(cap)
    # 前カバーの下端が底面より下に出る場合は、本体と同じ面で平らに切る
    s_inv = s_to_world().inverted()
    if min((s_inv @ v.co).z for v in cap.data.vertices) < BOTTOM_Z:
        boolean(cap, plane_cutter(True), "DIFFERENCE", "FAST")
    cap_local = dup(cap, "cap_print")      # 印刷向き用
    cap_local.matrix_world = local_to_world().inverted()
    apply_tf(cap_local)
    body = make_body()
    base = make_base()
    dial = import_dial()
    boolean(base, make_plug_relief(), "DIFFERENCE")
    plug_s = make_plug(False)   # 参考: L字
    plug = make_plug(True)      # 本命: ストレート

    # 干渉チェック（重なり体積と、その位置をローカル座標で表示）
    objs = {o.name: o for o in (cap, body, base, dial, plug, plug_s)}
    inv = local_to_world().inverted()
    zmin = min((v.co.z for v in plug.data.vertices))
    table = base_table_z()
    C = s_to_world() @ Vector((0, 0, BOTTOM_Z))
    t = math.radians(TILT)
    print(f"BASE table z={table:.1f}  height back={C.z - RB * math.sin(t) - table:.1f} front={C.z + RB * math.sin(t) - table:.1f}"
          f"  center offset (forward of sphere center)={-C.y:.1f} mm  total height={R - table:.1f} mm")
    print(f"PLUG straight end z={zmin:.1f}  room for cable bend={zmin - (table + BASE_FLOOR):.1f} mm")
    # プラグ周りのすき間（最小距離）
    zc = plug_zc()
    M = local_to_world()
    for W, H, label in [(12.3, 6.5, "12.3x6.5"), (14.0, 7.0, "14x7")]:
        pts = []
        n = 30
        for i in range(n + 1):
            for j in range(n + 1):
                u = -W / 2 + W * i / n
                v_ = -22.5 - PLUG_LEN * j / n
                for w in (zc - H / 2, zc + H / 2):
                    pts.append(M @ Vector((u, v_, w)))
                for u2 in (-W / 2, W / 2):
                    pts.append(M @ Vector((u2, v_, zc - H / 2 + H * i / n)))
        for o in (cap, body, base):
            tr = bvh(o)
            d = min(tr.find_nearest(q)[3] for q in pts)
            print(f"MARGIN plug {label} -> {o.name}: {d:.2f} mm")
    for a, b in [("M5Dial", "cap"), ("M5Dial", "body"), ("usb_straight", "cap"), ("usb_straight", "body"),
                 ("usb_straight", "base"), ("usb_L", "body"), ("usb_L", "base"),
                 ("cap", "body"), ("body", "base"), ("cap", "base")]:
        t = dup(objs[a], "tmp")
        boolean(t, dup(objs[b], "tmp2"), "INTERSECT")
        bm = bmesh.new(); bm.from_mesh(t.data)
        v = abs(bm.calc_volume())
        where = ""
        if bm.verts:
            cs = [inv @ x.co for x in bm.verts]
            rs = [math.hypot(c.x, c.y) for c in cs]
            where = (f" local z[{min(c.z for c in cs):.1f},{max(c.z for c in cs):.1f}]"
                     f" r[{min(rs):.1f},{max(rs):.1f}] y[{min(c.y for c in cs):.1f},{max(c.y for c in cs):.1f}]")
        bm.free()
        bpy.data.objects.remove(t, do_unlink=True)
        print(f"INTERFERENCE {a} x {b}: overlap volume {v:.3f} mm3{where}")
    bpy.data.objects.remove(plug_s, do_unlink=True)

    for o in (cap, body, base, cap_local):
        me = o.data
        bm = bmesh.new(); bm.from_mesh(me)
        nm = sum(1 for e in bm.edges if not e.is_manifold)
        vol = bm.calc_volume()
        bm.free()
        print(f"PART {o.name}: faces={len(me.polygons)} non_manifold_edges={nm} volume={vol/1000:.1f} cm3")

    # 印刷向きで出力
    out = HERE
    # 前カバー: 正面を下に
    cap_local.matrix_world = Matrix.Translation((0, 0, ZF)) @ Matrix.Rotation(math.pi, 4, "X")
    apply_tf(cap_local)
    export(cap_local, os.path.join(out, "m5dial_stand_1_cap.stl"))
    # 本体: 底面を下に
    bp = dup(body, "body_print")
    bp.matrix_world = Matrix.Translation((0, 0, -BOTTOM_Z)) @ s_to_world().inverted()
    apply_tf(bp)
    export(bp, os.path.join(out, "m5dial_stand_2_body.stl"))
    # 台座: そのまま底面を下に
    sp = dup(base, "base_print"); sp.location.z = -base_table_z(); apply_tf(sp)
    export(sp, os.path.join(out, "m5dial_stand_3_base.stl"))
    for o in (cap_local, bp, sp):
        bpy.data.objects.remove(o, do_unlink=True)

    # プレビュー
    setup_render()
    cap.data.materials.append(mat("shell", (0.11, 0.11, 0.12)))
    body.data.materials.append(mat("shell2", (0.16, 0.16, 0.17)))
    base.data.materials.append(mat("base", (0.20, 0.20, 0.21)))
    dial.data.materials.append(mat("dial", (0.95, 0.45, 0.12)))
    plug.data.materials.append(mat("plug", (0.2, 0.5, 0.95)))
    plug.hide_render = True
    prev = os.path.join(out, "preview")
    os.makedirs(prev, exist_ok=True)

    camera((-170, -260, 110), (0, 0, -8), 60)
    render(os.path.join(prev, "1_assembled.png"))

    # 分解図
    off = local_to_world().to_3x3() @ Vector((0, 0, 1))
    cap.location = off * 45
    dial.location = off * 45
    base.location.z = -35
    camera((-260, -300, 120), (0, -15, -20), 50)
    render(os.path.join(prev, "2_exploded.png"))
    cap.location = dial.location = base.location = Vector()

    # 断面（x>0 側を表示）＋ USB プラグ目安
    plug.hide_render = False
    secs = []
    for o in (cap, body, base, dial, plug):
        s = dup(o, o.name + "_sec")
        bm = bmesh.new(); bm.from_mesh(s.data)
        g = bm.verts[:] + bm.edges[:] + bm.faces[:]
        r = bmesh.ops.bisect_plane(bm, geom=g, plane_co=(0, 0, 0), plane_no=(-1, 0, 0), clear_outer=True)
        cut_edges = [e for e in r["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
        if o is not dial:
            try:
                bmesh.ops.edgenet_fill(bm, edges=cut_edges)
            except Exception:
                pass
        bm.to_mesh(s.data); bm.free()
        secs.append(s)
        o.hide_render = True
    camera((-330, 0, 0), (0, 0, -10), 60)
    render(os.path.join(prev, "3_section.png"))
    print("DONE")


main()
