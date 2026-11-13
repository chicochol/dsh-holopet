-- 皮肤系统：多套皮肤 + 三档速度 + 主题（颜色/字号）
-- 负责读取 skin.json、加载 assets/skins/<id>/manifest.lua、把相对文件名展开成绝对路径。

local Skin = {}

local function read_text(path)
  local getcontents = file and file.getcontents
  if not getcontents then return nil end
  local ok, value = pcall(getcontents, path)
  if ok and type(value) == "string" and #value > 0 then return value end
  return nil
end

local function decode_json(raw)
  if type(raw) ~= "string" or raw == "" then return nil end
  local codec = rawget(_G, "json") or rawget(_G, "sjson")
  if not codec or not codec.decode then return nil end
  local ok, value = pcall(codec.decode, raw)
  if ok and type(value) == "table" then return value end
  return nil
end

local function write_text(path, text)
  local putcontents = file and file.putcontents
  if putcontents then
    local ok = pcall(putcontents, path, text)
    if ok then return true end
  end
  local open, write, close = file and file.open, file and file.write, file and file.close
  if not (open and write and close) then return false end
  local fd = open(path, "w+")
  if not fd then return false end
  local ok = pcall(write, fd, text)
  pcall(close, fd)
  return ok and true or false
end

local function encode_json(value)
  local codec = rawget(_G, "json") or rawget(_G, "sjson")
  if codec and codec.encode then
    local ok, text = pcall(codec.encode, value)
    if ok and type(text) == "string" then return text end
  end
  -- 极简回退：只支持本模块用到的扁平结构
  local parts = {}
  for k, v in pairs(value) do
    if type(v) == "string" then
      parts[#parts + 1] = string.format('%q:%q', k, v)
    elseif type(v) == "number" then
      parts[#parts + 1] = string.format('%q:%s', k, tostring(v))
    elseif type(v) == "boolean" then
      parts[#parts + 1] = string.format('%q:%s', k, tostring(v))
    end
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

Skin.DEFAULT_THEME = {
  bg = "#0B1512",
  panel = "#13241C",
  track = "#223A2E",
  fg = "#F2FBF6",
  dim = "#7E9C8C",
  accent = "#4ADE80",
  warn = "#FBBF24",
  error = "#F87171",
  font_scale = 1.0,
  font_family = "console",
}

Skin.DEFAULT_STATE = {
  active = "whale",
  speed = "normal",
  theme = {},
  behavior = {
    walk_states = { "idle", "sleeping" },
    event_actions = {},
    -- 每个动作组可挂多个变体：enabled 是启用清单，walk 是允许边走边播的清单，
    -- 缺省（nil）表示「全部启用、全部不可走动」。
    variants = {
      Idle = {
        mode = "seq",
        enabled = { "idle_01.gif", "idle_02.gif", "idle_03.gif", "idle_04.gif" },
        walk = { "idle_01.gif" },
      },
    },
  },
  display = {},
  hidden = {},
  -- 音效：事件名 -> 音效名（assets/sounds/<name>.wav）；nil/off 表示不播
  sounds = {
    UserPromptSubmit = "tap",
    Stop = "success",
    Error = "error",
    PermissionRequest = "notify",
    SessionStart = "chime",
  },
  -- 应用音量 0..1（播放时按 PCM 幅度缩放）
  sound_volume = 0.8,
    move_speed = {},
  walk = { pace = "normal", pause = "normal", len = "normal" },
}

function Skin.state_path(APP_DIR)
  return APP_DIR .. "/skin.json"
end

function Skin.load_state(APP_DIR)
  local saved = decode_json(read_text(Skin.state_path(APP_DIR))) or {}
  local state = {
    active = type(saved.active) == "string" and saved.active or Skin.DEFAULT_STATE.active,
    speed = type(saved.speed) == "string" and saved.speed or Skin.DEFAULT_STATE.speed,
    theme = {},
    skins = type(saved.skins) == "table" and saved.skins or nil,
    hidden = type(saved.hidden) == "table" and saved.hidden or {},
    behavior = {},
    display = {},
    sounds = (type(saved.sounds) == "table" and next(saved.sounds))
      and saved.sounds or Skin.DEFAULT_STATE.sounds,
    sound_volume = tonumber(saved.sound_volume) or Skin.DEFAULT_STATE.sound_volume,
    walk = (function()
      local w = type(saved.walk) == "table" and saved.walk or {}
      local d = Skin.DEFAULT_STATE.walk
      return {
        pace = type(w.pace) == "string" and w.pace or d.pace,
        pause = type(w.pause) == "string" and w.pause or d.pause,
        len = type(w.len) == "string" and w.len or d.len,
      }
    end)(),
  }
  -- behavior / display 必须读回来，否则管理页改的走动、事件映射、变体、显示项一重启就全丢
  local saved_behavior = type(saved.behavior) == "table" and saved.behavior or {}
  local default_behavior = Skin.DEFAULT_STATE.behavior
  state.behavior.walk_states =
    type(saved_behavior.walk_states) == "table" and saved_behavior.walk_states or default_behavior.walk_states
  state.behavior.event_actions =
    type(saved_behavior.event_actions) == "table" and saved_behavior.event_actions or {}
  state.behavior.variants =
    type(saved_behavior.variants) == "table" and saved_behavior.variants or default_behavior.variants
  state.display = type(saved.display) == "table" and saved.display or {}
  for key, value in pairs(Skin.DEFAULT_THEME) do
    local override = type(saved.theme) == "table" and saved.theme[key] or nil
    if type(override) == type(value) then
      state.theme[key] = override
    else
      state.theme[key] = value
    end
  end
  return state
end

function Skin.save_state(APP_DIR, state)
  local payload = {
    active = state.active,
    speed = state.speed,
    theme = state.theme,
    skins = state.skins,
    behavior = state.behavior,
    display = state.display,
    hidden = state.hidden or {},
    sounds = state.sounds or {},
  walk = { pace = state.walk and state.walk.pace or "normal", pause = state.walk and state.walk.pause or "normal", len = state.walk and state.walk.len or "normal" },
    sound_volume = state.sound_volume or Skin.DEFAULT_STATE.sound_volume,
  }
  return write_text(Skin.state_path(APP_DIR), encode_json(payload))
end

function Skin.pack_dir(APP_DIR, id)
  return APP_DIR .. "/assets/skins/" .. id
end

function Skin.load_pack(APP_DIR, id)
  local dir = Skin.pack_dir(APP_DIR, id)
  local ok, manifest = pcall(dofile, dir .. "/manifest.lua")
  if not ok or type(manifest) ~= "table" then return nil, dir end
  return manifest, dir
end

-- 把 manifest 里的相对文件名展开成 { events = { Idle = { "<dir>/<speed>/idle_01.gif" } } }
local function pack_moves(list, dir, speed)
  local out = {}
  for i, m in ipairs(type(list) == "table" and list or {}) do
    local f = m.file or m[1]
    if type(f) == "string" then
      out[i] = { path = dir .. "/" .. speed .. "/" .. f, base = f,
                 lead = tonumber(m.lead) or 2.0, tail = tonumber(m.tail) or 2.0,
                 facing = m.facing or "right", speed = tonumber(m.speed) or 2.0 }
    end
  end
  return out
end

local function pack_turn(list, dir, speed)
  local out = {}
  for i, f in ipairs(type(list) == "table" and list or {}) do
    if type(f) == "string" then out[i] = dir .. "/" .. speed .. "/" .. f end
  end
  return out
end

function Skin.resolve(manifest, dir, speed)
  local chosen = speed
  if type(manifest.speeds) == "table" and not manifest.speeds[chosen] then
    chosen = manifest.default_speed or "normal"
  end
  -- 皮肤包可能只提供一档（如 pc2005 只有 normal），缺档时回退到 normal
  local base = dir .. "/" .. tostring(chosen) .. "/"
  do
    local probe
    for _, files in pairs(manifest.events or {}) do
      if type(files) == "table" and type(files[1]) == "string" then probe = files[1] break end
    end
    if probe and not file.exists(base .. probe) then
      local fallback = dir .. "/normal/"
      if file.exists(fallback .. probe) then base = fallback; chosen = "normal" end
    end
  end
  local out = { events = {}, weather = {}, speed = chosen, id = manifest.id, name = manifest.name,
        labels = manifest.labels or {},
        categories = manifest.categories or {},
    moves = pack_moves(manifest.moves, dir, speed),
    turn = pack_turn(manifest.turn, dir, speed) }
  -- 移动动画池：每项记下朝向（left/right），设备端据此决定要不要用镜像版
  if type(manifest.moves) == "table" then
    for _, m in ipairs(manifest.moves) do
      if type(m) == "table" and type(m.file) == "string" then
        out.moves[#out.moves + 1] = { path = base .. m.file, base = m.file,
          lead = tonumber(m.lead) or 2.0, tail = tonumber(m.tail) or 2.0,
          facing = m.facing or "right" }
      end
    end
  end
  if type(manifest.turn) == "table" then
    for _, f in ipairs(manifest.turn) do
      if type(f) == "string" then out.turn[#out.turn + 1] = base .. f end
    end
  end
  for event, files in pairs(manifest.events or {}) do
    local list = {}
    if type(files) == "table" then
      for _, item in ipairs(files) do
        if type(item) == "string" then list[#list + 1] = base .. item end
      end
    end
    if #list > 0 then out.events[event] = list end
  end
  return out
end

-- 可用皮肤清单：优先读 state.skins；缺失时用内置兜底表
Skin.BUILTIN_SKINS = { "whale", "chibi-blue" }

function Skin.list(APP_DIR, state)
  local ids, seen = {}, {}
  local function push(id)
    if type(id) == "string" and #id > 0 and not seen[id] then
      seen[id] = true
      ids[#ids + 1] = id
    end
  end

  local hidden = {}
  if type(state) == "table" and type(state.hidden) == "table" then
    for _, id in ipairs(state.hidden) do hidden[id] = true end
  end

  -- 扫描 assets/skins/ 下所有带 manifest.lua 的子目录：用户把皮肤包拷进设备就会自动出现
  local ok, entries = pcall(file.listdir, APP_DIR .. "/assets/skins")
  if ok and type(entries) == "table" then
    local names = {}
    for _, entry in ipairs(entries) do
      -- 设备固件的 file.listdir 返回的是 { name=..., ... } 表数组，不是字符串数组
      local name = type(entry) == "string" and entry
        or (type(entry) == "table" and (entry.name or entry[1]))
      if type(name) == "string" and #name > 0 and not hidden[name] then
        names[#names + 1] = name
      end
    end
    table.sort(names)
    for _, name in ipairs(names) do
      if Skin.load_pack(APP_DIR, name) then push(name) end
    end
  end

  -- 显式清单里声明过但没扫到的也补上（兼容旧配置）
  local source = type(state) == "table" and state.skins or nil
  if type(source) == "table" then
    for _, id in ipairs(source) do
      if not hidden[id] then push(id) end
    end
  end

  -- 一个都没有时退回内置两套
  if #ids == 0 then
    for _, id in ipairs(Skin.BUILTIN_SKINS) do
      if not hidden[id] and Skin.load_pack(APP_DIR, id) then ids[#ids + 1] = id end
    end
  end

  local result = {}
  for _, id in ipairs(ids) do
    local manifest = Skin.load_pack(APP_DIR, id)
    if manifest then
      local count = 0
      for _ in pairs(manifest.events or {}) do count = count + 1 end
      result[#result + 1] = {
        id = id,
        name = manifest.name or id,
        name_en = manifest.name_en or manifest.name or id,
        events = count,
        speeds = manifest.speeds or {},
        default_speed = manifest.default_speed or "normal",
      }
    end
  end
  return result
end

function Skin.parse_color(text, fallback)
  if type(text) ~= "string" then return fallback end
  local hex = text:match("^#?(%x%x%x%x%x%x)$")
  if not hex then return fallback end
  return tonumber(hex:sub(1, 2), 16) * 65536 + tonumber(hex:sub(3, 4), 16) * 256 + tonumber(hex:sub(5, 6), 16)
end

return Skin
