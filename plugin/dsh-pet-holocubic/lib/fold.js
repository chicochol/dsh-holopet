/**
 * dsh-holocubic 纯折叠层。
 *
 * 这一层只做一件事：把 DSH 的 `session/event`（以及会话对象）折叠成
 * HoloCubic 直接可用的一个状态快照。它不 import 任何 DSH 包、不碰网络、
 * 不读全局变量，因此 selftest.mjs 可以用假事件直接驱动。
 *
 * 设备端只认识 8 个状态：
 *   idle / thinking / working / building / notification / done / error / sleeping
 *
 * 其中 notification / done / error 是“瞬时状态”：只保持 8 秒，随后回落到
 * 一个持续状态（策略见 enterTransient 的注释）。
 */

/** 设备可显示的 8 个状态。 */
export const STATES = Object.freeze([
  'idle',
  'thinking',
  'working',
  'building',
  'notification',
  'done',
  'error',
  'sleeping',
])

/** 设备端协议允许的 11 个 holopet 事件名，`event` 字段只能取这些值。 */
export const DEVICE_EVENTS = Object.freeze([
  'SessionStart',
  'UserPromptSubmit',
  'PreToolUse',
  'PermissionRequest',
  'PostToolUse',
  'PreCompact',
  'PostCompact',
  'SubagentStart',
  'SubagentStop',
  'Stop',
  'AgentResume',
])

/** 超过 5 分钟没有任何事件 → idle。 */
export const IDLE_MS = 5 * 60 * 1000

/** 再空闲 30 分钟 → sleeping（设备可以熄屏/进入待机画面）。 */
export const SLEEP_MS = 30 * 60 * 1000

/** notification / done / error 的保持时长。 */
export const TRANSIENT_MS = 8 * 1000

/** 上下文窗口，用于把 inputTokens 折算成 0..1 的 ctx。
 *  DSH 的模型配置里 deepseek-v4.1-flash 是 1,000,000，Hunyuan 一类是 960,000。
 *  这里取 1M 作为默认；换小窗口模型时请在 patch 的 config 里覆盖。 */
export const CONTEXT_WINDOW = 1000000

/** history 最多保留的条数。 */
export const HISTORY_MAX = 6

const EVENT_NAME_SET = new Set(DEVICE_EVENTS)
const TRANSIENT_STATES = new Set(['notification', 'done', 'error'])
const DURABLE_STATES = new Set(['idle', 'thinking', 'working', 'building', 'sleeping'])

/** 未知事件直接忽略；这里列出我们会消费的事件类型。 */
const KNOWN_EVENT_TYPES = new Set([
  'turn/start',
  'turn/end',
  'assistant/chunk',
  'assistant/message',
  'tool/call',
  'tool/result',
  'approval/asked',
  'approval/decided',
  'request/header',
  'model/selection',
  'compaction/start',
  'compaction/summary',
  'compaction/prune',
  'session/start',
  'session/created',
  'session/resume',
  'session/resumed',
])

const TOOL_MAX = 40
const PROJECT_MAX = 40
const SESSION_MAX = 64

/* ------------------------------------------------------------------ */
/* 防御性读取                                                          */
/* ------------------------------------------------------------------ */

function isObj(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function finiteNum(v) {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    if (Number.isFinite(n)) return n
  }
  return null
}

function clip(v, max) {
  const s = typeof v === 'string' ? v : v == null ? '' : String(v)
  return s.length > max ? s.slice(0, max) : s
}

/** 取路径最后一段，兼容 Windows 反斜杠和结尾分隔符。 */
function basenameOf(p) {
  const raw = typeof p === 'string' ? p.trim() : ''
  if (raw === '') return ''
  const s = raw.replace(/[\\/]+$/, '')
  if (s === '') return ''
  const i = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'))
  return i >= 0 ? s.slice(i + 1) : s
}

/**
 * 事件时间的毫秒值。DSH 一般给 `time`（毫秒），旧日志可能给秒或 ISO 字符串。
 */
function eventTimeMs(event, fallback) {
  const raw = isObj(event)
    ? event.time ?? event.ts ?? event.createdAt ?? event.timestamp
    : undefined
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    return Math.round(raw < 1e12 ? raw * 1000 : raw)
  }
  if (typeof raw === 'string' && raw !== '') {
    const n = Date.parse(raw)
    if (Number.isFinite(n)) return n
  }
  return fallback
}

