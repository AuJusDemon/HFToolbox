import { useEffect, useRef } from 'react'

const MODE_LABELS = {
  home: ['BUSINESS', 'BUMPS', 'MARKET', 'CONTRACTS', 'POSTING', 'BYTES'],
  business: ['REPLY', 'REVIEW', 'ACTIVE', 'WAIT', 'DONE'],
  bumps: ['QUEUE', 'TIMER', 'POST', 'RESULT'],
  market: ['BAZAAR', 'PREMIUM', 'SERVICES', 'AUX'],
  contracts: ['REVIEW', 'ACTIVE', 'WAIT', 'DONE'],
  posting: ['DRAFT', 'PREVIEW', 'SUBMIT', 'WATCH'],
  bytes: ['BALANCE', 'SPEND', 'RECEIVE', 'LEDGER'],
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
  return context
}

function drawBackdrop(context, width, height, time, seed) {
  context.fillStyle = '#030603'
  context.fillRect(0, 0, width, height)
  context.font = '11px "Share Tech Mono", monospace'
  context.textBaseline = 'middle'
  context.fillStyle = 'rgba(72, 126, 72, .18)'
  const cellX = width < 420 ? 22 : 18
  const cellY = 19
  for (let y = 13; y < height; y += cellY) {
    for (let x = 10; x < width; x += cellX) {
      const noise = hash(x / cellX, y / cellY, seed)
      if (noise > .76) {
        const glyphs = '.:+-|'
        const offset = Math.floor((noise * glyphs.length + time * .00025) % glyphs.length)
        context.fillText(glyphs[offset], x, y)
      }
    }
  }
}

function drawNode(context, x, y, label, active = false) {
  context.strokeStyle = active ? '#39ff14' : 'rgba(93, 171, 93, .55)'
  context.fillStyle = active ? '#39ff14' : '#739473'
  context.lineWidth = active ? 1.5 : 1
  context.strokeRect(x - 4, y - 4, 8, 8)
  context.font = '10px "Share Tech Mono", monospace'
  context.fillText(label, x + 10, y)
}

function drawNetwork(context, width, height, labels, time, pointer, impulse) {
  const center = { x: width * .48, y: height * .48 }
  const radiusX = Math.min(width * .31, 170)
  const radiusY = Math.min(height * .3, 105)
  const nodes = labels.map((label, index) => {
    const angle = (Math.PI * 2 * index / labels.length) - Math.PI / 2
    return { label, x: center.x + Math.cos(angle) * radiusX, y: center.y + Math.sin(angle) * radiusY }
  })
  context.strokeStyle = 'rgba(57, 255, 20, .22)'
  nodes.forEach(node => {
    context.beginPath()
    context.moveTo(center.x, center.y)
    context.lineTo(node.x, node.y)
    context.stroke()
  })
  const active = Math.floor(time / 900 + impulse) % nodes.length
  nodes.forEach((node, index) => drawNode(context, node.x, node.y, node.label, index === active))
  drawNode(context, center.x, center.y, 'HF.TOOLBOX', true)
  if (pointer.active) {
    context.strokeStyle = 'rgba(255, 187, 0, .5)'
    context.beginPath()
    context.moveTo(center.x, center.y)
    context.lineTo(pointer.x * width, pointer.y * height)
    context.stroke()
  }
}

function drawPipeline(context, width, height, labels, time, impulse) {
  const left = 30
  const right = width - 30
  const gap = (right - left) / Math.max(1, labels.length - 1)
  const y = height * .52
  context.strokeStyle = 'rgba(57, 255, 20, .32)'
  context.beginPath()
  context.moveTo(left, y)
  context.lineTo(right, y)
  context.stroke()
  labels.forEach((label, index) => drawNode(context, left + gap * index, y, label, index === Math.floor(time / 850 + impulse) % labels.length))
  const progress = ((time / 2400) + impulse * .12) % 1
  context.fillStyle = '#ffbb00'
  context.fillRect(left + (right - left) * progress - 3, y - 3, 6, 6)
}

function drawBumps(context, width, height, time, impulse) {
  const cx = width * .47
  const cy = height * .5
  const radius = Math.min(width, height) * .27
  context.strokeStyle = 'rgba(57, 255, 20, .28)'
  context.lineWidth = 1
  ;[1, .72, .42].forEach(scale => {
    context.beginPath()
    context.arc(cx, cy, radius * scale, 0, Math.PI * 2)
    context.stroke()
  })
  const angle = time * .0012 + impulse * .45
  const x = cx + Math.cos(angle) * radius
  const y = cy + Math.sin(angle) * radius
  context.strokeStyle = '#39ff14'
  context.beginPath()
  context.moveTo(cx, cy)
  context.lineTo(x, y)
  context.stroke()
  drawNode(context, x, y, 'NEXT BUMP', true)
  drawNode(context, cx, cy, 'SCHEDULER', false)
}

