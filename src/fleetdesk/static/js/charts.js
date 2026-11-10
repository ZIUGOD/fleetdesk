// Chart panels shared by the pages. Each panel can show its data in several views (bars,
// donut, table...); the user's choice is remembered per panel in this browser. Colours come
// from the CSS theme tokens, and every panel is redrawn when the theme changes (layout.html).

const formatBRL = v => 'R$ ' + Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatNumber = (v, decimals = 0) =>
  Number(v).toLocaleString('pt-BR', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const formatPercent = v => (v * 100).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + '%';
const compactFormatter = new Intl.NumberFormat('pt-BR', { notation: 'compact', maximumFractionDigits: 1 });
const formatCompact = v => compactFormatter.format(v);

const FORMATTERS = {
  brl: formatBRL,
  tonnes: v => formatNumber(v, 1) + ' t',
  count: v => formatNumber(v),
};
const AXIS_FORMATTERS = {
  brl: v => 'R$ ' + formatCompact(v),
  tonnes: v => formatCompact(v) + ' t',
  count: v => formatCompact(v),
};

const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue('--' + name).trim();

// "#rrggbb" plus opacity, for area fills.
function withAlpha(hex, alpha) {
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

const isOthers = label => label.startsWith('Outros');
const categoryColor = (label, i) => (isOthers(label) ? cssVar('axis') : cssVar('cat-' + ((i % 6) + 1)));

function applyChartTheme() {
  Chart.defaults.color = cssVar('muted');
  Chart.defaults.borderColor = cssVar('grid');
  Chart.defaults.font.family = cssVar('font-ui');
  Chart.defaults.font.size = 11;
  // Charts are drawn at once, with no intro animation. Animations advance only while the
  // browser paints frames, so a page opened in a background tab or behind another window
  // showed empty or half-drawn charts (donuts especially, which "spin in" from nothing).
  Chart.defaults.animation = false;
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

/* ── Panels with a view switcher ──────────────────────────────────────────── */

const VIEW_ICONS = {
  bar: 'bi-bar-chart-line', donut: 'bi-pie-chart', table: 'bi-table', line: 'bi-graph-up',
  area: 'bi-graph-up-arrow', cumulative: 'bi-stack', columns: 'bi-bar-chart', waterfall: 'bi-bar-chart-steps',
};
const panels = [];

const savedView = id => { try { return localStorage.getItem('fleetdesk.view.' + id); } catch (_) { return null; } };
const saveView = (id, view) => { try { localStorage.setItem('fleetdesk.view.' + id, view); } catch (_) { /* private mode */ } };

// views: [{ key, label, chart(canvas) → Chart } or { key, label, table() → {columns, rows, footer} }]
function chartPanel(id, views) {
  const root = document.getElementById(id);
  if (!root) return;
  // Views that size themselves (bars, donut) change the height; the others get it back.
  const panel = { id, root, views, chart: null, view: null, height: root.querySelector('.chart-box').style.height };
  const remembered = savedView(id);
  panel.view = views.some(v => v.key === remembered) ? remembered : views[0].key;

  const switcher = root.querySelector('.view-switch');
  views.forEach(view => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.view = view.key;
    button.title = view.label;
    button.setAttribute('aria-label', 'Ver como ' + view.label.toLowerCase());
    button.innerHTML = `<i class="bi ${VIEW_ICONS[view.key] || 'bi-circle'}" aria-hidden="true"></i><span></span>`;
    button.querySelector('span').textContent = view.label;
    button.addEventListener('click', () => {
      panel.view = view.key;
      saveView(id, view.key);
      renderPanel(panel);
    });
    switcher.appendChild(button);
  });
  panels.push(panel);
  applyChartTheme();
  renderPanel(panel);
}

function renderPanel(panel) {
  if (panel.chart) { panel.chart.destroy(); panel.chart = null; }
  const view = panel.views.find(v => v.key === panel.view);
  const box = panel.root.querySelector('.chart-box');
  const tableBox = panel.root.querySelector('.chart-table');
  panel.root.querySelectorAll('.view-switch button').forEach(button => {
    button.setAttribute('aria-pressed', String(button.dataset.view === view.key));
  });
  if (view.table) {
    box.hidden = true;
    tableBox.hidden = false;
    tableBox.replaceChildren(buildTable(view.table()));
    return;
  }
  tableBox.hidden = true;
  box.hidden = false;
  box.style.height = panel.height || '260px';
  panel.chart = view.chart(box.querySelector('canvas'), box);
}

window.redrawCharts = function () {
  applyChartTheme();
  panels.forEach(renderPanel);
};

// Built with DOM nodes, never innerHTML: labels come from the spreadsheets.
function buildTable({ columns, rows, footer }) {
  const table = document.createElement('table');
  table.className = 'data-table';
  const row = (cells, tag) => {
    const tr = document.createElement('tr');
    cells.forEach((cell, i) => {
      const td = document.createElement(tag);
      td.textContent = cell;
      if (i > 0) td.className = 'end num';
      tr.appendChild(td);
    });
    return tr;
  };
  table.createTHead().appendChild(row(columns, 'th'));
  const body = table.createTBody();
  rows.forEach(cells => body.appendChild(row(cells, 'td')));
  if (footer) table.createTFoot().appendChild(row(footer, 'td'));
  const wrap = document.createElement('div');
  wrap.className = 'table-scroll bordered';
  wrap.appendChild(table);
  return wrap;
}

/* ── Category views: bars, donut, table ───────────────────────────────────── */

function barsView(series, format) {
  return canvas => {
    canvas.parentElement.style.height = (series.labels.length * 30 + 34) + 'px';
    const formatValue = FORMATTERS[format];
    // The folded "Outros (n)" bar is drawn in a neutral tone so it does not read as a peer.
    const colors = series.labels.map(label => (isOthers(label) ? cssVar('axis') : cssVar('series-1')));
    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels: series.labels,
        datasets: [{ data: series.values, backgroundColor: colors, hoverBackgroundColor: colors, borderRadius: 4, borderSkipped: 'start', barThickness: 14 }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false, axis: 'y' },
        plugins: { tooltip: { displayColors: false, callbacks: { label: c => formatValue(c.raw) + ' · ' + formatPercent(c.raw / total(series.values)) } } },
        scales: {
          x: { border: { display: false }, grid: { color: cssVar('grid') }, ticks: { callback: AXIS_FORMATTERS[format] } },
          y: { border: { color: cssVar('axis') }, grid: { display: false }, ticks: { color: cssVar('text-2'), autoSkip: false } },
        },
      },
    });
  };
}

