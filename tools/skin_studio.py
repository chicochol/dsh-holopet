#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大肥鱼 · 皮肤工作台（可视化小工具）

把任意 spritesheet（PNG/WebP）切成 HoloCubic 设备能播的三档 GIF 皮肤包：
    build/skins/<id>/<slow|normal|fast>/<event>_01.gif
    build/skins/<id>/manifest.lua
    build/skins/<id>/preview.png

用法：
    python tools/skin_studio.py

界面流程：
    1. 选精灵表 -> 填列数/行数（自动算单元格尺寸，预览上会画网格）
    2. 右侧表格里逐行填“事件 / 行号 / 起始列 / 帧数”（默认按鲸鱼娘的 13 个事件预填）
    3. 填皮肤 id 与中文名 -> 点“生成皮肤包”

复用 tools/build_fish_gifs.py 已跑通的裁切、联合包围盒、调色板量化、40KB 降级阶梯。
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_fish_gifs as B  # noqa: E402

SPEEDS = [("slow", 150), ("normal", 120), ("fast", 90)]
DEFAULT_SPEED = "normal"
FRAME_LADDER = [16, 8, 6, 4, 3]
COLOR_LADDER = [32, 24, 16, 12, 8]

# 事件顺序与默认 (行, 起始列, 帧数)，对齐鲸鱼娘素材的布局
DEFAULT_EVENTS = [
    ("Idle", 0, 0, 4),
    ("UserPromptSubmit", 0, 4, 1),
    ("PreToolUse", 1, 0, 6),
    ("PostToolUse", 2, 0, 6),
    ("PermissionRequest", 4, 0, 5),
    ("Error", 3, 0, 4),
    ("Stop", 4, 1, 5),
    ("SessionStart", 4, 3, 2),
    ("SubagentStart", 1, 2, 4),
    ("SubagentStop", 2, 3, 4),
    ("PreCompact", 5, 0, 5),
    ("PostCompact", 5, 4, 4),
    ("Sleeping", 6, 0, 4),
]


def slice_frames(sheet: Image.Image, row: int, start: int, count: int, cw: int, ch: int) -> list[Image.Image]:
    """按 (行, 起始列, 帧数) 从精灵表切出连续帧。"""
    frames = []
    for i in range(max(1, count)):
        col = start + i
        box = (col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)
        frames.append(sheet.crop(box))
    return frames


def build_one(prepared: list[Image.Image], path: Path, duration: int) -> tuple[int, int, int]:
    """按“帧数 × 色数”阶梯降级，直到单文件 <= 40KB。"""
    src_n = len(prepared)
    ladder = [src_n] + [n for n in FRAME_LADDER if n < src_n]
    for nframes in ladder:
        seq = B.subsample(prepared, nframes)
        for colors in COLOR_LADDER:
            B.DURATION = duration
            size = B.encode(seq, colors, path)
            if size <= B.MAX_BYTES:
                return nframes, colors, size
    raise SystemExit("%s 在最低参数下仍超过 %d 字节" % (path.name, B.MAX_BYTES))