/**
 * 兼容两种事件形状：
 *   { type: 'tool/call', data: { name: 'bash' } }
 *   { type: 'tool/call', name: 'bash' }
 * data 里的字段覆盖顶层同名字段；缺哪层都不抛异常。
 */
export function readEventData(event) {
  const out = {}
  if (!isObj(event)) return out
  for (const key of Object.keys(event)) {
    if (key === 'type' || key === 'data') continue
    out[key] = event[key]
  }
  if (isObj(event.data)) Object.assign(out, event.data)
  return out
}

/** turn/end 的 reason 可能是字符串，也可能是 { kind: 'completed' }。 */
function reasonKind(raw) {
  if (typeof raw === 'string') return raw
  if (isObj(raw) && typeof raw.kind === 'string') return raw.kind
  return ''
}

/** 从 tool/call 的 data 里取工具名。 */
function toolNameOf(d) {
  const cands = [
    d.name,
    d.tool,
    d.toolName,
    isObj(d.call) ? d.call.name : undefined,
  ]
  for (const c of cands) {
    if (typeof c === 'string' && c.trim() !== '') return clip(c.trim(), TOOL_MAX)
  }
  return ''
}

/** 子代理事件的开始/结束分类。 */
function subagentKind(type) {
  if (typeof type !== 'string' || !type.startsWith('subagent/')) return ''
  const tail = type.slice('subagent/'.length).toLowerCase()
  if (['descriptor', 'start', 'started', 'spawn', 'spawned', 'resume', 'resumed'].includes(tail)) {
    return 'start'
  }
  if (['settled', 'stop', 'stopped', 'end', 'ended', 'done', 'complete', 'completed', 'error', 'failed'].includes(tail)) {
    return 'end'
  }
  return 'other'
}

/** 从 assistant/message 的 data 里找 usage。 */
function usageOf(d) {
  const cands = [
    d.usage,
    isObj(d.message) ? d.message.usage : undefined,
    isObj(d.result) ? d.result.usage : undefined,
  ]
  for (const u of cands) {
    if (isObj(u)) return u
  }
  return null
}

/** 从多个可能的位置取模型名，取不到返回空字符串。 */
function modelOf(session, d) {
  const header = isObj(session) && isObj(session.header) ? session.header : {}
  const cands = [
    d.model,
    isObj(d.next) ? d.next.model : undefined,
    isObj(d.selection) ? d.selection.model : undefined,
    isObj(d.header) && isObj(d.header.config) ? d.header.config.model : undefined,
    isObj(d.config) ? d.config.model : undefined,
    isObj(d.message) ? d.message.model : undefined,
    isObj(session) ? session.model : undefined,
    header.model,
    isObj(session) && isObj(session.meta) ? session.meta.model : undefined,
    isObj(session) && isObj(session.metadata) ? session.metadata.model : undefined,
  ]
  for (const c of cands) {
    if (typeof c === 'string' && c.trim() !== '') return c.trim()
  }
  return ''
}

/**
 * 会话身份与项目名。
 * 子代理自己也有一条会话，但设备上显示主会话更有意义，所以子代理会话
 * 优先用 parentSessionId 作为 session 字段。
 */
function sessionInfo(session) {
  const header = isObj(session) && isObj(session.header) ? session.header : {}
  const rawId = isObj(session) ? (session.id ?? header.id) : undefined
  let sid = rawId == null ? '' : clip(String(rawId), SESSION_MAX)
  const parent = header.parentSessionId ?? (isObj(session) ? session.parentSessionId : undefined)
  if (header.origin === 'subagent' && parent != null && String(parent) !== '') {
    sid = clip(String(parent), SESSION_MAX)
  }
  const cwd =
    (isObj(session) ? session.workingDirectory : undefined) ??
    (isObj(session) ? session.cwd : undefined) ??
    header.cwd ??
    (isObj(session) && isObj(session.meta) ? session.meta.cwd : undefined)
  const project = clip(basenameOf(cwd), PROJECT_MAX)
  return { sid, project }
}

