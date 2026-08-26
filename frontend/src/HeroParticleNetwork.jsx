import { useEffect, useRef } from 'react'

const clamp = (value, min, max) => Math.min(Math.max(value, min), max)

export default function HeroParticleNetwork({ theme }) {
  const fieldRef = useRef(null)
  const canvasRef = useRef(null)

  useEffect(() => {
    const field = fieldRef.current
    const canvas = canvasRef.current
    const hero = field?.closest('.landing-hero')
    const context = canvas?.getContext('2d')
    if (!field || !canvas || !hero || !context) return undefined

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const particles = []
    const pointer = { x: 0, y: 0, active: false }
    let width = 0
    let height = 0
    let frame = 0
    let isVisible = true
    let lastTime = 0

    const styles = getComputedStyle(field)
    const dotColor = styles.getPropertyValue('--lp-particle-dot').trim() || '#ffffff'
    const lineColor = styles.getPropertyValue('--lp-particle-line').trim() || '#ffffff'

    const createParticles = () => {
      particles.length = 0
      const areaCount = Math.round((width * height) / 28000)
      const count = width < 620 ? clamp(areaCount, 16, 24) : clamp(areaCount, 24, 46)

      for (let index = 0; index < count; index += 1) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          radius: 1.65 + Math.random() * 1.8,
          vx: (Math.random() - 0.5) * 0.16,
          vy: (Math.random() - 0.5) * 0.16,
          phase: Math.random() * Math.PI * 2,
        })
      }
    }

    const resize = () => {
      const bounds = field.getBoundingClientRect()
      width = Math.max(1, bounds.width)
      height = Math.max(1, bounds.height)
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(width * pixelRatio)
      canvas.height = Math.round(height * pixelRatio)
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      createParticles()
      draw(0)
    }

    const drawConnection = (fromX, fromY, toX, toY, opacity, lineWidth = 0.85) => {
      context.globalAlpha = opacity
      context.strokeStyle = lineColor
      context.lineWidth = lineWidth
      context.beginPath()
      context.moveTo(fromX, fromY)
      context.lineTo(toX, toY)
      context.stroke()
    }

    const draw = (elapsed) => {
      context.clearRect(0, 0, width, height)
      const connectionDistance = clamp(width * 0.13, 116, 182)
      const pointerDistance = clamp(width * 0.21, 180, 275)

      for (let first = 0; first < particles.length; first += 1) {
        const particle = particles[first]

        if (!reducedMotion && elapsed > 0) {
          const step = Math.min(elapsed, 32)
          particle.x += particle.vx * step
          particle.y += particle.vy * step
          if (particle.x < -12) particle.x = width + 12
          if (particle.x > width + 12) particle.x = -12
          if (particle.y < -12) particle.y = height + 12
          if (particle.y > height + 12) particle.y = -12
        }

        for (let second = first + 1; second < particles.length; second += 1) {
          const neighbor = particles[second]
          const distance = Math.hypot(particle.x - neighbor.x, particle.y - neighbor.y)
          if (distance < connectionDistance) {
            drawConnection(
              particle.x,
              particle.y,
              neighbor.x,
              neighbor.y,
              (1 - distance / connectionDistance) * 0.38,
            )
          }
        }

        if (pointer.active) {
          const distance = Math.hypot(particle.x - pointer.x, particle.y - pointer.y)
          if (distance < pointerDistance) {
            drawConnection(
              pointer.x,
              pointer.y,
              particle.x,
              particle.y,
              (1 - distance / pointerDistance) * 0.74,
              1.05,
            )
          }
        }
      }

      particles.forEach((particle) => {
        const pulse = reducedMotion ? 0.66 : 0.58 + Math.sin(performance.now() * 0.0012 + particle.phase) * 0.14
        context.globalAlpha = pulse
        context.fillStyle = dotColor
        context.beginPath()
        context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2)
        context.fill()
      })

      if (pointer.active) {
        context.globalAlpha = 0.34
        context.fillStyle = dotColor
        context.beginPath()
        context.arc(pointer.x, pointer.y, 10, 0, Math.PI * 2)
        context.fill()
        context.globalAlpha = 0.92
        context.beginPath()
        context.arc(pointer.x, pointer.y, 2.8, 0, Math.PI * 2)
        context.fill()
      }

      context.globalAlpha = 1
    }

    const animate = (time) => {
      if (!isVisible || document.hidden) {
        frame = 0
        return
      }
      const elapsed = lastTime ? time - lastTime : 16
      lastTime = time
      draw(elapsed)
      frame = window.requestAnimationFrame(animate)
    }

    const start = () => {
      if (reducedMotion || frame || !isVisible || document.hidden) return
      lastTime = 0
      frame = window.requestAnimationFrame(animate)
    }

    const stop = () => {
      if (frame) window.cancelAnimationFrame(frame)
      frame = 0
    }

    const handlePointerMove = (event) => {
      if (reducedMotion || event.pointerType === 'touch') return
      const bounds = field.getBoundingClientRect()
      pointer.x = event.clientX - bounds.left
      pointer.y = event.clientY - bounds.top
      pointer.active = pointer.x >= 0 && pointer.x <= width && pointer.y >= 0 && pointer.y <= height
    }

    const handlePointerLeave = () => {
      pointer.active = false
    }

    const handleVisibilityChange = () => {
      if (document.hidden) stop()
      else start()
    }

    const resizeObserver = new ResizeObserver(resize)
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      isVisible = entry.isIntersecting
      if (isVisible) start()
      else stop()
    }, { threshold: 0.02 })

    resizeObserver.observe(field)
    intersectionObserver.observe(field)
    hero.addEventListener('pointermove', handlePointerMove, { passive: true })
    hero.addEventListener('pointerleave', handlePointerLeave, { passive: true })
    document.addEventListener('visibilitychange', handleVisibilityChange)
    resize()
    start()

    return () => {
      stop()
      resizeObserver.disconnect()
      intersectionObserver.disconnect()
      hero.removeEventListener('pointermove', handlePointerMove)
      hero.removeEventListener('pointerleave', handlePointerLeave)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [theme])

  return (
    <div className="landing-particle-field" ref={fieldRef} aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  )
}
