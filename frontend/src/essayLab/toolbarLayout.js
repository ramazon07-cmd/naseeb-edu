// How many toolbar groups fit in a width (tested under plain node).

const MORE_WIDTH = 48
const GROUP_PADDING = 13

// How many groups fit in `width`; the rest go to the "more" panel.
export function fitGroups(width, groups) {
  const widths = groups.map((group) => group.width + GROUP_PADDING)
  const total = widths.reduce((sum, value) => sum + value, 0)
  if (total <= width) return groups.length
  let used = MORE_WIDTH
  let count = 0
  for (const value of widths) {
    if (used + value > width) break
    used += value
    count += 1
  }
  return count
}