function drawMarket(context, width, height, time) {
  const labels = MODE_LABELS.market
  const columns = width < 420 ? 8 : 13
  const rows = 7
  const cellW = (width - 48) / columns
  const cellH = (height - 70) / rows
  labels.forEach((label, index) => {
    context.fillStyle = '#789678'
    context.font = '9px "Share Tech Mono", monospace'
    context.fillText(label, 24 + index * ((width - 48) / labels.length), 24)
  })
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < columns; col += 1) {
      const strength = hash(col, row, Math.floor(time / 700))
      context.fillStyle = strength > .84 ? '#39ff14' : strength > .62 ? 'rgba(57,255,20,.36)' : 'rgba(80,120,80,.12)'
      context.fillText(strength > .84 ? '#' : strength > .62 ? '+' : '.', 24 + col * cellW, 54 + row * cellH)
    }
  }
}

function drawPosting(context, width, height, time) {
  const max = width < 420 ? 20 : 34
  const completed = Math.floor(time / 90) % (max + 8)
  context.font = '11px "Share Tech Mono", monospace'
  MODE_LABELS.posting.forEach((label, index) => {
    const y = 46 + index * 48
    context.fillStyle = '#718c71'
    context.fillText(`${String(index + 1).padStart(2, '0')} ${label}`, 24, y)
    context.fillStyle = index <= Math.floor(completed / 10) ? '#39ff14' : 'rgba(57,255,20,.2)'
    context.fillText('='.repeat(Math.min(max, Math.max(0, completed - index * 7))), 120, y)
  })
}

function drawBytes(context, width, height, time) {
  const mid = height * .52
  context.strokeStyle = 'rgba(57,255,20,.24)'
  context.beginPath()
  context.moveTo(20, mid)
  for (let x = 20; x < width - 20; x += 5) {
    const y = mid + Math.sin(x * .035 + time * .002) * 28 + Math.sin(x * .012 - time * .001) * 13
    context.lineTo(x, y)
  }
  context.stroke()
  MODE_LABELS.bytes.forEach((label, index) => drawNode(context, 40 + index * ((width - 80) / 3), height * .78, label, index === Math.floor(time / 900) % 4))
}

function drawCasino(context, width, height, time) {
  const cx = width * .48
  const cy = height * .52
  const rx = Math.min(width * .34, 175)
  const ry = Math.min(height * .27, 86)
  context.strokeStyle = 'rgba(57,255,20,.36)'
  context.beginPath()
  context.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2)
  context.stroke()
  MODE_LABELS.casino.forEach((label, index) => {
    const angle = Math.PI * 2 * index / 4 + time * .00008
    drawNode(context, cx + Math.cos(angle) * rx, cy + Math.sin(angle) * ry, label, index === 0)
  })
  context.fillStyle = '#ffbb00'
  context.font = '10px "Share Tech Mono", monospace'
  context.fillText('COMING SOON', cx - 36, cy)
}

function drawPointer(context, width, height, pointer, time) {
  if (!pointer.active) return
  const x = pointer.x * width
  const y = pointer.y * height
  const radius = 7 + (time * .01 % 10)
  context.strokeStyle = 'rgba(255, 187, 0, .52)'
  context.beginPath()
  context.arc(x, y, radius, 0, Math.PI * 2)
  context.stroke()
  context.fillStyle = '#ffbb00'
  context.font = '9px "Share Tech Mono", monospace'
  context.fillText('+INPUT', x + 12, y - 9)
}

export default function AsciiField({ mode = 'home', motion = true, impulse = 0, onInteract }) {
  const canvasRef = useRef(null)
  const pointerRef = useRef({ x: .5, y: .5, active: false })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    let context
    let frame = 0
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
      drawBackdrop(context, width, height, time, mode.length)
      if (mode === 'home') drawNetwork(context, width, height, MODE_LABELS.home, time, pointerRef.current, impulse)
      else if (mode === 'business' || mode === 'contracts') drawPipeline(context, width, height, MODE_LABELS[mode], time, impulse)
      else if (mode === 'bumps') drawBumps(context, width, height, time, impulse)
      else if (mode === 'market') drawMarket(context, width, height, time)
      else if (mode === 'posting') drawPosting(context, width, height, time)
      else if (mode === 'bytes') drawBytes(context, width, height, time)
      else if (mode === 'casino') drawCasino(context, width, height, time)
      drawPointer(context, width, height, pointerRef.current, time)
      context.fillStyle = '#526b52'
      context.font = '9px "Share Tech Mono", monospace'
      context.fillText(`VIS/${mode.toUpperCase()}  ${motion ? 'DYNAMIC' : 'STATIC'}`, 12, height - 12)
    }

    const loop = (time) => {
      const target = width <= 720 ? 33 : 16
      if (visible && time - previous >= target) {
        draw(time)
        previous = time
      }
      frame = requestAnimationFrame(loop)
    }
    const visibility = () => { visible = !document.hidden }
    document.addEventListener('visibilitychange', visibility)
    if (motion) frame = requestAnimationFrame(loop)
    else draw(0)

    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [impulse, mode, motion])

  const updatePointer = (event) => {
    const rect = event.currentTarget.getBoundingClientRect()
    pointerRef.current = {
      x: Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
      active: true,
    }
    onInteract?.()
  }

  return (
    <canvas
      ref={canvasRef}
      className="os-ascii-canvas"
      aria-hidden="true"
      onPointerMove={updatePointer}
      onPointerDown={updatePointer}
      onPointerLeave={() => { pointerRef.current.active = false }}
    />
  )
}
