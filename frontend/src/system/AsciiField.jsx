import { useEffect, useRef } from 'react'

const COLORS = {
  bg: '#020502', faint: 'rgba(70, 110, 70, .14)', line: 'rgba(92, 154, 92, .34)',
  dim: '#4f694f', sub: '#7f9d7f', text: '#cbdacb', green: '#39ff14', amber: '#ffba18', cyan: '#58c7c4',
}

const LABELS = {
  home: ['BUSINESS', 'BUMPS', 'MARKET', 'CONTRACTS', 'POSTING', 'BYTES'],
  business: ['REVIEW', 'ACTIVE', 'WAITING', 'FOLLOW-UP'],
  bumps: ['ELIGIBLE', 'QUEUED', 'POSTED', 'MEASURED'],
  market: ['BAZAAR', 'PREMIUM', 'SERVICES', 'AUXILIARY'],
  contracts: ['REVIEW', 'PROGRESS', 'WAITING', 'CLOSED'],
  posting: ['DRAFT', 'PREVIEW', 'CONFIRM', 'WATCH'],
  bytes: ['BALANCE', 'DEBIT', 'CREDIT', 'REFERENCE'],
  casino: ['POKER', 'BLACKJACK', 'CASHIER', 'VERIFY'],
}

function hash(x, y, seed) {
  const value = Math.sin(x * 127.1 + y * 311.7 + seed * 17.13) * 43758.5453
  return value - Math.floor(value)
}

