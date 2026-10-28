(() => {
  const dataNode = document.getElementById('thk-data');
  if (!dataNode) return;
  const data = JSON.parse(dataNode.textContent);
  const money = value => (Number(value || 0) / 1000000).toLocaleString('es-CO', {maximumFractionDigits: 1});
  function bars(id, items, value, formatter = money) {
    const element = document.getElementById(id); if (!element) return;
    const max = Math.max(1, ...items.map(value));
    if (!items.length) { element.textContent = 'Sin trimestres completos para mostrar.'; return; }
    items.forEach(item => {
      const n = Number(value(item) || 0), col = document.createElement('div'); col.className = 'thk-col';
      const number = document.createElement('span'); number.textContent = formatter(n);
      const bar = document.createElement('i'); if (item.year && item.year < data.year) bar.classList.add('thk-prior'); bar.style.height = `${Math.max(1, 130 * Math.max(0, n) / max)}px`;
      const label = document.createElement('label'); label.textContent = item.label;
      col.setAttribute('aria-label', `${item.label}: ${formatter(n)}`);
      col.append(number, bar, label); element.appendChild(col);
    });
  }
  const quarters = data.quarters.filter(q => q.year >= data.year - 1).sort((a,b) => a.q - b.q || a.year - b.year);
  bars('thk-quarter-chart', quarters, q => q.sales);
  bars('thk-guide-chart', quarters, q => q.guides + q.rails);
  bars('thk-rails-quarter-chart', quarters, q => q.rails);
  bars('thk-guides-quarter-chart', quarters, q => q.guides);
  bars('thk-screw-chart', quarters, q => q.screw_erp);
  bars('thk-screws-only-chart', quarters, q => q.screws);
  bars('thk-nuts-chart', quarters, q => q.nuts);
  bars('thk-customer-chart', data.snapshots, q => q.buyers, n => String(n));
  function line(id, items, key, format) {
    const root = document.getElementById(id); if (!root || !items.length) return;
    const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
    svg.setAttribute('viewBox','0 0 500 190'); svg.setAttribute('role','img');
    svg.setAttribute('aria-label',items.map(x=>`${x.label}: ${format(x[key])}`).join('; '));
    const values=items.map(i=>Number(i[key] || 0)); const max=Math.max(...values,1), min=Math.min(...values,0);
    const point=(v,i)=>[45+i*410/Math.max(1,items.length-1),145-(v-min)/Math.max(1,max-min)*110];
    const line=document.createElementNS(ns,'polyline');line.setAttribute('points',values.map((v,i)=>point(v,i).join(',')).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#076f7b');line.setAttribute('stroke-width','3');svg.appendChild(line);
    items.forEach((item,i)=>{const [x,y]=point(values[i],i);const circle=document.createElementNS(ns,'circle');circle.setAttribute('cx',x);circle.setAttribute('cy',y);circle.setAttribute('r',4);circle.setAttribute('fill','#076f7b');svg.appendChild(circle);for(const [text,ty] of [[format(values[i]),Math.max(15,y-9)],[item.label,170]]){const t=document.createElementNS(ns,'text');t.setAttribute('x',x);t.setAttribute('y',ty);t.setAttribute('text-anchor','middle');t.textContent=text;svg.appendChild(t)}});root.appendChild(svg);
  }
  line('thk-ytd-chart',data.ytd,'sales',money);
  const selector=document.getElementById('thk-price-reference');
  if(selector){const render=()=>{const root=document.getElementById('thk-price-history');root.replaceChildren();line('thk-price-history',(data.price_history[selector.value] || []).slice(-12).map(x=>({...x,label:x.month})),'price',money)};selector.addEventListener('change',render);render()}
})();
