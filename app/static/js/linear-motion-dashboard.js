(() => {
  const root = document.querySelector('.lm');
  const chart = document.querySelector('#lm-chart');
  if (!root || !chart) return;
  const rows = JSON.parse(root.dataset.monthly || '[]');
  const months = new Map();
  rows.forEach((row) => {
    if (!months.has(row.month)) months.set(row.month, { THK: 0, Thomson: 0 });
    months.get(row.month)[row.brand] = Number(row.sales || 0);
  });
  const maximum = Math.max(1, ...Array.from(months.values()).flatMap((v) => [v.THK, v.Thomson]));
  months.forEach((values, month) => {
    const group = document.createElement('div');
    group.className = 'lm-chart-group';
    ['THK', 'Thomson'].forEach((brand) => {
      const bar = document.createElement('i');
      bar.className = `lm-chart-bar ${brand === 'Thomson' ? 'thomson' : ''}`;
      bar.style.height = `${Math.max(1, values[brand] / maximum * 100)}%`;
      bar.title = `${brand}: COP ${Math.round(values[brand]).toLocaleString('es-CO')}`;
      group.appendChild(bar);
    });
    const label = document.createElement('label');
    label.textContent = month.slice(2).replace('-', '/');
    group.appendChild(label);
    chart.appendChild(group);
  });
})();
