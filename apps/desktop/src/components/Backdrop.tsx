import { useStore } from '@nanostores/react'

import { $backdrop } from '@/store/backdrop'
import { useTheme } from '@/themes'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

export function Backdrop() {
  const on = useStore($backdrop)
  const { themeName } = useTheme()
  const chandra = themeName === 'chandra'

  if (!on) {
    return null
  }

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
