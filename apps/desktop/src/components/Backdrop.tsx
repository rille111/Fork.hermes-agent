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
    <div
      aria-hidden
      className={
        chandra
          ? 'pointer-events-none absolute inset-0 z-2 opacity-[0.34]'
          : 'pointer-events-none absolute inset-0 z-2 opacity-[0.025] mix-blend-difference'
      }
      data-chandra-backdrop={chandra ? '' : undefined}
    >
      <img
        alt=""
        className={
          chandra
            ? 'h-dvh w-full object-cover object-center [filter:saturate(1.08)_brightness(0.82)_contrast(1.08)]'
            : 'h-[160dvh] w-auto min-w-dvw object-cover object-left-top [filter:invert(var(--backdrop-invert-mul,1))]'
        }
        fetchPriority="low"
        src={assetPath('ds-assets/filler-bg0.jpg')}
      />
      {chandra && <div className="chandra-backdrop-scrim absolute inset-0" />}
    </div>
  )
}
