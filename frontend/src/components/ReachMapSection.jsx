import { useCallback, useEffect, useRef, useState } from 'react'

import { api } from '../api'
import { formatNumberLocale, t } from '../i18n'
import './reach-map.css'

function useReachData(active) {
  const [state, setState] = useState({ data: null, error: '', loading: false })
  const load = useCallback(() => {
    setState((previous) => ({ ...previous, loading: true, error: '' }))
    api.publicReach()
      .then((data) => setState({ data, error: '', loading: false }))
      .catch(() => setState({ data: null, error: t('Coverage data is unavailable right now.'), loading: false }))
  }, [])

  useEffect(() => {
    if (active && !state.data && !state.loading && !state.error) load()
  }, [active, load, state])

  return { ...state, reload: load }
}

function ReachMap({ regions, selected, onSelect, theme }) {
  const hostRef = useRef(null)
  const [supported, setSupported] = useState(null)

  useEffect(() => {
    const canvas = document.createElement('canvas')
    setSupported(Boolean(canvas.getContext('webgl2') || canvas.getContext('webgl')))
  }, [])

  useEffect(() => {
    if (supported !== true || !hostRef.current || !regions.length) return undefined
    const host = hostRef.current
    let disposed = false
    let cleanup = () => {}

    ;(async () => {
      const [THREE, { OrbitControls }, shapes] = await Promise.all([
        import('three'),
        import('three/examples/jsm/controls/OrbitControls.js'),
        fetch('/geo/uzbekistan-regions.json').then((response) => {
          if (!response.ok) throw new Error(`Map geometry request failed with ${response.status}`)
          return response.json()
        }),
      ])
      if (disposed) return

      const styleRoot = host.closest('[data-theme]') || document.documentElement
      const token = (name, fallback) => getComputedStyle(styleRoot).getPropertyValue(name).trim() || fallback
      const scene = new THREE.Scene()
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      host.appendChild(renderer.domElement)

      const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 1000)
      camera.position.set(0, 12.5, 11)
      camera.lookAt(0, 0, 0.4)
      scene.add(new THREE.AmbientLight(0xffffff, 1.5))
      const keyLight = new THREE.DirectionalLight(0xffffff, 1.1)
      keyLight.position.set(-4, 9, 6)
      scene.add(keyLight)

      const points = Object.values(shapes).flat().flat()
      const longitudes = points.map((point) => point[0])
      const latitudes = points.map((point) => point[1])
      const centerLongitude = (Math.min(...longitudes) + Math.max(...longitudes)) / 2
      const centerLatitude = (Math.min(...latitudes) + Math.max(...latitudes)) / 2
      const scale = 14 / (Math.max(...longitudes) - Math.min(...longitudes))
      const byRegion = new Map(regions.map((region) => [region.region, region]))
      const maxStudents = Math.max(1, ...regions.map((region) => region.students))
      const meshes = []

      Object.entries(shapes).forEach(([regionKey, rings]) => {
        const region = byRegion.get(regionKey)
        const share = region ? region.students / maxStudents : 0
        rings.forEach((ring) => {
          const shape = new THREE.Shape()
          ring.forEach(([longitude, latitude], index) => {
            const x = (longitude - centerLongitude) * scale
            const y = (latitude - centerLatitude) * scale
            if (index === 0) shape.moveTo(x, y)
            else shape.lineTo(x, y)
          })
          const geometry = new THREE.ExtrudeGeometry(shape, {
            depth: 0.28 + share * 1.15,
            bevelEnabled: false,
          })
          const material = new THREE.MeshLambertMaterial({ transparent: true })
          const mesh = new THREE.Mesh(geometry, material)
          mesh.rotation.x = -Math.PI / 2
          mesh.userData.region = regionKey
          scene.add(mesh)
          meshes.push(mesh)
        })
      })

      const selectedRef = { current: selected }
      const hoveredRef = { current: null }
      const paint = () => {
        const base = new THREE.Color(token('--text-subtle', '#888888'))
        const signal = new THREE.Color(token('--accent', '#8b7355'))
        const selectedColor = new THREE.Color(token('--text', '#4a4035'))
        meshes.forEach((mesh) => {
          const region = byRegion.get(mesh.userData.region)
          const share = region ? region.students / maxStudents : 0
          const highlighted = selectedRef.current === mesh.userData.region || hoveredRef.current === mesh.userData.region
          mesh.material.color.copy(highlighted ? selectedColor : base.clone().lerp(signal, 0.25 + share * 0.6))
          mesh.material.opacity = highlighted || region?.active ? 1 : 0.68
        })
      }

      const render = () => renderer.render(scene, camera)
      const resize = () => {
        const width = host.clientWidth
        const height = host.clientHeight || Math.round(width * 0.62)
        renderer.setSize(width, height, true)
        camera.aspect = width / height
        camera.updateProjectionMatrix()
        paint()
        render()
      }

      const controls = new OrbitControls(camera, renderer.domElement)
      controls.target.set(0, 0, 0.4)
      controls.enablePan = false
      controls.enableZoom = false
      controls.rotateSpeed = 0.72
      controls.minPolarAngle = Math.PI * 0.14
      controls.maxPolarAngle = Math.PI * 0.42
      controls.update()

      const setHoveredRegion = (regionKey) => {
        if (hoveredRef.current === regionKey) return
        hoveredRef.current = regionKey
        paint()
        render()
      }
      const rotateWithKeyboard = (event) => {
        const turns = {
          ArrowLeft: { theta: -0.12, phi: 0 },
          ArrowRight: { theta: 0.12, phi: 0 },
          ArrowUp: { theta: 0, phi: -0.08 },
          ArrowDown: { theta: 0, phi: 0.08 },
        }
        const turn = turns[event.key]
        if (!turn) return
        event.preventDefault()
        const offset = camera.position.clone().sub(controls.target)
        const spherical = new THREE.Spherical().setFromVector3(offset)
        spherical.theta += turn.theta
        spherical.phi = THREE.MathUtils.clamp(spherical.phi + turn.phi, controls.minPolarAngle, controls.maxPolarAngle)
        camera.position.copy(controls.target).add(offset.setFromSpherical(spherical))
        camera.lookAt(controls.target)
        controls.update()
        render()
      }

      const raycaster = new THREE.Raycaster()
      const pointer = new THREE.Vector2()
      const regionAtPointer = (event) => {
        const bounds = renderer.domElement.getBoundingClientRect()
        pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1
        pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1
        raycaster.setFromCamera(pointer, camera)
        return raycaster.intersectObjects(meshes)[0]?.object.userData.region || null
      }

      let gestureStart = null
      let dragged = false
      const startGesture = (event) => {
        gestureStart = { x: event.clientX, y: event.clientY }
        dragged = false
        setHoveredRegion(null)
      }
      const trackGesture = (event) => {
        if (!gestureStart) {
          if (event.pointerType === 'mouse') setHoveredRegion(regionAtPointer(event))
          return
        }
        if (Math.hypot(event.clientX - gestureStart.x, event.clientY - gestureStart.y) > 5) dragged = true
      }
      const endGesture = (event) => {
        const regionKey = regionAtPointer(event)
        if (gestureStart && !dragged) onSelect(regionKey)
        gestureStart = null
        dragged = false
        setHoveredRegion(event.pointerType === 'mouse' ? regionKey : null)
      }
      const cancelGesture = () => {
        gestureStart = null
        dragged = false
        setHoveredRegion(null)
      }
      const leaveMap = () => {
        if (!gestureStart) setHoveredRegion(null)
      }
      const startRotating = () => host.classList.add('is-rotating')
      const stopRotating = () => host.classList.remove('is-rotating')

      host.addEventListener('keydown', rotateWithKeyboard)
      controls.addEventListener('change', render)
      controls.addEventListener('start', startRotating)
      controls.addEventListener('end', stopRotating)
      renderer.domElement.addEventListener('pointerdown', startGesture)
      renderer.domElement.addEventListener('pointermove', trackGesture)
      renderer.domElement.addEventListener('pointerup', endGesture)
      renderer.domElement.addEventListener('pointercancel', cancelGesture)
      renderer.domElement.addEventListener('pointerleave', leaveMap)
      const observer = new ResizeObserver(resize)
      observer.observe(host)
      resize()

      host.__repaintReachMap = (nextSelected) => {
        selectedRef.current = nextSelected
        paint()
        render()
      }
      cleanup = () => {
        observer.disconnect()
        host.removeEventListener('keydown', rotateWithKeyboard)
        controls.removeEventListener('change', render)
        controls.removeEventListener('start', startRotating)
        controls.removeEventListener('end', stopRotating)
        controls.dispose()
        renderer.domElement.removeEventListener('pointerdown', startGesture)
        renderer.domElement.removeEventListener('pointermove', trackGesture)
        renderer.domElement.removeEventListener('pointerup', endGesture)
        renderer.domElement.removeEventListener('pointercancel', cancelGesture)
        renderer.domElement.removeEventListener('pointerleave', leaveMap)
        meshes.forEach((mesh) => {
          mesh.geometry.dispose()
          mesh.material.dispose()
        })
        renderer.dispose()
        delete host.__repaintReachMap
        renderer.domElement.remove()
      }
    })().catch(() => {
      if (!disposed) setSupported(false)
    })

    return () => {
      disposed = true
      cleanup()
    }
  }, [onSelect, regions, supported, theme])

  useEffect(() => {
    hostRef.current?.__repaintReachMap?.(selected)
  }, [selected])

  if (supported === false) return null
  return (
    <div
      className="reach-map-canvas"
      ref={hostRef}
      role="application"
      tabIndex="0"
      aria-label={t('Interactive map of Uzbekistan. Drag to rotate or use the arrow keys.')}
    >
      <span className="reach-map-hint" aria-hidden="true">{t('Drag to rotate')}</span>
    </div>
  )
}

