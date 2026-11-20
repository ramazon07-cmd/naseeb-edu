// The dashed "average" line on the Screen Time bar charts.

// Under a minute of daily average reads "< 1 min", never "0 min", while there was some activity.
export function averageText(average, format, minLabel) {
  return average > 0 && average < 60 ? `< 1 ${minLabel}` : format(average);
}

// The label sits at the right end of the line unless a bar there rises above
// the line; then it moves to the left end, when the bars there stay below it.
export function averageSide(rows, average) {
  const span = rows.length <= 7 ? 2 : rows.length <= 14 ? 4 : 8;
  const rises = (row) => row.seconds > average;
  return rows.slice(-span).some(rises) && !rows.slice(0, span).some(rises) ? 'start' : 'end';
}