/* ------------------------------------------------------------------ */
/* 状态对象                                                            */
/* ------------------------------------------------------------------ */

/** 新建一份初始状态（还没收到任何事件）。 */
export function createInitialState(now = Date.now(), opts = {}) {
  const startAt = finiteNum(now) ?? Date.now()
  return {
    state: 'idle',
    persistent: 'idle',
    event: 'SessionStart',
    project: typeof opts.project === 'string' && opts.project !== '' ? opts.project : 'dsh',
    tool: '',
    model: '',
    session: '',
    ctx: null,
    tokens: 0,
    turns: 0,
    subagents: 0,
    turn: emptyBuckets(),
    task: emptyBuckets(),
    turnKey: '',
    history: [],
    lastAt: startAt,
    startAt,
    transientUntil: 0,
    restoreTo: 'idle',
  }
}

/** 把任意状态对象补齐成完整形状（用于热重载/旧快照）。 */
function normalizeState(state, now) {
  const src = isObj(state) ? state : {}
  const base = createInitialState(now)
  const out = { ...base, ...src }

  out.state = STATES.includes(out.state) ? out.state : 'idle'
  out.persistent = DURABLE_STATES.has(out.persistent) ? out.persistent : 'idle'
  out.event = EVENT_NAME_SET.has(out.event) ? out.event : 'SessionStart'
  out.project = clip(out.project || 'dsh', PROJECT_MAX) || 'dsh'
  out.tool = clip(out.tool, TOOL_MAX)
  out.model = typeof out.model === 'string' ? out.model : ''
  out.session = clip(out.session, SESSION_MAX)
  out.ctx = Number.isFinite(out.ctx) ? Math.min(1, Math.max(0, out.ctx)) : null
  out.tokens = Math.max(0, Math.round(finiteNum(out.tokens) ?? 0))
  out.turns = Math.max(0, Math.round(finiteNum(out.turns) ?? 0))
  out.subagents = Math.max(0, Math.round(finiteNum(out.subagents) ?? 0))
  out.turn = normalizeBuckets(src.turn)
  out.task = normalizeBuckets(src.task)
  out.turnKey = typeof src.turnKey === 'string' ? src.turnKey : ''
  out.lastAt = finiteNum(out.lastAt) ?? now
  out.startAt = finiteNum(out.startAt) ?? now
  out.transientUntil = finiteNum(out.transientUntil) ?? 0
  out.restoreTo = DURABLE_STATES.has(out.restoreTo) ? out.restoreTo : 'idle'
  out.history = Array.isArray(src.history)
    ? src.history
        .filter(isObj)
        .map((h) => ({
          event: EVENT_NAME_SET.has(h.event) ? h.event : 'SessionStart',
          tool: clip(h.tool, TOOL_MAX),
          at: Math.max(0, Math.floor(finiteNum(h.at) ?? 0)),
        }))
        .slice(-HISTORY_MAX)
    : []
  return out
}

/**
 * 计算“此刻应该显示什么状态”。
 *
 * 优先级：
 *   1. 瞬时状态（notification/done/error）在 8 秒内保持原样；
 *   2. 到点后回落到 enterTransient 时记下的 restoreTo；
 *   3. thinking/working/building 超过 5 分钟无事件 → idle；
 *   4. idle 超过 30 分钟 → sleeping。
 *
 * 这个函数不修改状态，所以 /state 随时读取都能拿到“已经回落到正确状态”的视图。
 */
export function effectiveState(state, now = Date.now()) {
  const s = isObj(state) ? state : {}
  const st = STATES.includes(s.state) ? s.state : 'idle'
  const nowMs = finiteNum(now) ?? Date.now()
  const lastAt = finiteNum(s.lastAt) ?? nowMs

  if (TRANSIENT_STATES.has(st)) {
    const until = finiteNum(s.transientUntil) ?? 0
    if (until > 0 && nowMs >= until) {
      return DURABLE_STATES.has(s.restoreTo) ? s.restoreTo : 'idle'
    }
    return st
  }

  if (st === 'idle') {
    // 只有“空闲了很久”才进入 sleeping；有事件时 lastAt 会被刷新。
    return nowMs - lastAt > SLEEP_MS ? 'sleeping' : 'idle'
  }

  if (st !== 'sleeping' && nowMs - lastAt > IDLE_MS) return 'idle'
  return st
}

