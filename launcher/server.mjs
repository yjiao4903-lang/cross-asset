import http from 'node:http'
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HOST = '127.0.0.1'
const PORT = 8765
const APP_ID = 'macro-workbench'
const here = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(here, '..')
const distRoot = path.resolve(repoRoot, 'frontend', 'dist')
const logsDir = path.resolve(here, 'logs')
const serverLog = path.join(logsDir, 'server.log')

const MIME = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.gif', 'image/gif'],
  ['.webp', 'image/webp'],
  ['.ico', 'image/x-icon'],
  ['.woff', 'font/woff'],
  ['.woff2', 'font/woff2'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.map', 'application/json; charset=utf-8'],
])

await fsp.mkdir(logsDir, { recursive: true })

function log(message) {
  const line = `${new Date().toISOString()} ${message}`
  try {
    fs.appendFileSync(serverLog, `${line}\n`, 'utf8')
  } catch {
    // Logging failure must not broaden the server's file access or crash startup.
  }
  console.log(line)
}

function send(res, statusCode, body = '', headers = {}) {
  const buffer = Buffer.isBuffer(body) ? body : Buffer.from(body)
  res.writeHead(statusCode, {
    'Content-Length': buffer.length,
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    ...headers,
  })
  res.end(buffer)
}

function insideRoot(root, candidate) {
  return candidate === root || candidate.startsWith(`${root}${path.sep}`)
}

async function resolveStaticFile(rawPathname) {
  let decoded
  try {
    decoded = decodeURIComponent(rawPathname)
  } catch {
    return { error: 400 }
  }

  if (decoded.includes('\0')) return { error: 400 }

  const portable = decoded.replaceAll('\\', '/')
  const segments = portable.split('/')
  if (segments.includes('..')) return { error: 403 }

  let relative = portable.replace(/^\/+/, '')
  if (!relative) relative = 'index.html'

  const candidate = path.resolve(distRoot, relative)
  if (!insideRoot(distRoot, candidate)) return { error: 403 }

  try {
    const stat = await fsp.stat(candidate)
    const fileCandidate = stat.isDirectory() ? path.join(candidate, 'index.html') : candidate
    const realCandidate = await fsp.realpath(fileCandidate)
    const realDistRoot = await fsp.realpath(distRoot)
    if (!insideRoot(realDistRoot, realCandidate)) return { error: 403 }
    const fileStat = await fsp.stat(realCandidate)
    if (!fileStat.isFile()) return { error: 404 }
    return { file: realCandidate }
  } catch (error) {
    if (error?.code !== 'ENOENT' && error?.code !== 'ENOTDIR') {
      log(`static resolution error: ${error?.stack ?? error}`)
      return { error: 500 }
    }
  }

  // Vite SPA fallback is for application routes only. Missing asset-like paths stay 404.
  if (path.extname(relative) === '') {
    const fallback = path.join(distRoot, 'index.html')
    try {
      const realFallback = await fsp.realpath(fallback)
      const realDistRoot = await fsp.realpath(distRoot)
      if (!insideRoot(realDistRoot, realFallback)) return { error: 403 }
      return { file: realFallback }
    } catch {
      return { error: 404 }
    }
  }

  return { error: 404 }
}

async function serveFile(req, res, filePath) {
  try {
    const body = await fsp.readFile(filePath)
    const extension = path.extname(filePath).toLowerCase()
    const isIndex = path.basename(filePath).toLowerCase() === 'index.html'
    const headers = {
      'Content-Type': MIME.get(extension) ?? 'application/octet-stream',
      'Cache-Control': isIndex ? 'no-cache' : 'public, max-age=3600',
    }
    if (req.method === 'HEAD') {
      send(res, 200, Buffer.alloc(0), { ...headers, 'Content-Length': body.length })
      return
    }
    send(res, 200, body, headers)
  } catch (error) {
    log(`read error for ${filePath}: ${error?.stack ?? error}`)
    send(res, 500, 'Internal Server Error', { 'Content-Type': 'text/plain; charset=utf-8' })
  }
}

const indexPath = path.join(distRoot, 'index.html')
try {
  const stat = await fsp.stat(indexPath)
  if (!stat.isFile()) throw new Error('frontend/dist/index.html is not a file')
} catch (error) {
  log(`startup refused: frontend build missing at ${indexPath}: ${error?.message ?? error}`)
  process.exit(2)
}

const server = http.createServer(async (req, res) => {
  try {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      send(res, 405, 'Method Not Allowed', {
        Allow: 'GET, HEAD',
        'Content-Type': 'text/plain; charset=utf-8',
      })
      return
    }

    const rawPathname = (req.url ?? '/').split('?', 1)[0]
    if (rawPathname === '/__health') {
      const body = JSON.stringify({ status: 'ok', app: APP_ID })
      if (req.method === 'HEAD') {
        send(res, 200, Buffer.alloc(0), {
          'Content-Type': 'application/json; charset=utf-8',
          'Content-Length': Buffer.byteLength(body),
          'Cache-Control': 'no-store',
        })
      } else {
        send(res, 200, body, {
          'Content-Type': 'application/json; charset=utf-8',
          'Cache-Control': 'no-store',
        })
      }
      return
    }

    const resolved = await resolveStaticFile(rawPathname)
    if (resolved.file) {
      await serveFile(req, res, resolved.file)
      return
    }

    const status = resolved.error ?? 404
    const text = status === 403 ? 'Forbidden' : status === 400 ? 'Bad Request' : status === 500 ? 'Internal Server Error' : 'Not Found'
    send(res, status, text, { 'Content-Type': 'text/plain; charset=utf-8' })
  } catch (error) {
    log(`request error: ${error?.stack ?? error}`)
    if (!res.headersSent) {
      send(res, 500, 'Internal Server Error', { 'Content-Type': 'text/plain; charset=utf-8' })
    } else {
      res.end()
    }
  }
})

let shuttingDown = false
function shutdown(reason) {
  if (shuttingDown) return
  shuttingDown = true
  log(`shutdown requested: ${reason}`)
  const timer = setTimeout(() => {
    log('forced shutdown after grace period')
    process.exit(1)
  }, 3000)
  timer.unref()
  server.close((error) => {
    if (error) {
      log(`shutdown error: ${error?.stack ?? error}`)
      process.exit(1)
    }
    log('server stopped')
    process.exit(0)
  })
}

process.on('SIGINT', () => shutdown('SIGINT'))
process.on('SIGTERM', () => shutdown('SIGTERM'))
process.on('uncaughtException', (error) => {
  log(`uncaught exception: ${error?.stack ?? error}`)
  shutdown('uncaughtException')
})
process.on('unhandledRejection', (reason) => {
  log(`unhandled rejection: ${reason instanceof Error ? reason.stack : reason}`)
  shutdown('unhandledRejection')
})

server.on('error', (error) => {
  log(`listen error: ${error?.code ?? 'UNKNOWN'} ${error?.message ?? error}`)
  process.exitCode = 1
})

server.listen(PORT, HOST, () => {
  log(`serving Macro Workbench on http://${HOST}:${PORT} (pid=${process.pid})`)
})
