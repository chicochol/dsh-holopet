local APP_DIR = "/sd/apps/dsh_fish"
local APP_ID = nil
if app and app.current then
  local current = app.current()
  if current and type(current.id) == "string" and current.id ~= "" then
    APP_ID = current.id
    APP_DIR = "/sd/apps/" .. APP_ID
  end
end

if file and file.exists and not file.exists(APP_DIR .. "/config.lua") then
  for _, dir in ipairs({
    "/sd/apps/dsh_fish",
    "dsh_fish/package",
    "dsh_fish",
  }) do
    if file.exists(dir .. "/config.lua") then APP_DIR = dir; break end
  end
end

local APP_SLUG = APP_ID
  or APP_DIR:match("/sd/apps/([^/]+)")
  or APP_DIR:match("^(dsh_?fish)")
  or "dsh_fish"

local config = dofile(APP_DIR .. "/config.lua")
local I18n = dofile(APP_DIR .. "/i18n.lua")
local FontMetrics = dofile(APP_DIR .. "/font_metrics.lua")
local DshClient = dofile(APP_DIR .. "/dsh_client.lua")
local HoloWeb = dofile(APP_DIR .. "/web.lua")
local WeatherClient = dofile(APP_DIR .. "/weather_client.lua")
local Timezone = dofile(APP_DIR .. "/timezone.lua")
local Skin = dofile(APP_DIR .. "/skin.lua")
local Sound = dofile(APP_DIR .. "/sound.lua")
local SKIN_STATE = Skin.load_state(APP_DIR)
pcall(Sound.set_volume, (SKIN_STATE and SKIN_STATE.sound_volume) or 0.8)
local SKIN_MANIFEST, SKIN_DIR = Skin.load_pack(APP_DIR, SKIN_STATE.active)
local ClawdPack
if SKIN_MANIFEST then
  ClawdPack = Skin.resolve(SKIN_MANIFEST, SKIN_DIR, SKIN_STATE.speed)
else
  -- 回退：老的单皮肤布局
  ClawdPack = dofile(APP_DIR .. "/assets/whale/manifest.lua")
end
local ConsoleText = nil
local console_loader_error = ""
do
  local ok, module_or_error = pcall(dofile, APP_DIR .. "/console_text.lua")
  if ok and type(module_or_error) == "table" then
    ConsoleText = module_or_error
  else
    console_loader_error = "console renderer load failed: " .. tostring(module_or_error)
  end
end

local function rebase_asset_paths(value)
  if type(value) == "string" then
    return (value:gsub("^/sd/apps/dsh_fish/", APP_DIR .. "/"))
  end
  if type(value) == "table" then
    for key, item in pairs(value) do
      value[key] = rebase_asset_paths(item)
    end
  end
  return value
end

rebase_asset_paths(ClawdPack)

local APP_KEY = "HOLO_PET_APP"
local SETTINGS_PATH = "/sd/apps/settings.json"
local SYSTEM_UI_LANG = I18n.read(SETTINGS_PATH)
local UI_LANGUAGE_MODE = I18n.normalize_mode(config.language)
local REQUESTED_UI_LANG = I18n.resolve(UI_LANGUAGE_MODE, SYSTEM_UI_LANG)
local UI_LANG = REQUESTED_UI_LANG
local UI_ZH = I18n.is_zh(UI_LANG)
local function T(en, zh)
  return UI_ZH and zh or en
end
local TEMP_UNIT = nil

local previous = rawget(_G, APP_KEY)
if previous and previous.stop then
  pcall(function() previous.stop("reload") end)
end

local APP = {
  VERSION = "1.4.1",
  running = true,
  timer = nil,
  controller_timer = nil,
  controller_buttons = 0,
  client = nil,
  weather = nil,
  web = nil,
  reload_timer = nil,
  connection_detail = "",
  routes = {},
  current_visual = nil,
  status_visual_loaded = nil,
  gif_active = { status = 1, weather = 1, session = 1 },
  gif_sources = { status = {}, weather = {}, session = {} },
  gif_swaps = 0,
  current_visual_group = "Idle",
  event_visual_index = 1,
  visual_indices = {},
  last_event_signature = "",
  page = "status",
  idle_index = 1,
  next_idle_ms = 0,
  idle_delay_ms = 0,
  clock_text = "--:--",
  last_clock_check_ms = -1000,
  last_clock_retry_ms = -30000,
  next_weather_ms = 0,
  last_weather_sync_slot = "",
  weather_status = "waiting",
  weather_sync_text = "--:--",
  last_weather_updated_ms = 0,
  session_meme_loaded = nil,
  session_meme_index = 1,
  next_session_meme_ms = 0,
  last_page_switch_ms = -1000,
  last_gc_ms = -1000,
  timing = {
    chat_start_ms = 0,
    state_start_ms = 0,
    last_chat_elapsed_ms = 0,
    has_completed_chat = false,
  },
  usage = {
    weekly_percent = nil,
    weekly_reset_text = "--/--",
  },
  console_renderer = nil,
  font_error = "",
  ui = {},
  remote = {
    state = "idle",
    event = "AwaitingPrompt",
    project = "holocubic",
    tool = "",
    session = "",
    model = "",
    effort = "",
    context = {},
    last_update_ms = 0,
    transient_until = 0,
    subagents = {},
    subagent_count = 0,
    connected = false,
    source = "bridge",
    activity = {
      history = {},
      tool_count = 0,
      error_count = 0,
      subagent_count = 0,
    },
  },
}

_G[APP_KEY] = APP

local W, H = 320, 240
local MAIN = (rawget(_G, "LV_PART_MAIN") or 0) | (rawget(_G, "LV_STATE_DEFAULT") or 0)
local FALLBACK_FONT_9 = rawget(_G, "LV_FONT_MONTSERRAT_10") or 9
local FALLBACK_FONT_10 = rawget(_G, "LV_FONT_MONTSERRAT_10") or 10
local FALLBACK_FONT_12 = rawget(_G, "LV_FONT_MONTSERRAT_12") or 12
local FALLBACK_FONT_14 = rawget(_G, "LV_FONT_MONTSERRAT_14") or 14
local FALLBACK_FONT_16 = rawget(_G, "LV_FONT_MONTSERRAT_16") or 16
local FALLBACK_FONT_28 = rawget(_G, "LV_FONT_MONTSERRAT_28") or FALLBACK_FONT_16
APP.font_handles = {}
local ALIGN_LEFT = rawget(_G, "LV_TEXT_ALIGN_LEFT") or 0
local ALIGN_CENTER = rawget(_G, "LV_TEXT_ALIGN_CENTER") or 1
local ALIGN_RIGHT = rawget(_G, "LV_TEXT_ALIGN_RIGHT") or 2
local FLAG_SCROLLABLE = rawget(_G, "LV_OBJ_FLAG_SCROLLABLE")
local FLAG_OVERFLOW = rawget(_G, "LV_OBJ_FLAG_OVERFLOW_VISIBLE")
local FLAG_HIDDEN = rawget(_G, "LV_OBJ_FLAG_HIDDEN")
local CANVAS_FMT = rawget(_G, "LV_IMG_CF_TRUE_COLOR") or rawget(_G, "LV_COLOR_FORMAT_NATIVE")

local C = {
  -- True RGB565 black removes the warm cast from the backlit LCD background.
  bg = 0x0B1512,
  panel = 0x13241C,
  line = 0x2A4034,
  rust = 0x4ADE80,
  peach = 0xA8C2B5,
  cream = 0xF2FBF6,
  dim = 0x7E9C8C,
  track = 0x223A2E,
  mint = 0x4ADE80,
  warn = 0xFBBF24,
  error = 0xF87171,
}

-- 用户主题：skin.json 里的 theme 覆盖默认配色。LVGL 样式在对象创建时就定死，
-- 所以颜色改动需要重启应用才生效（管理页会提示）。
do
  local theme = type(SKIN_STATE) == "table" and type(SKIN_STATE.theme) == "table" and SKIN_STATE.theme or {}
  local mapping = {
    { from = "bg", to = "bg" },
    { from = "panel", to = "panel" },
    { from = "track", to = "track" },
    { from = "fg", to = "cream" },
    { from = "dim", to = "dim" },
    { from = "accent", to = "rust" },
    { from = "accent", to = "mint" },
    { from = "warn", to = "warn" },
    { from = "error", to = "error" },
  }
  for _, m in ipairs(mapping) do
    local text = theme[m.from]
    if type(text) == "string" and #text > 0 then
      C[m.to] = Skin.parse_color(text, C[m.to])
    end
  end
  APP.theme = theme
end

-- Select the packaged typeface from the normalized system language. The
-- compositor produces the same RGB565 canvases for both profiles.
local FONT_PROFILE = UI_ZH and {
  family = "AIDA Noto Sans SC",
  path = APP_DIR .. "/font/aida_noto_sans_sc.ttf",
} or {
  family = "Clawd Console",
  path = APP_DIR .. "/font/clawd_console.ttf",
}
local CONSOLE = ConsoleText and ConsoleText.open and ConsoleText.open({
  family = FONT_PROFILE.family,
  module_path = APP_DIR .. "/modules/aida_font.so",
  font_path = FONT_PROFILE.path,
}) or nil
APP.console_renderer = CONSOLE
APP.font_error = CONSOLE and tostring(CONSOLE.error or "") or console_loader_error

-- A firmware font cannot display Chinese. If the packaged Chinese renderer is
-- unavailable, keep the UI readable by using the English strings and expose
-- the real error through the WebUI status endpoint.
if UI_ZH and (not CONSOLE or not CONSOLE.ready) then
  UI_LANG = "en"
  UI_ZH = false
end
APP.language = UI_LANG
APP.requested_language = REQUESTED_UI_LANG
APP.system_language = SYSTEM_UI_LANG
APP.language_mode = UI_LANGUAGE_MODE
TEMP_UNIT = T("C", "℃")
APP.connection_detail = T("waiting for bridge", "等待桥接服务")

-- Keep Chinese and English line boxes optically equivalent. The vector
-- renderer consumes render_size, while size remains the public UI role.
-- 字号档位来自皮肤主题，范围 0.80–1.30，字形由 stb_truetype 每次栅格化，改完立即生效。
local FONT_SCALE = tonumber(APP.theme and APP.theme.font_scale) or 1
if FONT_SCALE < 0.8 then FONT_SCALE = 0.8 elseif FONT_SCALE > 1.3 then FONT_SCALE = 1.3 end
local function font_role(size, fallback)
  return FontMetrics.role(math.max(6, size * FONT_SCALE), fallback, UI_ZH)
end
local FONT_9 = font_role(9.5, FALLBACK_FONT_9)
local FONT_10 = font_role(10, FALLBACK_FONT_10)
local FONT_12 = font_role(12, FALLBACK_FONT_12)
local FONT_14 = font_role(14, FALLBACK_FONT_14)
local FONT_16 = font_role(16, FALLBACK_FONT_16)
local FONT_28 = font_role(28, FALLBACK_FONT_28)

local IDLE_VISUALS = ClawdPack.events.Idle or {}

-- 角色朝左走时改用水平镜像素材，否则看起来像"倒着走"。
local MIRROR_IDLE = {}
do
  for i = 1, #IDLE_VISUALS do
    local mirrored = (IDLE_VISUALS[i]:gsub("/assets/skins/([^/]+)/", "/assets/skins/%1/mirror/"))
    if file.exists(mirrored) then MIRROR_IDLE[i] = mirrored end
  end
end

-- 显示项开关：管理页可逐项隐藏，配置存 skin.json 的 display 字段。
-- 默认全部可见；渲染末尾统一应用一次，保证优先级高于各页面内部的状态隐藏逻辑。
local function set_hidden(obj, hidden)
  if not obj then return end
  if not obj or not FLAG_HIDDEN then return end
  if hidden and lv_obj_add_flag then
    pcall(function() lv_obj_add_flag(obj, FLAG_HIDDEN) end)
  elseif not hidden and lv_obj_clear_flag then
    pcall(function() lv_obj_clear_flag(obj, FLAG_HIDDEN) end)
  end
end

local DISPLAY_GROUPS = {
  a_title = { "title" },
  a_live = { "live" },
  a_clock = { "clock" },
  a_gif = { "viewport" },
  a_state = { "state_segment", "state", "state_arrow" },
  a_project = { "project" },
  a_source = { "source" },
  a_timers = { "chat_segment", "state_time_segment" },
  a_usage = { "usage_week", "usage_track", "usage_fill", "usage_reset" },
  b_title = { "session_title" },
  b_clock = { "session_clock" },
  b_log = { "session_log_panel" },
  b_state = { "session_state_segment", "session_state", "session_tool" },
  b_timeline = { "session_timeline" },
  b_meme = { "session_meme_panel" },
  b_context = { "session_context_panel" },
}

local function apply_display()
  if type(APP.ui) ~= "table" then return end
  local cfg = type(SKIN_STATE) == "table" and type(SKIN_STATE.display) == "table" and SKIN_STATE.display or {}
  for key, fields in pairs(DISPLAY_GROUPS) do
    local hidden = cfg[key] == false
    for _, name in ipairs(fields) do
      local obj = APP.ui[name]
      if obj then set_hidden(obj, hidden) end
    end
  end
end

local IDLE_MIN_MINUTES = 2
local IDLE_MAX_MINUTES = 5
local SESSION_MEME_MIN_MS = 60 * 1000
local SESSION_MEME_MAX_MS = 150 * 1000
local PAGE_SWITCH_COOLDOWN_MS = 1000
local WEATHER_FALLBACK_REFRESH_MS = 15 * 60 * 1000
local DEFAULT_TIMEZONE = "CST-8"
local LOCAL_TIMEZONE = Timezone.read_settings(SETTINGS_PATH, DEFAULT_TIMEZONE)
local NTP_SERVER = "ntp.aliyun.com"
local NTP_RETRY_MS = 30 * 1000

local STATE_LABELS = {
  idle = T("IDLE", "待命"),
  thinking = T("THINKING", "思考"),
  working = T("WORKING", "工作"),
  building = T("SUBAGENT", "子任务"),
  notification = T("APPROVAL", "待确认"),
  done = T("DONE", "完成"),
  error = T("ERROR", "错误"),
  sleeping = T("SLEEPING", "休眠"),
}

local EVENT_LABELS = {
  SessionStart = T("WAKE", "唤醒"),
  UserPromptSubmit = T("LISTEN", "接收"),
  PreToolUse = T("RUN", "执行"),
  PermissionRequest = T("APPROVAL", "确认"),
  PostToolUse = T("CHECK", "检查"),
  AgentResume = T("THINKING", "思考"),
  PreCompact = T("PACKING", "整理"),
  PostCompact = T("COMPACT", "压缩"),
  SubagentStart = T("DELEGATE", "分派"),
  SubagentStop = T("MERGED", "合并"),
  Stop = T("DONE", "完成"),
}

local EVENT_ALIASES = {
  ["event_msg:task_started"] = "UserPromptSubmit",
  ["event_msg:user_message"] = "UserPromptSubmit",
  ["event_msg:task_complete"] = "Stop",
  ["response_item:function_call"] = "PreToolUse",
  ["response_item:custom_tool_call"] = "PreToolUse",
  ["response_item:web_search_call"] = "PreToolUse",
}

