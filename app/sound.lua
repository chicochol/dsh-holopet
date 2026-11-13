-- 音效播放：读取 assets/sounds/*.wav，用板载 I2S 输出 PCM。
-- 分块写入 + 定时器驱动，避免一次性 write 长时间阻塞 UI。

local Sound = {}

local CHUNK = 1024          -- 每次写入的字节数（16k/16bit 单声道约 32ms）
local PORT = 0              -- i2s.start 的端口号，0 为默认

local S = {
  playing = false,
  timer = nil,
  chunks = nil,
  index = 1,
  rate = 16000,
  channels = 1,
  bits = 16,
  volume = 1.0,
}

local function u8(s, i)
  local v = string.byte(s, i)
  return v and v or 0
end

local function u16(s, i)
  return u8(s, i) + u8(s, i + 1) * 256
end

local function u32(s, i)
  return u8(s, i) + u8(s, i + 1) * 256 + u8(s, i + 2) * 65536 + u8(s, i + 3) * 16777216
end

-- 解析 RIFF/WAVE，返回 pcm 数据与参数；非 WAV 返回 nil
local function parse_wav(data)
  if type(data) ~= "string" or #data < 44 then return nil end
  if data:sub(1, 4) ~= "RIFF" or data:sub(9, 12) ~= "WAVE" then return nil end
  local pos = 13
  local rate, channels, bits = 16000, 1, 16
  while pos + 8 <= #data do
    local id = data:sub(pos, pos + 3)
    local size = u32(data, pos + 4)
    if id == "fmt " then
      channels = u16(data, pos + 10)
      rate = u32(data, pos + 12)
      bits = u16(data, pos + 22)
    elseif id == "data" then
      local from = pos + 8
      local to = from + size - 1
      if to > #data then to = #data end
      return data:sub(from, to), rate, channels, bits
    end
    pos = pos + 8 + size + (size % 2)
  end
  return nil
end

-- 按 16bit 有符号的幅度缩放（volume 0..1），其它位宽原样返回
local function apply_volume(pcm, bits, volume)
  if not volume or volume >= 0.999 or bits ~= 16 then return pcm end
  local out = {}
  local n = #pcm - (#pcm % 2)
  for i = 1, n, 2 do
    local v = u16(pcm, i)
    if v >= 32768 then v = v - 65536 end
    v = math.floor(v * volume)
    if v < -32768 then v = -32768 elseif v > 32767 then v = 32767 end
    if v < 0 then v = v + 65536 end
    out[#out + 1] = string.char(v % 256, math.floor(v / 256) % 256)
  end
  return table.concat(out)
end

function Sound.is_playing()
  return S.playing
end

function Sound.stop()
  if S.timer then
    pcall(function() S.timer:stop() end)
    pcall(function() S.timer:close() end)
    S.timer = nil
  end
  if S.playing then
    pcall(function() i2s.stop(PORT) end)
  end
  S.playing = false
  S.chunks = nil
  S.index = 1
end

-- 播放 assets/sounds/<name>.wav；正在播放时直接返回 false（不排队，避免叠音）
function Sound.play(app_dir, name, times)
  if type(name) ~= "string" or name == "" or name == "off" then return false end
  if S.playing then return false end
  if not (i2s and i2s.start and i2s.write) then return false end
  local path = app_dir .. "/assets/sounds/" .. name .. ".wav"
  if not (file and file.exists and file.exists(path)) then return false end
  local ok, data = pcall(file.getcontents, path)
  if not ok or not data then return false end
  local pcm, rate, channels, bits = parse_wav(data)
  if not pcm or #pcm == 0 then return false end
  pcm = apply_volume(pcm, bits, S.volume)

  local chunks = {}
  local i = 1
  while i <= #pcm do
    chunks[#chunks + 1] = pcm:sub(i, i + CHUNK - 1)
    i = i + CHUNK
  end
  if #chunks == 0 then return false end

  local started = pcall(function()
    i2s.start(PORT, { rate = rate, bits = bits, channels = channels, mode = i2s.MODE_TX })
  end)
  if not started then return false end

  S.playing = true
  S.repeat_left = math.max(0, (tonumber(times) or 1) - 1)
  S.chunks = chunks
  S.index = 1
  S.rate = rate
  S.timer = tmr.create()
  S.timer:alarm(1, tmr.ALARM_AUTO, function()
    local c = S.chunks and S.chunks[S.index]
    if not c then
      -- 需要重复播放（如峰谷提示音播三遍）时回到开头
      if (S.repeat_left or 0) > 0 then
        S.repeat_left = S.repeat_left - 1
        S.index = 1
        return
      end
      Sound.stop()
      return
    end
    local okw = pcall(function() i2s.write(PORT, c) end)
    if not okw then
      Sound.stop()
      return
    end
    S.index = S.index + 1
  end)
  return true
end

function Sound.set_volume(v)
  v = tonumber(v)
  if not v then return end
  if v < 0 then v = 0 elseif v > 1 then v = 1 end
  S.volume = v
end

-- 列出可用音效：根目录的 *.wav 与子目录（主题组）里的 *.wav，
-- 子目录里的返回 "组名/音效名"，例如 "soft/done"
local function entry_name(e)
  if type(e) == "string" then return e end
  if type(e) == "table" then return e.name or e[1] end
  return nil
end

local function scan_wavs(dir)
  local out = {}
  local ok, entries = pcall(file.listdir, dir)
  if not ok or type(entries) ~= "table" then return out end
  for _, e in ipairs(entries) do
    local n = entry_name(e)
    local base = type(n) == "string" and n:match("^(.+)%.wav$") or nil
    if base then out[#out + 1] = base end
  end
  table.sort(out)
  return out
end

function Sound.list(app_dir)
  local root = app_dir .. "/assets/sounds"
  local out = scan_wavs(root)
  local ok, entries = pcall(file.listdir, root)
  if ok and type(entries) == "table" then
    for _, e in ipairs(entries) do
      local n = entry_name(e)
      if type(n) == "string" and not n:match("%.wav$") then
        local sub = scan_wavs(root .. "/" .. n)
        for _, base in ipairs(sub) do
          out[#out + 1] = n .. "/" .. base
        end
      end
    end
  end
  return out
end

return Sound