/**
 * 生成设备端 JSON 帧。字段名与协议严格一致，所有值都已归一化，
 * JSON.stringify 之后一定是合法 JSON（不含 undefined/NaN/Infinity）。
 */
export function snapshot(state, opts = {}) {
  const nowMs = finiteNum(opts.now) ?? Date.now()
  const s = normalizeState(state, nowMs)
  const view = effectiveState(s, nowMs)
  const port = Math.max(0, Math.round(finiteNum(opts.port) ?? 0))

  return {
    state: view,
    event: EVENT_NAME_SET.has(s.event) ? s.event : 'SessionStart',
    project: s.project || 'dsh',
    tool: s.tool || '',
    model: s.model || '',
    session: s.session || '',
    ctx: s.ctx === null ? null : Math.round(s.ctx * 1000) / 1000,
    tokens: s.tokens,
    window_tokens: CONTEXT_WINDOW,
    turn: packBuckets(s.turn),
    task: packBuckets(s.task),
    turns: s.turns,
    subagents: s.subagents,
    history: s.history.slice(-HISTORY_MAX).map((h) => ({
      event: h.event,
      tool: h.tool,
      at: h.at,
    })),
    ts: Math.floor(nowMs / 1000),
    port,
    uptime: Math.max(0, Math.floor((nowMs - s.startAt) / 1000)),
  }
}

/* ------------------------------------------------------------------ */
/* 折叠                                                                */
/* ------------------------------------------------------------------ */

/** 切到一个持续状态，并清掉瞬时定时。 */
function setPersistent(s, next) {
  s.state = next
  s.persistent = next
  s.transientUntil = 0
  s.restoreTo = next
}

/**
 * 切到一个瞬时状态，8 秒后回落到 restoreTo。
 *
 * 回落策略：
 *   - done / error：restoreTo 固定为 idle。一轮已经结束，8 秒后如果仍没有
 *     新事件，显示“刚结束”没有意义，显示待机才符合设备预期。
 *   - notification：restoreTo 是进入通知前正在做的事（通常是 working）。
 *     审批只是打断，不是结束，8 秒后应回到原来干活的画面。
 */
function enterTransient(s, next, now, restoreTo) {
  s.state = next
  s.transientUntil = now + TRANSIENT_MS
  s.restoreTo = DURABLE_STATES.has(restoreTo) ? restoreTo : 'idle'
}

/** 记一条 history，并同步 event 字段。 */
function pushHistory(s, name, tool, atSec) {
  if (!EVENT_NAME_SET.has(name)) return
  s.event = name
  s.history = s.history
    .concat([
      {
        event: name,
        tool: clip(tool, TOOL_MAX),
        at: Math.max(0, Math.floor(atSec)),
      },
    ])
    .slice(-HISTORY_MAX)
}

/** token 四桶（互斥）：未缓存输入 / 输出 / 读缓存 / 写缓存；rs 仅记录不参与求和。 */
const BUCKET_KEYS = ['in', 'out', 'cr', 'cw', 'rs']

function emptyBuckets() {
  return { in: 0, out: 0, cr: 0, cw: 0, rs: 0 }
}

/** 把桶补齐成正整数（用于热重载/旧快照）。 */
function normalizeBuckets(src) {
  const out = emptyBuckets()
  if (!isObj(src)) return out
  for (const k of BUCKET_KEYS) {
    out[k] = Math.max(0, Math.round(finiteNum(src[k]) ?? 0))
  }
  return out
}

/** 输出给设备：总量与缓存命中率（cacheRead / 全部输入桶）。 */
function packBuckets(b) {
  const inB = b.in + b.cr + b.cw
  return {
    in: b.in,
    out: b.out,
    cr: b.cr,
    cw: b.cw,
    total: inB + b.out,
    hit: inB > 0 ? Math.round((b.cr / inB) * 1000) / 1000 : 0,
  }
}