const total = values => values.reduce((sum, v) => sum + v, 0);

// A donut stays readable with few slices: the top 5 plus everything else as "Outros".
function topSlices(series, keep = 5) {
  const pairs = series.labels.map((label, i) => [label, series.values[i]]);
  const named = pairs.filter(([label]) => !isOthers(label));
  const rest = pairs.filter(([label]) => isOthers(label)).concat(named.slice(keep));
  const kept = named.slice(0, keep);
  if (rest.length) {
    const count = rest.reduce((n, [label]) => n + (isOthers(label) ? parseInt(label.replace(/\D/g, ''), 10) || 1 : 1), 0);
    kept.push([`Outros (${count})`, rest.reduce((sum, [, v]) => sum + v, 0)]);
  }
  return { labels: kept.map(p => p[0]), values: kept.map(p => p[1]) };
}

function donutView(series, format, keep = 5) {
  return canvas => {
    canvas.parentElement.style.height = '300px';
    const slices = series.labels.length <= keep + 1 ? series : topSlices(series, keep);
    const sum = total(slices.values);
    const formatValue = FORMATTERS[format];
    return new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: slices.labels,
        datasets: [{
          data: slices.values,
          backgroundColor: slices.labels.map(categoryColor),
          borderColor: cssVar('surface'),
          borderWidth: 2,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '62%',
        // The biggest slice starts at 12 o'clock; slices come largest first.
        rotation: 0,
        plugins: {
          legend: {
            display: true,
            position: window.innerWidth < 576 ? 'bottom' : 'right',
            labels: {
              color: cssVar('text-2'),
              usePointStyle: true,
              pointStyle: 'rectRounded',
              padding: 10,
              // The share is written next to each name, so colour is never the only cue.
              generateLabels: chart => Chart.overrides.doughnut.plugins.legend.labels.generateLabels(chart).map(item => ({
                ...item,
                text: `${item.text} · ${formatPercent(slices.values[item.index] / sum)}`,
              })),
            },
          },
          tooltip: { callbacks: { label: c => ` ${formatValue(c.raw)} · ${formatPercent(c.raw / sum)}` } },
        },
      },
    });
  };
}

function shareTable(series, format, nameHeader, valueHeader) {
  return () => {
    const sum = total(series.values);
    const formatValue = FORMATTERS[format];
    return {
      columns: [nameHeader, valueHeader, '% do total'],
      rows: series.labels.map((label, i) => [label, formatValue(series.values[i]), formatPercent(series.values[i] / (sum || 1))]),
      footer: ['Total', formatValue(sum), sum ? '100%' : '—'],
    };
  };
}

// A donut says something only when a few slices stand out. With many similar categories
// (e.g. 28 drivers of similar output) it would be mostly a grey "Outros" ring.
function donutFits(series, keep = 5, minShare = 0.6) {
  const sum = total(series.values);
  if (!sum || series.values.some(v => v < 0)) return false;
  const named = series.labels.map((label, i) => [label, series.values[i]]).filter(([label]) => !isOthers(label));
  return total(named.slice(0, keep).map(([, v]) => v)) / sum >= minShare;
}

