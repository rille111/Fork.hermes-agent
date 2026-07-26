import { useStore } from '@nanostores/react'
import { Leva, useControls } from 'leva'
import { type CSSProperties, useEffect, useState } from 'react'

import { $backdrop } from '@/store/backdrop'
import { useTheme } from '@/themes'

const BLEND_MODES = [
  'normal',
  'multiply',
  'screen',
  'overlay',
  'darken',
  'lighten',
  'color-dodge',
  'color-burn',
  'hard-light',
  'soft-light',
  'difference',
  'exclusion',
  'hue',
  'saturation',
  'color',
  'luminosity'
] as const

type BlendMode = (typeof BLEND_MODES)[number]
const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

export function Backdrop() {
  const [controlsOpen, setControlsOpen] = useState(false)
  const on = useStore($backdrop)
  const { themeName } = useTheme()
  const chandra = themeName === 'chandra'

  useEffect(() => {
    if (!import.meta.env.DEV) {
      return
    }

    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null

      const editing =
        target?.isContentEditable ||
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement

      if (editing || event.repeat || event.altKey || event.ctrlKey || event.metaKey) {
        return
      }

      if (event.shiftKey && event.code === 'KeyY') {
        setControlsOpen(open => !open)
      }
    }

    window.addEventListener('keydown', onKeyDown)

    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const shape = useControls(
    'UI / Shape',
    { radiusScalar: { value: 0.2, min: 0, max: 2, step: 0.1, label: 'radius scalar' } },
    { collapsed: true }
  )

  useEffect(() => {
    document.documentElement.style.setProperty('--radius-scalar', String(shape.radiusScalar))
  }, [shape.radiusScalar])

  const statue = useControls(
    'Backdrop / Statue',
    {
      enabled: { value: true, label: 'on' },
      opacity: { value: 0.025, min: 0, max: 1, step: 0.005 },
      blendMode: { value: 'difference' as BlendMode, options: BLEND_MODES, label: 'blend' },
      invert: { value: true, label: 'invert color' },
      saturate: { value: 1, min: 0, max: 3, step: 0.05, label: 'saturate' },
      brightness: { value: 1, min: 0, max: 2, step: 0.05, label: 'brightness' },
      objectPosition: {
        value: 'top left',
        options: ['top left', 'top right', 'bottom left', 'bottom right', 'center', 'top', 'bottom', 'left', 'right'],
        label: 'position'
      },
      scale: { value: 160, min: 100, max: 300, step: 5, label: 'height (dvh)' }
    },
    { collapsed: true }
  )

  return (
    <>
      <Leva collapsed hidden={!import.meta.env.DEV || !controlsOpen} titleBar={{ title: 'backdrop', drag: true }} />

      {(on || chandra) && statue.enabled && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-2"
          data-chandra-backdrop={chandra ? '' : undefined}
          style={{
            mixBlendMode: (chandra ? 'normal' : statue.blendMode) as CSSProperties['mixBlendMode'],
            opacity: chandra ? 0.34 : statue.opacity
          }}
        >
          <img
            alt=""
            className={chandra ? 'h-dvh w-full object-cover' : 'w-auto min-w-dvw object-cover'}
            fetchPriority="low"
            src={assetPath('ds-assets/filler-bg0.jpg')}
            style={{
              height: chandra ? '100dvh' : `${statue.scale}dvh`,
              objectPosition: chandra ? 'center center' : statue.objectPosition,
              filter: chandra
                ? 'saturate(1.08) brightness(0.82) contrast(1.08)'
                : `invert(calc(${statue.invert ? 1 : 0} * var(--backdrop-invert-mul, 1))) saturate(${statue.saturate}) brightness(${statue.brightness})`
            }}
          />
          {chandra && <div className="chandra-backdrop-scrim absolute inset-0" />}
        </div>
      )}
    </>
  )
}
