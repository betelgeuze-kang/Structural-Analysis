/** Additional longitudinal bars at explicitly authored section-centroid heights. */
export function intermediateSteelBarCount(section: Record<string, unknown>): number {
  if (!Object.prototype.hasOwnProperty.call(section, 'intermediate_steel_layers')) return 0
  const layers = section.intermediate_steel_layers
  const depth = section.depth_m
  const cover = section.cover_m
  if (!Array.isArray(layers) || layers.length < 1 || layers.length > 32
    || typeof depth !== 'number' || !Number.isFinite(depth)
    || typeof cover !== 'number' || !Number.isFinite(cover)
    || cover <= 0 || depth <= 2 * cover) throw new Error('intermediate_steel_layers_invalid')
  let previous = -depth / 2 + cover
  let count = 0
  for (const layer of layers) {
    if (!layer || typeof layer !== 'object' || Array.isArray(layer)
      || Object.keys(layer).sort().join(',') !== 'bar_count,y_m'
      || typeof layer.y_m !== 'number' || !Number.isFinite(layer.y_m)
      || !(previous < layer.y_m && layer.y_m < depth / 2 - cover)
      || !Number.isInteger(layer.bar_count) || layer.bar_count < 1 || layer.bar_count > 64) {
      throw new Error('intermediate_steel_layer_invalid')
    }
    previous = layer.y_m
    count += layer.bar_count
  }
  return count
}
