import type { Waypoint } from '@/data/mockFleet'

export const VIEWBOX_WIDTH = 1000
export const VIEWBOX_HEIGHT = 560

export function project({ lng, lat }: Waypoint): { x: number; y: number } {
  const x = ((lng + 180) / 360) * VIEWBOX_WIDTH
  const y = ((90 - lat) / 180) * VIEWBOX_HEIGHT
  return { x, y }
}

export function projectPercent(point: Waypoint): { left: string; top: string } {
  const { x, y } = project(point)
  return {
    left: `${(x / VIEWBOX_WIDTH) * 100}%`,
    top: `${(y / VIEWBOX_HEIGHT) * 100}%`
  }
}

export function toPolylinePoints(points: Waypoint[]): string {
  return points.map((p) => { const { x, y } = project(p); return `${x},${y}` }).join(' ')
}

export function pointToPercent(x: number, y: number): { left: string; top: string } {
  return {
    left: `${(x / VIEWBOX_WIDTH) * 100}%`,
    top: `${(y / VIEWBOX_HEIGHT) * 100}%`
  }
}

export interface XY {
  x: number
  y: number
}

// Nudges points that are closer than minDist apart so their on-screen markers
// don't fully occlude each other, while staying as close as possible to the
// true projected position (real relative location matters for this radar).
export function declutter(points: (XY & { id: string })[], minDist = 34, iterations = 8): Record<string, XY> {
  const result: Record<string, XY> = {}
  points.forEach((p) => (result[p.id] = { x: p.x, y: p.y }))

  for (let iter = 0; iter < iterations; iter++) {
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const a = result[points[i].id]
        const b = result[points[j].id]
        const dx = b.x - a.x
        const dy = b.y - a.y
        const dist = Math.hypot(dx, dy) || 0.001
        if (dist < minDist) {
          const push = (minDist - dist) / 2
          const ux = dx / dist
          const uy = dy / dist
          a.x -= ux * push
          a.y -= uy * push
          b.x += ux * push
          b.y += uy * push
        }
      }
    }
  }
  return result
}