/** 用 assistant/message 的 usage 更新 tokens/ctx，并按 turn 累加各桶。 */
function applyUsage(s, d) {
  const u = usageOf(d)
  if (!u) return
  const bucket = {
    in: Math.max(0, Math.round(finiteNum(u.inputTokens) ?? 0)),
    out: Math.max(0, Math.round(finiteNum(u.outputTokens) ?? 0)),
    cr: Math.max(0, Math.round(finiteNum(u.cacheReadTokens) ?? 0)),
    cw: Math.max(0, Math.round(finiteNum(u.cacheWriteTokens) ?? 0)),
    rs: Math.max(0, Math.round(finiteNum(u.reasoningTokens) ?? 0)),
  }
  // 口径与 dsh-context 一致：prompt = input + cacheRead + cacheWrite
  const prompt = bucket.in + bucket.cr + bucket.cw
  if (prompt > 0) {
    s.tokens = prompt
    s.ctx = Math.min(1, Math.max(0, prompt / CONTEXT_WINDOW))
  }
  // 一次 turn 可能有多个 step，每条 assistant/message 各报一份，按 turn+step 幂等累加。
  if (prompt <= 0 && bucket.out <= 0) return
  const key = `${d.turn ?? ''}:${d.step ?? ''}`
  if (key === s.turnKey) return
  s.turnKey = key
  s.turn = normalizeBuckets(s.turn)
  s.task = normalizeBuckets(s.task)
  for (const k of BUCKET_KEYS) {
    s.turn[k] += bucket[k]
    s.task[k] += bucket[k]
  }
}

/** 判断 tool/result 是不是失败。兼容三种常见形状。 */
function isToolError(d) {
  if (d.isError === true || d.error === true) return true
  if (isObj(d.result) && d.result.isError === true) return true
  const blocks = isObj(d.message) ? d.message.content : undefined
  if (Array.isArray(blocks)) {
    return blocks.some(
      (b) => isObj(b) && b.type === 'tool-result' && b.isError === true,
    )
  }
  return false
}

/**
 * 折叠一个事件，返回新状态（不修改传入的 state）。
 *
 * 所有字段读取都走 `?.` + 类型判断；任何不认识的事件原样返回，绝不抛异常。
 *
 * @param {object} state 上一份状态（createInitialState 的产物）
 * @param {object} session DSH 传入的会话对象
 * @param {object} event DSH 的 session 事件
 * @param {number} now 当前毫秒时间戳（测试可注入）
 */
