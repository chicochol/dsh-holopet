"""skin_state 里给 variants 做文件名校验：旧皮肤残留的文件名在新皮肤里不存在就丢掉，全丢则回退全量。"""
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "build" / "dsh_fish" / "main.lua"
t = P.read_text(encoding="utf-8")

old = """      local cfg = variants[g]
      if type(cfg) == "table" and type(cfg.enabled) == "table" and #cfg.enabled > 0 then
        filled[g] = cfg
      else
        local en = {}
        for i = 1, #list do
          en[i] = tostring(list[i]):match("([^/]+)$") or tostring(list[i])
        end
        filled[g] = { mode = "seq", enabled = en, walk = (type(cfg) == "table" and cfg.walk) or {} }
      end"""

new = """      local cfg = variants[g]
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
      end"""

assert old in t, "anchor not found"
t = t.replace(old, new, 1)
P.write_text(t, encoding="utf-8", newline="\n")
print("variant validation applied")