export function ReachMapSection({ theme }) {
  const sectionRef = useRef(null)
  const [near, setNear] = useState(false)
  const [selected, setSelected] = useState(null)
  const { data, error, loading, reload } = useReachData(near)

  useEffect(() => {
    const section = sectionRef.current
    if (!section) return undefined
    const check = () => {
      if (section.getBoundingClientRect().top < window.innerHeight * 2) setNear(true)
    }
    check()
    window.addEventListener('scroll', check, { passive: true })
    return () => window.removeEventListener('scroll', check)
  }, [])

  const regions = data?.regions || []
  const current = regions.find((region) => region.region === selected)

  return (
    <section className="reach-section" id="reach" ref={sectionRef}>
      <header className="reach-section-header">
        <h2>{t('Where Naseeb Edu is working.')}</h2>
        <p>{t('Coverage is drawn from the schools using the platform, and updates as new ones join.')}</p>
      </header>
      <div className="reach-section-grid">
        <div className="reach-section-total">
          {loading && !data && <span className="reach-section-skeleton" aria-hidden="true" />}
          {data && <strong>{formatNumberLocale(data.total)}</strong>}
          <span>{t('Students on the platform')}</span>
          {error && <p role="alert">{error} <button type="button" onClick={reload}>{t('Retry')}</button></p>}
        </div>
        <div className="reach-section-map">
          <ReachMap regions={regions} selected={selected} onSelect={setSelected} theme={theme} />
          <ul className="reach-region-list">
            {regions.map((region) => (
              <li key={region.region} className={region.region === selected ? 'is-active' : ''}>
                <button
                  type="button"
                  onMouseEnter={() => setSelected(region.region)}
                  onFocus={() => setSelected(region.region)}
                  onClick={() => setSelected(region.region)}
                >
                  <span>{t(region.label)}</span>
                  <b>{formatNumberLocale(region.students)}</b>
                </button>
              </li>
            ))}
          </ul>
          <p className="reach-section-readout" role="status">
            {current
              ? `${t(current.label)} — ${formatNumberLocale(current.students)}`
              : t('Select a region to see its number.')}
          </p>
        </div>
      </div>
    </section>
  )
}