export function foldEvent(state, session, event, now = Date.now()) {
  if (!isObj(event) || typeof event.type !== 'string') return state
  const type = event.type
  if (!KNOWN_EVENT_TYPES.has(type) && !type.startsWith('subagent/')) return state

  const nowMs = finiteNum(now) ?? Date.now()
  const base = normalizeState(state, nowMs)
  // 折叠前先把已经过期的瞬时状态落到持续状态，避免新事件叠加在过期视图上。
  const eff = effectiveState(base, nowMs)
  if (eff !== base.state) {
    base.state = eff
    if (DURABLE_STATES.has(eff)) base.persistent = eff
    if (!TRANSIENT_STATES.has(eff)) base.transientUntil = 0
  }
  const at = eventTimeMs(event, nowMs)
  // 事件时间可能来自重放；不要让 lastAt 倒退。
  base.lastAt = Math.max(base.lastAt, at)

  const d = readEventData(event)
  const info = sessionInfo(session)
  if (info.sid) base.session = info.sid
  if (info.project) base.project = info.project

  const model = modelOf(session, d)
  if (model) base.model = model

  const atSec = Math.floor(at / 1000)
  const sub = subagentKind(type)
  if (sub) {
    // subagent/descriptor 既可能表示“子代理已创建”，也可能表示“子代理已结算”
    // （后者在 data.source.kind 或 data.status 里标出来）。不能一律当开始，
    // 否则 subagents 计数只增不减，设备会一直停在 building。
    const settled =
      sub !== 'end' &&
      (d.status === 'settled' ||
        d.state === 'settled' ||
        (isObj(d.source) &&
          (d.source.kind === 'subagent-settled' || d.source.kind === 'subagent-stopped')))
    if (sub === 'end' || settled) {
      base.subagents = Math.max(0, base.subagents - 1)
      const restore = base.persistent === 'building'
        ? (base.tool ? 'working' : 'thinking')
        : (base.persistent || 'thinking')
      setPersistent(base, base.subagents > 0 ? 'building' : restore)
      pushHistory(base, 'SubagentStop', base.tool, atSec)
    } else {
      // start 以及无法分类的 subagent/* 都视为“正在搭子代理”，宁可多显示 building。
      if (sub === 'start') base.subagents += 1
      base.tool = ''
      setPersistent(base, 'building')
      pushHistory(base, 'SubagentStart', '', atSec)
    }
    return base
  }

  switch (type) {
    case 'turn/start': {
      base.turns += 1
      base.tool = ''
      base.turn = emptyBuckets()
      base.turnKey = ''
      setPersistent(base, 'thinking')
      pushHistory(base, 'UserPromptSubmit', '', atSec)
      return base
    }

    case 'turn/end': {
      const reason = reasonKind(d.reason)
      base.tool = ''
      if (
        reason === 'error' ||
        reason === 'max-tokens' ||
        reason === 'aborted' ||
        reason === 'blocked' ||
        reason === 'interrupted'
      ) {
        enterTransient(base, 'error', nowMs, 'idle')
        base.persistent = 'idle'
      } else {
        // completed / forked / 未知 reason 都按正常结束处理
        enterTransient(base, 'done', nowMs, 'idle')
        base.persistent = 'idle'
      }
      pushHistory(base, 'Stop', '', atSec)
      return base
    }

    case 'assistant/chunk': {
      const chunk = isObj(d.chunk) ? d.chunk : d
      const kind = typeof chunk.type === 'string' ? chunk.type : ''
      if (kind === 'reasoning-delta' || kind === 'text-delta') {
        // 流式增量只改状态，不进 history，否则 6 条会被瞬间刷满。
        setPersistent(base, 'thinking')
      }
      return base
    }

    case 'assistant/message': {
      applyUsage(base, d)
      base.tool = ''
      setPersistent(base, 'thinking')
      return base
    }

    case 'tool/call': {
      const name = toolNameOf(d)
      base.tool = name
      if (name && /subagent/i.test(name)) {
        setPersistent(base, 'building')
        pushHistory(base, 'SubagentStart', name, atSec)
      } else {
        setPersistent(base, 'working')
        pushHistory(base, 'PreToolUse', name, atSec)
      }
      return base
    }

    case 'tool/result': {
      const name = toolNameOf(d)
      if (name) base.tool = name
      if (isToolError(d)) {
        // 工具失败不结束整轮：8 秒后回到 working，让设备继续显示“还在干活”。
        enterTransient(base, 'error', nowMs, 'working')
        base.persistent = 'working'
      } else {
        setPersistent(base, 'working')
      }
      pushHistory(base, 'PostToolUse', base.tool, atSec)
      return base
    }

    case 'approval/asked': {
      const name = toolNameOf(d) || base.tool
      if (name) base.tool = name
      // 审批打断的是当前动作，8 秒后回到打断前的持续状态。
      const restore = base.persistent !== 'idle' ? base.persistent : 'thinking'
      enterTransient(base, 'notification', nowMs, restore)
      pushHistory(base, 'PermissionRequest', name, atSec)
      return base
    }

    case 'approval/decided': {
      // 审批已经处理完，不必再让“通知”空等 8 秒。
      if (base.state === 'notification') {
        const restore = base.restoreTo || base.persistent || 'idle'
        base.state = restore
        base.persistent = restore
        base.transientUntil = 0
      }
      return base
    }

    case 'request/header': {
      // 只关心模型名，状态不动。
      return base
    }

    case 'model/selection': {
      return base
    }

    case 'compaction/start': {
      pushHistory(base, 'PreCompact', base.tool, atSec)
      return base
    }

    case 'compaction/summary':
    case 'compaction/prune': {
      pushHistory(base, 'PostCompact', base.tool, atSec)
      return base
    }

    case 'session/start':
    case 'session/created': {
      base.tool = ''
      setPersistent(base, 'idle')
      pushHistory(base, 'SessionStart', '', atSec)
      return base
    }

    case 'session/resume':
    case 'session/resumed': {
      pushHistory(base, 'AgentResume', base.tool, atSec)
      return base
    }

    default:
      // 已知集合里但不单独处理的事件：只当作活动，不改状态。
      return base
  }
}
