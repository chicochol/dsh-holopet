"""移动动作改成随机挑；并去掉「事件→动作组」下拉（改用变体勾选）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "build" / "dsh_fish" / "main.lua"
WEB = ROOT / "build" / "dsh_fish" / "web.lua"

# ---------- main.lua：移动动作随机 ----------
t = MAIN.read_text(encoding="utf-8")

old_mv = """  local walking = APP.walk and APP.walk.moving
  local mv = walking and ClawdPack and ClawdPack.moves and #ClawdPack.moves > 0
             and ClawdPack.moves[1] or nil"""
new_mv = """  local walking = APP.walk and APP.walk.moving
  -- 移动动画由 walk_tick 在每次进入 run 阶段时随机挑一个，避免永远同一个
  local mv = walking and APP.walk and APP.walk.move or nil"""
assert old_mv in t, "mv anchor"
t = t.replace(old_mv, new_mv, 1)

# 进入 run 时抽一个移动动作：三处（初始、act->run、turn->run）
old_init = """    if not APP.walk.phase then
      APP.walk.phase = "run"
      APP.walk.timer = 0
      APP.walk.pause_for = 0
    end"""
new_init = """    if not APP.walk.phase then
      APP.walk.phase = "run"
      APP.walk.timer = 0
      APP.walk.pause_for = 0
      APP.walk.move = pool[math.random(1, #pool)]
    end"""
assert old_init in t, "init anchor"
t = t.replace(old_init, new_init, 1)

old_act = """        APP.walk.phase = "run"
        APP.walk.timer = 0
        APP.walk.moving = true
        if APP.set_visual then APP.set_visual(APP.remote.state) end"""
new_act = """        APP.walk.phase = "run"
        APP.walk.timer = 0
        APP.walk.moving = true
        APP.walk.move = pool[math.random(1, #pool)]
        if APP.set_visual then APP.set_visual(APP.remote.state) end"""
assert old_act in t, "act anchor"
t = t.replace(old_act, new_act, 1)

old_turn = """        APP.walk.x = APP.walk.x + APP.walk.dir * 12   -- 先离开边界，否则下一拍又撞
        APP.walk.phase = "run"
        APP.walk.timer = 0
        APP.walk.moving = true"""
new_turn = """        APP.walk.x = APP.walk.x + APP.walk.dir * 12   -- 先离开边界，否则下一拍又撞
        APP.walk.phase = "run"
        APP.walk.timer = 0
        APP.walk.moving = true
        APP.walk.move = pool[math.random(1, #pool)]"""
assert old_turn in t, "turn anchor"
t = t.replace(old_turn, new_turn, 1)

MAIN.write_text(t, encoding="utf-8", newline="\n")
print("main.lua: move animation now randomized per run")

# ---------- web.lua：去掉动作组下拉，只显示当前默认组 ----------
w = WEB.read_text(encoding="utf-8")

old_row = """<div class="erow"><div class="evname">' .. evt_zh(name) .. '<br><span class="hint">(' .. name .. ')</span></div><select class="mapSel" id="map_' .. name .. '"></select><div class="ecells" id="cells_' .. name .. '"></div><button type="button" class="more" data-ev="' .. name .. '">全部</button></div>"""
new_row = """<div class="erow"><div class="evname">' .. evt_zh(name) .. '<br><span class="hint">(' .. name .. ')</span></div><div class="evgroup" id="grp_' .. name .. '">' .. evt_zh(name) .. '</div><div class="ecells" id="cells_' .. name .. '"></div><button type="button" class="more" data-ev="' .. name .. '">全部</button></div>"""
if old_row in w:
    w = w.replace(old_row, new_row, 1)
    print("web.lua: action-group dropdown replaced with static label")
else:
    print("WARN: erow template not matched, dump around it:")
    i = w.find('class="erow"')
    print(w[max(0, i - 200):i + 500])

WEB.write_text(w, encoding="utf-8", newline="\n")
