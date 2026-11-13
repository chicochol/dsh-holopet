local Web = {}
local JSON = rawget(_G, "sjson") or rawget(_G, "json")
local SETTINGS_PATH = "/sd/apps/settings.json"

local function trim(value)
  return tostring(value or ""):match("^%s*(.-)%s*$") or ""
end

local function url_decode(value)
  value = tostring(value or ""):gsub("+", " ")
  return value:gsub("%%(%x%x)", function(hex) return string.char(tonumber(hex, 16)) end)
end

local function parse_query(query)
  local out = {}
  for pair in tostring(query or ""):gmatch("([^&]+)") do
    local key, value = pair:match("^([^=]*)=(.*)$")
    out[url_decode(key or pair)] = url_decode(value or "")
  end
  return out
end


local function read_text(path)
  if not file then return nil end
  if file.getcontents then
    local ok, value = pcall(file.getcontents, path)
    if ok and type(value) == "string" then return value end
  end
  return nil
end

local function decode_json(raw)
  if type(raw) ~= "string" or raw == "" or not JSON or not JSON.decode then return {} end
  local ok, value = pcall(JSON.decode, raw)
  return ok and type(value) == "table" and value or {}
end

local function write_json(path, value)
  if not JSON or not JSON.encode or not file or not file.putcontents then return false, "json/file api missing" end
  local ok, raw = pcall(function() return JSON.encode(value) end)
  if not ok then return false, tostring(raw) end
  local write_ok, result = pcall(function() return file.putcontents(path, raw) end)
  if write_ok and result ~= false then return true end
  return false, tostring(result)
end

local function ui_is_zh(language)
  return tostring(language or ""):lower():match("^zh") ~= nil
end

local function W(language, en, zh)
  return ui_is_zh(language) and zh or en
end

local function normalize_language_mode(value)
  local text = tostring(value or ""):gsub("_", "-"):lower()
  if text == "en" or text:match("^en%-") then return "en" end
  if text == "zh" or text:match("^zh%-") then return "zh-CN" end
  return "system"
end

local function settings_weather_address()
  local doc = decode_json(read_text(SETTINGS_PATH))
  return trim(doc.weather_address or doc.weatherAddress or doc.weather_city or doc.city or "")
end

local function save_weather_address(address)
  address = trim(address)
  if address == "" then return true end
  local doc = decode_json(read_text(SETTINGS_PATH))
  doc.weather_address = address
  doc.weather_city = address
  doc.weather_location_address = address
  doc.weather_location_id = ""
  return write_json(SETTINGS_PATH, doc)
end

local function valid_ipv4(host)
  local a, b, c, d = tostring(host or ""):match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
  if not a then return false end
  for _, value in ipairs({ tonumber(a), tonumber(b), tonumber(c), tonumber(d) }) do
    if not value or value < 0 or value > 255 then return false end
  end
  return true
end

local function normalize_path(path)
  path = trim(path)
  if path == "" then return "/events" end
  return path:sub(1, 1) == "/" and path or ("/" .. path)
end

local function response(status, content_type, body, cache)
  return {
    status = status or "200 OK",
    type = content_type or "text/plain; charset=utf-8",
    headers = { ["cache-control"] = cache or "no-store", ["connection"] = "close" },
    body = body or "",
  }
end

local function json_response(status, value)
  local ok, raw = pcall(function() return JSON.encode(value) end)
  return response(ok and status or "500 Internal Server Error", "application/json; charset=utf-8", ok and raw or "{\"ok\":false}")
end

local function config_text(config)
  return string.format([=[local config = {}

config.host = %q
config.port = %d
config.path = %q
config.language = %q

config.timeout_ms = %d
config.reconnect_ms = %d
config.stale_ms = %d
config.watchdog_ms = %d
config.serial_log = %s

return config
]=],
    tostring(config.host or "192.168.0.100"),
    tonumber(config.port) or 17321,
    normalize_path(config.path),
    normalize_language_mode(config.language),
    tonumber(config.timeout_ms) or 7000,
    tonumber(config.reconnect_ms) or 2000,
    tonumber(config.stale_ms) or 120000,
    tonumber(config.watchdog_ms) or 1000,
    config.serial_log == false and "false" or "true"
  )
end

local function write_config(path, config)
  local raw = config_text(config)
  if file and file.putcontents then
    local ok, result = pcall(function() return file.putcontents(path, raw) end)
    if ok and result ~= false then return true end
    return false, tostring(result)
  end
  if file and file.open then
    local ok = pcall(function()
      file.open(path, "w+")
      file.write(raw)
      file.close()
    end)
    return ok, ok and nil or "write failed"
  end
  return false, "file api missing"
end

local function html_escape_js(value)
  value = tostring(value or "")
  value = value:gsub("\\", "\\\\"):gsub('"', '\\"')
  return value
end

