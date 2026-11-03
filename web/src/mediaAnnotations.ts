import style from '../../data/annotation-style.json'

export type MediaTarget = { id: string; name: string; label: string; label_name: string; first_seen: number; last_seen: number; samples: { t: number; bbox: number[]; confidence?: number }[] }
export type VisibleBox = { id: string; label: string; text: string; bbox: number[] }
export function classColor(label: string): string {
  return (style.colors as Record<string, string>)[label] || style.fallback_palette[[...label].reduce((sum, c) => sum + c.charCodeAt(0), 0) % style.fallback_palette.length]!
}
export function boxesAtTime(targets: MediaTarget[], time: number, fps: number, image: boolean): VisibleBox[] {
  const frame = image ? 0 : Math.floor((time + .0001) * fps)
  return targets.flatMap(target => {
    const sample = target.samples.find(s => image || Math.round(s.t * fps) === frame)
    return sample ? [{ id: target.id, label: target.label, text: `${target.label_name} #${target.id}`, bbox: sample.bbox }] : []
  })
}
type Rect = [number, number, number, number]
export function overlap(a: Rect, b: Rect): number {
  return Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]))
}
export function layoutLabels(boxes: VisibleBox[], width: number, height: number) {
  if (width < 40 || height < 40) return []
  const placed: Rect[] = [], h = style.label_height
  const pixels = boxes.map(b => b.bbox.map((v, i) => v * (i % 2 ? height : width)) as Rect)
  return boxes.map((box, index) => {
    const rect = pixels[index]!, [x1, y1, x2, y2] = rect
    const w = Math.min(width - 4, [...box.text].reduce((sum, c) => sum + (c.charCodeAt(0) > 255 ? 14 : 8), 12))
    let best: Rect = [2, 2, 2 + w, 2 + h], bestCost = Infinity
    for (const dy of [0, -h, h, -2*h, 2*h, -3*h, 3*h, -4*h, 4*h]) {
      for (const [rawX, rawY] of [[x1, y1-h-4+dy], [x1, y2+4+dy], [x2+5, y1+dy], [x1-w-5, y1+dy]]) {
        const x = Math.max(2, Math.min(width-w-2, rawX!)), y = Math.max(2, Math.min(height-h-2, rawY!))
        const candidate: Rect = [x, y, x+w, y+h]
        const cost = placed.reduce((s, p) => s + overlap(candidate, p)*1000, 0)
          + pixels.reduce((s, p, i) => s + overlap(candidate, p)*(i === index ? 4 : 12), 0)
          + Math.abs(x-x1) + Math.abs(y-(y1-h-4))
        if (cost < bestCost) { bestCost = cost; best = candidate }
      }
    }
    placed.push(best)
    const anchor = [Math.max(x1, Math.min(x2, (best[0]+best[2])/2)), y1]
    const end = [Math.max(best[0], Math.min(best[2], anchor[0]!)), Math.max(best[1], Math.min(best[3], anchor[1]!))]
    return { ...box, rect, labelRect: best, color: classColor(box.label), anchor, end }
  })
}
