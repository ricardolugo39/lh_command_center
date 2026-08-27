(() => {
    const dashboard = document.querySelector(".sa-dashboard");
    const chart = document.getElementById("revenue-chart");
    if (!dashboard || !chart) return;

    const data = JSON.parse(dashboard.dataset.revenue || "[]");
    if (!data.length) return;

    const width = 800;
    const height = 250;
    const padding = {top: 18, right: 16, bottom: 18, left: 72};
    const current = data.map((item) => Number(item.current) || 0);
    const previous = data.map((item) => Number(item.previous) || 0);
    const maximum = Math.max(...current, ...previous, 1);
    const x = (index) => padding.left + index * (width - padding.left - padding.right) /
        Math.max(data.length - 1, 1);
    const y = (value) => height - padding.bottom - value / maximum *
        (height - padding.top - padding.bottom);
    const points = (values) => values.map(
        (value, index) => `${x(index)},${y(value)}`
    ).join(" ");
    const currentPoints = points(current);
    const area = `${padding.left},${height - padding.bottom} ${currentPoints} ` +
        `${x(data.length - 1)},${height - padding.bottom}`;
    const hasPrevious = previous.some((value) => value > 0);
    const compactCop = (value) => new Intl.NumberFormat("es-CO", {
        style: "currency", currency: "COP", notation: "compact",
        maximumFractionDigits: 1,
    }).format(value);

    chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
    chart.innerHTML = `
        <defs><linearGradient id="sa-gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#315efb" stop-opacity=".2"/><stop offset="1" stop-color="#315efb" stop-opacity="0"/></linearGradient></defs>
        ${[0, .25, .5, .75, 1].map((ratio) => {
            const position = y(maximum * ratio);
            return `<line class="sa-chart-grid" x1="${padding.left}" y1="${position}" x2="${width - padding.right}" y2="${position}"/><text class="sa-chart-axis" x="${padding.left - 8}" y="${position + 3}" text-anchor="end">${compactCop(maximum * ratio)}</text>`;
        }).join("")}
        <polygon class="sa-chart-area" points="${area}"/>
        ${hasPrevious ? `<polyline class="sa-chart-line-previous" points="${points(previous)}"/>` : ""}
        <polyline class="sa-chart-line" points="${currentPoints}"/>
        ${hasPrevious ? previous.map((value, index) => `<circle class="sa-chart-dot-previous sa-chart-point" data-index="${index}" cx="${x(index)}" cy="${y(value)}" r="3"/>`).join("") : ""}
        ${current.map((value, index) => `<circle class="sa-chart-dot sa-chart-point" data-index="${index}" cx="${x(index)}" cy="${y(value)}" r="4"/>`).join("")}
    `;

    const tooltip = document.getElementById("revenue-tooltip");
    chart.querySelectorAll(".sa-chart-point").forEach((point) => {
        point.addEventListener("mouseenter", () => {
            if (!tooltip) return;
            const item = data[Number(point.dataset.index)];
            const difference = (Number(item.current) || 0) - (Number(item.previous) || 0);
            tooltip.innerHTML = `<strong>${item.label}</strong><span>Actual: ${compactCop(item.current)}</span><span>Referencia: ${compactCop(item.previous)}</span><span>Diferencia: ${compactCop(difference)}</span>`;
            tooltip.hidden = false;
            tooltip.style.left = `${Math.min(Number(point.getAttribute("cx")) / width * 100, 75)}%`;
            tooltip.style.top = `${Math.max(Number(point.getAttribute("cy")) / height * 100 - 12, 0)}%`;
        });
        point.addEventListener("mouseleave", () => { if (tooltip) tooltip.hidden = true; });
    });

    const legend = document.getElementById("revenue-legend");
    if (legend) legend.innerHTML = data.map((item) => `<span>${item.label}</span>`).join("");
})();
