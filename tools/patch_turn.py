"""给走动加「转身」阶段：撞边时先播 turn 动画（东张西望），播完再翻转方向。

官方 config.jsonc 对 turn 的定义是「每一项都必须是播完会翻转朝向的动画」，
所以正确用法就是：播完这个动画 -> 逻辑朝向翻转 -> 继续移动。
"""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "build" / "dsh_fish" / "main.lua"
t = P.read_text(encoding="utf-8")

# 1) set_visual 里加转身分支（播 turn 动画，不镜像）
anchor = "  local walking = APP.walk and APP.walk.moving\n"
assert anchor in t, "walking anchor"
turn_branch = """  -- 转身阶段：播皮肤包 turn 池里的动画（官方约定「播完会翻转朝向」），期间不镜像
  if APP.walk and APP.walk.phase == "turn" and ClawdPack and ClawdPack.turn and ClawdPack.turn[1] then
    local tv = ClawdPack.turn[1]
    APP.current_visual = tv
    if APP.page == "status" and APP.status_visual_loaded ~= tv then
      local tx = (APP.walk and APP.walk.x) or 80
      if swap_gif("status", tv, tx, 8) then APP.status_visual_loaded = tv end
    end
    return
  end
"""
t = t.replace(anchor, turn_branch + anchor, 1)

# 2) walk_tick 里加 turn 阶段
old_edge = """      if APP.walk.x >= WALK_MAX then APP.walk.x = WALK_MAX; APP.walk.dir = -1
        if APP.set_visual then APP.set_visual(APP.remote.state) end
      elseif APP.walk.x <= WALK_MIN then APP.walk.x = WALK_MIN; APP.walk.dir = 1
        if APP.set_visual then APP.set_visual(APP.remote.state) end
      end"""
new_edge = """      if APP.walk.x >= WALK_MAX or APP.walk.x <= WALK_MIN then
        APP.walk.x = math.max(WALK_MIN, math.min(WALK_MAX, APP.walk.x))
        -- 撞边：先播转身动画，播完再翻方向（方向此时还没翻）
        if ClawdPack and ClawdPack.turn and ClawdPack.turn[1] then
          APP.walk.phase = "turn"
          APP.walk.timer = 0
          APP.walk.moving = false
          if APP.set_visual then APP.set_visual(APP.remote.state) end
          for i = 1, #gifs do lv_obj_set_pos(gifs[i], APP.walk.x, 8) end
          return
        else
          APP.walk.dir = -APP.walk.dir
          if APP.set_visual then APP.set_visual(APP.remote.state) end
        end
      end"""
assert old_edge in t, "edge anchor"
t = t.replace(old_edge, new_edge, 1)

# 3) turn 阶段推进（插在 run 判断之前）
old_phase = "    if APP.walk.phase == \"run\" then"
new_phase = """    if APP.walk.phase == "turn" then
      APP.walk.moving = false
      if APP.walk.timer >= TURN_TICKS then
        APP.walk.dir = -APP.walk.dir        -- 播完翻转朝向
        APP.walk.phase = "run"
        APP.walk.timer = 0
        APP.walk.moving = true
        if APP.set_visual then APP.set_visual(APP.remote.state) end
      end
      for i = 1, #gifs do lv_obj_set_pos(gifs[i], APP.walk.x, 8) end
      return
    end

    if APP.walk.phase == "run" then"""
assert old_phase in t, "phase anchor"
t = t.replace(old_phase, new_phase, 1)

# 4) 常量 TURN_TICKS
old_c = "WALK_RUN_TICKS = { short = 50, normal = 100, long = 200 }"
if old_c in t:
    t = t.replace(old_c, old_c + "\nTURN_TICKS = 27   -- 10 帧 x 120ms / 45ms 每 tick，约 1.2 秒", 1)
else:
    raise SystemExit("WALK_STEP anchor missing")

P.write_text(t, encoding="utf-8", newline="\n")
print("turn phase wired into walk_tick / set_visual")

