/* 笔记关系图谱：有向依赖图。
 *
 * 为什么不用纯力导向：笔记之间是**有向依赖**，力导向会揉成一团毛线，
 * 「谁在谁前面」这个信息全丢。这里按拓扑深度锁一个轴（横向铺开），
 * 只让力去解决同层内的拥挤 —— 既有有机感，又能一眼看出先后。
 *
 * 交互：hover 高亮直接上下游；点击锁定并开侧栏；再点一次放开。
 * 节点少时不会乱，节点多到几十个时靠「聚焦」收敛视野，不靠用户自己找。
 */
(async function () {
  const cfg = await (await fetch('assets/notes.json')).json();
  const raw = cfg.notes;

  const byId = new Map(raw.map(n => [n.id, n]));
  const nodes = raw.map(n => ({ ...n, r: n.status === 'published' ? 8 : 6 }));
  const seen = new Set();
  const links = [];
  const add = (s, t) => {
    if (!byId.has(s) || !byId.has(t) || s === t) return;
    const k = s + '>' + t;
    if (!seen.has(k)) { seen.add(k); links.push({ source: s, target: t }); }
  };
  raw.forEach(n => {
    (n.deps || []).forEach(d => add(d, n.id));
    (n.leads_to || []).forEach(d => add(n.id, d));
  });

  // ── 拓扑深度 ──
  const preds = new Map(nodes.map(n => [n.id, []]));
  const succs = new Map(nodes.map(n => [n.id, []]));
  links.forEach(l => { preds.get(l.target).push(l.source); succs.get(l.source).push(l.target); });
  const depth = new Map();
  const depthOf = (id, guard = new Set()) => {
    if (depth.has(id)) return depth.get(id);
    if (guard.has(id)) return 0;                 // 有环就停
    guard.add(id);
    const p = preds.get(id) || [];
    const d = p.length ? Math.max(...p.map(x => depthOf(x, guard))) + 1 : 0;
    depth.set(id, d); return d;
  };
  nodes.forEach(n => { n.depth = depthOf(n.id); });
  const maxDepth = Math.max(1, ...nodes.map(n => n.depth));
  const lane = new Map();
  nodes.forEach(n => {
    const i = lane.get(n.depth) || 0;
    n.lane = i; lane.set(n.depth, i + 1);
  });

  const stage = document.getElementById('stage');
  const svg = d3.select('#graph');
  const tip = d3.select('#tip');
  const panel = d3.select('#panel');
  let W = stage.clientWidth, H = stage.clientHeight;

  const defs = svg.append('defs');
  [['arw', '#C6BCAA'], ['arw-on', '#B3565B']].forEach(([id, c]) => {
    defs.append('marker').attr('id', id).attr('viewBox', '0 -5 10 10')
      .attr('refX', 24).attr('refY', 0).attr('markerWidth', 6).attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,-4L9,0L0,4').attr('fill', c);
  });

  const root = svg.append('g');
  const gLink = root.append('g');
  const gNode = root.append('g');
  svg.call(d3.zoom().scaleExtent([.5, 2.4])
    .on('zoom', e => root.attr('transform', e.transform))).on('dblclick.zoom', null);

  const link = gLink.selectAll('path').data(links).join('path')
    .attr('class', 'link').attr('marker-end', 'url(#arw)');

  // 入场动画走 CSS（下面设 --delay），不要用 d3.transition 改 opacity：
  // 无头浏览器/截图工具的虚拟时间不推进 rAF，节点会永远停在 opacity:0。
  const node = gNode.selectAll('g').data(nodes, d => d.id).join('g')
    .attr('class', d => 'node in' + (d.status === 'published' ? ' pub' : ' soon'))
    .style('--delay', d => (85 * d.depth + 45 * d.lane) + 'ms');
  node.append('circle').attr('class', 'halo').attr('r', d => d.r + 10);
  // 节点不写编号：箭头已经表达了先后，圆点里再塞数字是重复、还把点撑大
  node.append('circle').attr('class', 'dot').attr('r', d => d.r);
  // 标签比节点宽，贴着画布边缘的那些要换对齐方向，否则会伸进 mask 的渐隐区变淡
  node.append('text').attr('class', 'label')
    .attr('dy', d => d.r + 19).text(d => d.title);
  function alignLabels() {
    const w = stage.clientWidth;
    node.select('text.label')
      .attr('text-anchor', d => d.x < w * 0.18 ? 'start' : d.x > w * 0.82 ? 'end' : 'middle')
      .attr('dx', d => d.x < w * 0.18 ? -d.r : d.x > w * 0.82 ? d.r : 0);
  }

  // ── 布局：深度 → 横向（宽屏铺得开），同层 → 纵向 ──────────────
  // PADX 要大于 #stage 左右 mask 的渐隐宽度（3.5vw），不然边上的节点会被吃淡
  const PADX = 190, PADY = 92;
  function place() {
    W = stage.clientWidth; H = stage.clientHeight;
    const vertical = W < 720;                      // 窄屏翻转成竖排
    nodes.forEach(n => {
      const c = lane.get(n.depth) || 1;
      const along = (n.depth / maxDepth);           // 沿依赖方向 0→1
      // 同层内铺满，不是 (lane+1)/(c+1) —— 那样只会用到 0.25~0.75，上下各空一大块
      const across = c > 1 ? n.lane / (c - 1) : 0.5;
      const jitter = c === 1 ? 0 : (n.lane % 2 ? 1 : -1) * 0.03;
      if (vertical) {
        n.tx = PADX + (W - PADX * 2) * (across + jitter);
        n.ty = PADY + (H - PADY * 2) * along;
      } else {
        n.tx = PADX + (W - PADX * 2) * along;
        n.ty = PADY + (H - PADY * 2) * (across + jitter);
      }
    });
    // 沿依赖方向锁死，垂直方向给中等强度：既不散开跑偏，也留一点有机的错落
    sim.force('x', d3.forceX(d => d.tx).strength(vertical ? .55 : 1))
       .force('y', d3.forceY(d => d.ty).strength(vertical ? 1 : .55))
       .alpha(.8).restart();
  }

  nodes.forEach(n => { n.x = W / 2; n.y = H / 2; });
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(120).strength(.12))
    .force('charge', d3.forceManyBody().strength(-190))
    .force('collide', d3.forceCollide().radius(d => d.r + 34))
    .on('tick', tick);
  place();

  function tick() {
    link.attr('d', d => {
      const x1 = d.source.x, y1 = d.source.y, x2 = d.target.x, y2 = d.target.y;
      const r = Math.hypot(x2 - x1, y2 - y1) * 1.8;   // 弧度小一点，不绕远路
      return `M${x1},${y1} A${r},${r} 0 0,1 ${x2},${y2}`;
    });
    node.attr('transform', d => `translate(${d.x},${d.y})`);
    alignLabels();
  }

  // ── 聚焦 ───────────────────────────────────────────────────
  let locked = null;
  const neigh = id => new Set([id, ...(preds.get(id) || []), ...(succs.get(id) || [])]);

  function focus(id) {
    if (!id) {
      node.classed('dim', false).classed('hi', false);
      link.classed('dim', false).classed('hi', false).attr('marker-end', 'url(#arw)');
      return;
    }
    const keep = neigh(id);
    node.classed('dim', d => !keep.has(d.id)).classed('hi', d => d.id === id);
    link.classed('dim', l => !(keep.has(l.source.id) && keep.has(l.target.id)))
      .classed('hi', l => l.source.id === id || l.target.id === id)
      .attr('marker-end', l => (l.source.id === id || l.target.id === id)
        ? 'url(#arw-on)' : 'url(#arw)');
  }

  node
    .on('mouseenter', (e, d) => {
      if (!locked) focus(d.id);
      const up = (preds.get(d.id) || []).map(i => byId.get(i).title);
      const dn = (succs.get(d.id) || []).map(i => byId.get(i).title);
      tip.html(`<b>${d.title}</b><p>${d.lede || ''}</p>`
        + (up.length ? `<span>要先读 · ${up.join(' / ')}</span>` : '')
        + (dn.length ? `<span>之后是 · ${dn.join(' / ')}</span>` : ''))
        .classed('on', true);
    })
    .on('mousemove', e => {
      const b = stage.getBoundingClientRect();
      tip.style('left', Math.min(e.clientX - b.left + 16, b.width - 290) + 'px')
         .style('top', Math.min(e.clientY - b.top + 14, b.height - 140) + 'px');
    })
    .on('mouseleave', () => { tip.classed('on', false); if (!locked) focus(null); })
    .on('click', (e, d) => {
      e.stopPropagation();
      locked = locked === d.id ? null : d.id;
      focus(locked);
      if (locked) showPanel(d); else panel.attr('hidden', true);
    })
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(.2).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

  svg.on('click', () => { locked = null; focus(null); panel.attr('hidden', true); });

  function showPanel(d) {
    const rel = (ids, label) => {
      const arr = (ids || []).map(i => byId.get(i)).filter(Boolean);
      return arr.length ? `<div class="pl"><span>${label}</span>${arr.map(n =>
        `<a href="${n.status === 'published' ? 'notes/' + n.id + '/index.html' : '#'}"
            class="${n.status === 'published' ? '' : 'soon'}">${n.num} ${n.title}</a>`).join('')}</div>` : '';
    };
    panel.attr('hidden', null).html(
      `<div class="pnum">${d.num}</div><h3>${d.title}</h3><p>${d.lede || ''}</p>
       ${rel(preds.get(d.id), '依赖')}${rel(succs.get(d.id), '延伸')}
       ${d.status === 'published'
        ? `<a class="pgo" href="notes/${d.id}/index.html">读这篇 →</a>`
        : '<span class="pgo soon">还没写</span>'}`);
  }

  let rt;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(place, 180); });
})();