local function build_html(api_prefix, language)
  api_prefix = html_escape_js(api_prefix)
  local zh = ui_is_zh(language)
  local title = zh and "DSH 伴侣 · 设备设置" or "DSH Companion · Device Settings"
  local headline = zh and "DSH 伴侣" or "DSH Companion"
  local subtitle = zh and "配置与 DeepSeek Harness 的连接、皮肤外观与显示内容。" or "Configure the DeepSeek Harness link, skins and on-screen items."
  local navHost = zh and "主机连接" or "Host"
  local navStatus = zh and "连接状态" or "Status"
  local navDisplay = zh and "显示项" or "Items"
  local navSkin = zh and "皮肤与动画" or "Skins"
  local navTheme = zh and "外观配色" or "Theme"
  local navBehavior = zh and "行为" or "Behavior"
  local back = zh and "返回主界面" or "Back to launcher"
  local hostTitle = zh and "主机连接" or "Host connection"
  local hostLabel = zh and "主机 IP" or "Host IP"
  local portLabel = zh and "端口" or "Port"
  local pathLabel = zh and "事件路径" or "Event path"
  local weatherLabel = zh and "天气城市" or "Weather city"
  local languageLabel = zh and "显示语言" or "Display language"
  local languageSystem = zh and "跟随系统" or "Follow system"
  local languageChinese = zh and "中文" or "Chinese"
  local languageEnglish = "English"
  local saveText = zh and "保存并重连" or "Save and reconnect"
  local testText = zh and "测试连接" or "Test connection"
  local loadingText = zh and "正在读取配置…" or "Loading settings..."
  local statusTitle = zh and "连接状态" or "Connection status"
  local deviceHost = zh and "设备 → 主机" or "Device → host"
  local eventStream = zh and "事件流" or "Event stream"
  local screenFont = zh and "屏幕字体" or "Screen font"
  local recentInfo = zh and "最近信息" or "Recent info"
  local onlineText = zh and "已连接" or "Connected"
  local offlineText = zh and "未连接" or "Disconnected"
  local waitText = zh and "等待连接" or "Waiting for connection"
  local loadedText = zh and "当前配置已载入。" or "Settings loaded."
  local readFail = zh and "读取失败" or "Read failed"
  local savingText = zh and "正在保存…" or "Saving..."
  local saveFail = zh and "保存失败" or "Save failed"
  local savedText = zh and "已保存，正在按新地址重连。" or "Saved. Reconnecting with the new address."
  local reloadingText = zh and "已保存，正在应用语言并重载应用…" or "Saved. Applying language and reloading the app..."
  local testingText = zh and "正在测试" or "Testing"
  local testOk = zh and "连接成功，Codex 桥接服务在线。" or "Connection OK. Codex bridge is online."
  local testFail = zh and "连接失败：" or "Connection failed: "
  local timeoutText = zh and "超时" or "timeout"
  local cfgFail = zh and "配置读取失败：" or "Failed to load settings: "
  local skinTitle = zh and "皮肤与动画" or "Skin and animation"
  local skinLabel = zh and "当前皮肤" or "Skin"
  local speedLabel = zh and "动画速度" or "Speed"
  local speedSlow = zh and "慢" or "Slow"
  local speedNormal = zh and "标准" or "Normal"
  local speedFast = zh and "快" or "Fast"
  local applyText = zh and "应用" or "Apply"
  local hideText = zh and "隐藏" or "Hide"
  local unhideText = zh and "全部显示" or "Show all"
  local resetText = zh and "恢复默认" or "Reset"
  local skinSaved = zh and "已切换。" or "Applied."
  local skinFail = zh and "切换失败：" or "Switch failed: "
  local themeTitle = zh and "外观配色" or "Appearance colors"
  local volLabel = zh and "音量" or "Volume"
  local themeHint = zh and "描边不再单独配色：A 页底栏跟着状态色、B 页事件窗跟着状态色、上下文窗跟着占用率变色。改完需重启应用才生效（LVGL 样式在创建时确定）。" or "Borders follow the status colour now. Restart the app to apply."
  local themeSaved = zh and "已保存，重启应用后生效。" or "Saved. Restart the app to apply."
  local colorBg = zh and "背景" or "Background"
  local colorPanel = zh and "面板" or "Panel"
  local paceLabel = zh and "走动节奏（只管左右移动，不影响动画播放速度）" or "Walk pacing (movement only)"
  local paceSpeed = zh and "移动速度" or "Move speed"
  local pacePause = zh and "停顿频率" or "Pause frequency"
  local paceLen = zh and "停顿时长" or "Pause length"
  local paceSlow = zh and "慢" or "Slow"
  local paceNormal = zh and "标准" or "Normal"
  local paceFast = zh and "快" or "Fast"
  local pauseNever = zh and "不停顿" or "Never"
  local pauseRare = zh and "偶尔" or "Rare"
  local pauseNormalOpt = zh and "适中" or "Normal"
  local pauseOften = zh and "频繁" or "Often"
  local lenShort = zh and "短" or "Short"
  local lenNormal = zh and "中" or "Medium"
  local lenLong = zh and "长" or "Long"
  local volTitle = zh and "音量（即时生效）" or "Volume (live)"
  local colorTrack = zh and "进度条底色" or "Bar track"
  local colorFg = zh and "主文字" or "Text"
  local colorDim = zh and "次要文字" or "Muted text"
  local colorAccent = zh and "强调色" or "Accent"
  local colorWarn = zh and "警示色" or "Warning"
  local colorError = zh and "错误色" or "Error"
  -- web.lua 是独立模块，没有 main.lua 里的本地 T()，这里补一个同义的
  local function T(en, cn) return zh and cn or en end
  local EVENT_GROUPS = { "Idle", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
    "Error", "Stop", "SessionStart", "SubagentStart", "SubagentStop", "PreCompact", "PostCompact", "Sleeping" }
  local WALK_STATES = { { "idle", T("IDLE", "待命") }, { "thinking", T("THINKING", "思考") },
    { "working", T("WORKING", "工作") }, { "building", T("SUBAGENT", "子任务") },
    { "notification", T("APPROVAL", "待确认") }, { "done", T("DONE", "完成") },
    { "error", T("ERROR", "错误") }, { "sleeping", T("SLEEPING", "休眠") } }
  local EVENT_ZH = {
    Idle = "待机", UserPromptSubmit = "接收指令", PreToolUse = "执行工具",
    PostToolUse = "检查结果", PermissionRequest = "等待确认", SubagentStart = "分派子任务",
    SubagentStop = "合并子任务", PreCompact = "压缩前", PostCompact = "压缩后",
    Error = "出错", Stop = "本轮完成", SessionStart = "会话开始", Sleeping = "休眠",
  }
  local function evt_zh(name)
    local zh_name = EVENT_ZH[name]
    if zh_name then return zh_name .. " (" .. name .. ")" end
    return name
  end
  local mapRows = {}
  for _, name in ipairs(EVENT_GROUPS) do
    local opts = {}
    for _, group in ipairs(EVENT_GROUPS) do
      opts[#opts + 1] = '<option value="' .. group .. '">' .. evt_zh(group) .. '</option>'
    end
    mapRows[#mapRows + 1] = '<div class="erow"><div class="evname">' .. evt_zh(name) .. '</div>' ..
      '<div class="evgroup" id="grp_' .. name .. '">' .. evt_zh(name) .. '</div>' ..
      '<div class="ecells" id="cells_' .. name .. '"></div>' ..
      '<select class="sndSel" id="snd_' .. name .. '" title="事件音效"></select>' ..
      '<button type="button" class="sndTry" data-ev="' .. name .. '" title="试听">&#9654;</button>' ..
      '<button type="button" class="more" data-ev="' .. name .. '" title="显示皮肤包里全部动作，可跨组挑">全部</button></div>'
  end
  local behaviorTitle = zh and "行为（动作与走动）" or "Behavior"
  local figACap = zh and "A 页 · 角色为主" or "Page A"
  local figBCap = zh and "B 页 · 场景化终端" or "Page B"
  local walkLabel = zh and "角色能否左右移动，由下面每行动作的「可走动」勾选决定——勾了才走，没勾就原地播放。" or "Whether the character walks is decided per variant below."
  local mapLabel = zh and "事件 → 动作组 · 该组动作（左键：启用播放；右键：允许边走边播）" or "Event → group · variants (left: enabled, right: allowed while walking)"
  local behSaved = zh and "已保存，立即生效。" or "Saved."
  local varLabel = zh and "同一事件可指定多个变体，按顺序轮播；走动时只在「右键」勾选的变体里挑。" or "Multiple variants rotate in order; while walking only the right-checked ones are used."
  local varSaveText = zh and "保存变体" or "Save variants"
  local DISPLAY_ITEMS = { { "a_title", T("Status title", "A 标题") }, { "a_live", T("Link state", "A 连接态") },
    { "a_clock", T("Status clock", "A 时钟") }, { "a_gif", T("Character", "A 角色区") },
    { "a_state", T("State bar", "A 状态条") }, { "a_project", T("Project", "A 项目名") },
    { "a_source", T("Source", "A 数据源") }, { "a_timers", T("Timers", "A 计时") },
    { "a_usage", T("Usage row", "A 用量区") }, { "b_title", T("Session title", "B 标题") },
    { "b_clock", T("Session clock", "B 时钟") }, { "b_log", T("Terminal", "B 终端窗") },
    { "b_state", T("State bar", "B 状态条") }, { "b_timeline", T("Event stream", "B 命令流") },
    { "b_meme", T("Character", "B 角色区") }, { "b_context", T("Context panel", "B 上下文面板") } }
  local dispChipsA, dispChipsB = {}, {}
  for _, item in ipairs(DISPLAY_ITEMS) do
    local chip = '<label class="chip"><input type="checkbox" class="dispSel" value="' ..
      item[1] .. '">' .. item[2] .. '</label>'
    if string.sub(item[1], 1, 2) == "b_" then
      dispChipsB[#dispChipsB + 1] = chip
    else
      dispChipsA[#dispChipsA + 1] = chip
    end
  end
  local pageALabel = zh and "A 页（角色为主）" or "Page A"
  local pageBLabel = zh and "B 页（场景化终端）" or "Page B"
  local displayTitle = zh and "显示项（取消勾选即隐藏）" or "Visible items"
  local dispSaved = zh and "已保存，立即生效。" or "Saved."
  local fontScaleLabel = zh and "字号倍率（0.80–1.30，重启应用生效）" or "Font scale (0.80-1.30, restart to apply)"

  local h0 = [=[<!doctype html>
<html lang="]=] .. (zh and "zh-CN" or "en") .. [=["><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>]=] .. title .. [=[</title><style>
.varlist{margin-top:10px;display:flex;flex-direction:column;gap:12px}
.vargroup{border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.vgname{font-weight:700;margin-bottom:6px;color:var(--accent)}
.vgitems{display:flex;flex-wrap:wrap;gap:10px}
.vcell{display:flex;flex-direction:column;align-items:center;gap:2px;font-size:12px;color:var(--muted);width:86px}
.vcell img{width:60px;height:60px;image-rendering:pixelated;background:rgba(0,0,0,.25);border-radius:6px}
.vcell input{margin:0}
.vcbs{display:flex;gap:8px;align-items:center}
input[type=color]{width:96px;height:34px;padding:2px;border:1px solid var(--line);border-radius:8px;background:transparent;cursor:pointer}
.evgroup{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:13px;padding-top:12px}.sub{font-weight:700;margin:10px 0 4px;color:var(--accent);font-size:13px}.hint{color:var(--muted);font-size:12px;margin:10px 0 2px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 10px}
.chip{display:inline-flex;align-items:center;gap:6px;background:#141b28;border:1px solid #243044;border-radius:8px;padding:5px 9px;font-size:13px;cursor:pointer}
.chip input{accent-color:var(--accent)}
.mapgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 14px;margin-top:6px}
.mapgrid select{width:100%}
.maprow{display:flex;gap:8px;align-items:flex-start}
.maprow>div{flex:1;min-width:0}
.prev{width:52px;height:52px;flex:0 0 auto;image-rendering:pixelated;background:#000;border:1px solid var(--line);border-radius:8px;object-fit:contain}
.gallery{display:flex;flex-wrap:wrap;align-items:flex-start;gap:16px}
.grow{background:#0b101a;border:1px solid var(--line);border-radius:10px;padding:6px;text-align:center}
.gcount{opacity:.55;font-size:11px;margin-left:4px}
.gname{font-size:12px;color:var(--muted);margin-bottom:4px;word-break:break-all}
.gimgs{display:flex;gap:4px;justify-content:center;flex-wrap:wrap}
.gimgs img{width:64px;height:64px;image-rendering:pixelated}
:root{color-scheme:dark;--bg:#0a0d12;--panel:#121722;--panel2:#161d2b;--line:#243044;--text:#e8eef7;--muted:#8b9bb4;--rust:#5b9cff;--mint:#3ddc9a;--red:#ff6b6b;--accent:#5b9cff;--accent2:#8f7bff}.tabs{position:sticky;top:0;z-index:30;display:flex;gap:8px;flex-wrap:wrap;padding:12px 0 10px;margin-bottom:6px;background:linear-gradient(180deg,var(--bg) 72%,rgba(10,13,18,.6) 100%);backdrop-filter:blur(10px)}.tabs a{padding:7px 13px;border-radius:999px;border:1px solid var(--line);color:var(--muted);text-decoration:none;font-size:13px;transition:.15s}.tabs a:hover{color:var(--text);border-color:var(--accent);background:#141b28}.panel{scroll-margin-top:72px}.erow{display:grid;grid-template-columns:100px 150px minmax(0,1fr) 96px 34px 60px;gap:12px;align-items:start;padding:10px 0;border-top:1px solid var(--line)}.erow:first-of-type{border-top:none}.evname{font-weight:700;color:var(--text);padding-top:8px;font-size:13px}.ecells{display:flex;flex-wrap:wrap;gap:10px}@media(max-width:820px){.erow{grid-template-columns:1fr;gap:6px}}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 520px at 85% -12%,#1b2a4a 0%,transparent 62%),radial-gradient(760px 460px at -8% 8%,#2a1b3d 0%,transparent 58%),var(--bg);color:var(--text);font:15px/1.55 "Cascadia Mono",Consolas,"Microsoft YaHei",monospace}
.page{width:min(1120px,calc(100% - 40px));margin:auto;padding:28px 0}.top{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}h1{margin:0;font-size:30px}.sub{margin:5px 0 0;color:var(--muted)}
.back{display:inline-flex;align-items:center;justify-content:center}.back,button{min-height:42px;border:1px solid var(--line);border-radius:9px;background:#1a2233;color:var(--text);padding:0 15px;text-decoration:none;cursor:pointer}.panel{border-radius:14px;background:linear-gradient(180deg,var(--panel2),var(--panel));box-shadow:0 10px 28px rgba(0,0,0,.32);border:1px solid var(--line);padding:16px 18px}.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px}h2{margin:0 0 14px;font-size:18px}
  .form{display:grid;gap:13px}.row{display:grid;grid-template-columns:1fr 150px;gap:10px}label{display:block;margin-bottom:5px;color:var(--muted);font-size:13px;font-weight:700}label.chip{display:inline-flex;margin-bottom:0}label.vcell{display:inline-flex;flex-direction:column;margin-bottom:0}.chip input,.vcell input{width:auto;height:auto;margin:0}.thememap{width:100%;height:auto;display:block;border:1px solid var(--line);border-radius:12px;background:#0a0d12}.themegrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-top:16px}.themegrid>div{display:flex;flex-direction:column;gap:6px;min-width:0}.themegrid label{margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.themegrid input[type=color]{width:100%;height:36px}@media(max-width:760px){.themegrid{grid-template-columns:repeat(2,minmax(0,1fr))}}input,select{width:100%;height:44px;border:1px solid var(--line);border-radius:8px;background:#0d1320;color:var(--text);padding:0 11px;outline:none}input:focus,select:focus{border-color:var(--rust);box-shadow:0 0 0 3px #d9775730}.actions{display:flex;gap:9px;flex-wrap:wrap}.primary{border-color:transparent;background:var(--rust);color:#170b07;font-weight:800}.status{min-height:24px;color:var(--muted)}.ok{color:var(--mint)}.bad{color:var(--red)}
.state{display:grid;gap:11px}.metric{padding:11px;border:1px solid #1e2839;border-radius:10px;background:#0d1320}.metric span{display:block;color:var(--muted);font-size:12px}.metric strong{display:block;margin-top:4px;overflow-wrap:anywhere}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);margin-right:7px}.dot.on{background:var(--mint)}code{color:#f4c1a7}@media(max-width:700px){.grid{grid-template-columns:1fr}.row{grid-template-columns:1fr}.top{align-items:start}h1{font-size:25px}}]=]
  local h1 = [=[.sndSel{align-self:center;height:34px;font-size:13px;padding:0 4px;min-width:0}.sndTry{align-self:center;height:32px;padding:0 6px;font-size:13px;border-radius:8px;background:var(--panel2);color:var(--text);border:1px solid var(--line);cursor:pointer}.more{align-self:center;white-space:nowrap}</style></head><body><main class="page"><nav class="tabs"><a href="#sec-host">]=] .. navHost .. [=[</a><a href="#sec-status">]=] .. navStatus .. [=[</a><a href="#sec-display">]=] .. navDisplay .. [=[</a><a href="#sec-skin">]=] .. navSkin .. [=[</a><a href="#sec-theme">]=] .. navTheme .. [=[</a><a href="#sec-behavior">]=] .. navBehavior .. [=[</a></nav><header class="top"><div><h1>]=] .. headline .. [=[</h1><p class="sub">]=] .. subtitle .. [=[</p></div><a class="back" href="/main">]=] .. back .. [=[</a></header>]=]
  local h2 = [=[<section class="grid"><section class="panel" id="sec-host"><h2>]=] .. hostTitle .. [=[</h2><form class="form" id="form"><div class="row"><div><label for="host">]=] .. hostLabel .. [=[</label><input id="host" inputmode="decimal" placeholder="192.168.0.100" required></div><div><label for="port">]=] .. portLabel .. [=[</label><input id="port" inputmode="numeric" placeholder="17321" required></div></div><div><label for="path">]=] .. pathLabel .. [=[</label><input id="path" placeholder="/events" required></div><div><label for="language">]=] .. languageLabel .. [=[</label><select id="language"><option value="system">]=] .. languageSystem .. [=[</option><option value="zh-CN">]=] .. languageChinese .. [=[</option><option value="en">]=] .. languageEnglish .. [=[</option></select></div><div style="display:flex;align-items:center;gap:12px;margin-top:6px"><label for="s_vol" style="flex:0 0 auto;margin-bottom:0">]=] .. volTitle .. [=[</label><input type="range" id="s_vol" min="0" max="100" step="5" value="80" style="flex:1"><span id="s_vol_val" style="min-width:52px;text-align:right;color:var(--text);font-variant-numeric:tabular-nums">80%</span></div><div class="actions"><button class="primary" type="submit">]=] .. saveText .. [=[</button><button id="test" type="button">]=] .. testText .. [=[</button></div><div class="status" id="message">]=] .. loadingText .. [=[</div></form></section>]=]
  local h3 = [=[<aside class="panel" id="sec-status"><h2>]=] .. statusTitle .. [=[</h2><div class="state"><div class="metric"><span>]=] .. deviceHost .. [=[</span><strong><i class="dot" id="dot"></i><b id="online">]=] .. offlineText .. [=[</b></strong></div><div class="metric"><span>]=] .. eventStream .. [=[</span><strong><code id="url">-</code></strong></div><div class="metric"><span>]=] .. screenFont .. [=[</span><strong id="font">-</strong></div><div class="metric"><span>]=] .. recentInfo .. [=[</span><strong id="detail">-</strong></div></div></aside></section>]=]
  local h4 = [=[<section class="panel" id="sec-display" style="margin-top:14px"><h2>]=] .. displayTitle .. [=[</h2><div class="form"><div class="sub">]=] .. pageALabel .. [=[</div><div class="chips">]=] .. table.concat(dispChipsA) .. [=[</div><div class="sub">]=] .. pageBLabel .. [=[</div><div class="chips">]=] .. table.concat(dispChipsB) .. [=[</div><div class="actions"><button class="primary" id="dispApply" type="button">]=] .. applyText .. [=[</button></div><div class="status" id="dispMsg"></div></div></section>]=]
  local h5 = [=[<section class="panel" id="sec-skin" style="margin-top:14px"><h2>]=] .. skinTitle .. [=[</h2><div class="form"><div class="row"><div><label for="skin">]=] .. skinLabel .. [=[</label><select id="skin"></select></div><div><label for="speed">]=] .. speedLabel .. [=[</label><select id="speed"><option value="slow">]=] .. speedSlow .. [=[</option><option value="normal">]=] .. speedNormal .. [=[</option><option value="fast">]=] .. speedFast .. [=[</option></select></div></div><div class="actions"><button class="primary" id="skinApply" type="button">]=] .. applyText .. [=[</button><button id="skinHide" type="button">]=] .. hideText .. [=[</button><button id="skinUnhide" type="button">]=] .. unhideText .. [=[</button></div><div class="status" id="skinMsg"></div><div id="gallery" class="gallery"></div></div></section>]=]
  local h6 = [=[<section class="panel" id="sec-theme" style="margin-top:14px"><h2>]=] .. themeTitle .. [=[</h2><div class="form"><img class="thememap" src="asset?p=assets%2Fui%2Fcolor-map.png" alt="配色作用区域对照图"><div class="themegrid"><div><label for="t_bg">]=] .. colorBg .. [=[</label><input type="color" id="t_bg" value="#0B1512"></div><div><label for="t_panel">]=] .. colorPanel .. [=[</label><input type="color" id="t_panel" value="#13241C"></div><div><label for="t_track">]=] .. colorTrack .. [=[</label><input type="color" id="t_track" value="#223A2E"></div><div><label for="t_fg">]=] .. colorFg .. [=[</label><input type="color" id="t_fg" value="#F2FBF6"></div><div><label for="t_dim">]=] .. colorDim .. [=[</label><input type="color" id="t_dim" value="#7E9C8C"></div><div><label for="t_accent">]=] .. colorAccent .. [=[</label><input type="color" id="t_accent" value="#4ADE80"></div><div><label for="t_warn">]=] .. colorWarn .. [=[</label><input type="color" id="t_warn" value="#FBBF24"></div><div><label for="t_error">]=] .. colorError .. [=[</label><input type="color" id="t_error" value="#F87171"></div></div></div><div style="color:var(--muted);font-size:13px;margin:12px 0 8px">]=] .. themeHint .. [=[</div><div><label for="t_scale">]=] .. fontScaleLabel .. [=[</label><div style="display:flex;align-items:center;gap:12px"><input type="range" id="t_scale" min="0.80" max="1.30" step="0.05" value="1.00" style="flex:1"><span id="t_scale_val" style="min-width:56px;text-align:right;color:var(--text);font-variant-numeric:tabular-nums">100%</span></div></div><div class="actions"><button class="primary" id="themeApply" type="button">]=] .. applyText .. [=[</button><button id="themeReset" type="button">]=] .. resetText .. [=[</button></div><div class="status" id="themeMsg"></div></div></section>]=]
  local h7 = [=[<section class="panel" id="sec-behavior" style="margin-top:14px"><h2>]=] .. behaviorTitle .. [=[</h2><div class="form"><div class="hint">]=] .. walkLabel .. [=[</div><div class="sub" style="margin-top:14px">]=] .. mapLabel .. [=[</div><div class="etable">]=] .. table.concat(mapRows) .. [=[</div><div class="hint">]=] .. varLabel .. [=[</div><div class="sub" style="margin-top:14px">]=] .. paceLabel .. [=[</div><div style="display:flex;gap:12px;flex-wrap:wrap"><div style="flex:1 1 150px"><label for="w_pause">]=] .. pacePause .. [=[</label><select id="w_pause"><option value="never">]=] .. pauseNever .. [=[</option><option value="rare">]=] .. pauseRare .. [=[</option><option value="normal">]=] .. pauseNormalOpt .. [=[</option><option value="often">]=] .. pauseOften .. [=[</option></select></div><div style="flex:1 1 150px"><label for="w_len">]=] .. paceLen .. [=[</label><select id="w_len"><option value="short">]=] .. lenShort .. [=[</option><option value="normal">]=] .. lenNormal .. [=[</option><option value="long">]=] .. lenLong .. [=[</option></select></div></div><div class="sub" style="margin-top:14px">三个位移动作的平移速度（像素/拍，1–8，越大越快）</div><div style="display:flex;gap:12px;flex-wrap:wrap"><div style="flex:1 1 180px"><label for="mvsp_ceshen">侧身急躁跑</label><input type="number" id="mvsp_ceshen" min="1" max="8" step="1" placeholder="5"></div><div style="flex:1 1 180px"><label for="mvsp_pangxie">螃蟹走路</label><input type="number" id="mvsp_pangxie" min="1" max="8" step="1" placeholder="2"></div><div style="flex:1 1 180px"><label for="mvsp_kaixin">开心小跑</label><input type="number" id="mvsp_kaixin" min="1" max="8" step="1" placeholder="1"></div></div><div class="sub" style="margin-top:14px">峰谷提示音（切入峰价/谷价时各播三遍，播完自动停）</div><div style="display:flex;gap:12px;flex-wrap:wrap"><div style="flex:1 1 200px"><label for="snd_Peak">进入峰价</label><select class="sndSel" id="snd_Peak" title="峰价提示音"></select></div><button type="button" class="sndTry" data-ev="Peak" title="试听">&#9654;</button><div style="flex:1 1 200px"><label for="snd_OffPeak">进入谷价</label><select class="sndSel" id="snd_OffPeak" title="谷价提示音"></select></div><button type="button" class="sndTry" data-ev="OffPeak" title="试听">&#9654;</button></div><div class="actions"><button class="primary" id="behApply" type="button">]=] .. applyText .. [=[</button></div><div class="status" id="behMsg"></div></div></section>]=]
  local h8 = [=[</main>]=]
  local h9 = [=[<script>window.onerror=function(m,s,l){var el=document.getElementById("message");if(el){el.textContent="JSERR "+m+" @"+l;el.className="status bad"}return false};window.addEventListener("unhandledrejection",function(e){var el=document.getElementById("message");if(el){el.textContent="REJ "+((e.reason&&e.reason.message)||e.reason);el.className="status bad"}});const API="]=] .. api_prefix .. [=[";const TXT={online:"]=] .. html_escape_js(onlineText) .. [=[",offline:"]=] .. html_escape_js(offlineText) .. [=[",wait:"]=] .. html_escape_js(waitText) .. [=[",loaded:"]=] .. html_escape_js(loadedText) .. [=[",readFail:"]=] .. html_escape_js(readFail) .. [=[",saving:"]=] .. html_escape_js(savingText) .. [=[",saveFail:"]=] .. html_escape_js(saveFail) .. [=[",saved:"]=] .. html_escape_js(savedText) .. [=[",reloading:"]=] .. html_escape_js(reloadingText) .. [=[",testing:"]=] .. html_escape_js(testingText) .. [=[",testOk:"]=] .. html_escape_js(testOk) .. [=[",testFail:"]=] .. html_escape_js(testFail) .. [=[",timeout:"]=] .. html_escape_js(timeoutText) .. [=[",cfgFail:"]=] .. html_escape_js(cfgFail) .. [=[",skinSaved:"]=] .. html_escape_js(skinSaved) .. [=[",skinFail:"]=] .. html_escape_js(skinFail) .. [=[",themeSaved:"]=] .. html_escape_js(themeSaved) .. [=[",behSaved:"]=] .. html_escape_js(behSaved) .. [=[",dispSaved:"]=] .. html_escape_js(dispSaved) .. [=["};const EVT_ZH={Idle:'待机',UserPromptSubmit:'接收指令',PreToolUse:'执行工具',PostToolUse:'检查结果',PermissionRequest:'等待确认',SubagentStart:'分派子任务',SubagentStop:'合并子任务',PreCompact:'压缩前',PostCompact:'压缩后',Error:'出错',Stop:'本轮完成',SessionStart:'会话开始',Sleeping:'休眠'};const evtName=n=>EVT_ZH[n]?EVT_ZH[n]+' ('+n+')':n;const $=id=>document.getElementById(id);const BASE=API.replace(/\/api$/,'');const assetUrl=p=>BASE+'/asset?p='+encodeURIComponent(p);const fields=['host','port','path','language'];let formDirty=false;fields.forEach(id=>{const node=$(id);node.addEventListener('input',()=>{formDirty=true});node.addEventListener('change',()=>{formDirty=true})});function path(v){v=(v||"").trim();return !v?"/events":v[0]==="/"?v:"/"+v}function url(){return "http://"+$('host').value.trim()+":"+$('port').value.trim()+path($('path').value)}function msg(t,c){$('message').textContent=t;$('message').className="status "+(c||"")}function syncForm(d,force){if(formDirty&&!force)return;$('host').value=d.host||"";$('port').value=d.port||17321;$('path').value=d.path||"/events";$('language').value=d.language_mode||"system";formDirty=false}function paint(d,sync,force){if(sync)syncForm(d,force);$('url').textContent=d.url||url();$('online').textContent=d.online?TXT.online:TXT.offline;$('dot').className="dot "+(d.online?"on":"");let f=d.font||{};$('font').textContent=(f.family||"-")+" · "+(f.rendering||"-");$('detail').textContent=f.error||d.detail||TXT.wait}
async function load(){const r=await fetch(API+"/state?_="+Date.now(),{cache:"no-store"});const d=await r.json();if(!r.ok)throw Error(d.error||TXT.readFail);paint(d,true,false);msg(TXT.loaded,"ok")}
$('form').onsubmit=async e=>{e.preventDefault();msg(TXT.saving,"");try{const q=new URLSearchParams({host:$('host').value.trim(),port:$('port').value.trim(),path:path($('path').value),language:$('language').value});const r=await fetch(API+"/save?"+q,{cache:"no-store"});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.saveFail);paint(d,true,true);msg(d.reload?TXT.reloading:TXT.saved,"ok");if(d.reload)setTimeout(()=>location.reload(),1800)}catch(e){msg(e.message,"bad")}};
$('test').onclick=async()=>{msg(TXT.testing+" "+url()+" ...","");const ctrl=new AbortController();const timer=setTimeout(()=>ctrl.abort(),3000);try{const base="http://"+$('host').value.trim()+":"+$('port').value.trim();const r=await fetch(base+"/health?_="+Date.now(),{cache:"no-store",signal:ctrl.signal});if(!r.ok)throw Error("HTTP "+r.status);msg(TXT.testOk,"ok")}catch(e){msg(TXT.testFail+(e.name==="AbortError"?TXT.timeout:e.message),"bad")}finally{clearTimeout(timer)}};load().catch(e=>msg(TXT.cfgFail+e.message,"bad"));setInterval(()=>fetch(API+"/state?_="+Date.now(),{cache:"no-store"}).then(r=>r.json()).then(d=>paint(d,false,false)).catch(()=>{}),2500);
function skinPaint(d){const s=(d&&d.skin)||{};const sel=$('skin');if(!sel)return;const cur=s.active||sel.value;sel.innerHTML='';(s.available||[]).forEach(x=>{const o=document.createElement('option');o.value=x.id;o.textContent=(x.name||x.id)+((x.name_en&&x.name_en!==x.name)?' / '+x.name_en:'');sel.appendChild(o)});if(cur)sel.value=cur;if(s.speed)$('speed').value=s.speed}
async function skinLoad(){try{const r=await fetch(API+"/skin?_="+Date.now(),{cache:"no-store"});const d=await r.json();skinPaint(d);themePaint(d);volFill(d);behPaint(d);dispPaint(d);galleryPaint(d);bindThemeInputs()}catch(e){var m=document.getElementById('skinMsg');if(m){m.textContent='E: '+e.message;m.className='status bad'}}}
function dispPaint(d){const m=((d&&d.skin)||{}).display||{};document.querySelectorAll('.dispSel').forEach(el=>{el.checked=m[el.value]!==false})}
$('dispApply').onclick=async()=>{const hide=[];document.querySelectorAll('.dispSel').forEach(el=>{if(!el.checked)hide.push(el.value)});$('dispMsg').textContent=TXT.saving;$('dispMsg').className="status";try{const r=await fetch(API+"/skin?"+new URLSearchParams({hide:hide.join(',')}),{cache:"no-store"});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.skinFail);dispPaint(d);$('dispMsg').textContent=TXT.behSaved;$('dispMsg').className="status ok"}catch(e){$('dispMsg').textContent=TXT.skinFail+e.message;$('dispMsg').className="status bad"}};
var LASTSNAP=null,SHOWALL={};var FLATN={};function flatNames(){const s=(LASTSNAP&&LASTSNAP.skin)||{};const names=s.names||{};FLATN={};Object.keys(names).forEach(k=>(names[k]||[]).forEach(v=>{if(v.base)FLATN[v.base]=v.label||v.base}));}
function paintCells(ev,group){const box=$('cells_'+ev);if(!box)return;const s=(LASTSNAP&&LASTSNAP.skin)||{};const acts=s.actions||{};const names=s.names||{};const vs=((s.behavior||{}).variants)||{};const conf=vs[group]||{};const en=Array.isArray(conf.enabled)?conf.enabled:[];const wk=Array.isArray(conf.walk)?conf.walk:[];let list=(acts[group]||[]).slice();if(SHOWALL[ev]){const seen={};list.forEach(function(x){seen[x]=1});const all=[];const cats=s.categories||[];if(cats.length){cats.forEach(function(c){(c.files||[]).forEach(function(f){all.push(f)})})}else{Object.keys(acts).forEach(function(g){(acts[g]||[]).forEach(function(f){all.push(f)})})}all.forEach(function(f){if(!seen[f]){seen[f]=1;list.push(f)}})}box.innerHTML='';list.forEach(f=>{const base=f.split('/').pop();let label=FLATN[base]||base;const cell=document.createElement('label');cell.className='vcell';cell.title=f+(wk.indexOf(base)>=0?'（走动时会自动左右翻转）':'');const img=document.createElement('img');img.src=assetUrl(f);cell.appendChild(img);const nm=document.createElement('span');nm.textContent=label;nm.style.cssText='font-size:11px;max-width:84px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';cell.appendChild(nm);const cbs=document.createElement('span');cbs.className='vcbs';const be=document.createElement('input');be.type='checkbox';be.className='varEn';be.dataset.g=group;be.dataset.ev=ev;be.dataset.f=base;be.checked=(en.length===0)||en.indexOf(base)>=0;const bw=document.createElement('input');bw.type='checkbox';bw.className='varWk';bw.dataset.g=group;bw.dataset.ev=ev;bw.dataset.f=base;bw.checked=wk.indexOf(base)>=0;cbs.appendChild(be);cbs.appendChild(bw);cell.appendChild(cbs);box.appendChild(cell)})}function walkPaint(d){const w=((d&&d.skin)||{}).walk||{};var a=[['w_pace',w.pace],['w_pause',w.pause],['w_len',w.len]];a.forEach(function(p){var el=document.getElementById(p[0]);if(el&&p[1])el.value=p[1]})}
var MOVE_MAP={ceshen:'ceshen-jizao-pao.gif',pangxie:'pangxie-zoulu.gif',kaixin:'kaixin-xiaopao.gif'};
function mvPaint(d){const mv=((d&&d.skin)||{}).moves||[];Object.keys(MOVE_MAP).forEach(function(s){const el=document.getElementById('mvsp_'+s);if(!el)return;const m=mv.find(function(x){return x.base===MOVE_MAP[s]});if(m&&m.speed!=null)el.value=m.speed});}
function behPaint(d){sndPaint(d);LASTSNAP={skin:(d&&d.skin)||LASTSNAP.skin};flatNames();LASTSNAP=d;const b=((d&&d.skin)||{}).behavior||{};const m=b.event_actions||{};const acts=((d&&d.skin)||{}).actions||{};Object.keys(acts).forEach(name=>{paintCells(name,m[name]||name)});walkPaint(d);volFill(d)}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('.more');if(!b)return;const ev=b.dataset.ev;SHOWALL[ev]=!SHOWALL[ev];const sel=$('map_'+ev);paintCells(ev,sel?sel.value:ev);b.textContent=SHOWALL[ev]?'收起':'全部'});
function galleryPaint(d){const g=$('gallery');if(!g)return;const s=(d&&d.skin)||{};const cats=s.categories||[];if(cats.length){g.innerHTML=cats.map(c=>{const fs=c.files||[];const imgs=fs.map(p=>'<img src="'+assetUrl(p)+'" title="'+p+'">').join('');return '<div class="grow"><div class="gname">'+c.id+' <span class="gcount">'+fs.length+'</span></div><div class="gimgs">'+imgs+'</div></div>'}).join('');return}const acts=s.actions||{};const keys=Object.keys(acts).sort();g.innerHTML=keys.map(k=>{const imgs=(acts[k]||[]).map(p=>'<img src="'+assetUrl(p)+'" title="'+p+'">').join('');return '<div class="grow"><div class="gname">'+evtName(k)+'</div><div class="gimgs">'+imgs+'</div></div>'}).join('')}
function sndPaint(d){const s=((d&&d.skin)||{});const list=s.sound_list||[];const cur=s.sounds||{};document.querySelectorAll('.sndSel').forEach(el=>{const n=el.id.slice(4);el.innerHTML='<option value="off">无</option>'+list.map(v=>'<option value="'+v+'">'+v+'</option>').join('');el.value=cur[n]&&cur[n]!=='off'?cur[n]:'off';});}
document.addEventListener('click',e=>{const b=e.target.closest&&e.target.closest('.sndTry');if(!b)return;const ev=b.dataset.ev;const sel=$('snd_'+ev);const v=sel?sel.value:'off';if(!v||v==='off'){return;}fetch(API+'/skin?test_snd='+encodeURIComponent(v),{cache:'no-store'}).catch(()=>{});});
$('behApply').onclick=async()=>{const mEl=$('behMsg');mEl.textContent=TXT.saving;mEl.className='status';try{const q=new URLSearchParams();['pace','pause','len'].forEach(function(k,i){var id=['w_pace','w_pause','w_len'][i];var el=document.getElementById(id);if(el)q.set('walk_'+k,el.value)});const used={};Object.keys(((LASTSNAP&&LASTSNAP.skin)||{}).actions||{}).forEach(function(n){used[n]=1});let r=await fetch(API+'/skin?'+q,{cache:'no-store'});let d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.skinFail);const groups=Object.keys(used);for(let k=0;k<groups.length;k++){const g=groups[k];const en=[],wk=[];document.querySelectorAll('.varEn[data-ev="'+g+'"]').forEach(i=>{if(i.checked)en.push(i.dataset.f)});document.querySelectorAll('.varWk[data-ev="'+g+'"]').forEach(i=>{if(i.checked)wk.push(i.dataset.f)});const q2=new URLSearchParams();q2.set('var_'+g,en.join(',')+'|'+wk.join(',')+'|seq');const r2=await fetch(API+'/skin?'+q2,{cache:'no-store'});const d2=await r2.json();if(!r2.ok||!d2.ok)throw Error((d2&&d2.error)||TXT.skinFail);d=d2}const q3=new URLSearchParams();document.querySelectorAll('.sndSel').forEach(el=>{const n=el.id.slice(4);q3.set('snd_'+n,el.value||'off')});Object.keys(MOVE_MAP).forEach(function(s){var e=document.getElementById('mvsp_'+s);if(e&&e.value)q3.set('mvsp_'+s,e.value)});const r3=await fetch(API+'/skin?'+q3,{cache:'no-store'});const d3=await r3.json();if(!r3.ok||!d3.ok)throw Error((d3&&d3.error)||TXT.skinFail);d=d3;behPaint(d);mEl.textContent=TXT.behSaved;mEl.className='status ok'}catch(e){mEl.textContent=TXT.skinFail+(e&&e.message||e);mEl.className='status bad'}};const THEME_DEF={bg:'#0B1512',panel:'#13241C',track:'#223A2E',fg:'#F2FBF6',dim:'#7E9C8C',accent:'#4ADE80',warn:'#FBBF24',error:'#F87171'};function bindThemeInputs(){Object.keys(THEME_DEF).forEach(k=>{const el=$('t_'+k);if(el)el.addEventListener('input',drawFigs)});const sc=$('t_scale');if(sc)sc.addEventListener('input',()=>scaleLabel(sc.value));const sv=$('s_vol');if(sv)sv.addEventListener('input',()=>volLabel_(sv.value/100))}
function figColors(){const o={};Object.keys(THEME_DEF).forEach(k=>{const el=$('t_'+k);o[k]=(el&&el.value)||THEME_DEF[k]});return o}
function drawFigs(){const _a=$('figA'),_b=$('figB');if(!_a||!_b)return;const c=figColors();const cvA=$('figA'),cvB=$('figB');if(!cvA||!cvB)return;
let x=cvA.getContext('2d');x.clearRect(0,0,320,240);x.fillStyle=c.bg;x.fillRect(0,0,320,240);
x.fillStyle=c.panel;x.fillRect(0,0,320,26);x.fillStyle=c.line;x.fillRect(0,26,320,1);
x.fillStyle=c.fg;x.fillRect(10,9,58,9);x.fillStyle=c.dim;x.fillRect(206,11,42,6);x.fillRect(258,11,46,6);
x.beginPath();x.arc(160,104,58,0,7);x.fillStyle=c.panel;x.fill();x.strokeStyle=c.line;x.lineWidth=3;x.stroke();
x.beginPath();x.arc(160,104,16,0,7);x.fillStyle=c.accent;x.fill();
x.fillStyle=c.panel;x.fillRect(0,196,320,44);x.fillStyle=c.line;x.fillRect(0,196,320,1);
x.fillStyle=c.fg;x.fillRect(8,206,64,14);x.fillStyle=c.dim;x.fillRect(120,208,88,9);
x.fillStyle=c.warn;x.fillRect(232,208,36,9);x.fillStyle=c.error;x.fillRect(276,208,34,9);
x.fillStyle=c.accent;x.fillRect(178,228,84*0.42,4);
x=cvB.getContext('2d');x.clearRect(0,0,320,240);x.fillStyle=c.bg;x.fillRect(0,0,320,240);
x.fillStyle=c.fg;x.fillRect(10,8,120,9);x.fillStyle=c.dim;x.fillRect(258,10,46,6);
x.fillStyle=c.panel;x.fillRect(4,24,312,110);x.strokeStyle=c.line;x.lineWidth=2;x.strokeRect(5,25,310,108);
x.fillStyle=c.fg;x.fillRect(12,32,96,8);x.fillStyle=c.dim;x.fillRect(200,32,80,8);
x.fillStyle=c.panel;x.fillRect(8,44,304,22);x.fillStyle=c.accent;x.fillRect(8,44,304,22);
x.fillStyle=c.bg;x.fillRect(14,51,88,9);x.fillStyle=c.dim;x.fillRect(8,74,280,8);x.fillRect(8,88,280,8);x.fillRect(8,102,280,8);
x.fillStyle=c.panel;x.fillRect(4,136,96,92);x.fillRect(104,136,212,92);
x.fillStyle=c.accent;x.fillRect(112,142,39,16);x.fillStyle=c.fg;x.fillRect(160,144,140,12);
x.fillStyle=c.line;x.fillRect(110,166,200,6);x.fillStyle=c.accent;x.fillRect(110,166,200*0.42,6);
x.fillStyle=c.dim;x.fillRect(110,180,160,10);x.fillStyle=c.accent;x.fillRect(110,196,200*0.29,4);
x.fillStyle=c.warn;x.fillRect(110,196,200*0.125,4)}
function scaleLabel(v){const el=$('t_scale_val');if(el)el.textContent=Math.round(Number(v)*100)+'%'}
function volFill(d){const s=((d&&d.skin)||{});const v=(typeof s.sound_volume==='number')?s.sound_volume:0.8;const el=$('s_vol');if(el){el.value=Math.round(v*100);volLabel_(v)}}
function volPush(){
  var el=document.getElementById('s_vol'); if(!el) return;
  var v=parseInt(el.value,10)||0;
  var lbl=document.getElementById('s_vol_val'); if(lbl) lbl.textContent=v+'%';
  clearTimeout(window.__volT);
  window.__volT=setTimeout(function(){
    fetch(API+'/skin?sound_volume='+v,{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){
      var m=document.getElementById('message'); if(m){m.textContent='音量 '+v+'%'; m.className='status ok'}
    }).catch(function(){});
  },220);
}
document.addEventListener('DOMContentLoaded',function(){var el=document.getElementById('s_vol');if(el)el.addEventListener('input',volPush)});
function volLabel_(v){const el=$('s_vol_val');if(el)el.textContent=Math.round(v*100)+'%'}
function themePaint(d){const t=((d&&d.skin)||{}).theme||{};Object.keys(THEME_DEF).forEach(k=>{const el=$('t_'+k);if(el)el.value=String(t[k]||THEME_DEF[k]).toUpperCase()});const sc=Number(t.font_scale||1);$('t_scale').value=sc.toFixed(2);scaleLabel(sc);drawFigs()}
async function askRestart(){
    if(!confirm('配色/字号改动需要重启应用才生效，现在重启吗？\n取消则稍后手动重启。')) return;
    try{
      await fetch('/api/system/exit',{method:'POST'});
      setTimeout(()=>fetch('/api/system/launch?id=dsh_fish',{method:'POST'}),900);
      document.body.innerHTML='<div style="padding:40px;font:16px sans-serif;color:#ccc">正在重启应用…</div>';
    }catch(e){}
  }
  $('themeReset').onclick=()=>{Object.keys(THEME_DEF).forEach(k=>{const el=$('t_'+k);if(el)el.value=THEME_DEF[k]});const sc=$('t_scale');if(sc)sc.value='1';$('themeMsg').textContent='已填回默认配色，点「应用」后生效';$('themeMsg').className='status'};
  $('themeApply').onclick=async()=>{const q=new URLSearchParams();const svEl=$('s_vol');if(svEl)q.set('sound_volume',svEl.value);Object.keys(THEME_DEF).forEach(k=>q.set('theme_'+k,$('t_'+k).value));q.set('theme_scale',$('t_scale').value);$('themeMsg').textContent=TXT.saving;$('themeMsg').className="status";try{const r=await fetch(API+"/skin?"+q,{cache:"no-store"});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.skinFail);themePaint(d);$('themeMsg').textContent=TXT.themeSaved;$('themeMsg').className="status ok";await askRestart()}catch(e){$('themeMsg').textContent=TXT.skinFail+e.message;$('themeMsg').className="status bad"}};
$('themeReset').onclick=()=>{Object.keys(THEME_DEF).forEach(k=>{const el=$('t_'+k);if(el)el.value=THEME_DEF[k]})};
$('skinApply').onclick=async()=>{const q=new URLSearchParams({active:$('skin').value,speed:$('speed').value});$('skinMsg').textContent=TXT.saving;$('skinMsg').className="status";try{const r=await fetch(API+"/skin?"+q,{cache:"no-store"});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.skinFail);skinPaint(d);behPaint(d);galleryPaint(d);$('skinMsg').textContent=TXT.skinSaved;$('skinMsg').className="status ok"}catch(e){$('skinMsg').textContent=TXT.skinFail+e.message;$('skinMsg').className="status bad"}};
$('skinHide').onclick=async()=>{const id=$('skin').value;if(!id)return;try{const r=await fetch(API+"/skin/hide?id="+encodeURIComponent(id),{cache:"no-store"});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.skinFail);skinPaint(d);$('skinMsg').textContent=TXT.saved;$('skinMsg').className="status ok"}catch(e){$('skinMsg').textContent=TXT.skinFail+e.message;$('skinMsg').className="status bad"}};

  $('skinUnhide').onclick=async()=>{try{const r=await fetch(API+"/skin?hidden=",{cache:"no-store"});const d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||TXT.skinFail);skinPaint(d);$('skinMsg').textContent=TXT.saved;$('skinMsg').className="status ok"}catch(e){$('skinMsg').textContent=TXT.skinFail+e.message;$('skinMsg').className="status bad"}};skinLoad();</script></body></html>]=]
  return h0 .. h1 .. h2 .. h3 .. h4 .. h5 .. h6 .. h7 .. h8 .. h9
end

function Web.new(opts)
  opts = opts or {}
  local self = {
    config = opts.config or {},
    config_path = opts.config_path or "/sd/apps/dsh_fish/config.lua",
    route_base = opts.route_base or "/dsh_fish",
    api_prefix = (opts.route_base or "/dsh_fish") .. "/api",
    restart = opts.restart,
    reload_app = opts.reload_app,
    refresh_weather = opts.refresh_weather,
    set_page = opts.set_page,
    skin_state = opts.skin_state, play_sound = opts.play_sound,
    apply_skin = opts.apply_skin,
    app_dir = opts.app_dir,
    connection_state = opts.connection_state,
    language = tostring(opts.language or "en"),
    requested_language = tostring(opts.requested_language or opts.language or "en"),
    system_language = tostring(opts.system_language or opts.requested_language or opts.language or "en"),
    routes = {},
    started = false,
  }

  function self:snapshot(ok, message)
    local extra = self.connection_state and self.connection_state() or {}
    local host = tostring(self.config.host or "")
    local port = tonumber(self.config.port) or 17321
    local path = normalize_path(self.config.path)
    return {
      ok = ok ~= false, host = host, port = port, path = path,
      version = extra.version,
      url = "http://" .. host .. ":" .. tostring(port) .. path,
      weather_address = settings_weather_address(),
      online = extra.online == true, detail = extra.detail or message or "",
      state = extra.state or "idle", event = extra.event or "",
      source = extra.source or "",
      model = extra.model or "",
      effort = extra.effort or "",
      context = extra.context,
      usage = extra.usage,
      memory = extra.memory,
      language = self.language,
      requested_language = self.requested_language,
      system_language = self.system_language,
      language_mode = normalize_language_mode(self.config.language),
      idle_variant = extra.idle_variant,
      idle_delay_minutes = extra.idle_delay_minutes,
      clock = extra.clock,
      page = extra.page,
      visual_group = extra.visual_group,
      visual_index = extra.visual_index,
      weather = extra.weather,
      weather_visual = extra.weather_visual,
      weather_sync = extra.weather_sync,
      activity = extra.activity,
      session_meme = extra.session_meme,
      font = extra.font,
      chat_timer = extra.chat_timer or "", state_timer = extra.state_timer or "",
      skin = self.skin_state and self.skin_state() or nil,
      error = ok == false and message or nil,
    }
  end

  function self:register(method, route, handler)
    if not httpd or not httpd.dynamic then return false, "httpd missing" end
    local ok, err = pcall(function() return httpd.dynamic(method, route, handler) end)
    if not ok or err then return false, tostring(err) end
    self.routes[#self.routes + 1] = { method = method, route = route }
    return true
  end

  function self:save(req)
    local q = parse_query(req and req.query or "")
    local host, port, path = trim(q.host), tonumber(q.port), normalize_path(q.path)
    if not valid_ipv4(host) then return json_response("400 Bad Request", self:snapshot(false, W(self.language, "Please enter a valid IPv4 address", "请输入有效的 IPv4 地址"))) end
    if not port or port < 1 or port > 65535 then return json_response("400 Bad Request", self:snapshot(false, W(self.language, "Port must be between 1 and 65535", "端口需为 1 到 65535"))) end
    local previous_language = normalize_language_mode(self.config.language)
    local language_mode = q.language ~= nil and normalize_language_mode(q.language) or previous_language
    local language_changed = language_mode ~= previous_language
    self.config.host, self.config.port, self.config.path = host, math.floor(port), path
    self.config.language = language_mode
    local weather_address = trim(q.weather or q.weather_address or "")
    if weather_address ~= "" then
      local weather_ok, weather_err = save_weather_address(weather_address)
      if not weather_ok then return json_response("500 Internal Server Error", self:snapshot(false, W(self.language, "Failed to save weather city: ", "天气地址保存失败: ") .. tostring(weather_err))) end
    end
    local ok, err = write_config(self.config_path, self.config)
    if not ok then return json_response("500 Internal Server Error", self:snapshot(false, W(self.language, "Failed to write config: ", "配置写入失败: ") .. tostring(err))) end
    local result = self:snapshot(true, "saved")
    result.reload = language_changed
    if language_changed then
      if self.reload_app then pcall(self.reload_app) end
    else
      if self.restart then pcall(self.restart) end
      if self.refresh_weather then pcall(self.refresh_weather) end
    end
    return json_response("200 OK", result)
  end

  function self:start()
    if self.started or not httpd or not httpd.start then return end
    pcall(function() httpd.start({ webroot = "/sd", auto_index = httpd.INDEX_NONE, max_handlers = 36 }) end)
    self:register(httpd.GET, self.route_base, function() return response("200 OK", "text/html; charset=utf-8", build_html(self.api_prefix, self.language)) end)
    self:register(httpd.GET, self.route_base .. "/", function() return response("200 OK", "text/html; charset=utf-8", build_html(self.api_prefix, self.language)) end)
    self:register(httpd.GET, self.route_base .. "/asset", function(req)
      -- 把应用目录下的素材原样吐给浏览器，用于管理页里的 GIF 预览
      local q = parse_query(req and req.query or "")
      local rel = tostring(q.p or "")
      if rel == "" or rel:find("..", 1, true) or rel:sub(1, 1) == "/" then
        return response("400 Bad Request", "text/plain; charset=utf-8", "bad path")
      end
      local full = tostring(self.app_dir or "") .. "/" .. rel
      local data = file and file.getcontents and file.getcontents(full)
      if not data or data == "" then
        return response("404 Not Found", "text/plain; charset=utf-8", "not found")
      end
      local ext = tostring(rel:match("%.([%w]+)$") or ""):lower()
      local mime = "application/octet-stream"
      if ext == "gif" then mime = "image/gif"
      elseif ext == "png" then mime = "image/png"
      elseif ext == "webp" then mime = "image/webp" end
      return response("200 OK", mime, data, "public, max-age=86400")
    end)
    self:register(httpd.GET, self.api_prefix .. "/state", function() return json_response("200 OK", self:snapshot(true, "loaded")) end)
    self:register(httpd.GET, self.api_prefix .. "/page", function(req)
      local q = parse_query(req and req.query or "")
      if self.set_page then pcall(self.set_page, q.name or "status") end
      return json_response("200 OK", self:snapshot(true, "page"))
    end)
    self:register(httpd.GET, self.api_prefix .. "/save", function(req) return self:save(req) end)
    local EVENT_NAMES = { "Idle", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
                          "Error", "Stop", "SessionStart", "SubagentStart", "SubagentStop",
                          "PreCompact", "PostCompact", "Sleeping" }
    self:register(httpd.GET, self.api_prefix .. "/skin", function(req)
      local q = parse_query(req and req.query or "")
      local patch = {}
      local active = trim(q.active or "")
      local speed = trim(q.speed or "")
      if active ~= "" then patch.active = active end
      if speed ~= "" then patch.speed = speed end
      local theme = {}
      for _, key in ipairs({ "bg", "panel", "track", "fg", "dim", "accent", "warn", "error" }) do
        local value = trim(q["theme_" .. key] or "")
        if value ~= "" then theme[key] = value end
      end
      local walk = {}
      for _, key in ipairs({ "pace", "pause", "len" }) do
        local value = trim(q["walk_" .. key] or "")
        if value ~= "" then walk[key] = value end
      end
      if next(walk) then patch.walk = walk end
      local scale = tonumber(q.theme_scale)
      if scale then theme.font_scale = math.max(0.8, math.min(1.4, scale)) end
      if next(theme) then patch.theme = theme end
      local behavior = {}
      if q.walk ~= nil then
        local list = {}
        for item in string.gmatch(trim(q.walk or ""), "[^,]+") do
          local name = trim(item)
          if name ~= "" then list[#list + 1] = name end
        end
        behavior.walk_states = list
      end
      local mapping = {}
      for _, name in ipairs(EVENT_NAMES) do
        local value = trim(q["map_" .. name] or "")
        if value ~= "" then mapping[name] = value end
      end
      if next(mapping) then behavior.event_actions = mapping end
      -- 变体配置：var_<组>=启用文件1,启用文件2|可走动文件1,可走动文件2|seq|random
      local variants = {}
      for _, name in ipairs(EVENT_NAMES) do
        local raw = q["var_" .. name]
        if raw ~= nil then
          local enabled_text, walk_text, mode = raw, "", "seq"
          local p1 = string.find(raw, "|", 1, true)
          if p1 then
            enabled_text = string.sub(raw, 1, p1 - 1)
            local rest = string.sub(raw, p1 + 1)
            local p2 = string.find(rest, "|", 1, true)
            if p2 then
              walk_text = string.sub(rest, 1, p2 - 1)
              mode = trim(string.sub(rest, p2 + 1))
            else
              walk_text = rest
            end
          end
          if mode ~= "random" then mode = "seq" end
          local en, wk = {}, {}
          for item in string.gmatch(trim(enabled_text), "[^,]+") do
            local v = trim(item)
            if v ~= "" then en[#en + 1] = v end
          end
          for item in string.gmatch(trim(walk_text), "[^,]+") do
            local v = trim(item)
            if v ~= "" then wk[#wk + 1] = v end
          end
          variants[name] = { mode = mode, enabled = en, walk = wk }
        end
      end
      if next(variants) then behavior.variants = variants end
      if next(behavior) then patch.behavior = behavior end
      -- 音效：snd_<事件>=<音效名>（空或 off 表示关闭）
      local sounds = {}
      for _, name in ipairs(EVENT_NAMES) do
        local raw = q["snd_" .. name]
        if raw ~= nil then
          local value = trim(raw)
          sounds[name] = (value == "" or value == "off") and "off" or value
        end
      end
      -- 三个位移动作的平移速度（像素/拍）
      local MOVE_KEYS = { ceshen = "ceshen-jizao-pao.gif", pangxie = "pangxie-zoulu.gif", kaixin = "kaixin-xiaopao.gif" }
      local msp = {}
      for slug, base in pairs(MOVE_KEYS) do
        local raw = q["mvsp_" .. slug]
        if raw ~= nil then
          local n = tonumber(trim(raw))
          if n then msp[base] = math.max(1, math.min(8, math.floor(n))) end
        end
      end
      if next(msp) then patch.move_speed = msp end
      -- 峰谷切换提示音（不挂在 13 个事件上，单独两项）
      for _, name in ipairs({ "Peak", "OffPeak" }) do
        local raw = q["snd_" .. name]
        if raw ~= nil then
          local value = trim(raw)
          sounds[name] = (value == "" or value == "off") and "off" or value
        end
      end
      if next(sounds) then patch.sounds = sounds end
      -- 音量：sound_volume=0..100
      local sv = tonumber(trim(q.sound_volume or ""))
      if sv then
        if sv < 0 then sv = 0 elseif sv > 100 then sv = 100 end
        patch.sound_volume = sv / 100
      end
      -- 试听：test_snd=<音效名>
      local test_snd = trim(q.test_snd or "")
      if test_snd ~= "" and self.play_sound then
        pcall(self.play_sound, test_snd)
      end
      local display = {}
      local hide = trim(q.hide or "")
      local hid = trim(q.hidden or "")
  if q.hidden ~= nil then
    local list = {}
    for item in string.gmatch(hid, "[^,]+") do
      local name = trim(item)
      if name ~= "" then list[#list + 1] = name end
    end
    patch.hidden = list
  end
  if q.hide ~= nil then
        local shown = {}
        for item in string.gmatch(hide, "[^,]+") do
          local name = trim(item)
          if name ~= "" then shown[name] = true end
        end
        for _, key in ipairs({ "a_title", "a_live", "a_clock", "a_gif", "a_state", "a_project", "a_source",
                               "a_timers", "a_usage", "b_title", "b_clock", "b_log", "b_state",
                               "b_timeline", "b_meme", "b_context" }) do
          if shown[key] then display[key] = false end
        end
      end
      if q.hide ~= nil then patch.display = display end
      if (patch.active or patch.speed or patch.theme or patch.behavior or patch.display or patch.hidden or patch.sounds or patch.sound_volume or patch.walk or patch.move_speed) and self.apply_skin then
        local ok, err = pcall(self.apply_skin, patch)
        if not ok then
          return json_response("500 Internal Server Error",
            self:snapshot(false, W(self.language, "Failed to switch skin: ", "切换皮肤失败: ") .. tostring(err)))
        end
      end
      return json_response("200 OK", self:snapshot(true, "skin"))
    end)
    self:register(httpd.GET, self.api_prefix .. "/skin/hide", function(req)
      local q = parse_query(req and req.query or "")
      local id = trim(q.id or "")
      local current = self.skin_state and self.skin_state() or {}
      if id == "" or id == current.active then
        return json_response("400 Bad Request",
          self:snapshot(false, W(self.language, "Cannot hide the active skin", "不能隐藏正在使用的皮肤")))
      end
      -- 隐藏 = 记进排除清单，皮肤目录仍在设备上，随时可以恢复
      local hidden = {}
      for _, old in ipairs((self.skin_state and self.skin_state().hidden) or {}) do
        if old ~= id then hidden[#hidden + 1] = old end
      end
      hidden[#hidden + 1] = id
      if self.apply_skin then pcall(self.apply_skin, { hidden = hidden }) end
      return json_response("200 OK", self:snapshot(true, "hidden"))
    end)
    if app and app.set_webui then pcall(function() app.set_webui(true) end) end
    self.started = true
  end

  function self:stop()
    if httpd and httpd.unregister then
      for i = #self.routes, 1, -1 do
        local item = self.routes[i]
        pcall(function() httpd.unregister(item.method, item.route) end)
      end
    end
    self.routes = {}
    if app and app.set_webui then pcall(function() app.set_webui(false) end) end
    self.started = false
  end

  return self
end

Web.build_html = build_html
Web.config_text = config_text
Web.normalize_language_mode = normalize_language_mode

return Web
