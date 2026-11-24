"""
Ø100 版と Ø84 版を並べた比較画像（preview/size_compare.png）を出力する。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender -b -P stand/render_compare.py
"""
import os
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "render_views.py")
# render_views.py の関数定義だけを使う（最後の実行部分は外す）
code = open(SRC, encoding="utf-8").read().split("\nrear_notch()\n")[0]
code = code.replace('__file__ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_stand.py")',
                    f'__file__ = {os.path.join(HERE, "build_stand.py")!r}')

ns = None
for i, (variant, dx) in enumerate((("100", -75), ("84", 75))):
    os.environ["VARIANT"] = variant
    ns = {"__name__": "compare"}
    exec(compile(code, SRC, "exec"), ns)
    if i > 0:
        ns["clear"] = lambda: None          # 1 つ目のモデルを消さない
    parts = ns["build"]()
    t = ns["base_table_z"]()
    for o in parts:
        o.name = f"{o.name}_{variant}"
        o.location.x += dx
        o.location.z -= t                   # 机の高さをそろえる
        ns["apply_tf"](o)
    ns["colorize"](*parts)

ns["scene_setup"](0.0)
ns["camera"]((0, -420, 120), Vector((0, 0, 55)), 50)
ns["render"](os.path.join(HERE, "preview", "size_compare.png"))
print("DONE")