// Bars, donut (when it fits the data) and table for a "total per category" series.
function categoryPanel(id, series, format, nameHeader, valueHeader) {
  const views = [{ key: 'bar', label: 'Barras', chart: barsView(series, format) }];
  if (donutFits(series)) views.push({ key: 'donut', label: 'Rosca', chart: donutView(series, format) });
  views.push({ key: 'table', label: 'Tabela', table: shareTable(series, format, nameHeader, valueHeader) });
  chartPanel(id, views);
}

/* ── Time series ──────────────────────────────────────────────────────────── */

function timeChart(canvas, labels, datasets, { type = 'line', fill = false, format = 'brl' } = {}) {
  const formatValue = FORMATTERS[format];
  return new Chart(canvas, {
    type,
    data: {
      labels,
      datasets: datasets.map((dataset, i) => {
        const color = cssVar(dataset.color || 'series-' + (i + 1));
        return {
          label: dataset.label,
          data: dataset.data,
          borderColor: color,
          backgroundColor: type === 'bar' ? color : (fill ? withAlpha(color, 0.18) : color),
          fill: fill ? 'origin' : false,
          borderWidth: type === 'bar' ? 0 : 2,
          // A second series is dashed, so the two lines differ by more than colour.
          borderDash: type === 'line' && i === 1 && !fill ? [6, 4] : [],
          borderRadius: type === 'bar' ? 3 : 0,
          maxBarThickness: 28,
          cubicInterpolationMode: 'monotone',
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBorderWidth: 2,
          pointHoverBorderColor: cssVar('surface'),
        };
      }),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: { callbacks: { label: c => ' ' + c.dataset.label + ': ' + formatValue(c.raw) } } },
      scales: {
        x: { border: { color: cssVar('axis') }, grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
        y: { border: { display: false }, grid: { color: cssVar('grid') }, beginAtZero: type === 'bar', ticks: { callback: AXIS_FORMATTERS[format] } },
      },
    },
    plugins: type === 'line' ? [crosshairPlugin] : [],
  });
}

const runningTotal = values => { let sum = 0; return values.map(v => Math.round((sum += v) * 100) / 100); };

function seriesTable(labels, datasets, firstHeader, format = 'brl', withTotal = true) {
  return () => {
    const formatValue = FORMATTERS[format];
    return {
      columns: [firstHeader, ...datasets.map(d => d.label)],
      rows: labels.map((label, i) => [label, ...datasets.map(d => formatValue(d.data[i]))]),
      footer: withTotal ? ['Total', ...datasets.map(d => formatValue(total(d.data)))] : null,
    };
  };
}

// Daily gross and net: line, area, columns, running total, table.
function dailyPanel(id, daily) {
  const datasets = [
    { label: 'Faturamento bruto', data: daily.gross_revenue },
    { label: 'Produção líquida', data: daily.net_revenue },
  ];
  const cumulative = datasets.map(d => ({ label: d.label + ' acumulado', data: runningTotal(d.data) }));
  chartPanel(id, [
    { key: 'line', label: 'Linhas', chart: c => timeChart(c, daily.labels, datasets) },
    { key: 'area', label: 'Área', chart: c => timeChart(c, daily.labels, datasets, { fill: true }) },
    { key: 'columns', label: 'Colunas', chart: c => timeChart(c, daily.labels, datasets, { type: 'bar' }) },
    { key: 'cumulative', label: 'Acumulado', chart: c => timeChart(c, daily.labels, cumulative, { fill: true }) },
    { key: 'table', label: 'Tabela', table: seriesTable(daily.labels, datasets, 'Dia') },
  ]);
}

// Gross, net and operating result per payroll period.
function periodPanel(id, periods) {
  const datasets = [
    { label: 'Faturamento bruto', data: periods.gross_revenue, color: 'series-1' },
    { label: 'Produção líquida', data: periods.net_revenue, color: 'series-2' },
    { label: 'Resultado operacional', data: periods.operating_result, color: 'positive' },
  ];
  chartPanel(id, [
    { key: 'columns', label: 'Colunas', chart: c => timeChart(c, periods.labels, datasets, { type: 'bar' }) },
    { key: 'line', label: 'Linhas', chart: c => timeChart(c, periods.labels, datasets) },
    { key: 'table', label: 'Tabela', table: seriesTable(periods.labels, datasets, 'Competência') },
  ]);
}

