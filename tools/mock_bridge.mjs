// 本地联调用的假数据源：模拟 dsh-holocubic 的 /state 与 /events，
// 让设备在真插件装好之前也能验证 UI 与动画。
import http from 'node:http'

const PORT = Number(process.argv[2] || 17890)
const WINDOW = 128000

const steps = [
  { state: 'idle', event: 'SessionStart', tool: '', ctx: 0.08, tokens: 9600, line: '> waiting for events' },
  { state: 'thinking', event: 'UserPromptSubmit', tool: '', ctx: 0.21, tokens: 26800, line: '> reasoning...' },
  { state: 'working', event: 'PreToolUse', tool: 'bash', ctx: 0.34, tokens: 43500, line: '$ bash npm run build' },
  { state: 'working', event: 'PostToolUse', tool: 'edit', ctx: 0.41, tokens: 52400, line: 'ok bash 12.4s' },
  { state: 'notification', event: 'PermissionRequest', tool: 'write', ctx: 0.44, tokens: 56300, line: '? approval write' },
  { state: 'working', event: 'PreToolUse', tool: 'bash', ctx: 0.55, tokens: 70400, line: '$ bash git status' },
  { state: 'done', event: 'Stop', tool: '', ctx: 0.62, tokens: 79300, line: 'done turn 1' },
  { state: 'error', event: 'Error', tool: 'bash', ctx: 0.64, tokens: 81900, line: 'err bash exit 1' },
  { state: 'building', event: 'SubagentStart', tool: '', ctx: 0.66, tokens: 84400, line: '+ subagent' },
]

const frame = {
  state: 'idle',
  event: 'SessionStart',
  project: 'HoloCubic',
  tool: '',
  model: 'deepseek-reasoner',
  session: 'a1b2c3d4',
  ctx: 0,
  tokens: 0,
  window_tokens: WINDOW,
  history: [],
  tools: 0,
  errors: 0,
  subagents: 0,
  ts: Date.now(),
}

const clients = new Set()

function broadcast() {
  const payload = `data: ${JSON.stringify(frame)}\n\n`
  for (const res of clients) {
    try {
      res.write(payload)
    } catch {
      clients.delete(res)
    }
  }
}

let i = 0
function tick() {
  const s = steps[i % steps.length]
  i += 1
  Object.assign(frame, {
    state: s.state,
    event: s.event,
    tool: s.tool,
    ctx: s.ctx,
    tokens: s.tokens,
    ts: Date.now(),
  })
  frame.history.push(s.line)
  while (frame.history.length > 6) frame.history.shift()
  if (s.event === 'PreToolUse') frame.tools += 1
  if (s.event === 'Error') frame.errors += 1
  broadcast()
  console.log(new Date().toLocaleTimeString(), s.state, s.event, s.line)
}

const server = http.createServer((req, res) => {
  const url = String(req.url || '/')
  if (url.startsWith('/state')) {
    res.writeHead(200, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify(frame))
    return
  }
  if (url.startsWith('/events')) {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    })
    res.write(': connected\n\n')
    res.write(`data: ${JSON.stringify(frame)}\n\n`)
    clients.add(res)
    console.log('client connected, total', clients.size)
    req.on('close', () => {
      clients.delete(res)
      console.log('client gone, total', clients.size)
    })
    return
  }
  res.writeHead(404)
  res.end('not found')
})

setInterval(tick, 5000)
server.listen(PORT, '0.0.0.0', () => {
  console.log('mock bridge on http://0.0.0.0:' + PORT)
})
