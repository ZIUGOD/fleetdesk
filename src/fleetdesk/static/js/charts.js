// Chart helpers shared by every page. Colours come from the CSS theme tokens, and charts
// are rebuilt when the theme changes (see layout.html).

const formatBRL = v => 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatNumber = (v, decimals = 0) =>
  Number(v).toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const compactFormatter = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });
const formatCompact = v => compactFormatter.format(v);

const FORMATTERS = {
  brl: formatBRL,
  tonnes: v => formatNumber(v, 1) + ' t',
  count: v => formatNumber(v),
};

const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim();

function applyChartTheme() {
  Chart.defaults.color = cssVar('muted');
  Chart.defaults.borderColor = cssVar('grid');
  Chart.defaults.font.family = cssVar('font-ui');
  Chart.defaults.font.size = 11;
  Chart.defaults.animation.duration = 300;
  Chart.defaults.plugins.legend.display = false;
  Object.assign(Chart.defaults.plugins.tooltip, {
    backgroundColor: cssVar('surface'),
    titleColor: cssVar('text'),
    bodyColor: cssVar('text-2'),
    borderColor: cssVar('border-strong'),
    borderWidth: 1,
    padding: 10,
    cornerRadius: 8,
    boxPadding: 4,
    usePointStyle: true,
    titleFont: { weight: '600' },
  });
}

// Vertical guide line that follows the hovered point on line charts.
const crosshairPlugin = {
  id: 'crosshair',
  afterDatasetsDraw(chart) {
    const active = chart.tooltip && chart.tooltip.getActiveElements();
    if (!active || !active.length) return;
    const x = active[0].element.x;
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = cssVar('axis');
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.restore();
  },
};

const chartBuilders = [];
let chartInstances = [];

// Registers a function that creates charts, so they can be rebuilt on theme change.
function registerCharts(build) {
  chartBuilders.push(build);
  applyChartTheme();
  chartInstances = chartInstances.concat(build());
}

window.redrawCharts = function () {
  chartInstances.forEach(chart => chart.destroy());
  chartInstances = [];
  applyChartTheme();
  chartBuilders.forEach(build => { chartInstances = chartInstances.concat(build()); });
};

function horizontalBarChart(canvasId, series, format = 'brl') {
  const canvas = document.getElementById(canvasId);
  canvas.parentElement.style.height = (series.labels.length * 30 + 34) + 'px';
  const formatValue = FORMATTERS[format];
  // The folded "Outros (n)" bar is drawn in a neutral tone so it does not read as a peer.
  const colors = series.labels.map(label => label.startsWith('Outros') ? cssVar('axis') : cssVar('series-1'));
  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels: series.labels,
      datasets: [{
        data: series.values,
        backgroundColor: colors,
        hoverBackgroundColor: colors,
        borderRadius: 4,
        borderSkipped: 'start',
        barThickness: 14,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false, axis: 'y' },
      plugins: { tooltip: { displayColors: false, callbacks: { label: c => formatValue(c.raw) } } },
      scales: {
        x: { border: { display: false }, grid: { color: cssVar('grid') }, ticks: { callback: v => formatCompact(v) } },
        y: { border: { color: cssVar('axis') }, grid: { display: false }, ticks: { color: cssVar('text-2'), autoSkip: false } },
      },
    },
  });
}

function lineChart(canvasId, labels, datasets) {
  return new Chart(document.getElementById(canvasId), {
    type: 'line',
    data: {
      labels,
      datasets: datasets.map((dataset, i) => ({
        label: dataset.label,
        data: dataset.data,
        borderColor: cssVar('series-' + (i + 1)),
        backgroundColor: cssVar('series-' + (i + 1)),
        borderWidth: 2,
        cubicInterpolationMode: 'monotone',
        pointRadius: 0,
        pointHoverRadius: 5,
        pointHoverBorderWidth: 2,
        pointHoverBorderColor: cssVar('surface'),
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: { callbacks: { label: c => ' ' + c.dataset.label + ': ' + formatBRL(c.raw) } } },
      scales: {
        x: { border: { color: cssVar('axis') }, grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
        y: { border: { display: false }, grid: { color: cssVar('grid') }, ticks: { callback: v => 'R$ ' + formatCompact(v) } },
      },
    },
    plugins: [crosshairPlugin],
  });
}
