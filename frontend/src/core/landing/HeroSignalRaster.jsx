import { useEffect, useRef } from 'react'

const HEX = '0123456789ABCDEF'

function seededValue(index) {
  return ((index * 37 + 11) % 97) / 97
}

function drawRaster(context, width, height, time, intensity, still) {
  context.clearRect(0, 0, width, height)
  context.save()
  context.globalAlpha = .52 + intensity * .16
  context.strokeStyle = '#183218'
  context.fillStyle = '#315c31'
  context.lineWidth = 1

  const rowHeight = 19
  const rows = Math.max(5, Math.floor(height / rowHeight))
  const drift = still ? 0 : (time * .018) % 48
  context.font = '8px "Share Tech Mono", monospace'
  context.textBaseline = 'middle'

  for (let row = 0; row < rows; row += 1) {
    const y = 10 + row * rowHeight
    context.globalAlpha = .17 + (row % 3) * .045
    context.beginPath()
    context.moveTo(0, y + 7)
    context.lineTo(width, y + 7)
    context.stroke()

    const direction = row % 2 ? 1 : -1
    const offset = ((drift * direction) + row * 29 + 96) % 48
    for (let column = -1; column < Math.ceil(width / 48) + 1; column += 1) {
      const seed = row * 31 + column * 7
      const x = column * 48 + offset
      const length = 8 + Math.floor(seededValue(seed) * 19)
      const left = Math.round(x)
      context.globalAlpha = .20 + seededValue(seed + 4) * .16
      context.fillRect(left, y + 5, length, 1)
      if ((row + column) % 3 === 0) {
        const code = `${HEX[(seed + 16) & 15]}${HEX[(seed + 5) & 15]}`
        context.fillText(code, left + length + 4, y)
      }
    }
  }

  const sweep = still ? width * .64 : (time * (.024 + intensity * .018)) % (width + 36) - 18
  context.globalAlpha = .22 + intensity * .15
  context.fillStyle = '#39ff14'
  context.fillRect(Math.round(sweep), 0, 1, height)
  context.fillRect(Math.round(sweep - 5), 0, 1, height)

  const baseline = height - 24
  context.globalAlpha = .35 + intensity * .2
  context.strokeStyle = '#78c76a'
  context.beginPath()
  for (let x = 0; x <= width; x += 4) {
    const gate = ((x + Math.floor(time * .025)) % 72) < 34 ? 1 : -1
    const wave = Math.sin((x + time * .035) * .055) * (3 + intensity * 5)
    const y = baseline + gate * 3 + wave
    if (x === 0) context.moveTo(x, y)
    else context.lineTo(x, y)
  }
  context.stroke()
  context.restore()
}

export default function HeroSignalRaster({ active = false, reducedMotion = false }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    const context = canvas.getContext('2d')
    if (!context) return undefined

    let frame = 0
    let visible = !document.hidden
    let width = 0
    let height = 0
    let lastFrame = 0
    const frameInterval = window.matchMedia('(max-width: 720px)').matches ? 50 : 32

    const resize = () => {
      const bounds = canvas.getBoundingClientRect()
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      width = Math.max(1, Math.round(bounds.width))
      height = Math.max(1, Math.round(bounds.height))
      canvas.width = Math.round(width * ratio)
      canvas.height = Math.round(height * ratio)
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      drawRaster(context, width, height, 0, active ? 1 : 0, reducedMotion)
    }

    const render = (time) => {
      if (visible && time - lastFrame >= frameInterval) {
        drawRaster(context, width, height, time, active ? 1 : 0, false)
        lastFrame = time
      }
      frame = window.requestAnimationFrame(render)
    }
    const onVisibilityChange = () => { visible = !document.hidden }
    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    document.addEventListener('visibilitychange', onVisibilityChange)
    resize()
    if (!reducedMotion) frame = window.requestAnimationFrame(render)

    return () => {
      observer.disconnect()
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.cancelAnimationFrame(frame)
    }
  }, [active, reducedMotion])

  return <canvas ref={canvasRef} className="hero-signal-raster" data-motion={reducedMotion ? 'still' : 'running'} aria-hidden="true" />
}
