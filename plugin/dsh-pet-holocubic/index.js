/**
 * dsh-holocubic —— DeepSeek Harness（DSH）本地插件。
 *
 * 作用：把 agent 的实时状态以只读 HTTP/SSE 暴露给局域网里的
 * HoloCubic（320×240 桌搭屏）。官方 Web GUI 只绑 127.0.0.1，所以这里
 * 用 node:http 自建一个 0.0.0.0 服务。
 *
 * 端口：默认 17890，被占用时依次试 17891..17895；实际端口会出现在
 * 日志、/state 的 `port` 字段以及每一帧 SSE 里。
 *
 * 安全：只暴露只读状态，没有写接口。请只在可信局域网内使用。
 */

import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { URL } from 'node:url'

import {
  createInitialState,
  foldEvent,
  snapshot,
} from './lib/fold.js'

export const name = 'dsh-holocubic'

/** 本插件不依赖任何 DSH 服务；ctx.on / ctx.effect 是宿主上下文自带的。 */
export const inject = []

const DEFAULT_PORT = 17890
const DEFAULT_ATTEMPTS = 6 // 17890..17895
const DEFAULT_HEARTBEAT_MS = 10000
const TICK_MS = 1000

/* ---------------- 余额 / 峰谷 / 单价 ----------------
 * 口径见 build/docs/balance-research.md：
 *  - 余额走账号服务 ctx.get('deepseekAccount').getBalance()，不需要 API Key
 *  - 峰谷：北京时间工作日 09:00–12:00、14:00–18:00 为峰（UTC 1-4 / 6-10）
 *  - token 四桶互斥：input / cacheRead / cacheWrite / output，output 已含 reasoning
 */
const DSH_HOME = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
const BALANCE_MS = 60000
const LEDGER_MS = 60000
const PEAK_WINDOWS_UTC = [
  [1, 4],
  [6, 10],
]
const PRICE_TABLE = [
  { match: 'v4-pro', peak: { in: 9, hit: 0.3, out: 27 }, off: { in: 4.5, hit: 0.15, out: 13.5 } },
  { match: 'flash', peak: { in: 2, hit: 0.04, out: 8 }, off: { in: 1, hit: 0.02, out: 4 } },
]

/** 当前是否峰时。星期用「加 8 小时后的 UTC 星期」，时段用原始 UTC 小时。 */
function peakPhase(nowMs = Date.now()) {
  const bj = new Date(nowMs + 8 * 3600000)
  const dow = bj.getUTCDay() // 0 = 周日（北京时间）
  const h = bj.getUTCHours() + bj.getUTCMinutes() / 60 // 北京时间 0..24，给刻度条画箭头
  const u = new Date(nowMs)
  const uh = u.getUTCHours() + u.getUTCMinutes() / 60 // UTC 小时，比对 UTC 窗口
  const workday = dow >= 1 && dow <= 5
  const inPeak = workday && PEAK_WINDOWS_UTC.some(([s, e]) => uh >= s && uh < e)
  return { inPeak, hour: h, workday, ratio: Math.min(1, Math.max(0, (h * 60) / 1440)) }
}

function priceOf(model, inPeak) {
  const n = String(model || '').toLowerCase()
  const hit = PRICE_TABLE.find((p) => n.includes(p.match))
  if (!hit) return null
  return inPeak ? hit.peak : hit.off
}

/** 按当前峰谷把四桶换算成人民币（元）。 */
function costOf(bucket, model, inPeak) {
  const p = priceOf(model, inPeak)
  if (!p || !bucket) return 0
  const cny =
    ((bucket.in || 0) * p.in + (bucket.cr || 0) * p.hit + (bucket.cw || 0) * p.hit + (bucket.out || 0) * p.out) / 1e6
  return Math.round(cny * 1e6) / 1e6
}

function isObj(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v)
}

function toPort(value, fallback) {
  const n = Number(value)
  return Number.isInteger(n) && n > 0 && n < 65536 ? n : fallback
}

function toInt(value, fallback, min, max) {
  const n = Number(value)
  if (!Number.isInteger(n)) return fallback
  return Math.min(max, Math.max(min, n))
}

/** 列出本机局域网 IPv4，仅用于启动日志，方便照抄到设备端。 */
function lanUrls(port) {
  const out = []
  try {
    for (const list of Object.values(os.networkInterfaces())) {
      for (const item of list || []) {
        if (!item || item.internal) continue
        if (item.family !== 'IPv4' && item.family !== 4) continue
        out.push(`http://${item.address}:${port}`)
      }
    }
  } catch {
    // 取不到网卡就算了，不影响服务本身
  }
  return out
}