local MEME_DIR = APP_DIR .. "/assets/whale/meme/"
-- B 页左下角的「陪看」角色直接用当前皮肤包里的 Idle 动画——皮肤包里一定有素材，
-- 老的 assets/whale/meme/*.gif 梗图不再作为必需项。
local SESSION_MEMES = {}
do
  local idle = (ClawdPack and ClawdPack.events and ClawdPack.events.Idle) or {}
  for i = 1, #idle do
    -- B 页角色格只有 96x92，优先用专门缩好的小图，没有才回退全尺寸
    local small = (idle[i]:gsub("/assets/skins/([^/]+)/", "/assets/skins/%1/meme/"))
    local path = file.exists(small) and small or idle[i]
    SESSION_MEMES[#SESSION_MEMES + 1] = { path = path, label = "" }
  end
end

local function refresh_language_tables()
  local states = {
    idle = T("IDLE", "待命"), thinking = T("THINKING", "思考"),
    working = T("WORKING", "工作"), building = T("SUBAGENT", "子任务"),
    notification = T("APPROVAL", "待确认"), done = T("DONE", "完成"),
    error = T("ERROR", "错误"), sleeping = T("SLEEPING", "休眠"),
  }
  for key, value in pairs(states) do STATE_LABELS[key] = value end

  local events = {
    SessionStart = T("WAKE", "唤醒"), UserPromptSubmit = T("LISTEN", "接收"),
    PreToolUse = T("RUN", "执行"), PermissionRequest = T("APPROVAL", "确认"),
    PostToolUse = T("CHECK", "检查"), AgentResume = T("THINKING", "思考"),
    PreCompact = T("PACKING", "整理"), PostCompact = T("COMPACT", "压缩"),
    SubagentStart = T("DELEGATE", "分派"), SubagentStop = T("MERGED", "合并"),
    Stop = T("DONE", "完成"),
  }
  for key, value in pairs(events) do EVENT_LABELS[key] = value end

  local meme_labels = {
    T("DEAL WITH IT", "稳住能赢"), T("THIS IS FINE", "问题不大"),
    T("NOT ME", "不是我干的"), T("SHIP FIESTA", "发布派对"),
    T("SURFING IT", "浪里调试"), T("KEYBOARD SMASH", "键盘风暴"),
    T("POPCORN MODE", "吃瓜模式"), T("BONK", "敲一下"),
    T("STONKS", "一路上涨"), T("PANIC BUTTON", "紧急按钮"),
  }
  for index, value in ipairs(meme_labels) do
    if SESSION_MEMES[index] then SESSION_MEMES[index].label = value end
  end
end

local ALLOWED_STATES = {
  idle = true, thinking = true, working = true, building = true,
  notification = true, done = true, error = true, sleeping = true,
}

local function now_ms()
  if millis then
    local ok, value = pcall(millis)
    if ok and type(value) == "number" then return value end
  end
  return 0
end

pcall(function()
  local seed = now_ms()
  if rtctime and rtctime.get then
    local epoch = rtctime.get()
    if type(epoch) == "number" then seed = seed + epoch end
  end
  math.randomseed(seed % 2147483647)
  math.random()
  math.random()
end)

local function random_idle_delay_ms()
  local minutes = 3
  local ok, value = pcall(math.random, IDLE_MIN_MINUTES, IDLE_MAX_MINUTES)
  if ok and type(value) == "number" then minutes = value end
  return minutes * 60 * 1000
end

local function random_session_meme_delay_ms()
  local ok, value = pcall(math.random, SESSION_MEME_MIN_MS, SESSION_MEME_MAX_MS)
  return ok and tonumber(value) or SESSION_MEME_MIN_MS
end

local function random_visual_index(group, count)
  count = tonumber(count) or 0
  if count <= 0 then return 1 end
  if count == 1 then
    APP.visual_indices[group] = 1
    return 1
  end

  local previous = APP.visual_indices[group]
  local ok_random, index = pcall(math.random, 1, count)
  index = ok_random and tonumber(index) or 1
  if previous and index == previous then
    local ok_step, step = pcall(math.random, 1, count - 1)
    step = ok_step and tonumber(step) or 1
    index = ((index - 1 + step) % count) + 1
  end

  APP.visual_indices[group] = index
  if group == "Idle" then
    APP.idle_index = index
  else
    APP.event_visual_index = index
  end
  return index
end

local clip = I18n.clip

local function compositor_align(value)
  if value == ALIGN_RIGHT then return 2 end
  if value == ALIGN_CENTER then return 1 end
  return 0
end

local function weather_city_text(state)
  for _, value in ipairs({ state and state.city, state and state.address }) do
    local text = tostring(value or "")
    if text ~= "" and (UI_ZH or not text:find("[\128-\255]")) then return text end
  end
  return T("WEATHER", "天气")
end

local raw_lv_label_create = lv_label_create
local raw_lv_label_set_text = lv_label_set_text
local raw_lv_obj_create = lv_obj_create
local raw_lv_obj_set_size = lv_obj_set_size
local raw_lv_obj_set_pos = lv_obj_set_pos
local raw_lv_obj_set_style_bg_color = lv_obj_set_style_bg_color
local raw_lv_obj_set_style_text_color = lv_obj_set_style_text_color
local raw_lv_obj_set_style_text_font = lv_obj_set_style_text_font
local raw_lv_obj_set_style_text_align = lv_obj_set_style_text_align
local raw_lv_obj_set_style_text_opa = lv_obj_set_style_text_opa
local OBJECT_BG = {}
local OBJECT_BG_OPA = {}
local OBJECT_PARENT = {}
local TEXT_CHILDREN = {}
local ALL_TEXT_TOKENS = {}
local render_console_text

-- 在容器最上层补一圈边框：LVGL 先画父对象边框、再画子对象，
-- 子对象贴着边缘时会把边框盖住，所以最后再叠一个只有边框的透明层。
local function add_border_overlay(parent, w, h, color, opa)
  if not parent or not lv_obj_create then return nil end
  local o = lv_obj_create(parent)
  pcall(lv_obj_set_size, o, w, h)
  pcall(lv_obj_set_pos, o, 0, 0)
  -- 设备固件的可用 API 不齐（比如 lv_obj_set_style_pad_all 可能没有），
  -- 这里每个样式调用都单独 pcall，任何一个缺失都不会中断 UI 构建。
  if lv_obj_set_style_bg_opa then pcall(lv_obj_set_style_bg_opa, o, 0, MAIN) end
  if lv_obj_set_style_radius then pcall(lv_obj_set_style_radius, o, 0, MAIN) end
  if lv_obj_set_style_pad_all then pcall(lv_obj_set_style_pad_all, o, 0, MAIN) end
  if lv_obj_set_style_border_width then pcall(lv_obj_set_style_border_width, o, 1, MAIN) end
  if lv_obj_set_style_border_color then pcall(lv_obj_set_style_border_color, o, color, MAIN) end
  if lv_obj_set_style_border_opa then pcall(lv_obj_set_style_border_opa, o, opa or 200, MAIN) end
  local flag = rawget(_G, "LV_OBJ_FLAG_CLICKABLE")
  if flag and lv_obj_clear_flag then
    pcall(lv_obj_clear_flag, o, flag)
  end
  return o
end

local function is_console_text(obj)
  return type(obj) == "table" and obj._clawd_console_text == true
end

local function blend_color(foreground, background, opacity)
  opacity = math.max(0, math.min(255, tonumber(opacity) or 255))
  if opacity >= 255 then return tonumber(foreground) or 0 end
  local inverse = 255 - opacity
  foreground, background = tonumber(foreground) or 0, tonumber(background) or 0
  local fr, fg, fb = (foreground >> 16) & 0xFF, (foreground >> 8) & 0xFF, foreground & 0xFF
  local br, bg, bb = (background >> 16) & 0xFF, (background >> 8) & 0xFF, background & 0xFF
  local r = math.floor((fr * opacity + br * inverse + 127) / 255)
  local g = math.floor((fg * opacity + bg * inverse + 127) / 255)
  local b = math.floor((fb * opacity + bb * inverse + 127) / 255)
  return (r << 16) | (g << 8) | b
end

local function fallback_text_token(token)
  if token.native then return token.native end
  if token.canvas and lv_obj_del then pcall(lv_obj_del, token.canvas) end
  token.canvas = nil
  local native = raw_lv_label_create(token.parent)
  token.native = native
  raw_lv_obj_set_size(native, token.width or 1, token.height or 1)
  raw_lv_obj_set_pos(native, token.x or 0, token.y or 0)
  raw_lv_obj_set_style_text_color(native, token.color or C.cream, MAIN)
  raw_lv_obj_set_style_text_font(native, token.fallback_font or FALLBACK_FONT_12, MAIN)
  if raw_lv_obj_set_style_text_opa then raw_lv_obj_set_style_text_opa(native, 255, MAIN) end
  if raw_lv_obj_set_style_text_align then
    raw_lv_obj_set_style_text_align(native, token.align or ALIGN_LEFT, MAIN)
  end
  raw_lv_label_set_text(native, tostring(token.text or ""))
  return native
end

local function disable_console(reason)
  APP.font_error = tostring(reason or "console renderer disabled")
  if CONSOLE then CONSOLE:disable(APP.font_error) end
  for _, token in ipairs(ALL_TEXT_TOKENS) do fallback_text_token(token) end
end

local function lv_label_create(parent)
  if not CONSOLE or not CONSOLE.ready then return raw_lv_label_create(parent) end
  local token = {
    _clawd_console_text = true,
    parent = parent,
    width = 1,
    height = 1,
    x = 0,
    y = 0,
    size = 12,
    y_offset = 0,
    color = C.cream,
    background = C.bg,
    align = ALIGN_LEFT,
    fallback_font = FALLBACK_FONT_12,
    text = nil,
    canvas = nil,
    native = nil,
  }
  ALL_TEXT_TOKENS[#ALL_TEXT_TOKENS + 1] = token
  TEXT_CHILDREN[parent] = TEXT_CHILDREN[parent] or {}
  TEXT_CHILDREN[parent][#TEXT_CHILDREN[parent] + 1] = token
  return token
end

local function lv_obj_create(parent)
  local obj = raw_lv_obj_create(parent)
  OBJECT_PARENT[obj] = parent
  return obj
end

local function lv_obj_set_size(obj, width, height)
  if not is_console_text(obj) then return raw_lv_obj_set_size(obj, width, height) end
  obj.width, obj.height = math.max(1, math.floor(width or 1)), math.max(1, math.floor(height or 1))
  if obj.native then return raw_lv_obj_set_size(obj.native, obj.width, obj.height) end
end

local function lv_obj_set_pos(obj, x, y)
  if not is_console_text(obj) then return raw_lv_obj_set_pos(obj, x, y) end
  obj.x, obj.y = math.floor(x or 0), math.floor(y or 0)
  if obj.native then return raw_lv_obj_set_pos(obj.native, obj.x, obj.y) end
  if obj.canvas then return raw_lv_obj_set_pos(obj.canvas, obj.x, obj.y + (obj.y_offset or 0)) end
end

local function lv_obj_set_style_text_color(obj, color, part)
  if not obj then return end
  if not is_console_text(obj) then return raw_lv_obj_set_style_text_color(obj, color, part) end
  local next_color = tonumber(color) or C.cream
  if obj.color == next_color then return true end
  obj.color = next_color
  if obj.native then return raw_lv_obj_set_style_text_color(obj.native, obj.color, part) end
  if obj.text ~= nil then return render_console_text(obj) end
end

local function lv_obj_set_style_bg_color(obj, color, part)
  if not obj then return end
  local parent_background = OBJECT_BG[OBJECT_PARENT[obj]] or C.bg
  local next_background = blend_color(color, parent_background, OBJECT_BG_OPA[obj] or 255)
  if OBJECT_BG[obj] == next_background then return true end
  OBJECT_BG[obj] = next_background
  local result = raw_lv_obj_set_style_bg_color(obj, color, part)
  for _, token in ipairs(TEXT_CHILDREN[obj] or {}) do
    token.background = OBJECT_BG[obj]
    if token.text ~= nil and not token.native then render_console_text(token) end
  end
  return result
end

render_console_text = function(token)
  if token.native then
    raw_lv_label_set_text(token.native, tostring(token.text or ""))
    return true
  end
  if not CONSOLE or not CONSOLE.ready then
    fallback_text_token(token)
    return false
  end
  token.background = OBJECT_BG[token.parent] or token.background or C.bg
  if not token.canvas then
    token.canvas = CONSOLE:create_canvas(token.parent, token.width, token.height)
    if not token.canvas then
      disable_console(CONSOLE.error ~= "" and CONSOLE.error or "console canvas create failed")
      return false
    end
    raw_lv_obj_set_pos(token.canvas, token.x, token.y + (token.y_offset or 0))
    if lv_obj_set_style_bg_opa then pcall(lv_obj_set_style_bg_opa, token.canvas, 0, MAIN) end
  end
  local data, raster_error = CONSOLE:raster(token.text, token.width, token.height,
    token.render_size or token.size, token.color, token.background, compositor_align(token.align))
  if not data then
    disable_console(raster_error)
    return false
  end
  local ok, blit_error = CONSOLE:blit(token.canvas, data, token.width, token.height)
  if not ok then
    disable_console(blit_error)
    return false
  end
  APP.font_error = ""
  return true
end

local function set_bg(obj, color, opa, radius)
  if not obj then return end
  OBJECT_BG_OPA[obj] = opa or 255
  lv_obj_set_style_bg_color(obj, color, MAIN)
  lv_obj_set_style_bg_opa(obj, opa or 255, MAIN)
  lv_obj_set_style_border_width(obj, 0, MAIN)
  lv_obj_set_style_radius(obj, radius or 0, MAIN)
  if lv_obj_set_style_pad_all then lv_obj_set_style_pad_all(obj, 0, MAIN) end
end

local function style_text(obj, color, font, align)
  if not obj then return end
  -- C 表理论上不会缺键，但主题覆盖/降级路径上出现过 nil 色值，这里兜底，
  -- 避免 raw_lv_obj_set_style_text_color 收到 nil 直接抛错。
  color = tonumber(color) or C.cream or 0xF2FBF6
  local font_role = type(font) == "table" and font or { size = 12, fallback = font }
  if is_console_text(obj) then
    obj.color = tonumber(color) or C.cream
    obj.size = tonumber(font_role.size) or 12
    obj.render_size = tonumber(font_role.render_size) or obj.size
    obj.y_offset = tonumber(font_role.y_offset) or 0
    obj.fallback_font = font_role.fallback or FALLBACK_FONT_12
    obj.align = align or ALIGN_LEFT
    if obj.native then
      raw_lv_obj_set_style_text_color(obj.native, obj.color, MAIN)
      raw_lv_obj_set_style_text_font(obj.native, obj.fallback_font, MAIN)
      if raw_lv_obj_set_style_text_opa then raw_lv_obj_set_style_text_opa(obj.native, 255, MAIN) end
      if raw_lv_obj_set_style_text_align then raw_lv_obj_set_style_text_align(obj.native, obj.align, MAIN) end
    elseif obj.text ~= nil then
      render_console_text(obj)
    end
    if obj.canvas then raw_lv_obj_set_pos(obj.canvas, obj.x, obj.y + obj.y_offset) end
    return
  end
  raw_lv_obj_set_style_text_color(obj, color, MAIN)
  raw_lv_obj_set_style_text_font(obj, font_role.fallback or FALLBACK_FONT_12, MAIN)
  if raw_lv_obj_set_style_text_opa then raw_lv_obj_set_style_text_opa(obj, 255, MAIN) end
  if raw_lv_obj_set_style_text_align then raw_lv_obj_set_style_text_align(obj, align or ALIGN_LEFT, MAIN) end
end

local function set_text(obj, value)
  if not obj then return end
  local text = tostring(value or "")
  if is_console_text(obj) then
    if obj.text == text then return end
    obj.text = text
    render_console_text(obj)
  else
    raw_lv_label_set_text(obj, text)
  end
end


local root = lv_scr_act()
lv_obj_clean(root)
set_bg(root, C.bg, 255, 0)
if CONSOLE and CONSOLE.ready then
  local ok, validation_error = CONSOLE:validate(root)
  if not ok then
    disable_console(validation_error or CONSOLE.error)
    if UI_ZH then
      UI_LANG, UI_ZH, TEMP_UNIT = "en", false, "C"
      APP.language = UI_LANG
      APP.connection_detail = T("waiting for bridge", "等待桥接服务")
      refresh_language_tables()
    end
  end
end

APP.ui.status_page = lv_obj_create(root)
lv_obj_set_size(APP.ui.status_page, W, H)
lv_obj_set_pos(APP.ui.status_page, 0, 0)
set_bg(APP.ui.status_page, C.bg, 255, 0)
if FLAG_SCROLLABLE and lv_obj_clear_flag then pcall(function() lv_obj_clear_flag(APP.ui.status_page, FLAG_SCROLLABLE) end) end

APP.ui.title = lv_label_create(APP.ui.status_page)
lv_obj_set_size(APP.ui.title, 190, 20)
lv_obj_set_pos(APP.ui.title, 10, 3)
style_text(APP.ui.title, C.rust, FONT_14, ALIGN_LEFT)
set_text(APP.ui.title, T("DSH // idle", "DSH // 待命"))

APP.ui.clock = lv_label_create(APP.ui.status_page)
lv_obj_set_size(APP.ui.clock, 58, 18)
lv_obj_set_pos(APP.ui.clock, 253, 5)
style_text(APP.ui.clock, C.peach, FONT_12, ALIGN_RIGHT)
set_text(APP.ui.clock, APP.clock_text)

APP.ui.live = lv_label_create(APP.ui.status_page)
lv_obj_set_size(APP.ui.live, 47, 18)
lv_obj_set_pos(APP.ui.live, 202, 5)
style_text(APP.ui.live, C.dim, FONT_12, ALIGN_RIGHT)
set_text(APP.ui.live, T("WAIT", "等待"))

-- ClawdMoji status GIFs are generated at 160 x 160 for native device playback.
APP.ui.viewport = lv_obj_create(APP.ui.status_page)
lv_obj_set_size(APP.ui.viewport, 320, 180)
lv_obj_set_pos(APP.ui.viewport, 0, 20)
set_bg(APP.ui.viewport, C.bg, 255, 0)
if FLAG_SCROLLABLE and lv_obj_clear_flag then
  pcall(function() lv_obj_clear_flag(APP.ui.viewport, FLAG_SCROLLABLE) end)
end
if FLAG_OVERFLOW and lv_obj_clear_flag then
  pcall(function() lv_obj_clear_flag(APP.ui.viewport, FLAG_OVERFLOW) end)
end
if lv_obj_set_style_clip_corner then
  pcall(function() lv_obj_set_style_clip_corner(APP.ui.viewport, true, MAIN) end)
end

APP.ui.status_gifs = {}
for i = 1, 2 do
  local gif = lv_gif_create(APP.ui.viewport)
  lv_obj_set_pos(gif, 80, 8)
  set_hidden(gif, i ~= 1)
  APP.ui.status_gifs[i] = gif
end

-- 待机时角色在屏幕里左右散步：viewport 宽 320、角色 160，可走 160px。
APP.walk = { x = 80, dir = 1, idle = 0 }
local WALK_MIN, WALK_MAX, WALK_STEP = 0, 160, 2

-- 走动节奏的可调档位（设置页「行为」里可改）
WALK_PACE = { slow = 3, normal = 2, fast = 1 }
WALK_PAUSE_CHANCE = { never = 0, rare = 0.004, normal = 0.010, often = 0.030 }
WALK_PAUSE_LEN = { short = { 40, 80 }, normal = { 60, 140 }, long = { 120, 260 } }
-- 跑多久才停（帧数，45ms/帧）：短 2.2s / 中 4.5s / 长 9s
WALK_RUN_TICKS = { short = 50, normal = 100, long = 200 }
TURN_TICKS = 27   -- 10 帧 x 120ms / 45ms 每 tick，约 1.2 秒
local function walk_tick()
  local ok, err = pcall(function()
    if APP.page ~= "status" then return end
    local gifs = APP.ui.status_gifs
    if not gifs or #gifs == 0 then return end

    -- 只有皮肤包带移动动画时才让它走；其它皮肤保持原地播事件动作
    local pool = ClawdPack and ClawdPack.moves
    if type(pool) ~= "table" or #pool == 0 then
      APP.walk.moving = false
      APP.walk.phase = nil
      for i = 1, #gifs do lv_obj_set_pos(gifs[i], APP.walk.x, 8) end
      return
    end

    -- 只有待命（含休眠）才四处走动；其它事件原地播动作，回到待命再恢复移动
    local cur_state = (APP.remote and APP.remote.state) or "idle"
    if cur_state ~= "idle" and cur_state ~= "sleeping" then
      APP.walk.moving = false
      APP.walk.phase = nil
      for i = 1, #gifs do lv_obj_set_pos(gifs[i], APP.walk.x, 8) end
      return
    end

    local wk = (type(SKIN_STATE) == "table" and type(SKIN_STATE.walk) == "table") and SKIN_STATE.walk or {}
    local run_len = WALK_RUN_TICKS[wk.len or "normal"] or WALK_RUN_TICKS.normal
    local plen = WALK_PAUSE_LEN[wk.len or "normal"] or WALK_PAUSE_LEN.normal
    local pace = WALK_PACE[wk.pace or "normal"] or WALK_PACE.normal

    if not APP.walk.phase then
      APP.walk.phase = "run"; APP.walk.run_started = nil
      APP.walk.timer = 0
      APP.walk.pause_for = 0
      APP.walk.move = pool[math.random(1, #pool)]
    end
    APP.walk.timer = APP.walk.timer + 1

    if APP.walk.phase == "turn" then
      APP.walk.moving = false
      if APP.walk.timer >= TURN_TICKS then
        APP.walk.dir = -APP.walk.dir        -- 播完翻转朝向
        APP.walk.x = APP.walk.x + APP.walk.dir * 12   -- 先离开边界，否则下一拍又撞
        APP.walk.phase = "run"; APP.walk.run_started = nil
        APP.walk.timer = 0
        APP.walk.moving = true
        APP.walk.move = pool[math.random(1, #pool)]
        APP.walk.move = pool[math.random(1, #pool)]
        if APP.set_visual then APP.set_visual(APP.remote.state) end
      end
      for i = 1, #gifs do lv_obj_set_pos(gifs[i], APP.walk.x, 8) end
      return
    end

    if APP.walk.phase == "run" then
      APP.walk.moving = true
      -- 平移速度（像素/拍），可在「行为」页按动作单独调
      local mv = APP.walk.move or {}
      local sp = (type(SKIN_STATE) == "table" and type(SKIN_STATE.move_speed) == "table") and SKIN_STATE.move_speed or {}
      local MOVE_SPEED = { ["ceshen-jizao-pao.gif"] = tonumber(sp["ceshen-jizao-pao.gif"]) or 5,
                           ["pangxie-zoulu.gif"] = tonumber(sp["pangxie-zoulu.gif"]) or 2,
                           ["kaixin-xiaopao.gif"] = tonumber(sp["kaixin-xiaopao.gif"]) or 1 }
      local step = MOVE_SPEED[mv.base] or tonumber(mv.speed) or WALK_STEP
      -- 静止段判定用真实时间（tmr.now 是微秒），不要用 tick 计数，否则和 GIF 播放对不齐
      local nf = 24
      local dur = 120
      if type(SKIN_STATE) == "table" then
        if SKIN_STATE.speed == "slow" then dur = 150 elseif SKIN_STATE.speed == "fast" then dur = 90 end
      end
      local total = nf * dur
      local now = tmr.now() / 1000
      if not APP.walk.run_started then APP.walk.run_started = now end
      local phase_ms = (now - APP.walk.run_started) % total
      local lead_ms = (tonumber(mv.lead) or 0) / 10 * total
      local tail_ms = (tonumber(mv.tail) or 0) / 10 * total
      local hold = (phase_ms < lead_ms) or (phase_ms > (total - tail_ms))
      if (not hold) and APP.walk.timer % pace == 0 then
        APP.walk.x = APP.walk.x + APP.walk.dir * step
      end
      if APP.walk.x >= WALK_MAX or APP.walk.x <= WALK_MIN then
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
      end
      if APP.walk.timer >= run_len then
        APP.walk.phase = "act"
        APP.walk.timer = 0
        APP.walk.pause_for = math.random(plen[1], plen[2])
        APP.walk.moving = false
        if APP.set_visual then APP.set_visual(APP.remote.state) end
      end
    else
      APP.walk.moving = false
      if APP.walk.timer >= APP.walk.pause_for then
        APP.walk.phase = "run"; APP.walk.run_started = nil
        APP.walk.timer = 0
        APP.walk.moving = true
        if APP.set_visual then APP.set_visual(APP.remote.state) end
      end
    end

    for i = 1, #gifs do lv_obj_set_pos(gifs[i], APP.walk.x, 8) end
  end)
  if not ok then pcall(file.putcontents, APP_DIR .. "/walkerr.txt", tostring(err)) end
end

APP.walk_timer = tmr.create()
APP.walk_timer:alarm(45, tmr.ALARM_AUTO, walk_tick)

APP.ui.panel = lv_obj_create(APP.ui.status_page)
lv_obj_set_size(APP.ui.panel, 320, 44)
lv_obj_set_pos(APP.ui.panel, 0, 196)
set_bg(APP.ui.panel, C.bg, 255, 0)
lv_obj_set_style_border_width(APP.ui.panel, 0, MAIN)
lv_obj_set_style_border_color(APP.ui.panel, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.panel, 190, MAIN)

APP.ui.state_segment = lv_obj_create(APP.ui.panel)
lv_obj_set_size(APP.ui.state_segment, 102, 21)
lv_obj_set_pos(APP.ui.state_segment, 0, 0)
set_bg(APP.ui.state_segment, C.cream, 255, 0)

APP.ui.state = lv_label_create(APP.ui.state_segment)
lv_obj_set_size(APP.ui.state, 91, 18)
lv_obj_set_pos(APP.ui.state, 6, 1)
style_text(APP.ui.state, C.bg, FONT_14, ALIGN_LEFT)

APP.ui.state_arrow = lv_label_create(APP.ui.panel)
lv_obj_set_size(APP.ui.state_arrow, 10, 19)
lv_obj_set_pos(APP.ui.state_arrow, 103, 0)
style_text(APP.ui.state_arrow, C.cream, FONT_14, ALIGN_LEFT)
set_text(APP.ui.state_arrow, ">")

APP.ui.project = lv_label_create(APP.ui.panel)
lv_obj_set_size(APP.ui.project, 132, 17)
lv_obj_set_pos(APP.ui.project, 114, 3)
style_text(APP.ui.project, C.rust, FONT_12, ALIGN_LEFT)

APP.ui.source = lv_label_create(APP.ui.panel)
lv_obj_set_size(APP.ui.source, 47, 15)
lv_obj_set_pos(APP.ui.source, 262, 4)
style_text(APP.ui.source, C.dim, FONT_10, ALIGN_RIGHT)

APP.ui.chat_segment = lv_obj_create(APP.ui.panel)
lv_obj_set_size(APP.ui.chat_segment, 58, 21)
lv_obj_set_pos(APP.ui.chat_segment, 0, 23)
set_bg(APP.ui.chat_segment, C.line, 150, 0)

APP.ui.chat_timer = lv_label_create(APP.ui.chat_segment)
lv_obj_set_size(APP.ui.chat_timer, 54, 14)
lv_obj_set_pos(APP.ui.chat_timer, 3, 3)
style_text(APP.ui.chat_timer, C.cream, FONT_10, ALIGN_LEFT)

APP.ui.state_time_segment = lv_obj_create(APP.ui.panel)
lv_obj_set_size(APP.ui.state_time_segment, 58, 21)
lv_obj_set_pos(APP.ui.state_time_segment, 58, 23)
set_bg(APP.ui.state_time_segment, C.rust, 210, 0)

APP.ui.state_timer = lv_label_create(APP.ui.state_time_segment)
lv_obj_set_size(APP.ui.state_timer, 54, 14)
lv_obj_set_pos(APP.ui.state_timer, 3, 3)
style_text(APP.ui.state_timer, C.bg, FONT_10, ALIGN_LEFT)

APP.ui.usage_week = lv_label_create(APP.ui.panel)
lv_obj_set_size(APP.ui.usage_week, 55, 14)
lv_obj_set_pos(APP.ui.usage_week, 120, 27)
style_text(APP.ui.usage_week, C.peach, FONT_10, ALIGN_LEFT)

APP.ui.usage_track = lv_obj_create(APP.ui.panel)
lv_obj_set_size(APP.ui.usage_track, 84, 4)
lv_obj_set_pos(APP.ui.usage_track, 178, 32)
set_bg(APP.ui.usage_track, C.line, 210, 0)

APP.ui.usage_fill = lv_obj_create(APP.ui.usage_track)
lv_obj_set_size(APP.ui.usage_fill, 1, 4)
lv_obj_set_pos(APP.ui.usage_fill, 0, 0)
set_bg(APP.ui.usage_fill, C.mint, 255, 0)

APP.ui.usage_reset = lv_label_create(APP.ui.panel)
lv_obj_set_size(APP.ui.usage_reset, 52, 14)
lv_obj_set_pos(APP.ui.usage_reset, 264, 27)
style_text(APP.ui.usage_reset, C.dim, FONT_10, ALIGN_RIGHT)
APP.ui.panel_border = add_border_overlay(APP.ui.panel, 320, 44, C.line, 190)

-- Weather instrument: one native 128 x 128 ClawdMoji scene plus a compact
-- terminal rail. Gesture hints are intentionally omitted.
APP.ui.weather_page = lv_obj_create(root)
lv_obj_set_size(APP.ui.weather_page, W, H)
lv_obj_set_pos(APP.ui.weather_page, 0, 0)
set_bg(APP.ui.weather_page, C.bg, 255, 0)
if FLAG_SCROLLABLE and lv_obj_clear_flag then pcall(function() lv_obj_clear_flag(APP.ui.weather_page, FLAG_SCROLLABLE) end) end
set_hidden(APP.ui.weather_page, true)

APP.ui.weather_title = lv_label_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_title, 235, 18)
lv_obj_set_pos(APP.ui.weather_title, 9, 4)
style_text(APP.ui.weather_title, C.rust, FONT_14, ALIGN_LEFT)
set_text(APP.ui.weather_title, T("WX // SYNC", "天气 // 同步"))

APP.ui.weather_clock = lv_label_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_clock, 58, 18)
lv_obj_set_pos(APP.ui.weather_clock, 253, 5)
style_text(APP.ui.weather_clock, C.peach, FONT_12, ALIGN_RIGHT)
set_text(APP.ui.weather_clock, APP.clock_text)

APP.ui.weather_art_panel = lv_obj_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_art_panel, 132, 132)
lv_obj_set_pos(APP.ui.weather_art_panel, 9, 23)
set_bg(APP.ui.weather_art_panel, C.panel, 255, 0)
lv_obj_set_style_border_width(APP.ui.weather_art_panel, 2, MAIN)
lv_obj_set_style_border_color(APP.ui.weather_art_panel, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.weather_art_panel, 220, MAIN)

APP.ui.weather_gifs = {}
for i = 1, 2 do
  local gif = lv_gif_create(APP.ui.weather_art_panel)
  lv_obj_set_pos(gif, 0, 0)
  set_hidden(gif, i ~= 1)
  APP.ui.weather_gifs[i] = gif
end

APP.ui.weather_info_panel = lv_obj_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_info_panel, 166, 132)
lv_obj_set_pos(APP.ui.weather_info_panel, 145, 23)
set_bg(APP.ui.weather_info_panel, C.panel, 255, 0)
lv_obj_set_style_border_width(APP.ui.weather_info_panel, 1, MAIN)
lv_obj_set_style_border_color(APP.ui.weather_info_panel, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.weather_info_panel, 220, MAIN)

APP.ui.weather_condition_segment = lv_obj_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_condition_segment, 104, 22)
lv_obj_set_pos(APP.ui.weather_condition_segment, 0, 0)
set_bg(APP.ui.weather_condition_segment, C.warn, 255, 0)

APP.ui.weather_condition = lv_label_create(APP.ui.weather_condition_segment)
lv_obj_set_size(APP.ui.weather_condition, 96, 18)
lv_obj_set_pos(APP.ui.weather_condition, 5, 2)
style_text(APP.ui.weather_condition, C.bg, FONT_14, ALIGN_LEFT)
set_text(APP.ui.weather_condition, T("SYNCING", "同步中"))

APP.ui.weather_condition_arrow = lv_label_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_condition_arrow, 10, 20)
lv_obj_set_pos(APP.ui.weather_condition_arrow, 105, 1)
style_text(APP.ui.weather_condition_arrow, C.warn, FONT_14, ALIGN_LEFT)
set_text(APP.ui.weather_condition_arrow, ">")

APP.ui.weather_source = lv_label_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_source, 45, 14)
lv_obj_set_pos(APP.ui.weather_source, 116, 4)
style_text(APP.ui.weather_source, C.dim, FONT_10, ALIGN_RIGHT)
set_text(APP.ui.weather_source, T("WAIT", "等待"))

APP.ui.weather_temp = lv_label_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_temp, 76, 38)
lv_obj_set_pos(APP.ui.weather_temp, 7, 28)
style_text(APP.ui.weather_temp, C.cream, FONT_28, ALIGN_LEFT)
set_text(APP.ui.weather_temp, "--" .. TEMP_UNIT)

APP.ui.weather_feels = lv_label_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_feels, 76, 15)
lv_obj_set_pos(APP.ui.weather_feels, 7, 68)
style_text(APP.ui.weather_feels, C.dim, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_feels, T("FEELS ", "体感 ") .. "--" .. TEMP_UNIT)

APP.ui.weather_hum_segment = lv_obj_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_hum_segment, 76, 26)
lv_obj_set_pos(APP.ui.weather_hum_segment, 84, 29)
set_bg(APP.ui.weather_hum_segment, C.line, 140, 0)

APP.ui.weather_humidity = lv_label_create(APP.ui.weather_hum_segment)
lv_obj_set_size(APP.ui.weather_humidity, 68, 15)
lv_obj_set_pos(APP.ui.weather_humidity, 4, 6)
style_text(APP.ui.weather_humidity, C.cream, FONT_12, ALIGN_LEFT)
set_text(APP.ui.weather_humidity, T("HUM --%", "湿度 --%"))

APP.ui.weather_gust_segment = lv_obj_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_gust_segment, 76, 26)
lv_obj_set_pos(APP.ui.weather_gust_segment, 84, 58)
set_bg(APP.ui.weather_gust_segment, C.line, 90, 0)

APP.ui.weather_gust = lv_label_create(APP.ui.weather_gust_segment)
lv_obj_set_size(APP.ui.weather_gust, 68, 15)
lv_obj_set_pos(APP.ui.weather_gust, 4, 6)
style_text(APP.ui.weather_gust, C.peach, FONT_12, ALIGN_LEFT)
set_text(APP.ui.weather_gust, T("GUST --", "阵风 --"))

APP.ui.weather_updated = lv_label_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_updated, 150, 13)
lv_obj_set_pos(APP.ui.weather_updated, 7, 88)
style_text(APP.ui.weather_updated, C.dim, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_updated, T("WAITING FOR FORECAST", "等待天气数据"))

APP.ui.weather_cmd_segment = lv_obj_create(APP.ui.weather_info_panel)
lv_obj_set_size(APP.ui.weather_cmd_segment, 164, 27)
lv_obj_set_pos(APP.ui.weather_cmd_segment, 1, 104)
set_bg(APP.ui.weather_cmd_segment, C.bg, 255, 0)
lv_obj_set_style_border_width(APP.ui.weather_cmd_segment, 1, MAIN)
lv_obj_set_style_border_color(APP.ui.weather_cmd_segment, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.weather_cmd_segment, 170, MAIN)

APP.ui.weather_wind = lv_label_create(APP.ui.weather_cmd_segment)
lv_obj_set_size(APP.ui.weather_wind, 154, 15)
lv_obj_set_pos(APP.ui.weather_wind, 5, 6)
style_text(APP.ui.weather_wind, C.mint, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_wind, T("WIND -- GUST --", "风 -- 阵风 --"))

APP.ui.weather_alert = lv_obj_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_alert, 302, 27)
lv_obj_set_pos(APP.ui.weather_alert, 9, 158)
set_bg(APP.ui.weather_alert, C.line, 220, 0)

APP.ui.weather_alert_text = lv_label_create(APP.ui.weather_alert)
lv_obj_set_size(APP.ui.weather_alert_text, 292, 17)
lv_obj_set_pos(APP.ui.weather_alert_text, 5, 5)
style_text(APP.ui.weather_alert_text, C.cream, FONT_12, ALIGN_LEFT)
set_text(APP.ui.weather_alert_text, T("RAIN --% @--:--  GUST --", "降雨 --% @--:--  阵风 --"))

APP.ui.weather_chart_panel = lv_obj_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_chart_panel, 181, 50)
lv_obj_set_pos(APP.ui.weather_chart_panel, 9, 187)
set_bg(APP.ui.weather_chart_panel, C.panel, 255, 0)
lv_obj_set_style_border_width(APP.ui.weather_chart_panel, 1, MAIN)
lv_obj_set_style_border_color(APP.ui.weather_chart_panel, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.weather_chart_panel, 180, MAIN)

APP.ui.weather_chart_rain = lv_label_create(APP.ui.weather_chart_panel)
lv_obj_set_size(APP.ui.weather_chart_rain, 74, 12)
lv_obj_set_pos(APP.ui.weather_chart_rain, 3, 0)
style_text(APP.ui.weather_chart_rain, 0x5BB7D9, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_chart_rain, T("R 0.0mm", "雨 0.0mm"))

APP.ui.weather_chart_temp = lv_label_create(APP.ui.weather_chart_panel)
lv_obj_set_size(APP.ui.weather_chart_temp, 98, 12)
lv_obj_set_pos(APP.ui.weather_chart_temp, 79, 0)
style_text(APP.ui.weather_chart_temp, C.peach, FONT_10, ALIGN_RIGHT)
set_text(APP.ui.weather_chart_temp, T("T ", "温 ") .. "-- > --" .. TEMP_UNIT)

if lv_canvas_create then
  if CANVAS_FMT then
    APP.ui.weather_chart_canvas = lv_canvas_create(APP.ui.weather_chart_panel, 179, 25, CANVAS_FMT)
  else
    APP.ui.weather_chart_canvas = lv_canvas_create(APP.ui.weather_chart_panel, 179, 25)
  end
  lv_obj_set_pos(APP.ui.weather_chart_canvas, 1, 12)
end

APP.ui.weather_chart_hours = {}
for i = 1, 4 do
  local label = lv_label_create(APP.ui.weather_chart_panel)
  lv_obj_set_size(label, 42, 11)
  lv_obj_set_pos(label, 3 + (i - 1) * 43, 38)
  style_text(label, C.dim, FONT_10, i == 4 and ALIGN_RIGHT or ALIGN_LEFT)
  set_text(label, "--")
  APP.ui.weather_chart_hours[i] = label
end

APP.ui.weather_tomorrow_panel = lv_obj_create(APP.ui.weather_page)
lv_obj_set_size(APP.ui.weather_tomorrow_panel, 118, 50)
lv_obj_set_pos(APP.ui.weather_tomorrow_panel, 193, 187)
set_bg(APP.ui.weather_tomorrow_panel, C.bg, 255, 0)
lv_obj_set_style_border_width(APP.ui.weather_tomorrow_panel, 1, MAIN)
lv_obj_set_style_border_color(APP.ui.weather_tomorrow_panel, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.weather_tomorrow_panel, 180, MAIN)

APP.ui.weather_tomorrow_segment = lv_obj_create(APP.ui.weather_tomorrow_panel)
lv_obj_set_size(APP.ui.weather_tomorrow_segment, 39, 17)
lv_obj_set_pos(APP.ui.weather_tomorrow_segment, 0, 0)
set_bg(APP.ui.weather_tomorrow_segment, C.rust, 255, 0)

APP.ui.weather_tomorrow_tag = lv_label_create(APP.ui.weather_tomorrow_segment)
lv_obj_set_size(APP.ui.weather_tomorrow_tag, 35, 13)
lv_obj_set_pos(APP.ui.weather_tomorrow_tag, 3, 2)
style_text(APP.ui.weather_tomorrow_tag, C.bg, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_tomorrow_tag, T("TMR", "明日"))

APP.ui.weather_tomorrow_kind = lv_label_create(APP.ui.weather_tomorrow_panel)
lv_obj_set_size(APP.ui.weather_tomorrow_kind, 73, 13)
lv_obj_set_pos(APP.ui.weather_tomorrow_kind, 42, 2)
style_text(APP.ui.weather_tomorrow_kind, C.peach, FONT_10, ALIGN_RIGHT)
set_text(APP.ui.weather_tomorrow_kind, T("SYNC", "同步"))

APP.ui.weather_tomorrow_temp = lv_label_create(APP.ui.weather_tomorrow_panel)
lv_obj_set_size(APP.ui.weather_tomorrow_temp, 110, 13)
lv_obj_set_pos(APP.ui.weather_tomorrow_temp, 4, 19)
style_text(APP.ui.weather_tomorrow_temp, C.cream, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_tomorrow_temp, T("T ", "温 ") .. "-- > --" .. TEMP_UNIT)

APP.ui.weather_tomorrow_rain = lv_label_create(APP.ui.weather_tomorrow_panel)
lv_obj_set_size(APP.ui.weather_tomorrow_rain, 110, 13)
lv_obj_set_pos(APP.ui.weather_tomorrow_rain, 4, 34)
style_text(APP.ui.weather_tomorrow_rain, C.dim, FONT_10, ALIGN_LEFT)
set_text(APP.ui.weather_tomorrow_rain, T("R--% 0.0mm G--", "雨--% 0.0mm 风--"))

-- Session instrument: the left rail is a compact live trace; the right side
-- reserves a native 128 x 128 frame for Clawd's meme loops.
APP.ui.session_page = lv_obj_create(root)
lv_obj_set_size(APP.ui.session_page, W, H)
lv_obj_set_pos(APP.ui.session_page, 0, 0)
set_bg(APP.ui.session_page, C.bg, 255, 0)
if FLAG_SCROLLABLE and lv_obj_clear_flag then pcall(function() lv_obj_clear_flag(APP.ui.session_page, FLAG_SCROLLABLE) end) end
set_hidden(APP.ui.session_page, true)

APP.ui.session_title = lv_label_create(APP.ui.session_page)
lv_obj_set_size(APP.ui.session_title, 220, 18)
lv_obj_set_pos(APP.ui.session_title, 9, 4)
style_text(APP.ui.session_title, C.rust, FONT_14, ALIGN_LEFT)
set_text(APP.ui.session_title, T("SESSION // LIVE", "会话 // 实时"))

APP.ui.session_clock = lv_label_create(APP.ui.session_page)
lv_obj_set_size(APP.ui.session_clock, 58, 18)
lv_obj_set_pos(APP.ui.session_clock, 253, 5)
style_text(APP.ui.session_clock, C.peach, FONT_12, ALIGN_RIGHT)
set_text(APP.ui.session_clock, APP.clock_text)

APP.ui.session_log_panel = lv_obj_create(APP.ui.session_page)
lv_obj_set_size(APP.ui.session_log_panel, 312, 110)
lv_obj_set_pos(APP.ui.session_log_panel, 4, 22)
set_bg(APP.ui.session_log_panel, C.panel, 255, 0)
lv_obj_set_style_border_width(APP.ui.session_log_panel, 0, MAIN)
lv_obj_set_style_border_color(APP.ui.session_log_panel, C.rust, MAIN)
lv_obj_set_style_border_opa(APP.ui.session_log_panel, 200, MAIN)

APP.ui.session_project = lv_label_create(APP.ui.session_log_panel)
lv_obj_set_size(APP.ui.session_project, 150, 14)
lv_obj_set_pos(APP.ui.session_project, 4, 2)
style_text(APP.ui.session_project, C.rust, FONT_10, ALIGN_LEFT)
set_text(APP.ui.session_project, T("MODEL --", "模型 --"))

APP.ui.session_model = lv_label_create(APP.ui.session_log_panel)
lv_obj_set_size(APP.ui.session_model, 150, 14)
lv_obj_set_pos(APP.ui.session_model, 156, 2)
style_text(APP.ui.session_model, C.rust, FONT_10, ALIGN_RIGHT)
set_text(APP.ui.session_model, "")

APP.ui.session_state_segment = lv_obj_create(APP.ui.session_log_panel)
lv_obj_set_size(APP.ui.session_state_segment, 310, 26)
lv_obj_set_pos(APP.ui.session_state_segment, 0, 16)
set_bg(APP.ui.session_state_segment, C.rust, 255, 0)

APP.ui.session_state = lv_label_create(APP.ui.session_state_segment)
lv_obj_set_size(APP.ui.session_state, 110, 18)
lv_obj_set_pos(APP.ui.session_state, 5, 4)
style_text(APP.ui.session_state, C.bg, FONT_12, ALIGN_LEFT)
set_text(APP.ui.session_state, T("IDLE", "待命"))

APP.ui.session_tool = lv_label_create(APP.ui.session_state_segment)
lv_obj_set_size(APP.ui.session_tool, 190, 15)
lv_obj_set_pos(APP.ui.session_tool, 115, 6)
style_text(APP.ui.session_tool, C.bg, FONT_10, ALIGN_RIGHT)
set_text(APP.ui.session_tool, T("awaiting", "等待中"))

APP.ui.session_timeline = {}
for i = 1, 5 do
  local row = lv_label_create(APP.ui.session_log_panel)
  lv_obj_set_size(row, 298, 12)
  lv_obj_set_pos(row, 6, 44 + (i - 1) * 12)
  style_text(row, C.dim, FONT_10, ALIGN_LEFT)
  set_text(row, i == 1 and T("> waiting for events", "> 等待事件") or "|")
  APP.ui.session_timeline[i] = row
end
APP.ui.session_log_border = add_border_overlay(APP.ui.session_log_panel, 312, 110, C.line, 200)

APP.ui.session_meme_panel = lv_obj_create(APP.ui.session_page)
lv_obj_set_size(APP.ui.session_meme_panel, 96, 92)
lv_obj_set_pos(APP.ui.session_meme_panel, 4, 136)
set_bg(APP.ui.session_meme_panel, C.panel, 255, 0)
lv_obj_set_style_border_width(APP.ui.session_meme_panel, 2, MAIN)
lv_obj_set_style_border_color(APP.ui.session_meme_panel, C.rust, MAIN)
lv_obj_set_style_border_opa(APP.ui.session_meme_panel, 230, MAIN)

APP.ui.session_gifs = {}
for i = 1, 2 do
  local gif = lv_gif_create(APP.ui.session_meme_panel)
  lv_obj_set_size(gif, 88, 88)   -- 固定缩略尺寸，否则 lv_gif 会按首帧原图 160x160 撑破格子
  lv_obj_set_pos(gif, 4, 2)
  set_hidden(gif, i ~= 1)
  APP.ui.session_gifs[i] = gif
end

APP.ui.session_context_panel = lv_obj_create(APP.ui.session_page)
lv_obj_set_size(APP.ui.session_context_panel, 212, 92)
lv_obj_set_pos(APP.ui.session_context_panel, 104, 136)
set_bg(APP.ui.session_context_panel, C.bg, 255, 0)
lv_obj_set_style_border_width(APP.ui.session_context_panel, 0, MAIN)
lv_obj_set_style_border_color(APP.ui.session_context_panel, C.rust, MAIN)
lv_obj_set_style_border_opa(APP.ui.session_context_panel, 190, MAIN)

APP.ui.session_context_tag = lv_obj_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_context_tag, 39, 18)
lv_obj_set_pos(APP.ui.session_context_tag, 0, 0)
set_bg(APP.ui.session_context_tag, C.rust, 255, 0)

APP.ui.session_context_tag_text = lv_label_create(APP.ui.session_context_tag)
lv_obj_set_size(APP.ui.session_context_tag_text, 35, 14)
lv_obj_set_pos(APP.ui.session_context_tag_text, 3, 2)
style_text(APP.ui.session_context_tag_text, C.bg, FONT_10, ALIGN_LEFT)
set_text(APP.ui.session_context_tag_text, T("CTX", "上下文"))

APP.ui.session_context_percent = lv_label_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_context_percent, 160, 14)
lv_obj_set_pos(APP.ui.session_context_percent, 44, 2)
style_text(APP.ui.session_context_percent, C.peach, FONT_10, ALIGN_RIGHT)
set_text(APP.ui.session_context_percent, "--.-%")

APP.ui.session_context_track = lv_obj_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_context_track, 200, 6)
lv_obj_set_pos(APP.ui.session_context_track, 6, 20)
set_bg(APP.ui.session_context_track, C.track, 190, 0)

APP.ui.session_context_fill = lv_obj_create(APP.ui.session_context_track)
lv_obj_set_size(APP.ui.session_context_fill, 1, 6)
lv_obj_set_pos(APP.ui.session_context_fill, 0, 0)
set_bg(APP.ui.session_context_fill, C.rust, 255, 0)

APP.ui.session_context_tokens = lv_label_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_context_tokens, 200, 10)
lv_obj_set_pos(APP.ui.session_context_tokens, 6, 30)
style_text(APP.ui.session_context_tokens, C.dim, FONT_10, ALIGN_LEFT)
set_text(APP.ui.session_context_tokens, T("-- / -- TOK", "-- / -- 词"))
set_hidden(APP.ui.session_context_tokens, true)

-- tokens 细分：两列三行（本轮/总计、未缓存输入/输出、缓存读取/命中率）
local metric_specs = {
  { key = "session_m_turn", x = 6, y = 32, tag = T("TURN ", "本轮 ") },
  { key = "session_m_task", x = 108, y = 32, tag = T("TASK ", "总计 ") },
  { key = "session_m_in", x = 6, y = 46, tag = T("IN ", "未缓存 ") },
  { key = "session_m_out", x = 108, y = 46, tag = T("OUT ", "输出 ") },
  { key = "session_m_cr", x = 6, y = 60, tag = T("CRC ", "缓存读 ") },
  { key = "session_m_hit", x = 108, y = 60, tag = T("HIT ", "命中 ") },
}
for _, spec in ipairs(metric_specs) do
  local label = lv_label_create(APP.ui.session_context_panel)
  lv_obj_set_size(label, 100, 11)
  lv_obj_set_pos(label, spec.x, spec.y)
  style_text(label, C.dim, FONT_9, ALIGN_LEFT)
  set_text(label, spec.tag .. "--")
  APP.ui[spec.key] = label
end

local function peak_eta_text()
  local hh, mm = tostring(APP.clock_text or ""):match("^(%d+):(%d+)$")
  if not hh then return "-> --" end
  local now = tonumber(hh) * 60 + tonumber(mm)
  local marks = { 9 * 60, 12 * 60, 14 * 60, 18 * 60, 24 * 60 }
  local target = 24 * 60
  for i = 1, #marks do
    if marks[i] > now then target = marks[i] break end
  end
  local left = target - now
  if left <= 0 then return "-> 0m" end
  local h = math.floor(left / 60)
  local m = left % 60
  if h > 0 then return string.format("-> %dh%02dm", h, m) end
  return string.format("-> %dm", m)
end

APP.ui.session_peak_eta = lv_label_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_peak_eta, 110, 11)
lv_obj_set_pos(APP.ui.session_peak_eta, 96, 71)
style_text(APP.ui.session_peak_eta, C.dim, FONT_9, ALIGN_RIGHT)
set_text(APP.ui.session_peak_eta, "-> --")

-- 峰谷刻度：整条代表 24h，黄色 = 峰时（09-12 / 14-18），蓝色 = 谷时，小白点指当前时刻
APP.ui.session_peak_track = lv_obj_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_peak_track, 200, 4)
lv_obj_set_pos(APP.ui.session_peak_track, 6, 84)
set_bg(APP.ui.session_peak_track, 0x3B82F6, 200, 0)
APP.ui.session_peak_peaks = {}
for _, seg in ipairs({ { 75, 25 }, { 116, 34 } }) do
  local bar = lv_obj_create(APP.ui.session_peak_track)
  lv_obj_set_size(bar, seg[2], 4)
  lv_obj_set_pos(bar, seg[1], 0)
  set_bg(bar, C.warn, 255, 0)
  APP.ui.session_peak_peaks[#APP.ui.session_peak_peaks + 1] = bar
end
APP.ui.session_peak_arrow = lv_obj_create(APP.ui.session_context_panel)
lv_obj_set_size(APP.ui.session_peak_arrow, 2, 6)
lv_obj_set_pos(APP.ui.session_peak_arrow, 6, 79)
set_bg(APP.ui.session_peak_arrow, C.cream, 255, 0)
APP.ui.session_context_border = add_border_overlay(APP.ui.session_context_panel, 212, 92, C.line, 190)

APP.ui.session_footer = lv_obj_create(APP.ui.session_page)
lv_obj_set_size(APP.ui.session_footer, 302, 27)
lv_obj_set_pos(APP.ui.session_footer, 9, 320)
set_bg(APP.ui.session_footer, C.panel, 255, 0)
set_hidden(APP.ui.session_footer, true)
lv_obj_set_style_border_width(APP.ui.session_footer, 1, MAIN)
lv_obj_set_style_border_color(APP.ui.session_footer, C.line, MAIN)
lv_obj_set_style_border_opa(APP.ui.session_footer, 190, MAIN)

local session_footer_specs = {
  { key = "session_chat", x = 0, w = 78, color = C.line, text = T("C CHAT", "对话 --") },
  { key = "session_tools", x = 78, w = 74, color = C.rust, text = T("TOOL 00", "工具 00") },
  { key = "session_errors", x = 152, w = 65, color = C.panel, text = T("ERR 00", "错误 00") },
  { key = "session_agents", x = 217, w = 84, color = C.line, text = T("AGENT 0", "子任务 0") },
}
for _, spec in ipairs(session_footer_specs) do
  local segment = lv_obj_create(APP.ui.session_footer)
  lv_obj_set_size(segment, spec.w, 25)
  lv_obj_set_pos(segment, spec.x, 0)
  set_bg(segment, spec.color, 255, 0)
  local label = lv_label_create(segment)
  lv_obj_set_size(label, spec.w - 6, 15)
  lv_obj_set_pos(label, 3, 5)
  style_text(label, spec.key == "session_tools" and C.bg or C.cream, FONT_10, ALIGN_LEFT)
  set_text(label, spec.text)
  APP.ui[spec.key] = label
end

local function visual_color(state)
  if state == "error" then return C.error end
  if state == "notification" then return C.warn end
  if state == "done" then return C.mint end
  if state == "thinking" or state == "working" or state == "building" then return C.peach end
  return C.cream
end

local function visual_group(state, event)
  if state == "error" then return "Error" end
  if state == "sleeping" then return "Sleeping" end
  event = EVENT_ALIASES[event] or event
  -- 空闲时只保留「会话开始」这个瞬发动作；残留事件（Stop/SubagentStop 等）一律回到待机。
  -- 这条必须放在自定义映射之前：插件只在有事件时更新 event，空闲时 event 会停留在上次的值，
  -- 若让映射先生效，就会在待命状态下一直播上一个事件的动作。
  if state == "idle" then
    if event == "SessionStart" then return "SessionStart" end
    return "Idle"
  end
  -- 管理页可以把某个事件改绑到任意动作组，优先于内置映射
  local behavior = type(SKIN_STATE) == "table" and type(SKIN_STATE.behavior) == "table" and SKIN_STATE.behavior or {}
  local mapping = type(behavior.event_actions) == "table" and behavior.event_actions or {}
  local mapped = event and mapping[event]
  if type(mapped) == "string" and ClawdPack.events[mapped] then return mapped end
  if event and ClawdPack.events[event] then return event end
  if state == "thinking" then return "UserPromptSubmit" end
  if state == "building" then return "SubagentStart" end
  if state == "notification" then return "PermissionRequest" end
  if state == "done" then return "Stop" end
  if state == "working" then return "PreToolUse" end
  return "Idle"
end

-- 换动作时淡入，避免「啪」一下跳过去
local function fade_in(obj, ms)
  if not obj or not lv_obj_set_style_opa then return end
  local steps = math.max(1, math.floor((ms or 240) / 30))
  local i = 0
  pcall(lv_obj_set_style_opa, obj, 0, MAIN)
  local t = tmr.create()
  t:alarm(30, tmr.ALARM_AUTO, function()
    i = i + 1
    if i >= steps then
      pcall(lv_obj_set_style_opa, obj, 255, MAIN)
      t:stop(); t:unregister()
    else
      pcall(lv_obj_set_style_opa, obj, math.floor(255 * i / steps), MAIN)
    end
  end)
end

local function swap_gif(slot, source, x, y)
  local gifs = APP.ui[slot .. "_gifs"]
  if not gifs or not gifs[1] or not gifs[2] or not source then return false end
  local sources = APP.gif_sources[slot]
  local active = tonumber(APP.gif_active[slot]) or 1
  if sources[active] == source then
    set_hidden(gifs[active], false)
    return true
  end

  local standby = active == 1 and 2 or 1
  local next_gif = gifs[standby]
  local current_gif = gifs[active]
  set_hidden(next_gif, true)
  local loaded = pcall(function()
    lv_gif_set_src(next_gif, source)
    lv_obj_set_pos(next_gif, x or 0, y or 0)
  end)
  if not loaded then return false end

  -- fade_in 暂时停用：走动时动作频繁切换，淡入会被看成闪烁
  -- lv_gif_set_src prepares the first frame synchronously. Reveal the new
  -- decoder before retiring the old one so LVGL never paints an empty slot.
  set_hidden(next_gif, false)
  set_hidden(current_gif, true)
  if lv_obj_invalidate then pcall(function() lv_obj_invalidate(next_gif) end) end
  pcall(function() lv_gif_set_src(current_gif, nil) end)
  sources[active] = nil
  sources[standby] = source
  APP.gif_active[slot] = standby
  APP.gif_swaps = APP.gif_swaps + 1
  return true
end

local function memory_snapshot()
  local native = CONSOLE and CONSOLE.stats and CONSOLE:stats() or nil
  local lua_kb = nil
  if type(collectgarbage) == "function" then
    local ok, value = pcall(collectgarbage, "count")
    if ok then lua_kb = tonumber(value) end
  end
  return {
    lua_kb = lua_kb,
    gif_swaps = APP.gif_swaps,
    internal_free = native and native.internal_free or nil,
    psram_free = native and native.psram_free or nil,
    psram_largest = native and native.psram_largest or nil,
    font_cache_bytes = native and native.cache_bytes or nil,
    font_cache_entries = native and native.cache_entries or nil,
    font_renders = native and native.renders or nil,
  }
end

local function clear_gif_slot(slot)
  local gifs = APP.ui[slot .. "_gifs"] or {}
  for i = 1, 2 do
    if gifs[i] then
      set_hidden(gifs[i], true)
      pcall(function() lv_gif_set_src(gifs[i], nil) end)
    end
  end
  APP.gif_sources[slot] = {}
  APP.gif_active[slot] = 1
end

local function name_in(list, name)
  if type(list) ~= "table" then return false end
  for i = 1, #list do
    if list[i] == name then return true end
  end
  return false
end

-- 某个动作组当前启用的变体。enabled 里可以直接写皮肤包内任意 GIF 名，允许跨组混选。
local function visual_candidates(group, moving)
  local behavior = type(SKIN_STATE) == "table" and type(SKIN_STATE.behavior) == "table" and SKIN_STATE.behavior or {}
  local variants = type(behavior.variants) == "table" and behavior.variants or {}
  local conf = type(variants[group]) == "table" and variants[group] or {}
  local enabled = type(conf.enabled) == "table" and conf.enabled or nil
  local walkable = type(conf.walk) == "table" and conf.walk or nil
  local speed = (type(SKIN_STATE) == "table" and SKIN_STATE.speed) or "normal"
  local base_dir = (SKIN_DIR or (APP_DIR .. "/assets/skins/whale")) .. "/" .. speed
  local out = {}
  local function push(path, base)
    if moving and (walkable == nil or not name_in(walkable, base)) then return end
    out[#out + 1] = { path = path, base = base }
  end
  if enabled then
    for i = 1, #enabled do
      local base = tostring(enabled[i])
      local path = base_dir .. "/" .. base
      if file.exists(path) then push(path, base) end
    end
  else
    local all = ClawdPack.events[group] or IDLE_VISUALS
    if all then
      for i = 1, #all do
        local base = tostring(all[i]):match("([^/]+)$") or tostring(all[i])
        push(all[i], base)
      end
    end
  end
  if #out == 0 then
    local all = ClawdPack.events[group] or IDLE_VISUALS
    if all then
      for i = 1, #all do
        out[#out + 1] = { path = all[i], base = tostring(all[i]):match("([^/]+)$") }
      end
    end
  end
  return out, conf
end

APP.visual_group = visual_group

local function set_visual(state)
  local group = visual_group(state, APP.remote.event)
  if group == "Idle" and APP.last_visual_group and APP.last_visual_group ~= "Idle"
     and APP.walk then
    APP.walk.x = 80
    APP.walk.dir = 1
  end
  APP.last_visual_group = group
  -- 转身阶段：播皮肤包 turn 池里的动画（官方约定「播完会翻转朝向」），期间不镜像
  if APP.walk and APP.walk.phase == "turn" and ClawdPack and ClawdPack.turn and ClawdPack.turn[1] then
    local tv = ClawdPack.turn[1]
    APP.current_visual = tv
    if APP.page == "status" and APP.status_visual_loaded ~= tv then
      local tx = (APP.walk and APP.walk.x) or 80
      if swap_gif("status", tv, tx, 8) then APP.status_visual_loaded = tv end
    end
    return
  end
  local walking = APP.walk and APP.walk.moving
  -- 移动动画由 walk_tick 在每次进入 run 阶段时随机挑一个，避免永远同一个
  local mv = walking and APP.walk and APP.walk.move or nil
  local source, base
  if mv then
    -- 走动中统一播皮肤包的移动动画，比原地迈步自然
    source, base = mv.path, mv.base
  else
    local candidates = visual_candidates(group, false)
    if not candidates or #candidates == 0 then return end
    local index = group == "Idle" and APP.idle_index or APP.event_visual_index
    index = ((tonumber(index) or 1) - 1) % #candidates + 1
    local pick = candidates[index]
    source, base = pick.path, pick.base
  end
  -- 走动变体（当前是东张西望 idle_02）原图朝右：向右走用原图，向左走才用镜像版。
  -- 原地待命不切镜像，保持原图朝向。
  -- 任何可走动的动作都套镜像（侧身动作都有 mirror 版）
  if walking then
    -- 原图朝左的动作向右走才要镜像，朝右的反之
    local facing = mv and mv.facing or "right"
    local need = (facing == "left" and APP.walk.dir == 1) or (facing ~= "left" and APP.walk.dir == -1)
    if need then
      local speed = (type(SKIN_STATE) == "table" and SKIN_STATE.speed) or "normal"
      local mirrored = (SKIN_DIR or (APP_DIR .. "/assets/skins/whale")) .. "/mirror/" .. speed .. "/" .. tostring(base)
      if file.exists(mirrored) then source = mirrored end
    end
  end
  APP.current_visual = source
  APP.current_visual_group = group
  if APP.page ~= "status" or APP.status_visual_loaded == source then return end
  -- 保持在当前走动位置：只有重新进入待机时才回到屏幕中间，
  -- 中途切到其它事件动作时原地播放，避免闪回中间再跳回来。
  local wx = (APP.walk and APP.walk.x) or 80
  if swap_gif("status", source, wx, 8) then APP.status_visual_loaded = source end
end
APP.set_visual = set_visual

-- 待机时每 30 秒换一个 idle 变体：signature 不变时 set_visual 内部不会重选，
-- 清掉 signature 再调一次即可让它走随机分支。
APP.idle_rotate_timer = tmr.create()
APP.idle_rotate_timer:alarm(30000, tmr.ALARM_AUTO, function()
  if APP.page ~= "status" then return end
  local st = APP.remote.state
  if st ~= "idle" and st ~= "sleeping" then return end
  if #IDLE_VISUALS <= 1 then return end
  APP.last_event_signature = nil
  if APP.set_visual then APP.set_visual(st) end
end)

local function percent(value)
  local number = tonumber(value)
  if not number then return nil end
  return math.max(0, math.min(100, math.floor(number + 0.5)))
end

local function update_usage()
  -- A 页底部：11 = 上下文占用百分比，12 = 上下文进度条，13 = 账户余额
  local pct = nil
  local context = APP.remote.context
  if context then
    pct = tonumber(context.percent)
    local used, window = tonumber(context.used_tokens), tonumber(context.window_tokens)
    if not pct and used and window and window > 0 then pct = used / window * 100 end
  end
  pct = pct and math.max(0, math.min(100, pct)) or nil
  set_text(APP.ui.usage_week, pct and string.format("CTX %.0f%%", pct) or T("CTX --", "上下文 --"))

  local balance = tonumber(APP.remote.balance)
  set_text(APP.ui.usage_reset, balance and string.format("￥%.2f", balance) or "￥--")

  local width = pct and math.floor(84 * pct / 100) or 1
  if width < 1 then width = 1 end
  lv_obj_set_size(APP.ui.usage_fill, width, 4)
  local color = C.mint
  if pct and pct >= 90 then color = C.error
  elseif pct and pct >= 70 then color = C.warn end
  lv_obj_set_style_bg_color(APP.ui.usage_fill, color, MAIN)
end

local function duration_text(elapsed_ms)
  local seconds = math.max(0, math.floor((tonumber(elapsed_ms) or 0) / 1000))
  local minutes = math.floor(seconds / 60)
  if minutes >= 100 then
    return tostring(math.floor(minutes / 60)) .. ":" .. string.format("%02d", minutes % 60)
  end
  return string.format("%02d:%02d", minutes, seconds % 60)
end

local function elapsed_text(start_ms)
  if not start_ms or start_ms <= 0 then return "" end
  return duration_text(now_ms() - start_ms)
end

local function timer_display_texts()
  if APP.remote.state == "idle" then
    if APP.timing.has_completed_chat then
      return "C" .. duration_text(APP.timing.last_chat_elapsed_ms), "LAST"
    end
    return T("C CHAT", "对话 --"), T("S STATE", "状态 --")
  elseif APP.remote.state == "sleeping" then
    return "", ""
  end
  return "C" .. elapsed_text(APP.timing.chat_start_ms), "S" .. elapsed_text(APP.timing.state_start_ms)
end

local function update_timers()
  local chat_text, state_text = timer_display_texts()
  set_text(APP.ui.chat_timer, chat_text)
  set_text(APP.ui.state_timer, state_text)
end

local function request_time_sync(force)
  local time_mod = rawget(_G, "time")
  if not time_mod then return end
  local ts = now_ms()
  if not force and ts - (APP.last_clock_retry_ms or 0) < NTP_RETRY_MS then return end
  APP.last_clock_retry_ms = ts
  if time_mod.settimezone then pcall(time_mod.settimezone, LOCAL_TIMEZONE) end
  if time_mod.initntp then pcall(time_mod.initntp, NTP_SERVER) end
end

local function read_clock_text()
  local time_mod = rawget(_G, "time")
  if time_mod and time_mod.getlocal then
    local ok_local, calendar = pcall(time_mod.getlocal)
    if ok_local and type(calendar) == "table" and tonumber(calendar.year) and tonumber(calendar.year) >= 2024 then
      return string.format("%02d:%02d", tonumber(calendar.hour) or 0, tonumber(calendar.min) or 0)
    end
  end
  if rtctime and rtctime.get and rtctime.epoch2cal then
    local ok_get, epoch = pcall(rtctime.get)
    if ok_get and type(epoch) == "number" and epoch > 1600000000 then
      local offset = Timezone.offset_for_epoch(LOCAL_TIMEZONE, epoch)
      local ok_cal, year, mon, day, hour, minute = pcall(rtctime.epoch2cal, epoch + offset)
      if ok_cal and type(year) == "number" and year >= 2024 and type(hour) == "number" and type(minute) == "number" then
        return string.format("%02d:%02d", hour, minute)
      end
    end
  end
  if os and os.time and os.date then
    local ok_epoch, epoch = pcall(os.time)
    if ok_epoch and type(epoch) == "number" and epoch > 1600000000 then
      local offset = Timezone.offset_for_epoch(LOCAL_TIMEZONE, epoch)
      local ok_date, value = pcall(os.date, "!%H:%M", epoch + offset)
      if ok_date and type(value) == "string" then return value end
    end
  end
  return "--:--"
end

local function update_clock()
  local ts = now_ms()
  if ts - (APP.last_clock_check_ms or -1000) < 1000 then return end
  APP.last_clock_check_ms = ts
  local value = read_clock_text()
  if value == "--:--" then request_time_sync(false) end
  if value ~= APP.clock_text then
    APP.clock_text = value
    set_text(APP.ui.clock, value)
    set_text(APP.ui.weather_clock, value)
    set_text(APP.ui.session_clock, value)
  end
end

local function weather_quarter_slot()
  local hour, minute = tostring(APP.clock_text or ""):match("^(%d%d):(%d%d)$")
  hour, minute = tonumber(hour), tonumber(minute)
  if not hour or not minute then return nil, false end
  if minute % 15 ~= 0 then return nil, true end
  return string.format("%02d:%02d", hour, minute), true
end

local function weather_color(kind)
  if kind == "clear" then return C.warn end
  if kind == "partly" then return C.peach end
  if kind == "rain" or kind == "drizzle" then return 0x5BB7D9 end
  if kind == "storm" then return C.error end
  if kind == "snow" then return C.cream end
  if kind == "wind" then return C.mint end
  if kind == "fog" or kind == "cloudy" or kind == "overcast" then return C.dim end
  return C.rust
end

local function set_weather_visual(kind, mood)
  local group = ClawdPack.weather[kind] or ClawdPack.weather.cloudy
  local source = group and (group[mood] or group.mild_dry)
  if not source then return end
  APP.current_weather_visual = source
  if APP.page ~= "weather" or APP.weather_visual_loaded == source then return end
  if swap_gif("weather", source, 0, 0) then APP.weather_visual_loaded = source end
end

-- B 页角色跟随当前事件组，和 A 页用同一套 visual_group 规则；
-- 优先用 meme/ 下的 88x88 缩略图（格子只有 96x92），没有就回退主素材。
local function session_meme_group()
  return visual_group(APP.remote.state, APP.remote.event)
end

local function session_meme_pool()
  local group = session_meme_group()
  local list = (ClawdPack and ClawdPack.events and ClawdPack.events[group]) or nil
  if not list or #list == 0 then list = IDLE_VISUALS end
  local out = {}
  for i = 1, #list do
    local main_path = tostring(list[i])
    local small = main_path:gsub("/assets/skins/([^/]+)/[^/]+/", "/assets/skins/%1/meme/normal/")
    local base = main_path:match("([^/]+)$") or main_path
    out[#out + 1] = {
      path = (file.exists(small) and small) or main_path,
      label = (ClawdPack and ClawdPack.labels and ClawdPack.labels[base]) or base,
    }
  end
  return out, group
end

local function set_session_meme(force)
  local pool, group = session_meme_pool()
  if #pool == 0 then return end
  local ts = now_ms()
  -- 组变了（事件变化）就立刻换，不等定时器
  local group_changed = group ~= APP.session_meme_group
  if not force and not group_changed and APP.next_session_meme_ms > ts then return end
  local ok, slot = pcall(math.random, 1, #pool)
  local index = ok and slot or 1
  if #pool > 1 and index == APP.session_meme_index and not group_changed then
    index = (index % #pool) + 1
  end
  APP.session_meme_group = group
  APP.session_meme_index = index
  APP.session_meme_label = pool[index].label
  APP.next_session_meme_ms = ts + random_session_meme_delay_ms()
  local meme = pool[index]
  if APP.page ~= "session" or APP.session_meme_loaded == meme.path then return end
  if swap_gif("session", meme.path, 0, 0) then APP.session_meme_loaded = meme.path end
end

local function compact_tokens(value)
  local number = math.max(0, tonumber(value) or 0)
  if number >= 1000000 then return string.format("%.1fM", number / 1000000) end
  if number >= 1000 then return string.format("%.1fK", number / 1000) end
  return tostring(math.floor(number + 0.5))
end

local function render_session()
  local remote = APP.remote
  local activity = remote.activity or {}
  local state = remote.state or "idle"
  local accent = visual_color(state)
  local canonical = EVENT_ALIASES[remote.event] or remote.event
  local state_label = EVENT_LABELS[canonical] or STATE_LABELS[state] or string.upper(state)
  local tool = remote.tool ~= "" and remote.tool or string.lower(state_label)

  set_text(APP.ui.session_project, clip(remote.model ~= "" and remote.model or T("MODEL --", "模型 --"), 16))
  local balance = tonumber(remote.balance)
  set_text(APP.ui.session_model, balance and string.format("￥%.2f", balance) or "")
  set_text(APP.ui.session_state, clip(state_label, 11))
  set_text(APP.ui.session_tool, "$ " .. clip(tool, 12))
  lv_obj_set_style_bg_color(APP.ui.session_state_segment, accent, MAIN)
  lv_obj_set_style_border_color(APP.ui.session_log_panel, C.rust, MAIN)
  lv_obj_set_style_border_color(APP.ui.session_meme_panel, accent, MAIN)

  local context = remote.context or {}
  local context_percent = tonumber(context.percent)
  local context_color = C.rust
  if context_percent and context_percent >= 90 then context_color = C.error
  elseif context_percent and context_percent >= 75 then context_color = C.warn end
  set_text(APP.ui.session_context_percent, context_percent and string.format("%.1f%%", context_percent) or "--.-%")
  set_text(APP.ui.session_context_tokens, context_percent and (compact_tokens(context.used_tokens)
    .. " / " .. compact_tokens(context.window_tokens)) or T("-- / -- TOK", "-- / -- 词"))
  lv_obj_set_style_bg_color(APP.ui.session_context_tag, context_color, MAIN)
  lv_obj_set_style_text_color(APP.ui.session_context_percent, context_color, MAIN)
  lv_obj_set_style_border_color(APP.ui.session_context_panel, C.rust, MAIN)
  lv_obj_set_style_bg_color(APP.ui.session_context_fill, context_color, MAIN)
  local context_width = context_percent and math.max(1, math.floor(200 * math.min(100, context_percent) / 100)) or 1
  lv_obj_set_size(APP.ui.session_context_fill, context_width, 5)

  -- tokens 细分与峰谷刻度
  local turn = type(remote.turn) == "table" and remote.turn or {}
  local task = type(remote.task) == "table" and remote.task or {}
  set_text(APP.ui.session_m_turn, T("TURN ", "本轮 ") .. compact_tokens(turn.total))
  set_text(APP.ui.session_m_task, T("TASK ", "总计 ") .. compact_tokens(task.total))
  set_text(APP.ui.session_m_in, T("IN ", "未缓存 ") .. compact_tokens(turn["in"]))
  set_text(APP.ui.session_m_out, T("OUT ", "输出 ") .. compact_tokens(turn.out))
  set_text(APP.ui.session_m_cr, T("CRC ", "缓存读 ") .. compact_tokens(turn.cr))
  set_text(APP.ui.session_m_hit, T("HIT ", "命中 ") .. string.format("%.1f%%", (tonumber(turn.hit) or 0) * 100))
  -- 箭头跟随设备本地时钟推进，避免插件不推帧时箭头卡住
  local peak_ratio = tonumber(remote.peak_ratio) or 0
  local hh, mm = tostring(APP.clock_text or ""):match("^(%d+):(%d+)$")
  if hh then peak_ratio = (tonumber(hh) + tonumber(mm) / 60) / 24 end
  peak_ratio = math.max(0, math.min(1, peak_ratio))
  local arrow_x = math.floor(200 * peak_ratio)
  if arrow_x > 198 then arrow_x = 198 end
  lv_obj_set_pos(APP.ui.session_peak_arrow, 6 + arrow_x, 79)
  if APP.ui.session_peak_eta then
    set_text(APP.ui.session_peak_eta, peak_eta_text())
  end
  -- 非工作日（周末/节假日）全天谷价，把两段黄色峰时藏起来，整条留蓝
  local workday = remote.peak_workday ~= false
  for _, bar in ipairs(APP.ui.session_peak_peaks or {}) do
    if workday then lv_obj_clear_flag(bar, LV_OBJ_FLAG_HIDDEN)
    else lv_obj_add_flag(bar, LV_OBJ_FLAG_HIDDEN) end
  end

  local history = type(activity.history) == "table" and activity.history or {}
  for i = 1, 6 do
    local row = APP.ui.session_timeline[i]
    local item = history[i]
    if type(item) == "table" then
      local event = EVENT_ALIASES[item.event] or item.event
      local label = EVENT_LABELS[event] or STATE_LABELS[item.state] or tostring(event or T("EVENT", "事件"))
      local detail = tostring(item.tool or "")
      set_text(row, (i == #history and "> " or "| ") .. clip(label .. (detail ~= "" and ("  " .. detail) or ""), 23))
      lv_obj_set_style_text_color(row, item.state == "error" and C.error or (i == #history and accent or C.dim), MAIN)
    else
      set_text(row, i == 1 and T("> waiting for events", "> 等待事件") or "|")
      lv_obj_set_style_text_color(row, C.dim, MAIN)
    end
  end

  local chat_text = timer_display_texts()
  set_text(APP.ui.session_chat, chat_text ~= "" and chat_text or "C --:--")
  set_text(APP.ui.session_tools, T("TOOL ", "工具 ") .. string.format("%02d", tonumber(activity.tool_count) or 0))
  set_text(APP.ui.session_errors, T("ERR ", "错误 ") .. string.format("%02d", tonumber(activity.error_count) or 0))
  set_text(APP.ui.session_agents, T("AGENT ", "子任务 ") .. tostring(tonumber(activity.subagent_count) or remote.subagent_count or 0))
  lv_obj_set_style_text_color(APP.ui.session_errors, (tonumber(activity.error_count) or 0) > 0 and C.error or C.cream, MAIN)
  set_session_meme(false)
  apply_display()
end

-- B 页的峰谷箭头要跟着真实时间走：插件只在有事件时推帧，
-- 空闲时箭头会停在原地，所以这里每分钟按设备时钟重画一次。
APP.peak_timer = tmr.create()
APP.peak_timer:alarm(60000, tmr.ALARM_AUTO, function()
  if APP.page == "session" then
    update_timers()   -- 先把 clock_text 刷到当前分钟，箭头才不会落后一格
    render_session()
  end
end)

local function chart_begin(canvas)
  local fn = rawget(_G, "lv_canvas_frame_begin") or rawget(_G, "lv_canvas_begin")
  if fn then pcall(fn, canvas) end
end

local function chart_end(canvas)
  local fn = rawget(_G, "lv_canvas_frame_end") or rawget(_G, "lv_canvas_end")
  if fn then pcall(fn, canvas)
  elseif lv_obj_invalidate then pcall(lv_obj_invalidate, canvas) end
end

local function chart_fill(canvas, color)
  local fn = rawget(_G, "lv_canvas_fill_bg") or rawget(_G, "lv_canvas_fill")
  if fn then pcall(fn, canvas, color, 255) end
end

local function chart_line(canvas, x1, y1, x2, y2, color, opa, width)
  if lv_canvas_draw_line then pcall(lv_canvas_draw_line, canvas, x1, y1, x2, y2, color, opa or 255, width or 1) end
end

local function chart_rect(canvas, x, y, w, h, color, opa)
  if lv_canvas_draw_rect then pcall(lv_canvas_draw_rect, canvas, x, y, w, h, color, opa or 255) end
end

local function render_weather_trend(state)
  local rows = state and state.hourly or {}
  local canvas = APP.ui.weather_chart_canvas
  local min_temp, max_temp, max_rain, rain_sum = nil, nil, 0, 0
  for i = 1, math.min(8, #rows) do
    local temp = tonumber(rows[i].temp)
    local rain = tonumber(rows[i].precipitation) or 0
    if temp then
      min_temp = not min_temp and temp or math.min(min_temp, temp)
      max_temp = not max_temp and temp or math.max(max_temp, temp)
    end
    max_rain = math.max(max_rain, rain)
    rain_sum = rain_sum + rain
  end
  set_text(APP.ui.weather_chart_rain, T("R ", "雨 ") .. string.format("%.1f", rain_sum) .. "mm")
  set_text(APP.ui.weather_chart_temp, min_temp and (T("T ", "温 ") .. tostring(min_temp) .. " > " .. tostring(max_temp) .. TEMP_UNIT)
    or (T("T ", "温 ") .. "-- > --" .. TEMP_UNIT))

  for i = 1, 4 do
    local row = rows[1 + (i - 1) * 2]
    set_text(APP.ui.weather_chart_hours[i], row and tostring(row.hour or "--"):sub(1, 2) or "--")
  end

  if canvas then
    chart_begin(canvas)
    chart_fill(canvas, C.panel)
    chart_line(canvas, 3, 22, 175, 22, C.line, 210, 1)
    chart_line(canvas, 3, 11, 175, 11, C.line, 90, 1)
    local previous_x, previous_y = nil, nil
    local temp_span = math.max(1, (max_temp or 1) - (min_temp or 0))
    for i = 1, math.min(8, #rows) do
      local x = 7 + (i - 1) * 23
      local rain = tonumber(rows[i].precipitation) or 0
      if rain > 0 and max_rain > 0 then
        local height = math.max(1, math.floor(rain / max_rain * 18 + 0.5))
        chart_rect(canvas, x - 4, 22 - height, 8, height, 0x5BB7D9, 230)
      else
        chart_rect(canvas, x - 1, 21, 2, 1, 0x5BB7D9, 100)
      end
      local temp = tonumber(rows[i].temp) or min_temp or 0
      local y = 19 - math.floor((temp - (min_temp or temp)) / temp_span * 15 + 0.5)
      if previous_x then chart_line(canvas, previous_x, previous_y, x, y, C.peach, 255, 2) end
      chart_rect(canvas, x - 1, y - 1, 3, 3, C.cream, 255)
      previous_x, previous_y = x, y
    end
    chart_end(canvas)
  end

  local tomorrow = state and state.tomorrow or {}
  if tomorrow and tomorrow.kind then
    local accent = weather_color(tomorrow.kind)
    lv_obj_set_style_bg_color(APP.ui.weather_tomorrow_segment, accent, MAIN)
    lv_obj_set_style_border_color(APP.ui.weather_tomorrow_panel, accent, MAIN)
    lv_obj_set_style_text_color(APP.ui.weather_tomorrow_kind, accent, MAIN)
    set_text(APP.ui.weather_tomorrow_kind, tomorrow.label or string.upper(tomorrow.kind))
    set_text(APP.ui.weather_tomorrow_temp, T("T ", "温 ") .. tostring(tomorrow.temp_min or 0) .. " > " .. tostring(tomorrow.temp_max or 0) .. TEMP_UNIT)
    set_text(APP.ui.weather_tomorrow_rain, T("R", "雨") .. tostring(tomorrow.pop or 0) .. "% "
      .. string.format("%.1f", tonumber(tomorrow.precipitation) or 0) .. T("mm G", "mm 风")
      .. tostring(math.floor((tonumber(tomorrow.gust) or 0) + 0.5)))
  else
    set_text(APP.ui.weather_tomorrow_kind, T("SYNC", "同步"))
    set_text(APP.ui.weather_tomorrow_temp, T("T ", "温 ") .. "-- > --" .. TEMP_UNIT)
    set_text(APP.ui.weather_tomorrow_rain, T("R--% 0.0mm G--", "雨--% 0.0mm 风--"))
  end
end

local function render_weather()
  local state = APP.weather and APP.weather.state or nil
  if not state then return end
  local city = clip(weather_city_text(state), 20)
  set_text(APP.ui.weather_title, T("WX // ", "天气 // ") .. string.upper(city))

  if not state.valid then
    set_text(APP.ui.weather_condition, state.loading and T("SYNCING", "同步中") or T("OFFLINE", "离线"))
    set_text(APP.ui.weather_source, state.loading and T("POLL", "请求") or T("DOWN", "断开"))
    set_text(APP.ui.weather_temp, "--" .. TEMP_UNIT)
    set_text(APP.ui.weather_feels, state.error ~= "" and clip(state.error, 23) or T("RESOLVING LOCATION", "正在解析位置"))
    set_text(APP.ui.weather_humidity, T("HUM --%", "湿度 --%"))
    set_text(APP.ui.weather_gust, T("GUST --", "阵风 --"))
    set_text(APP.ui.weather_wind, T("WIND -- GUST --", "风 -- 阵风 --"))
    set_text(APP.ui.weather_updated, T("WAITING FOR FORECAST", "等待天气数据"))
    set_text(APP.ui.weather_alert_text, T("RAIN --% @--:--  GUST --", "降雨 --% @--:--  阵风 --"))
    render_weather_trend(state)
    return
  end

  local current = state.current or {}
  local kind = current.kind or "cloudy"
  local accent = weather_color(kind)
  set_weather_visual(kind, current.mood or "mild_dry")
  lv_obj_set_style_border_color(APP.ui.weather_art_panel, accent, MAIN)
  lv_obj_set_style_border_color(APP.ui.weather_info_panel, accent, MAIN)
  lv_obj_set_style_bg_color(APP.ui.weather_condition_segment, accent, MAIN)
  lv_obj_set_style_text_color(APP.ui.weather_condition, C.bg, MAIN)
  lv_obj_set_style_text_color(APP.ui.weather_condition_arrow, accent, MAIN)
  lv_obj_set_style_text_color(APP.ui.weather_source, state.stale and C.warn or accent, MAIN)
  lv_obj_set_style_bg_color(APP.ui.weather_hum_segment, accent, MAIN)
  lv_obj_set_style_bg_color(APP.ui.weather_gust_segment, accent, MAIN)
  lv_obj_set_style_border_color(APP.ui.weather_cmd_segment, accent, MAIN)
  lv_obj_set_style_text_color(APP.ui.weather_wind, accent, MAIN)
  lv_obj_set_style_bg_color(APP.ui.weather_alert, accent, MAIN)
  lv_obj_set_style_text_color(APP.ui.weather_alert_text, C.bg, MAIN)
  set_text(APP.ui.weather_condition, current.label or string.upper(kind))
  set_text(APP.ui.weather_source, state.stale and T("STALE", "过期") or T("NOW", "当前"))
  set_text(APP.ui.weather_temp, current.temp_text or ("--" .. TEMP_UNIT))
  set_text(APP.ui.weather_feels, T("FEELS ", "体感 ") .. tostring(math.floor((tonumber(current.feels) or 0) + 0.5)) .. TEMP_UNIT)
  set_text(APP.ui.weather_humidity, T("HUM ", "湿度 ") .. tostring(current.humidity or 0) .. "%")
  set_text(APP.ui.weather_gust, T("GUST ", "阵风 ") .. tostring(math.floor((tonumber(current.wind_gust) or 0) + 0.5)))
  set_text(APP.ui.weather_wind, T("WIND ", "风 ") .. tostring(math.floor((tonumber(current.wind_speed) or 0) + 0.5))
    .. T(" GUST ", " 阵风 ") .. tostring(math.floor((tonumber(current.wind_gust) or 0) + 0.5))
    .. " " .. string.format("%03d", tonumber(current.wind_direction) or 0) .. T("deg", "°"))
  local data_time = tostring(current.time or ""):sub(12, 16)
  set_text(APP.ui.weather_updated, (state.stale and T("STALE ", "过期 ") or T("DATA ", "数据 ")) .. data_time
    .. T(" SYNC ", " 同步 ") .. tostring(APP.weather_sync_text or "--:--"))
  set_text(APP.ui.weather_alert_text, T("RAIN ", "降雨 ") .. tostring(state.rain_probability or 0) .. "% @"
    .. tostring(state.rain_time or T("DRY", "无雨")) .. T("  GUST ", "  阵风 ") .. tostring(math.floor((tonumber(state.max_gust) or 0) + 0.5)))
  render_weather_trend(state)
end

local function show_page(name)
  if name ~= "weather" and name ~= "session" then name = "status" end
  local previous_page = APP.page
  APP.page = name

  -- Prepare the target page while it is still hidden. The previous page stays
  -- visible until the target GIF has decoded its first frame.
  if name == "weather" then
    APP.weather_visual_loaded = nil
    render_weather()
    if APP.weather and (not APP.weather.state.valid or APP.weather.state.stale) then APP.weather:fetch() end
  elseif name == "session" then
    APP.session_meme_loaded = nil
    APP.next_session_meme_ms = 0
    local ok, err = pcall(render_session)
    if not ok then pcall(file.putcontents, APP_DIR .. "/err.txt", tostring(err)) end
  else
    APP.status_visual_loaded = nil
    set_visual(APP.remote.state)
  end

  set_hidden(APP.ui.status_page, name ~= "status")
  set_hidden(APP.ui.weather_page, name ~= "weather")
  set_hidden(APP.ui.session_page, name ~= "session")

  if previous_page ~= name then
    if previous_page == "status" then
      clear_gif_slot("status")
      APP.status_visual_loaded = nil
    elseif previous_page == "weather" then
      clear_gif_slot("weather")
      APP.weather_visual_loaded = nil
    elseif previous_page == "session" then
      clear_gif_slot("session")
      APP.session_meme_loaded = nil
    end
  end
end

local function update_labels()
  local remote = APP.remote
  local state = remote.state
  local canonical_event = EVENT_ALIASES[remote.event] or remote.event
  local label = EVENT_LABELS[canonical_event] or STATE_LABELS[state] or string.upper(state)
  if state == "error" then label = T("ERROR", "错误") end
  if state == "sleeping" then label = T("SLEEPING", "休眠") end
  if state == "idle" and canonical_event ~= "SessionStart" then label = T("IDLE", "待命") end
  if remote.subagent_count > 0 then
    label = label .. " x" .. tostring(remote.subagent_count)
  end

  set_text(APP.ui.title, "DSH // " .. label)
  set_text(APP.ui.state, label)
  local state_color = visual_color(state)
  lv_obj_set_style_bg_color(APP.ui.state_segment, state_color, MAIN)
  lv_obj_set_style_text_color(APP.ui.state, C.bg, MAIN)
  lv_obj_set_style_text_color(APP.ui.state_arrow, state_color, MAIN)
  lv_obj_set_style_bg_color(APP.ui.state_time_segment, state_color, MAIN)
  lv_obj_set_style_text_color(APP.ui.state_timer, C.bg, MAIN)
  set_text(APP.ui.project, "~/" .. clip(remote.project ~= "" and remote.project or T("local", "本地"), 17))
  local source = tostring(remote.source or "")
  set_text(APP.ui.source, source:find("jsonl", 1, true) and T("LOG", "日志") or T("HOOK", "钩子"))

  if remote.connected then
    set_text(APP.ui.live, T("LIVE", "在线"))
    lv_obj_set_style_text_color(APP.ui.live, C.mint, MAIN)
  else
    set_text(APP.ui.live, T("WAIT", "等待"))
    lv_obj_set_style_text_color(APP.ui.live, C.dim, MAIN)
  end
  update_usage()
  update_timers()
  apply_display()
  if APP.page == "session" then render_session() end
  -- 底栏描边跟着当前状态色走（描边不再是可配色项）
  if APP.ui.panel_border and lv_obj_set_style_border_color then
    local vc = visual_color(state)
    if APP.last_border_color ~= vc then
      APP.last_border_color = vc
      pcall(lv_obj_set_style_border_color, APP.ui.panel_border, vc, MAIN)
    end
  end
end

local function apply_remote_state(state, transient_ms)
  if not ALLOWED_STATES[state] then state = "idle" end
  local previous_state = APP.remote.state
  APP.remote.state = state
  if previous_state ~= state or APP.timing.state_start_ms <= 0 then
    APP.timing.state_start_ms = now_ms()
  end
  if state ~= "idle" and state ~= "sleeping" and APP.timing.chat_start_ms <= 0 then
    APP.timing.chat_start_ms = now_ms()
  end
  APP.remote.transient_until = transient_ms and (now_ms() + transient_ms) or 0
  if state == "idle" then
    APP.idle_delay_ms = random_idle_delay_ms()
    APP.next_idle_ms = now_ms() + APP.idle_delay_ms
  end
  set_visual(state)
  update_labels()
end

local function update_subagents(doc)
  local id = clip(doc.subagent_id or "", 80)
  if doc.event == "SubagentStart" then
    if id ~= "" then APP.remote.subagents[id] = true end
  elseif doc.event == "SubagentStop" then
    if id ~= "" then APP.remote.subagents[id] = nil end
  end
  local count = 0
  for _ in pairs(APP.remote.subagents) do count = count + 1 end
  APP.remote.subagent_count = count
end

-- 事件音效：查 skin.json 的 sounds 表，命中就播；Sound.play 内部有同名节流
local function play_event_sound(event, times)
  if type(event) ~= "string" or event == "" then return end
  local map = (type(SKIN_STATE) == "table" and type(SKIN_STATE.sounds) == "table") and SKIN_STATE.sounds or nil
  if not map then return end
  local name = map[event]
  if type(name) == "string" and name ~= "" and name ~= "off" then
    pcall(Sound.play, APP_DIR, name, times or 1)
  end
end

local function accept_status(doc)
  APP.remote.connected = true
  APP.remote.last_update_ms = now_ms()
  APP.remote.event = clip(doc.event or "", 48)
  APP.remote.project = clip(doc.project or "", 40)
  APP.remote.tool = clip(doc.tool or "", 48)
  APP.remote.session = clip(doc.session or "", 80)
  APP.remote.model = clip(doc.model or "", 32)
  APP.remote.effort = clip(doc.effort or APP.remote.effort or "", 16)
  if type(doc.context) == "table" then APP.remote.context = doc.context end
  APP.remote.source = clip(doc.source or "bridge", 24)
  if type(doc.activity) == "table" then APP.remote.activity = doc.activity end
  APP.remote.balance = tonumber(doc.balance)
  APP.remote.balance_status = doc.balance_status or ""
  APP.remote.today_cny = tonumber(doc.today_cny)
  APP.remote.today_tokens = tonumber(doc.today_tokens)
  APP.remote.turn_cny = tonumber(doc.turn_cny)
  APP.remote.peak = (doc.peak == "peak") and "peak" or "off"
  APP.remote.peak_ratio = tonumber(doc.peak_ratio) or 0
  APP.remote.peak_workday = doc.peak_workday ~= false
  APP.remote.turn = type(doc.turn) == "table" and doc.turn or nil
  APP.remote.task = type(doc.task) == "table" and doc.task or nil
  if type(doc.usage) == "table" then
    APP.usage.weekly_percent = doc.usage.weekly_percent
    APP.usage.weekly_reset_text = clip(doc.usage.weekly_reset_text or "--/--", 5)
  end
  APP.connection_detail = APP.remote.event
  if APP.remote.tool ~= "" then APP.connection_detail = APP.connection_detail .. " // " .. APP.remote.tool end
  update_subagents(doc)

  local state = tostring(doc.state or "idle")
  if not ALLOWED_STATES[state] then state = "idle" end
  local group = visual_group(state, APP.remote.event)
  local choices = ClawdPack.events[group] or IDLE_VISUALS
  local signature = tostring(APP.remote.event) .. "|" .. tostring(APP.remote.tool) .. "|" .. tostring(state)
  if signature ~= APP.last_event_signature and choices and #choices > 0 then
    APP.last_event_signature = signature
    random_visual_index(group, #choices)
  end
  -- 峰谷切换提示音：只在峰/谷状态真正切换时播，默认播三遍后停止
  local pk = (doc.peak == "peak") and "Peak" or "OffPeak"
  if APP.last_peak ~= nil and APP.last_peak ~= pk then
    play_event_sound(pk, 3)
  end
  APP.last_peak = pk
  if APP.remote.event ~= "" and APP.remote.event ~= APP.last_sound_event then
    APP.last_sound_event = APP.remote.event
    play_event_sound(APP.remote.event)
  end
  if APP.remote.event == "UserPromptSubmit" or APP.remote.event == "event_msg:task_started" then
    APP.timing.chat_start_ms = now_ms()
  end
  if state == "done" then
    apply_remote_state("done", 5000)
  elseif state == "error" then
    apply_remote_state("error", 7000)
  elseif state == "notification" then
    apply_remote_state("notification", 8000)
  elseif APP.remote.event == "SessionStart" then
    apply_remote_state("idle", 8000)
  else
    apply_remote_state(state)
  end
  local chat_elapsed = tonumber(doc.chat_elapsed_seconds)
  local state_elapsed = tonumber(doc.state_elapsed_seconds)
  local received_at = now_ms()
  if chat_elapsed and chat_elapsed >= 0 then
    APP.timing.chat_start_ms = received_at - math.floor(chat_elapsed * 1000)
  end
  if state_elapsed and state_elapsed >= 0 then
    APP.timing.state_start_ms = received_at - math.floor(state_elapsed * 1000)
  end
  if state == "done" and APP.timing.chat_start_ms > 0 then
    APP.timing.last_chat_elapsed_ms = math.max(0, received_at - APP.timing.chat_start_ms)
    APP.timing.has_completed_chat = true
  end
  update_timers()
end

local function start_client()
  if APP.client then APP.client:stop() end
  APP.remote.connected = false
  APP.connection_detail = T("connecting to ", "正在连接 ") .. tostring(config.host) .. ":" .. tostring(config.port)
  update_labels()
  APP.client = DshClient.new(config, {
    on_event = function(doc)
      accept_status(doc)
    end,
    on_status = function(state, detail)
      if state == "online" then
        APP.remote.connected = true
        if APP.remote.last_update_ms == 0 then APP.connection_detail = tostring(detail or state or "") end
      elseif state == "offline" or state == "error" then
        APP.remote.connected = false
        APP.connection_detail = tostring(detail or state or "")
      else
        APP.connection_detail = tostring(detail or state or "")
      end
      update_labels()
    end,
  })
  APP.client:start()
end

local function bind_keys()
  local function tilt_show_page(name)
    local ts = now_ms()
    if ts - (APP.last_page_switch_ms or -PAGE_SWITCH_COOLDOWN_MS) < PAGE_SWITCH_COOLDOWN_MS then return end
    APP.last_page_switch_ms = ts
    show_page(name)
  end

  -- 大肥鱼只有两个界面：B（角色为主）与 C（场景化终端），左右键互切。
  key.on(key.LEFT, function(event_type)
    if event_type == key.START or event_type == key.SHORT then
      if APP.page == "session" then tilt_show_page("status") end
    end
  end)

  key.on(key.RIGHT, function(event_type)
    if event_type == key.START or event_type == key.SHORT then
      if APP.page ~= "session" then tilt_show_page("session") end
    end
  end)

  key.on(key.UP, function(event_type)
    if event_type == key.SHORT and APP.page == "status" then
      APP.remote.event = "ManualReset"
      APP.remote.tool = ""
      apply_remote_state("idle")
    end
  end)

  key.on(key.DOWN, function(event_type)
    if event_type == key.SHORT and APP.page == "status" then
      APP.remote.event = "ManualSleep"
      APP.remote.tool = ""
      apply_remote_state("sleeping")
    end
  end)

  key.on(key.HOME, function(event_type)
    if event_type == key.SHORT then
      APP.stop("home")
      pcall(function() app.exit() end)
    end
  end)

  local PAD_SELECT, PAD_HOME = 4096, 32768
  if controller and controller.state and tmr and tmr.create then
    APP.controller_timer = tmr.create()
    APP.controller_timer:alarm(40, tmr.ALARM_AUTO, function()
      if not APP.running then return end
      local ok, pad = pcall(function() return controller.state("ble-main") end)
      local buttons = ok and type(pad) == "table" and tonumber(pad.buttons) or 0
      buttons = buttons or 0
      local pressed = buttons & (~APP.controller_buttons)
      APP.controller_buttons = buttons
      if (pressed & (PAD_SELECT | PAD_HOME)) ~= 0 then
        APP.stop("controller")
        if app and app.exit then pcall(function() app.exit() end) end
      end
    end)
  end
end

function APP.stop(reason)
  if not APP.running then return end
  APP.running = false
  if APP.client then APP.client:stop(); APP.client = nil end
  if APP.weather then APP.weather:stop(); APP.weather = nil end
  if APP.web then APP.web:stop(); APP.web = nil end
  pcall(function() key.off() end)

  for i = #APP.routes, 1, -1 do
    local item = APP.routes[i]
    pcall(function() httpd.unregister(item.method, item.route) end)
  end
  APP.routes = {}

  if APP.timer then
    pcall(function() APP.timer:stop() end)
    pcall(function() APP.timer:unregister() end)
    APP.timer = nil
  end
  if APP.reload_timer then
    pcall(function() APP.reload_timer:stop() end)
    pcall(function() APP.reload_timer:unregister() end)
    APP.reload_timer = nil
  end
  if APP.controller_timer then
    pcall(function() APP.controller_timer:stop() end)
    pcall(function() APP.controller_timer:unregister() end)
    APP.controller_timer = nil
  end

  clear_gif_slot("status")
  clear_gif_slot("weather")
  clear_gif_slot("session")
  if APP.font_handles and lv_font_free then
    for _, handle in ipairs(APP.font_handles) do
      pcall(function() lv_font_free(handle) end)
    end
  end
  APP.font_handles = {}
  if lv_obj_clean and root then pcall(function() lv_obj_clean(root) end) end
  if rawget(_G, APP_KEY) == APP then _G[APP_KEY] = nil end
end

APP.shutdown = APP.stop

if #IDLE_VISUALS > 0 then random_visual_index("Idle", #IDLE_VISUALS) end
apply_remote_state("idle")
request_time_sync(true)
update_clock()
APP.weather = WeatherClient.new({
  language = UI_LANG,
  on_update = function(state)
    local updated_at = state and tonumber(state.updated_at_ms) or 0
    if state and state.valid and not state.loading and not state.stale
      and updated_at > 0 and updated_at ~= APP.last_weather_updated_ms then
      APP.last_weather_updated_ms = updated_at
      APP.weather_sync_text = APP.clock_text
    end
    if APP.running then render_weather() end
  end,
  on_status = function(state)
    APP.weather_status = tostring(state or "")
  end,
})
-- 天气页已移除（设置页也不再配置城市），不再启动轮询
  -- APP.weather:start()
local initial_weather_slot = weather_quarter_slot()
if initial_weather_slot then APP.last_weather_sync_slot = initial_weather_slot end
APP.next_weather_ms = now_ms() + WEATHER_FALLBACK_REFRESH_MS
bind_keys()

-- 运行时切换皮肤 / 速度：重建 ClawdPack，清掉已缓存的 GIF，立刻重画当前页。
-- 主题（颜色/字号）只在启动时套用，改动后提示重启应用。
local function apply_skin(patch)
  patch = patch or {}
  if type(patch.active) == "string" and #patch.active > 0 then
    if Skin.load_pack(APP_DIR, patch.active) then
      if SKIN_STATE.active ~= patch.active then
        -- 换皮肤 = 换整套动作库，旧皮肤的文件名配置对新皮肤无意义，清空让页面按新皮肤重填
        SKIN_STATE.behavior = SKIN_STATE.behavior or {}
        SKIN_STATE.behavior.variants = {}
        SKIN_STATE.active = patch.active
      end
    end
  end
  if type(patch.speed) == "string" and patch.speed ~= "" then SKIN_STATE.speed = patch.speed end
  if type(patch.skins) == "table" then SKIN_STATE.skins = patch.skins end
  if type(patch.move_speed) == "table" then
    SKIN_STATE.move_speed = SKIN_STATE.move_speed or {}
    for k, v in pairs(patch.move_speed) do SKIN_STATE.move_speed[k] = v end
  end
  if type(patch.theme) == "table" then
    for key, value in pairs(patch.theme) do
      local ref = Skin.DEFAULT_THEME[key]
      if ref ~= nil and type(value) == type(ref) then
        SKIN_STATE.theme[key] = value
      end
    end
  end
  if type(patch.behavior) == "table" then
    SKIN_STATE.behavior = SKIN_STATE.behavior or {}
    if type(patch.behavior.walk_states) == "table" then
      SKIN_STATE.behavior.walk_states = patch.behavior.walk_states
    end
    -- 事件->动作组：逐键合并，前端每次提交全量也不会丢别的键
    if type(patch.behavior.event_actions) == "table" then
      local merged = {}
      for k, v in pairs(SKIN_STATE.behavior.event_actions or {}) do merged[k] = v end
      for k, v in pairs(patch.behavior.event_actions) do merged[k] = v end
      SKIN_STATE.behavior.event_actions = merged
    end
    -- 变体：前端是按组（事件）逐个提交的，必须逐组合并，不能整体替换
    if type(patch.behavior.variants) == "table" then
      local into = {}
      for g, cfg in pairs(SKIN_STATE.behavior.variants or {}) do into[g] = cfg end
      for g, cfg in pairs(patch.behavior.variants) do into[g] = cfg end
      SKIN_STATE.behavior.variants = into
    end
  end
  if type(patch.display) == "table" then
    SKIN_STATE.display = patch.display
end
  if type(patch.hidden) == "table" then
    SKIN_STATE.hidden = patch.hidden
  end
  if type(patch.sounds) == "table" then
    local into = {}
    for k, v in pairs(SKIN_STATE.sounds or {}) do into[k] = v end
    for k, v in pairs(patch.sounds) do into[k] = v end
    SKIN_STATE.sounds = into
  end
  if type(patch.walk) == "table" then
    SKIN_STATE.walk = SKIN_STATE.walk or {}
    for k in pairs({ pace = 1, pause = 1, len = 1 }) do
      local v = patch.walk[k]
      if type(v) == "string" and v ~= "" then SKIN_STATE.walk[k] = v end
    end
  end
  if type(patch.sound_volume) == "number" then
    local v = patch.sound_volume
    if v < 0 then v = 0 elseif v > 1 then v = 1 end
    SKIN_STATE.sound_volume = v
    pcall(Sound.set_volume, v)
  end

  local manifest, dir = Skin.load_pack(APP_DIR, SKIN_STATE.active)
  if manifest then
    ClawdPack = Skin.resolve(manifest, dir, SKIN_STATE.speed)
    IDLE_VISUALS = ClawdPack.events.Idle or {}
  end
  Skin.save_state(APP_DIR, SKIN_STATE)

  APP.status_visual_loaded = nil
  APP.session_meme_loaded = nil
  APP.idle_index = 1
  clear_gif_slot("status")
  clear_gif_slot("session")
  set_visual(APP.remote.state)
  apply_display()
  if APP.page == "session" then render_session() end
  return true
end

APP.web = HoloWeb.new({
  language = UI_LANG,
  requested_language = REQUESTED_UI_LANG,
  system_language = SYSTEM_UI_LANG,
  config = config,
  config_path = APP_DIR .. "/config.lua",
  route_base = (app and app.route_base and app.route_base()) or ("/" .. APP_SLUG),
  restart = start_client,
  reload_app = function()
    if not app or not app.launch or not tmr or not tmr.create then return false end
    if APP.reload_timer then
      pcall(function() APP.reload_timer:stop() end)
      pcall(function() APP.reload_timer:unregister() end)
    end
    APP.reload_timer = tmr.create()
    APP.reload_timer:alarm(600, tmr.ALARM_SINGLE, function()
      APP.reload_timer = nil
      pcall(function() app.launch(APP_ID or APP_SLUG) end)
    end)
    return true
  end,
  refresh_weather = function()
    if APP.weather then
      APP.weather.resolved_for = ""
      APP.weather.latitude = nil
      APP.weather.longitude = nil
      APP.weather:fetch()
    end
  end,
  set_page = show_page,
  skin_state = function()
    -- actions 给管理页做 GIF 预览：事件名 -> 相对 APP_DIR 的 gif 路径列表
    local actions = {}
    local events = (ClawdPack and ClawdPack.events) or {}
    for name, list in pairs(events) do
      local rel = {}
      for i = 1, #list do
        local p = tostring(list[i])
        local stripped = p:gsub("^" .. APP_DIR:gsub("%p", "%%%0") .. "/", "")
        rel[#rel + 1] = stripped
      end
      actions[name] = rel
    end
      local names = {}
      local labels = (ClawdPack and ClawdPack.labels) or {}
      for name, list in pairs(actions) do
        local row = {}
        for i = 1, #list do
          local base = tostring(list[i]):match("([^/]+)$") or tostring(list[i])
          row[i] = { file = list[i], base = base, label = labels[base] or labels[name] or base }
        end
        names[name] = row
      end
    -- 没配置过的组补一份默认变体（全启用、不可走动），
    -- 否则管理页会把它们显示成「一个都没勾」，而实际播放时会回退成全部启用。
    local behavior = SKIN_STATE.behavior or {}
    local variants = behavior.variants or {}
    local filled = {}
    for g, list in pairs(actions) do
      local cfg = variants[g]
      local pkg = nil
      if type(cfg) == "table" and type(cfg.enabled) == "table" and #cfg.enabled > 0 then
        -- 只保留当前皮肤里真实存在的文件名：切皮肤后旧配置会全部失效，
        -- 不校验的话页面显示「一个都没勾」而实际播放又回退成全部启用。
        local valid = {}
        for _, p in ipairs(list) do
          valid[tostring(p):match("([^/]+)$") or tostring(p)] = true
        end
        local keep_en, keep_wk = {}, {}
        for _, b in ipairs(cfg.enabled) do if valid[b] then keep_en[#keep_en + 1] = b end end
        for _, b in ipairs(type(cfg.walk) == "table" and cfg.walk or {}) do
          if valid[b] then keep_wk[#keep_wk + 1] = b end
        end
        if #keep_en > 0 then
          pkg = { mode = cfg.mode or "seq", enabled = keep_en, walk = keep_wk }
        end
      end
      if pkg then
        filled[g] = pkg
      else
        local en = {}
        for i = 1, #list do
          en[i] = tostring(list[i]):match("([^/]+)$") or tostring(list[i])
        end
        filled[g] = { mode = "seq", enabled = en, walk = (type(cfg) == "table" and cfg.walk) or {} }
      end
    end
    behavior.variants = filled

    return {
      active = SKIN_STATE.active,
      speed = SKIN_STATE.speed,
      theme = SKIN_STATE.theme,
      behavior = behavior,
      display = SKIN_STATE.display or {},
      moves = (function()
      local MS = { ["ceshen-jizao-pao.gif"] = 5, ["pangxie-zoulu.gif"] = 2, ["kaixin-xiaopao.gif"] = 1 }
      local usr = (type(SKIN_STATE) == "table" and type(SKIN_STATE.move_speed) == "table") and SKIN_STATE.move_speed or {}
      local out = {}
      for i, m in ipairs(ClawdPack.moves or {}) do
        out[i] = { base = m.base, facing = m.facing, lead = m.lead, tail = m.tail,
                   speed = tonumber(usr[m.base]) or MS[m.base] or 2 }
      end
      return out
    end)(),
      turn = ClawdPack.turn or {},
      hidden = SKIN_STATE.hidden or {},
      sounds = SKIN_STATE.sounds or {},
      sound_list = (Sound and Sound.list) and Sound.list(APP_DIR) or {},
      sound_volume = SKIN_STATE.sound_volume or 0.8,
      walk = SKIN_STATE.walk or {},
      categories = (function()
  local out = {}
  local skin_id = (type(SKIN_STATE) == "table" and SKIN_STATE.active) or "whale"
  local spd = (type(SKIN_STATE) == "table" and SKIN_STATE.speed) or "normal"
  for _, c in ipairs((ClawdPack and ClawdPack.categories) or {}) do
    local item = { id = c.id or "?", files = {} }
    for _, f in ipairs(c.files or {}) do
      item.files[#item.files + 1] = "assets/skins/" .. skin_id .. "/" .. spd .. "/" .. tostring(f)
    end
    if #item.files > 0 then out[#out + 1] = item end
  end
  return out
end)(),
actions = actions,
      names = names,
      available = Skin.list(APP_DIR, SKIN_STATE),
    }
  end,
  app_dir = APP_DIR,
  apply_skin = apply_skin,
  play_sound = function(name) pcall(Sound.play, APP_DIR, name) end,
  connection_state = function()
    local chat_text, state_text = timer_display_texts()
    return {
      version = APP.VERSION,
      online = APP.remote.connected,
      detail = APP.connection_detail,
      state = APP.remote.state,
      event = APP.remote.event,
      source = APP.remote.source,
      model = APP.remote.model,
      effort = APP.remote.effort,
      context = APP.remote.context,
      usage = APP.usage,
      memory = memory_snapshot(),
      idle_variant = APP.idle_index,
      idle_delay_minutes = math.floor((APP.idle_delay_ms or 0) / 60000),
      clock = APP.clock_text,
      chat_timer = chat_text,
      state_timer = state_text,
      page = APP.page,
      visual_group = APP.current_visual_group,
      visual_index = APP.current_visual_group == "Idle" and APP.idle_index or APP.event_visual_index,
      weather = APP.weather and APP.weather.state or nil,
      weather_visual = APP.current_weather_visual,
      weather_sync = APP.weather_sync_text,
      activity = APP.remote.activity,
      session_meme = APP.session_meme_label or "",
      font = {
        family = CONSOLE and CONSOLE.ready and CONSOLE.family or "LVGL Montserrat",
        source = CONSOLE and CONSOLE.ready and CONSOLE.source or "builtin font fallback",
        rendering = CONSOLE and CONSOLE.ready and CONSOLE.rendering or T("LVGL grayscale fallback", "LVGL 灰度兜底"),
        loaded = CONSOLE and CONSOLE.ready or false,
        loaded_sizes = CONSOLE and CONSOLE.ready and 5 or 0,
        error = APP.font_error,
      },
    }
  end,
})
APP.web:start()
start_client()

APP.timer = tmr.create()
APP.timer:alarm(250, tmr.ALARM_AUTO, function()
  if not APP.running then return end
  if app and app.exiting and app.exiting() then
    APP.stop("exit")
    return
  end

  local ts = now_ms()
  if type(collectgarbage) == "function" and ts - (APP.last_gc_ms or -1000) >= 1000 then
    APP.last_gc_ms = ts
    pcall(collectgarbage, "step", 32)
  end
  if APP.remote.state == "idle" and APP.next_idle_ms > 0 and ts >= APP.next_idle_ms then
    if #IDLE_VISUALS > 0 then random_visual_index("Idle", #IDLE_VISUALS) end
    APP.idle_delay_ms = random_idle_delay_ms()
    APP.next_idle_ms = ts + APP.idle_delay_ms
    set_visual("idle")
  end
  if APP.weather then
    local weather_slot, clock_valid = weather_quarter_slot()
    if clock_valid then
      if weather_slot and weather_slot ~= APP.last_weather_sync_slot then
        APP.last_weather_sync_slot = weather_slot
        APP.next_weather_ms = ts + WEATHER_FALLBACK_REFRESH_MS
        APP.weather:fetch()
      end
    elseif APP.next_weather_ms > 0 and ts >= APP.next_weather_ms then
      APP.next_weather_ms = ts + WEATHER_FALLBACK_REFRESH_MS
      APP.weather:fetch()
    end
  end
  update_clock()
  update_timers()
  if APP.page == "session" then
    set_session_meme(false)
    render_session()
  end
  if APP.remote.transient_until > 0 and ts >= APP.remote.transient_until then
    APP.remote.transient_until = 0
    APP.remote.event = "AwaitingPrompt"
    APP.remote.tool = ""
    apply_remote_state("idle")
  end
end)