// Trips per day of the week, with the revenue of those trips in the tooltip and table.
function weekdayPanel(id, weekday) {
  const trips = [{ label: 'Viagens', data: weekday.trips, color: 'series-1' }];
  chartPanel(id, [
    {
      key: 'columns',
      label: 'Colunas',
      chart: c => {
        const chart = timeChart(c, weekday.labels, trips, { type: 'bar', format: 'count' });
        chart.options.plugins.tooltip.callbacks.afterLabel = item => ' Faturamento bruto: ' + formatBRL(weekday.gross_revenue[item.dataIndex]);
        chart.update('none');
        return chart;
      },
    },
    { key: 'donut', label: 'Rosca', chart: donutView({ labels: weekday.labels, values: weekday.trips }, 'count', 7) },
    {
      key: 'table',
      label: 'Tabela',
      table: () => ({
        columns: ['Dia', 'Viagens', 'Faturamento bruto'],
        rows: weekday.labels.map((label, i) => [label, formatNumber(weekday.trips[i]), formatBRL(weekday.gross_revenue[i])]),
        footer: ['Total', formatNumber(total(weekday.trips)), formatBRL(total(weekday.gross_revenue))],
      }),
    },
  ]);
}

/* ── Where the revenue goes: waterfall ────────────────────────────────────── */

function revenueSteps(k) {
  return [
    { label: 'Faturamento bruto', value: k.gross_revenue, kind: 'total' },
    { label: 'Retenções e impostos', value: -k.withholding, kind: 'out' },
    { label: 'Comissões', value: -k.commission, kind: 'out' },
    { label: 'Combustível', value: -k.fuel, kind: 'out' },
    { label: 'Pedágio', value: -k.tolls, kind: 'out' },
    { label: 'Resultado operacional', value: k.operating_result, kind: 'total' },
  ];
}

function waterfallView(kpis) {
  return canvas => {
    canvas.parentElement.style.height = '300px';
    const steps = revenueSteps(kpis);
    // On a phone the six step names do not fit side by side: lay the bars down instead.
    const horizontal = canvas.parentElement.clientWidth < 520;
    const [labelAxis, valueAxis] = horizontal ? ['y', 'x'] : ['x', 'y'];
    let level = 0;
    const bars = steps.map(step => {
      if (step.kind === 'total') { level = step.value; return [0, step.value]; }
      const start = level;
      level += step.value;
      return [level, start];
    });
    const colors = steps.map(step => {
      if (step.kind === 'out') return cssVar('negative');
      return step.value < 0 ? cssVar('negative') : (step.label.startsWith('Resultado') ? cssVar('positive') : cssVar('series-1'));
    });
    return new Chart(canvas, {
      type: 'bar',
      data: {
        labels: steps.map(s => s.label),
        datasets: [{ data: bars, backgroundColor: colors, hoverBackgroundColor: colors, borderRadius: 4, borderSkipped: false, maxBarThickness: 56 }],
      },
      options: {
        indexAxis: labelAxis,
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          tooltip: {
            displayColors: false,
            callbacks: {
              label: c => {
                const step = steps[c.dataIndex];
                const share = kpis.gross_revenue ? ' · ' + formatPercent(Math.abs(step.value) / kpis.gross_revenue) + ' do bruto' : '';
                return (step.kind === 'out' ? '− ' : '') + formatBRL(Math.abs(step.value)) + share;
              },
            },
          },
        },
        scales: {
          [labelAxis]: {
            border: { color: cssVar('axis') }, grid: { display: false },
            ticks: { color: cssVar('text-2'), maxRotation: 0, autoSkip: false, callback(value) { return horizontal ? steps[value].label : steps[value].label.split(' '); } },
          },
          [valueAxis]: { border: { display: false }, grid: { color: cssVar('grid') }, beginAtZero: true, ticks: { callback: AXIS_FORMATTERS.brl } },
        },
      },
    });
  };
}

function revenuePanel(id, kpis) {
  chartPanel(id, [
    { key: 'waterfall', label: 'Cascata', chart: waterfallView(kpis) },
    {
      key: 'donut',
      label: 'Rosca',
      chart: donutView({
        labels: ['Resultado operacional', 'Retenções e impostos', 'Comissões', 'Combustível', 'Pedágio'],
        values: [Math.max(kpis.operating_result, 0), kpis.withholding, kpis.commission, kpis.fuel, kpis.tolls],
      }, 'brl'),
    },
    {
      key: 'table',
      label: 'Tabela',
      table: () => ({
        columns: ['Etapa', 'Valor', '% do bruto'],
        rows: revenueSteps(kpis).map(step => [
          step.label,
          (step.kind === 'out' ? '− ' : '') + formatBRL(Math.abs(step.value)),
          kpis.gross_revenue ? formatPercent(Math.abs(step.value) / kpis.gross_revenue) : '—',
        ]),
      }),
    },
  ]);
}