class Studio:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.sheet: Image.Image | None = None
        self.preview_photo = None
        self.cell_w = 192
        self.cell_h = 208
        self.rows: list[tuple[str, tk.StringVar, tk.StringVar, tk.StringVar]] = []

        root.title("大肥鱼 · 皮肤工作台")
        root.geometry("1180x760")
        root.minsize(1000, 700)

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="选择精灵表…", command=self.pick_file).pack(side="left")
        self.path_var = tk.StringVar(value="（未选择）")
        ttk.Label(top, textvariable=self.path_var).pack(side="left", padx=8)
        ttk.Label(top, text="列数").pack(side="left", padx=(12, 2))
        self.cols_var = tk.StringVar(value="8")
        ttk.Entry(top, textvariable=self.cols_var, width=5).pack(side="left")
        ttk.Label(top, text="行数").pack(side="left", padx=(10, 2))
        self.rows_var = tk.StringVar(value="7")
        ttk.Entry(top, textvariable=self.rows_var, width=5).pack(side="left")
        ttk.Button(top, text="刷新网格", command=self.refresh_grid).pack(side="left", padx=8)
        self.cell_var = tk.StringVar(value="单元格 -")
        ttk.Label(top, textvariable=self.cell_var).pack(side="left", padx=8)

        body = ttk.Frame(root, padding=(8, 0))
        body.pack(fill="both", expand=True)

        left = ttk.LabelFrame(body, text="精灵表预览", padding=6)
        left.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(left, background="#101820", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        right = ttk.LabelFrame(body, text="事件 → 帧映射（行 / 起始列 / 帧数）", padding=6)
        right.pack(side="left", fill="y", padx=(8, 0))
        self.table = ttk.Frame(right)
        self.table.pack(fill="both", expand=True)
        for idx, (name, row, start, count) in enumerate(DEFAULT_EVENTS):
            ttk.Label(self.table, text=name, width=18).grid(row=idx, column=0, sticky="w", pady=1)
            rv, sv, cv = tk.StringVar(value=str(row)), tk.StringVar(value=str(start)), tk.StringVar(value=str(count))
            ttk.Entry(self.table, textvariable=rv, width=4).grid(row=idx, column=1, padx=2)
            ttk.Entry(self.table, textvariable=sv, width=4).grid(row=idx, column=2, padx=2)
            ttk.Entry(self.table, textvariable=cv, width=4).grid(row=idx, column=3, padx=2)
            self.rows.append((name, rv, sv, cv))
        ttk.Label(self.table, text="提示：帧数指该行连续取多少格；留 0 表示跳过该事件。").grid(
            row=len(DEFAULT_EVENTS), column=0, columnspan=4, sticky="w", pady=(8, 0))

        foot = ttk.Frame(root, padding=8)
        foot.pack(fill="x")
        ttk.Label(foot, text="皮肤 id").pack(side="left")
        self.id_var = tk.StringVar(value="myskin")
        ttk.Entry(foot, textvariable=self.id_var, width=16).pack(side="left", padx=(4, 12))
        ttk.Label(foot, text="中文名").pack(side="left")
        self.name_var = tk.StringVar(value="新皮肤")
        ttk.Entry(foot, textvariable=self.name_var, width=16).pack(side="left", padx=(4, 12))
        self.build_btn = ttk.Button(foot, text="生成皮肤包", command=self.build)
        self.build_btn.pack(side="left", padx=8)

        self.log = tk.Text(root, height=12, background="#0f1720", foreground="#d7e3ee", insertbackground="#d7e3ee")
        self.log.pack(fill="both", padx=8, pady=(0, 8))

    # ------------------------------------------------------------------ 交互

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(
            title="选择精灵表",
            filetypes=[("图片", "*.png *.webp *.gif"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            img = Image.open(path)
            img.load()
            if img.mode != "RGBA":
                img = img.convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("打开失败", str(exc))
            return
        self.sheet = img
        self.path_var.set("%s  (%dx%d)" % (Path(path).name, img.width, img.height))
        self.cols_var.set(str(B.COLS))
        self.rows_var.set(str(len(B.ROW_FRAMES)))
        self.refresh_grid()

    def refresh_grid(self) -> None:
        if self.sheet is None:
            return
        try:
            cols = max(1, int(self.cols_var.get()))
            rows = max(1, int(self.rows_var.get()))
        except ValueError:
            messagebox.showerror("参数错误", "列数和行数必须是整数")
            return
        cw, ch = self.sheet.width // cols, self.sheet.height // rows
        self.cell_w, self.cell_h = cw, ch
        self.cell_var.set("单元格 %d×%d" % (cw, ch))
        self.draw_preview(cols, rows, cw, ch)

    def draw_preview(self, cols: int, rows: int, cw: int, ch: int) -> None:
        assert self.sheet is not None
        cw_canvas = max(self.canvas.winfo_width(), 400)
        ch_canvas = max(self.canvas.winfo_height(), 400)
        scale = min((cw_canvas - 16) / self.sheet.width, (ch_canvas - 16) / self.sheet.height)
        tw, th = int(self.sheet.width * scale), int(self.sheet.height * scale)
        flat = Image.new("RGBA", self.sheet.size, (16, 24, 32, 255))
        flat.alpha_composite(self.sheet)
        scaled = flat.convert("RGB").resize((tw, th), Image.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(scaled)
        self.canvas.delete("all")
        ox, oy = (cw_canvas - tw) // 2, (ch_canvas - th) // 2
        self.canvas.create_image(ox, oy, image=self.preview_photo, anchor="nw")
        for c in range(cols + 1):
            x = ox + tw * c / cols
            self.canvas.create_line(x, oy, x, oy + th, fill="#4ADE80", width=1)
        for r in range(rows + 1):
            y = oy + th * r / rows
            self.canvas.create_line(ox, y, ox + tw, y, fill="#4ADE80", width=1)
        self.canvas.create_text(ox + 6, oy + 6, anchor="nw", fill="#0B1512",
                                text="%d×%d" % (cols, rows), font=("Consolas", 10))

    def logline(self, text: str) -> None:
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    # ------------------------------------------------------------------ 生成

    def build(self) -> None:
        if self.sheet is None:
            messagebox.showerror("缺少素材", "请先选择精灵表")
            return
        skin_id = (self.id_var.get() or "").strip()
        if not skin_id.isidentifier():
            messagebox.showerror("id 不合法", "皮肤 id 只能是字母、数字、下划线")
            return
        spec = []
        for name, rv, sv, cv in self.rows:
            try:
                row, start, count = int(rv.get()), int(sv.get()), int(cv.get())
            except ValueError:
                messagebox.showerror("参数错误", "%s 的行/列/帧数必须是整数" % name)
                return
            if count > 0:
                spec.append((name, row, start, count))
        if not spec:
            messagebox.showerror("没有动作", "至少给一个事件填正数帧数")
            return

        out = ROOT / "build" / "skins" / skin_id
        if out.exists():
            if not messagebox.askyesno("覆盖确认", "%s 已存在，继续会整体覆盖。" % out):
                return
        self.build_btn.state(["disabled"])
        self.log.delete("1.0", "end")
        try:
            self._build(skin_id, out, spec)
        except BaseException as exc:  # noqa: BLE001
            self.logline("失败：%s" % exc)
            messagebox.showerror("生成失败", str(exc))
        finally:
            self.build_btn.state(["!disabled"])

    def _build(self, skin_id: str, out: Path, spec) -> None:
        assert self.sheet is not None
        import shutil

        if out.exists():
            shutil.rmtree(out)
        per_speed: dict[str, list[dict]] = {}
        self.logline("精灵表 %dx%d，单元格 %dx%d，共 %d 个动作" % (
            self.sheet.width, self.sheet.height, self.cell_w, self.cell_h, len(spec)))

        for speed, duration in SPEEDS:
            gif_dir = out / speed
            gif_dir.mkdir(parents=True, exist_ok=True)
            records = []
            for name, row, start, count in spec:
                frames = slice_frames(self.sheet, row, start, count, self.cell_w, self.cell_h)
                prepared = B.prepare_frames(frames)
                filename = "%s_01.gif" % name.lower()
                path = gif_dir / filename
                nframes, colors, size = build_one(prepared, path, duration)
                check = B.verify_gif(path)
                if tuple(check["size"]) != (B.CANVAS, B.CANVAS):
                    raise SystemExit("%s 尺寸异常 %s" % (filename, check["size"]))
                records.append({"event": name, "file": filename, "bytes": size,
                                "frames": nframes, "colors": colors})
                self.logline("%-6s %-26s %2d 帧 %2d 色 %6.1f KB" % (
                    speed, filename, nframes, colors, size / 1024.0))
            per_speed[speed] = records
            total = sum(r["bytes"] for r in records)
            self.logline("--- %s 档：%d 个文件，%.1f KB" % (speed, len(records), total / 1024.0))

        name_zh = (self.name_var.get() or skin_id).strip()
        lines = [
            "-- Generated by tools/skin_studio.py",
            "return {",
            '  id = "%s",' % skin_id,
            '  name = "%s",' % name_zh,
            '  name_en = "%s",' % skin_id,
            "  speeds = { slow = 150, normal = 120, fast = 90 },",
            '  default_speed = "%s",' % DEFAULT_SPEED,
            "  events = {",
        ]
        for name, _row, _start, _count in spec:
            files = [r["file"] for r in per_speed[DEFAULT_SPEED] if r["event"] == name]
            lines.append('    ["%s"] = { %s },' % (name, ", ".join('"%s"' % f for f in files)))
        lines += ["  },", "  weather = {},", "}", ""]
        (out / "manifest.lua").write_text("\n".join(lines), encoding="utf-8")

        # 预览图：把 normal 档每个事件的首帧拼成一行
        tiles = []
        for name, _row, _start, _count in spec:
            f = Image.open(out / DEFAULT_SPEED / ("%s_01.gif" % name.lower())).convert("RGBA")
            tiles.append((name, f))
        cols = min(5, len(tiles))
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new("RGBA", (cols * 170, rows * 190), (11, 21, 18, 255))
        for i, (name, f) in enumerate(tiles):
            x, y = (i % cols) * 170 + 5, (i // cols) * 190 + 5
            sheet.alpha_composite(f, (x, y))
        sheet.convert("RGB").save(out / "preview.png")

        grand = sum(r["bytes"] for recs in per_speed.values() for r in recs)
        self.logline("\n完成：%d 个 GIF，总体积 %.1f KB" % (
            sum(len(v) for v in per_speed.values()), grand / 1024.0))
        self.logline("输出目录 %s" % out)
        self.logline("下一步：python tools/deploy_app.py 会把 build/dsh_fish 同步到设备；")
        self.logline("新皮肤还要把 %s 复制到 build/dsh_fish/assets/skins/ 并调用 /dsh_fish/api/skin 切换。" % out.name)


def main() -> int:
    root = tk.Tk()
    try:
        style = ttk.Style()
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    Studio(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