function errorText(err) {
  try {
    return err && (err.stack || err.message) ? String(err.message || err) : String(err)
  } catch {
    return 'unknown error'
  }
}

/**
 * Cordis 插件入口。
 *
 * 外层再包一层 try/catch：插件初始化失败时只写日志，绝不能让宿主加载
 * 流程跟着崩掉。
 */
export function apply(ctx, config = {}) {
  try {
    return boot(ctx, config)
  } catch (err) {
    try {
      console.error('[dsh-holocubic] 初始化失败（宿主继续运行）: ' + errorText(err))
    } catch {
      // 连 console 都不可用时也无能为力
    }
    return undefined
  }
}

function boot(ctx, config) {
  const cfg = isObj(config) ? config : {}
  const basePort = toPort(cfg.port, DEFAULT_PORT)
  const attempts = toInt(cfg.portAttempts, DEFAULT_ATTEMPTS, 1, 32)
  const heartbeatMs = toInt(cfg.heartbeatMs, DEFAULT_HEARTBEAT_MS, 1000, 60000)

  /** 当前折叠出来的状态。事件到达时整体替换。 */
  const stateRef = { value: createInitialState(Date.now()) }
  /** 已连接的 SSE 响应对象。 */
  const clients = new Set()
  /** 账户余额缓存（异步刷新，避免每次取帧都打接口）。 */
  const balanceRef = { value: { cny: null, status: 'pending', at: 0 } }
  /** 今日花费缓存（读 cost-meter 账本）。 */
  const ledgerRef = { value: { cny: null, tokens: 0 } }

  let server = null
  let actualPort = 0
  let lastSig = ''
  let stopped = false
  let starting = false
  let tickTimer = null
  let heartbeatTimer = null
  let balanceTimer = null

  const log = (level, message) => {
    const line = '[dsh-holocubic] ' + message
    try {
      const logger = ctx && ctx.logger
      if (logger && typeof logger[level] === 'function') {
        logger[level](line)
        return
      }
      if (level === 'error') console.error(line)
      else if (level === 'warn') console.warn(line)
      else console.log(line)
    } catch {
      // 日志失败不影响主流程
    }
  }

  /** 刷新账户余额。账号服务未就绪时降级为 unavailable，不影响主流程。 */
  const refreshBalance = async () => {
    try {
      const account = typeof ctx.get === 'function' ? ctx.get('deepseekAccount') : null
      if (!account || typeof account.getBalance !== 'function') {
        balanceRef.value = { cny: null, status: 'unavailable', at: Date.now() }
        return
      }
      const d = await account.getBalance({
        version: '',
        locale: 'zh',
        timezoneOffsetSeconds: -new Date().getTimezoneOffset() * 60,
      })
      if (!d || d.status !== 'ready') {
        balanceRef.value = { cny: null, status: String((d && d.status) || 'error'), at: Date.now() }
        return
      }
      const wallets = [...(d.value ?? []), ...(d.bonusWallets ?? [])]
      const cny = wallets
        .filter((w) => w && w.currency === 'CNY')
        .reduce((n, w) => n + Number(w.balance || 0), 0)
      balanceRef.value = { cny: Math.round(cny * 1e4) / 1e4, status: 'ok', at: Date.now() }
    } catch (err) {
      balanceRef.value = { cny: null, status: 'error', at: Date.now() }
      log('warn', 'balance refresh failed: ' + errorText(err))
    }
  }

  /** 读 cost-meter 账本里的「今日花费」，拿不到就保持 null。 */
  const refreshLedger = () => {
    try {
      const file = path.join(DSH_HOME, 'storages', 'cost-meter', 'ledger.json')
      const j = JSON.parse(fs.readFileSync(file, 'utf8'))
      const today = new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10)
      const d = j && j.days && j.days[today]
      if (!d) return
      ledgerRef.value = {
        cny: Math.round(Number(d.costCny || 0) * 1e4) / 1e4,
        tokens: (d.input || 0) + (d.output || 0) + (d.cacheRead || 0) + (d.cacheWrite || 0),
      }
    } catch {
      // 账本不存在或损坏都不影响设备显示
    }
  }

  /** 生成当前时刻的协议帧。 */
  const currentFrame = () => {
    const now = Date.now()
    const frame = snapshot(stateRef.value, { now, port: actualPort })
    const peak = peakPhase(now)
    const bal = balanceRef.value
    const day = ledgerRef.value
    return {
      ...frame,
      balance: bal.cny,
      balance_currency: 'CNY',
      balance_status: bal.status,
      balance_at: bal.at,
      today_cny: day.cny,
      today_tokens: day.tokens,
      turn_cny: costOf(stateRef.value.turn, frame.model, peak.inPeak),
      peak: peak.inPeak ? 'peak' : 'off',
      peak_ratio: Math.round(peak.ratio * 1000) / 1000,
      peak_workday: peak.workday,
    }
  }

  /**
   * 用于判断“状态有没有变化”。ts / uptime 每秒都在变，不能参与比较，
   * 否则 SSE 会变成每秒一帧的无意义流量。
   */
  const signatureOf = (frame) => {
    const { ts, uptime, ...rest } = frame
    return JSON.stringify(rest)
  }

  const broadcast = (frame) => {
    if (clients.size === 0) return
    const payload = 'data: ' + JSON.stringify(frame) + '\n\n'
    for (const res of clients) {
      try {
        res.write(payload)
      } catch {
        clients.delete(res)
      }
    }
  }

  /** 只在快照真正变化时推帧；force 用于端口确定、新客户端接入。 */
  const publish = (force = false) => {
    const frame = currentFrame()
    const sig = signatureOf(frame)
    if (!force && sig === lastSig) return
    lastSig = sig
    broadcast(frame)
  }

  /** 订阅 DSH 事件总线。任何异常都只记日志，不能打断事件流。 */
  const onSessionEvent = (session, event) => {
    try {
      stateRef.value = foldEvent(stateRef.value, session, event, Date.now())
      publish()
    } catch (err) {
      log('warn', '折叠 session/event 失败（已忽略该事件）: ' + errorText(err))
    }
  }

  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Max-Age': '86400',
    'Cache-Control': 'no-store',
  }

  const sendJson = (res, status, body) => {
    let text
    try {
      text = JSON.stringify(body)
    } catch {
      text = '{"ok":false}'
    }
    try {
      res.writeHead(status, {
        ...corsHeaders,
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': Buffer.byteLength(text),
      })
      res.end(text)
    } catch {
      try { res.destroy() } catch { /* ignore */ }
    }
  }

  /** 打开一条 SSE 流：先发一帧当前状态，之后由 publish 推送变化。 */
  const openSse = (req, res) => {
    try {
      res.writeHead(200, {
        ...corsHeaders,
        'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      })
      try {
        res.socket?.setNoDelay?.(true)
        res.socket?.setKeepAlive?.(true)
      } catch { /* ignore */ }

      clients.add(res)
      const frame = currentFrame()
      lastSig = signatureOf(frame)
      try {
        res.write('retry: 3000\n\n')
        res.write('data: ' + JSON.stringify(frame) + '\n\n')
      } catch {
        clients.delete(res)
        return
      }

      req.on('close', () => clients.delete(res))
      req.on('error', () => clients.delete(res))
      res.on('error', () => clients.delete(res))
    } catch (err) {
      clients.delete(res)
      log('warn', '建立 SSE 连接失败: ' + errorText(err))
      try { res.destroy() } catch { /* ignore */ }
    }
  }

  const handleRequest = (req, res) => {
    try {
      const method = req.method || 'GET'
      if (method === 'OPTIONS') {
        res.writeHead(204, corsHeaders)
        res.end()
        return
      }
      if (method !== 'GET' && method !== 'HEAD') {
        sendJson(res, 405, { ok: false, error: 'method-not-allowed' })
        return
      }

      let pathname = '/'
      try {
        pathname = new URL(req.url || '/', 'http://127.0.0.1').pathname
      } catch {
        pathname = '/'
      }

      if (pathname === '/state') {
        sendJson(res, 200, currentFrame())
        return
      }
      if (pathname === '/events') {
        openSse(req, res)
        return
      }
      if (pathname === '/') {
        sendJson(res, 200, {
          ok: true,
          name: 'dsh-holocubic',
          endpoints: ['/state', '/events'],
        })
        return
      }
      sendJson(res, 404, { ok: false, error: 'not-found' })
    } catch (err) {
      log('warn', '处理 HTTP 请求失败: ' + errorText(err))
      try { res.destroy() } catch { /* ignore */ }
    }
  }

  /** 端口被占用时递归尝试下一个，全部失败返回 null。 */
  const tryListen = (port, left) => {
    return new Promise((resolve) => {
      let settled = false
      const s = http.createServer(handleRequest)

      s.once('error', (err) => {
        if (settled) return
        settled = true
        try { s.close() } catch { /* ignore */ }
        if (err && err.code === 'EADDRINUSE' && left > 1 && port + 1 <= 65535) {
          log('warn', `端口 ${port} 被占用，尝试 ${port + 1}`)
          resolve(tryListen(port + 1, left - 1))
          return
        }
        log('warn', `无法监听 ${port}（${(err && (err.code || err.message)) || err}），设备端暂不可用`)
        resolve(null)
      })

      s.once('listening', () => {
        if (settled) return
        settled = true
        resolve(s)
      })

      try {
        s.listen(port, '0.0.0.0')
      } catch (err) {
        if (settled) return
        settled = true
        try { s.close() } catch { /* ignore */ }
        log('warn', `监听 ${port} 抛异常: ${errorText(err)}`)
        resolve(null)
      }
    })
  }

  const stop = () => {
    stopped = true
    if (tickTimer) {
      clearInterval(tickTimer)
      tickTimer = null
    }
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
    if (balanceTimer) {
      clearInterval(balanceTimer)
      balanceTimer = null
    }
    for (const res of clients) {
      try { res.end() } catch { /* ignore */ }
    }
    clients.clear()
    const s = server
    server = null
    actualPort = 0
    if (s) {
      try { s.close() } catch { /* ignore */ }
      try { s.closeAllConnections?.() } catch { /* ignore */ }
    }
  }

  const start = () => {
    if (stopped || starting) return
    starting = true
    tryListen(basePort, attempts)
      .then((s) => {
        starting = false
        if (stopped) {
          try { s?.close() } catch { /* ignore */ }
          return
        }
        if (!s) {
          log('warn', 'HTTP 服务没有起来：插件保持加载，但 /state 与 /events 不可用')
          return
        }
        server = s
        const addr = s.address()
        actualPort = addr && typeof addr === 'object' && addr.port ? addr.port : basePort
        log('info', `已监听 0.0.0.0:${actualPort}（GET /state, GET /events）`)
        const urls = lanUrls(actualPort)
        if (urls.length === 0) {
          log('warn', '没找到局域网 IPv4，设备端请用 127.0.0.1 或检查网络')
        } else {
          for (const url of urls) log('info', `局域网地址: ${url}/state`)
        }

        // 端口确定后 port 字段变了，强制推一帧给已经连上的客户端。
        publish(true)

        // 首帧前先抓一次余额与今日花费，之后按分钟刷新。
        refreshLedger()
        refreshBalance().catch(() => {})


        tickTimer = setInterval(() => {
          try { publish() } catch { /* ignore */ }
        }, TICK_MS)
        tickTimer.unref?.()

        heartbeatTimer = setInterval(() => {
          const line = ': ping\n\n'
          for (const res of clients) {
            try {
              res.write(line)
            } catch {
              clients.delete(res)
            }
          }
        }, heartbeatMs)
        heartbeatTimer.unref?.()

        balanceTimer = setInterval(() => {
          try {
            refreshLedger()
            refreshBalance().catch(() => {})
            publish()
          } catch {
            /* ignore */
          }
        }, BALANCE_MS)
        balanceTimer.unref?.()
      })
      .catch((err) => {
        starting = false
        log('warn', 'HTTP 服务启动异常: ' + errorText(err))
      })
  }

  /** 订阅事件 + 启服务，并登记清理。 */
  const mount = () => {
    let offEvent = null
    try {
      if (typeof ctx.on === 'function') {
        offEvent = ctx.on('session/event', onSessionEvent)
        log('info', '已订阅 session/event 事件总线')
      } else {
        log('warn', 'ctx.on 不可用：只能提供静态 /state')
      }
    } catch (err) {
      log('warn', '订阅 session/event 失败: ' + errorText(err))
    }

    start()

    return () => {
      try { offEvent?.() } catch { /* ignore */ }
      stop()
    }
  }

  if (ctx && typeof ctx.effect === 'function') {
    // 宿主卸载插件/关闭作用域时会执行返回的清理函数：
    // 退订总线、结束所有 SSE 连接、关闭 HTTP 服务与定时器。
    ctx.effect(mount, 'dsh-holocubic: lan status server')
  } else {
    // 没有 effect 的旧宿主/测试环境：只能直接启动。
    mount()
  }
}

/* 纯折叠函数对外导出，方便 selftest.mjs 与设备端协议测试直接复用。 */export {
  STATES,
  DEVICE_EVENTS,
  IDLE_MS,
  SLEEP_MS,
  TRANSIENT_MS,
  CONTEXT_WINDOW,
  HISTORY_MAX,
  readEventData,
  createInitialState,
  effectiveState,
  snapshot,
  foldEvent,
} from './lib/fold.js'

/* 同时给出 default 导出，形状与 dsh-console-plugin 保持一致：
 * 兼容只读 default 的旧 loader，新 loader 仍可用具名 apply。 */
export default { name, inject, apply }
