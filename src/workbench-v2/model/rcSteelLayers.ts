interface ExplicitSteelLayer { id: string; y_m: number; bar_count: number; bar_area_m2: number; steel_material: string }
const explicitSectionType = 'rectangular_rc_explicit_steel_layers'

/** Validate authored geometry before recomputing a stored quantity report. */
function explicitSteelLayers(section: Record<string, unknown>): ExplicitSteelLayer[] {
  const layers = section.steel_layers
  const depth = section.depth_m, width = section.width_m
  if (!Array.isArray(layers) || layers.length < 1 || layers.length > 32
    || typeof depth !== 'number' || !Number.isFinite(depth) || depth <= 0
    || typeof width !== 'number' || !Number.isFinite(width) || width <= 0) throw new Error('explicit_steel_layers_invalid')
  let previous = -depth / 2
  const ids = new Set<string>()
  for (const layer of layers) {
    if (!layer || typeof layer !== 'object' || Array.isArray(layer)
      || Object.keys(layer).sort().join(',') !== 'bar_area_m2,bar_count,id,steel_material,y_m'
      || typeof layer.id !== 'string' || !layer.id || ids.has(layer.id)
      || typeof layer.steel_material !== 'string' || !layer.steel_material
      || typeof layer.y_m !== 'number' || !Number.isFinite(layer.y_m) || !(previous < layer.y_m && layer.y_m < depth / 2)
      || !Number.isInteger(layer.bar_count) || layer.bar_count < 1 || layer.bar_count > 64
      || typeof layer.bar_area_m2 !== 'number' || !Number.isFinite(layer.bar_area_m2) || layer.bar_area_m2 <= 0) {
      throw new Error('explicit_steel_layer_invalid')
    }
    previous = layer.y_m
    ids.add(layer.id)
  }
  const total = sumAreas(layers.map(layer => layer.bar_count * layer.bar_area_m2))
  if (!Number.isFinite(total) || !Number.isFinite(width * depth) || total >= width * depth) throw new Error('explicit_steel_area_invalid')
  return layers
}

function sumAreas(values: number[]): number {
  let total = 0, correction = 0
  for (const value of values) {
    const next = total + value
    correction += Math.abs(total) >= Math.abs(value) ? (total - next) + value : (value - next) + total
    total = next
  }
  return total + correction
}

/** Distances are from each concrete face to the longitudinal bar centroid. */
export function outerSteelCentroidDistances(section: Record<string, unknown>): [number, number] {
  const depth = section.depth_m
  const distance = (value: unknown): number => {
    if (typeof depth !== 'number' || !Number.isFinite(depth) || typeof value !== 'number'
      || !Number.isFinite(value) || value <= 0 || value >= depth / 2) throw new Error('steel_centroid_distance_invalid')
    return value
  }
  const common = distance(section.cover_m)
  return ['top_cover_m', 'bottom_cover_m'].map(key => Object.prototype.hasOwnProperty.call(section, key) ? distance(section[key]) : common) as [number, number]
}

/** Additional longitudinal bars at explicitly authored section-centroid heights. */
export function intermediateSteelBarCount(section: Record<string, unknown>): number {
  const [topCover, bottomCover] = outerSteelCentroidDistances(section)
  if (!Object.prototype.hasOwnProperty.call(section, 'intermediate_steel_layers')) return 0
  const layers = section.intermediate_steel_layers
  const depth = section.depth_m
  const cover = section.cover_m
  if (!Array.isArray(layers) || layers.length < 1 || layers.length > 32
    || typeof depth !== 'number' || !Number.isFinite(depth)
    || typeof cover !== 'number' || !Number.isFinite(cover)
    || cover <= 0 || depth <= 2 * cover) throw new Error('intermediate_steel_layers_invalid')
  let previous = -depth / 2 + bottomCover
  let count = 0
  for (const layer of layers) {
    if (!layer || typeof layer !== 'object' || Array.isArray(layer)
      || Object.keys(layer).sort().join(',') !== 'bar_count,y_m'
      || typeof layer.y_m !== 'number' || !Number.isFinite(layer.y_m)
      || !(previous < layer.y_m && layer.y_m < depth / 2 - topCover)
      || !Number.isInteger(layer.bar_count) || layer.bar_count < 1 || layer.bar_count > 64) {
      throw new Error('intermediate_steel_layer_invalid')
    }
    previous = layer.y_m
    count += layer.bar_count
  }
  return count
}

const outerAreaFields = ['top_bar_area_m2', 'bottom_bar_area_m2'] as const
export function outerSteelAreas(section: Record<string, unknown>): [number, number] {
  const area = (value: unknown): number => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) throw new Error('steel_bar_area_invalid')
    return value
  }
  const common = area(section.bar_area_m2)
  return outerAreaFields.map(key => Object.prototype.hasOwnProperty.call(section, key) ? area(section[key]) : common) as [number, number]
}

export function longitudinalSteelArea(section: Record<string, unknown>): number {
  if (section.type === explicitSectionType) return sumAreas(explicitSteelLayers(section).map(layer => layer.bar_count * layer.bar_area_m2))
  const [top, bottom] = outerSteelAreas(section)
  const common = section.bar_area_m2 as number
  const counts = ['top_bar_count', 'bottom_bar_count'].map(key => {
    const count = section[key]
    if (typeof count !== 'number' || !Number.isInteger(count) || count < 1 || count > 64) throw new Error('steel_bar_count_invalid')
    return count
  })
  const middle = intermediateSteelBarCount(section)
  return top === common && bottom === common
    ? (counts[0] + counts[1] + middle) * common
    : counts[0] * top + counts[1] * bottom + middle * common
}

export function longitudinalSteelDescription(section: Record<string, unknown>): string {
  if (section.type === explicitSectionType) return explicitSteelLayers(section)
    .map(layer => `${layer.id}: ${layer.bar_count} × ${layer.bar_area_m2} m² at ${layer.y_m} m; ${layer.steel_material}`).join('; ')
  const [top, bottom] = outerSteelAreas(section)
  const middle = intermediateSteelBarCount(section)
  return `top ${section.top_bar_count} × ${top} m²; bottom ${section.bottom_bar_count} × ${bottom} m²`
    + (middle ? `; intermediate ${middle} × ${section.bar_area_m2} m²` : '')
    + (['top_cover_m', 'bottom_cover_m'].some(key => Object.prototype.hasOwnProperty.call(section, key))
      ? `; face-to-steel centroid top/bottom ${outerSteelCentroidDistances(section).join('/')} m` : '')
}