function setupCanvas(canvas, width, height) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  canvas.width = Math.max(1, Math.floor(width * ratio))
  canvas.height = Math.max(1, Math.floor(height * ratio))
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`
  const context = canvas.getContext('2d')
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  context.textBaseline = 'middle'
  return context
}

function text(context, value, x, y, color = COLORS.sub, size = 9, align = 'left') {
  context.fillStyle = color
  context.font = `${size}px "Share Tech Mono", monospace`
  context.textAlign = align
  context.fillText(value, x, y)
}

function line(context, x1, y1, x2, y2, color = COLORS.line) {
  context.strokeStyle = color
  context.lineWidth = 1
  context.beginPath()
  context.moveTo(x1, y1)
  context.lineTo(x2, y2)
  context.stroke()
}

function frame(context, x, y, width, height, label = '') {
  context.strokeStyle = COLORS.line
  context.strokeRect(x, y, width, height)
  const notch = Math.min(58, width * .3)
  context.fillStyle = COLORS.bg
  context.fillRect(x + 8, y - 4, notch, 9)
  if (label) text(context, label, x + 12, y, COLORS.dim, 7)
  line(context, x, y + 15, x + width, y + 15, COLORS.faint)
  const corner = 7
  line(context, x, y, x + corner, y, COLORS.green)
  line(context, x, y, x, y + corner, COLORS.green)
  line(context, x + width - corner, y + height, x + width, y + height, COLORS.dim)
  line(context, x + width, y + height - corner, x + width, y + height, COLORS.dim)
}

function node(context, x, y, label, active = false, side = 'right') {
  const color = active ? COLORS.green : COLORS.sub
  context.strokeStyle = active ? COLORS.green : COLORS.line
  context.strokeRect(x - 4, y - 4, 8, 8)
  context.fillStyle = active ? COLORS.green : COLORS.dim
  context.fillRect(x - 1, y - 1, 2, 2)
  text(context, label, x + (side === 'right' ? 10 : -10), y, color, 8, side === 'right' ? 'left' : 'right')
}

function backdrop(context, width, height, time, seed, pointer, impulse) {
  context.fillStyle = COLORS.bg
  context.fillRect(0, 0, width, height)
  const cellX = width < 420 ? 23 : 19
  const cellY = 18
  const glyphs = ['.', ':', '+', '-', '|']
  for (let y = 12; y < height; y += cellY) {
    for (let x = 9; x < width; x += cellX) {
      const noise = hash(x / cellX, y / cellY, seed)
      const pointerDistance = pointer.active ? Math.hypot(x / width - pointer.x, y / height - pointer.y) : 1
      const energized = pointerDistance < .16 || Math.abs(noise - ((impulse * .13) % 1)) < .025
      if (noise > .8 || energized) {
        const glyph = energized ? '+' : glyphs[Math.floor((noise * glyphs.length + time * .00016) % glyphs.length)]
        text(context, glyph, x, y, energized ? 'rgba(255,186,24,.55)' : COLORS.faint, 8)
      }
    }
  }
}

function scopeHeader(context, width, mode, time, motion) {
  text(context, `HF.TOOLBOX / ${mode.toUpperCase()} FIELD`, 12, 13, COLORS.sub, 7)
  text(context, motion ? 'RUNTIME DYNAMIC' : 'RUNTIME STATIC', width - 12, 13, motion ? COLORS.green : COLORS.amber, 7, 'right')
  line(context, 12, 25, width - 12, 25)
  const scan = motion ? ((time * .06) % Math.max(1, width - 24)) : width * .42
  line(context, 12 + scan, 22, 12 + scan, 28, COLORS.green)
}

function compactField(context, width, height, time, impulse, mode) {
  const labels = LABELS[mode] || LABELS.home
  const active = Math.floor(time / 800 + impulse) % labels.length
  const left = 18
  const right = width - 18
  const y = Math.max(58, height * .57)
  frame(context, 12, 36, width - 24, Math.max(45, height - 48), `${mode.toUpperCase()} SIGNAL`)
  line(context, left, y, right, y, COLORS.line)
  labels.forEach((label, index) => {
    const x = labels.length === 1 ? width / 2 : left + index * ((right - left) / (labels.length - 1))
    context.strokeStyle = index === active ? COLORS.green : COLORS.line
    context.strokeRect(x - 3, y - 3, 6, 6)
    if (index === active) text(context, label, x, y - 14, COLORS.green, 7, 'center')
  })
  const progress = ((time / 1700) + impulse * .13) % 1
  context.fillStyle = COLORS.amber
  context.fillRect(left + (right - left) * progress - 2, y - 2, 4, 4)
  text(context, `FOCUS ${labels[active]}`, 17, height - 8, COLORS.green, 7)
  text(context, `${String(active + 1).padStart(2, '0')}/${String(labels.length).padStart(2, '0')}`, width - 17, height - 8, COLORS.dim, 7, 'right')
}

function homeField(context, width, height, time, impulse) {
  const cx = width * .5
  const cy = height * .43
  const labels = LABELS.home
  const rx = Math.min(width * .34, 175)
  const ry = Math.min(height * .26, 128)
  frame(context, 14, 38, width - 28, height - 86, 'PROGRAM TOPOLOGY')
  const nodes = labels.map((label, index) => {
    const angle = Math.PI * 2 * index / labels.length - Math.PI / 2
    return { label, x: cx + Math.cos(angle) * rx, y: cy + Math.sin(angle) * ry }
  })
  const active = Math.floor(time / 760 + impulse) % labels.length
  nodes.forEach((item, index) => {
    line(context, cx, cy, item.x, item.y, index === active ? 'rgba(57,255,20,.55)' : COLORS.line)
    node(context, item.x, item.y, item.label, index === active, item.x > cx ? 'right' : 'left')
  })
  context.strokeStyle = COLORS.green
  context.strokeRect(cx - 31, cy - 12, 62, 24)
  text(context, 'HF.TBX', cx, cy, COLORS.green, 10, 'center')
  const progress = ((time / 2200) + impulse * .1) % 1
  const target = nodes[active]
  context.fillStyle = COLORS.amber
  context.fillRect(cx + (target.x - cx) * progress - 2, cy + (target.y - cy) * progress - 2, 4, 4)
  text(context, 'PROGRAM BUS', 18, height - 31, COLORS.dim, 7)
  text(context, labels[active], width - 18, height - 31, COLORS.green, 8, 'right')
}

function pipelineField(context, width, height, time, impulse, mode) {
  const labels = LABELS[mode]
  const top = 54
  const bottom = height - 50
  const left = 26
  const right = width - 28
  frame(context, 14, 38, width - 28, height - 79, mode === 'contracts' ? 'CONTRACT STATE TREE' : 'WORK QUEUE')
  const active = Math.floor(time / 820 + impulse) % labels.length
  const laneH = (bottom - top) / labels.length
  labels.forEach((label, index) => {
    const y = top + laneH * index + laneH / 2
    text(context, String(index + 1).padStart(2, '0'), left, y, COLORS.dim, 7)
    text(context, label, left + 20, y, index === active ? COLORS.green : COLORS.sub, 8)
    line(context, left + 90, y, right, y, index === active ? 'rgba(57,255,20,.55)' : COLORS.faint)
    const blocks = 4 + index
    for (let block = 0; block < blocks; block += 1) {
      const x = left + 104 + block * 15
      if (x < right - 10) {
        context.fillStyle = block === ((Math.floor(time / 310) + impulse) % blocks) && index === active ? COLORS.amber : COLORS.line
        context.fillRect(x, y - 3, 8, 6)
      }
    }
  })
  text(context, `FOCUS ${labels[active]}`, 18, height - 25, COLORS.green, 7)
  text(context, 'STATE / OWNER / NEXT ACTION', width - 18, height - 25, COLORS.dim, 7, 'right')
}

function bumpField(context, width, height, time, impulse) {
  const cx = width * .5
  const cy = height * .43
  const radius = Math.min(width, height) * .25
  frame(context, 14, 38, width - 28, height - 79, 'SCHEDULER SCOPE')
  ;[1, .72, .44].forEach((scale, index) => {
    context.strokeStyle = index === 0 ? COLORS.line : COLORS.faint
    context.beginPath()
    context.arc(cx, cy, radius * scale, 0, Math.PI * 2)
    context.stroke()
  })
  line(context, cx - radius - 16, cy, cx + radius + 16, cy, COLORS.faint)
  line(context, cx, cy - radius - 16, cx, cy + radius + 16, COLORS.faint)
  const angle = -Math.PI / 2 + time * .001 + impulse * .42
  line(context, cx, cy, cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius, COLORS.green)
  context.fillStyle = COLORS.amber
  context.fillRect(cx + Math.cos(angle) * radius - 3, cy + Math.sin(angle) * radius - 3, 6, 6)
  text(context, 'NEXT WINDOW', cx, cy - 9, COLORS.dim, 7, 'center')
  text(context, 'SCHEDULED', cx, cy + 6, COLORS.green, 10, 'center')
  const labels = ['ELIGIBLE', 'QUEUED', 'POSTED', 'MEASURED']
  labels.forEach((label, index) => text(context, `${index + 1} ${label}`, 20 + index * ((width - 40) / labels.length), height - 25, index === Math.floor(time / 900 + impulse) % 4 ? COLORS.green : COLORS.dim, 7))
}

function marketField(context, width, height, time, impulse) {
  frame(context, 14, 38, width - 28, height - 79, 'INDEX HEATMAP')
  const labels = LABELS.market
  const x0 = 25
  const y0 = 64
  const usableW = width - 50
  const usableH = height - 128
  const columns = width < 420 ? 9 : 15
  const rows = 8
  labels.forEach((label, index) => text(context, label, x0 + index * (usableW / labels.length), 53, COLORS.sub, 7))
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      const x = x0 + col * (usableW / columns)
      const y = y0 + row * (usableH / rows)
      const strength = hash(col, row, Math.floor(time / 800) + impulse)
      text(context, strength > .87 ? '#' : strength > .68 ? '+' : '.', x, y, strength > .87 ? COLORS.green : strength > .68 ? COLORS.sub : COLORS.faint, 9)
    }
  }
  const sweep = (time * .035 + impulse * 19) % usableW
  line(context, x0 + sweep, y0 - 8, x0 + sweep, y0 + usableH, 'rgba(88,199,196,.42)')
  text(context, 'OBSERVED THREAD FIELD', 18, height - 25, COLORS.cyan, 7)
  text(context, 'FILTER -> WATCH -> OPEN', width - 18, height - 25, COLORS.dim, 7, 'right')
}

function postingField(context, width, height, time, impulse) {
  const x = 18
  const y = 39
  const w = width - 36
  const h = height - 80
  frame(context, x, y, w, h, 'POST ASSEMBLY')
  const labels = LABELS.posting
  const active = Math.floor(time / 900 + impulse) % labels.length
  labels.forEach((label, index) => {
    const rowY = y + 29 + index * 29
    text(context, `${index === active ? '>' : ' '} ${String(index + 1).padStart(2, '0')} ${label}`, x + 11, rowY, index === active ? COLORS.green : COLORS.dim, 8)
    const chars = Math.max(2, Math.floor((w - 115) / 9))
    text(context, (index <= active ? '=' : '-').repeat(chars), x + 100, rowY, index === active ? COLORS.green : COLORS.faint, 7)
  })
  const cursorX = x + 100 + ((time * .04 + impulse * 25) % Math.max(20, w - 120))
  line(context, cursorX, y + 19, cursorX, y + h - 12, 'rgba(255,186,24,.36)')
  text(context, 'PRIVATE UNTIL CONFIRMED', 18, height - 25, COLORS.amber, 7)
}

function bytesField(context, width, height, time, impulse) {
  frame(context, 14, 38, width - 28, height - 79, 'LEDGER SIGNAL')
  const left = 24
  const right = width - 24
  const top = 62
  const labels = ['BALANCE', 'SERVICE', 'FORUM', 'TRANSFER']
  labels.forEach((label, index) => {
    const y = top + index * 27
    text(context, label, left, y, COLORS.dim, 7)
    text(context, index % 2 ? '- BYTE ENTRY' : '+ BYTE ENTRY', right, y, index % 2 ? COLORS.amber : COLORS.green, 7, 'right')
    line(context, left + 70, y, right - 78, y, COLORS.faint)
  })
  const mid = height - 69
  context.strokeStyle = COLORS.green
  context.beginPath()
  context.moveTo(left, mid)
  for (let x = left; x <= right; x += 4) {
    const y = mid + Math.sin(x * .045 + time * .002 + impulse) * 13 + Math.sin(x * .013 - time * .001) * 8
    context.lineTo(x, y)
  }
  context.stroke()
  text(context, 'AMOUNT / REASON / REFERENCE', 18, height - 25, COLORS.sub, 7)
}

function casinoField(context, width, height, time, impulse) {
  frame(context, 14, 38, width - 28, height - 79, 'TABLE PROGRAM / RESERVED')
  const cx = width * .5
  const cy = height * .46
  const rx = Math.min(width * .34, 175)
  const ry = Math.min(height * .22, 94)
  context.strokeStyle = COLORS.line
  context.beginPath()
  context.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
  context.stroke()
  context.beginPath()
  context.ellipse(cx, cy, rx - 9, ry - 9, 0, 0, Math.PI * 2)
  context.stroke()
  LABELS.casino.forEach((label, index) => {
    const angle = Math.PI * 2 * index / 4 - Math.PI / 2
    node(context, cx + Math.cos(angle) * rx, cy + Math.sin(angle) * ry, label, index === (Math.floor(time / 1100 + impulse) % 4), Math.cos(angle) >= 0 ? 'right' : 'left')
  })
  ;[-1, 0, 1].forEach((offset, index) => {
    context.strokeStyle = index === 1 ? COLORS.amber : COLORS.line
    context.strokeRect(cx + offset * 22 - 8, cy - 12, 16, 24)
  })
  text(context, 'COMING SOON', cx, cy + 26, COLORS.amber, 8, 'center')
  text(context, 'NO SIMULATED TABLE ACTIVITY', 18, height - 25, COLORS.dim, 7)
}

function pointerReticle(context, width, height, pointer, time) {
  if (!pointer.active) return
  const x = pointer.x * width
  const y = pointer.y * height
  const radius = 9 + (time * .008 % 8)
  context.strokeStyle = 'rgba(255,186,24,.62)'
  context.beginPath()
  context.arc(x, y, radius, 0, Math.PI * 2)
  context.stroke()
  line(context, x - radius - 5, y, x - radius + 1, y, COLORS.amber)
  line(context, x + radius - 1, y, x + radius + 5, y, COLORS.amber)
  text(context, 'INPUT', x + 14, y - 11, COLORS.amber, 7)
}

export default function AsciiField({ mode = 'home', motion = true, impulse = 0, onInteract }) {
  const canvasRef = useRef(null)
  const pointerRef = useRef({ x: .5, y: .5, active: false })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    let context
    let frameId = 0
    let width = 1
    let height = 1
    let visible = !document.hidden
    let previous = 0

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, rect.width)
      height = Math.max(1, rect.height)
      context = setupCanvas(canvas, width, height)
    }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    resize()

    const draw = (time = 0) => {
      if (!context) return
      backdrop(context, width, height, time, mode.length, pointerRef.current, impulse)
      scopeHeader(context, width, mode, time, motion)
      if (height < 180) compactField(context, width, height, time, impulse, mode)
      else if (mode === 'home') homeField(context, width, height, time, impulse)
      else if (mode === 'business' || mode === 'contracts') pipelineField(context, width, height, time, impulse, mode)
      else if (mode === 'bumps') bumpField(context, width, height, time, impulse)
      else if (mode === 'market') marketField(context, width, height, time, impulse)
      else if (mode === 'posting') postingField(context, width, height, time, impulse)
      else if (mode === 'bytes') bytesField(context, width, height, time, impulse)
      else if (mode === 'casino') casinoField(context, width, height, time, impulse)
      pointerReticle(context, width, height, pointerRef.current, time)
    }

    const loop = (time) => {
      const target = width <= 720 ? 33 : 16
      if (visible && time - previous >= target) {
        draw(time)
        previous = time
      }
      frameId = requestAnimationFrame(loop)
    }
    const visibility = () => { visible = !document.hidden }
    document.addEventListener('visibilitychange', visibility)
    if (motion) frameId = requestAnimationFrame(loop)
    else draw(0)

    return () => {
      cancelAnimationFrame(frameId)
      observer.disconnect()
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [impulse, mode, motion])

  const updatePointer = (event, fire = false) => {
    const rect = event.currentTarget.getBoundingClientRect()
    pointerRef.current = {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
      active: true,
    }
    if (fire) onInteract?.()
  }

  return (
    <canvas
      ref={canvasRef}
      className="os-ascii-canvas"
      aria-hidden="true"
      onPointerMove={updatePointer}
      onPointerDown={event => updatePointer(event, true)}
      onPointerLeave={() => { pointerRef.current.active = false }}
    />
  )
}
