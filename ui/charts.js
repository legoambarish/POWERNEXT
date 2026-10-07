// Compact, data-faithful visualisations built only from saved optimizer fields.
import {tailLabel,esc,fmt,signed,paramLabel,paramUnit,frontKey,statusTone} from './format.js';

const pct=(v,lo,hi)=>Math.max(0,Math.min(100,(v-lo)/(hi-lo)*100));

// One parameter against its unchanged allowed interval (score component limits).
export function toleranceBar(key,c,{label=null,compact=false}={}){
  if(!c)return `<div class="tol tol-na"><div class="tol-head"><span>${esc(label??paramLabel(key))}</span><b>Not evaluable</b></div><div class="tol-track na"></div></div>`;
  const [unit,scale]=paramUnit(key),[a,b]=c.limits,span=b-a;
  const lo=Math.min(a-span*.35,c.value-span*.08),hi=Math.max(b+span*.35,c.value+span*.08);
  const inside=c.within_limits,distance=Math.max(a-c.value,c.value-b,0);
  return `<div class="tol ${inside?'in':'out'} ${compact?'compact':''}" role="group" aria-label="${esc(label??paramLabel(key))}: ${fmt(c.value,scale,3)} ${unit}, allowed ${fmt(a,scale,3)} to ${fmt(b,scale,3)} ${unit}, ${inside?'inside':'outside'} limits">
  <div class="tol-head"><span>${esc(label??paramLabel(key))}</span><b class="num">${fmt(c.value,scale,3)} <small>${unit}</small></b></div>
  <div class="tol-track"><span class="tol-band" style="left:${pct(a,lo,hi)}%;width:${pct(b,lo,hi)-pct(a,lo,hi)}%"></span><span class="tol-target" style="left:${pct(c.target,lo,hi)}%"></span><span class="tol-value" style="left:${pct(c.value,lo,hi)}%"></span></div>
  <div class="tol-foot"><span class="num">${fmt(a,scale,3)}</span><span class="${inside?'':'out-text'}">${inside?`${signed(c.deviation_pct,2)}% from target · inside`:`${fmt(distance,scale,3)} ${unit} outside limit`}</span><span class="num">${fmt(b,scale,3)}</span></div></div>`;
}

// Physics baseline, learned estimate and checked reference on one shared scale with the allowed interval.
export function dotRows(key,{limits,target,rows}){
  const [unit,scale]=paramUnit(key),vals=rows.map(r=>r.value).filter(Number.isFinite);
  const span=limits?limits[1]-limits[0]:Math.abs(target||1)*.2;
  const lo=Math.min(...vals,limits?.[0]??target)-span*.25,hi=Math.max(...vals,limits?.[1]??target)+span*.25;
  return `<div class="dot-rows">${rows.map(r=>`<div class="dot-row ${r.kind}"><span class="dot-name">${esc(r.label)}</span><div class="dot-track">${limits?`<span class="tol-band" style="left:${pct(limits[0],lo,hi)}%;width:${pct(limits[1],lo,hi)-pct(limits[0],lo,hi)}%"></span>`:''}<span class="tol-target" style="left:${pct(target,lo,hi)}%"></span>${Number.isFinite(r.value)?`<span class="dot ${r.kind}" style="left:${pct(r.value,lo,hi)}%"></span>`:''}</div><span class="dot-value num">${Number.isFinite(r.value)?`${fmt(r.value,scale,3)} <small>${unit}</small>`:'<small>not available</small>'}</span></div>`).join('')}<div class="dot-axis"><span></span><div><span class="num">${fmt(lo,scale,2)}</span><span class="num">${fmt(hi,scale,2)} ${unit}</span></div><span></span></div></div>`;
}

// J = sum of squared normalized deviations, drawn on a common scale so candidates compare fairly.
export function scoreBar(row,p,max){
  const comps=row?.score?.components;if(!comps)return '<div class="jbar empty"><small>Not scored: waveform not evaluable</small></div>';
  const keys=['crest',frontKey(p),'T2_s'],J=row.score.J,scaleMax=Math.max(max??J,1e-12);
  return `<div class="jbar" role="img" aria-label="Score J ${fmt(J,1,6)}: ${keys.map(k=>`${paramLabel(k)} ${fmt(comps[k]?.squared_contribution,1,6)}`).join(', ')}"><div class="jbar-track">${keys.map((k,i)=>`<span class="jseg s${i}" style="width:${(comps[k]?.squared_contribution??0)/scaleMax*100}%"></span>`).join('')}</div><div class="jbar-legend">${keys.map((k,i)=>`<span><i class="s${i}"></i>${paramLabel(k)} <b class="num">${fmt(comps[k]?.squared_contribution,1,4)}</b></span>`).join('')}<span class="jbar-total">J <b class="num">${fmt(J,1,6)}</b></span></div></div>`;
}

// Search space: active stages × resistor pair, each cell one evaluated configuration in original rank.
export function searchMatrix(rows,selectedId){
  const stages=[...new Set(rows.map(r=>r.configuration.stages))].sort((a,b)=>a-b);
  const pairs=[...new Set(rows.map(r=>`${r.configuration.front_per_stage_ohm}|${r.configuration.tail_per_stage_ohm}|${r.configuration.recipe_id}`))].sort((a,b)=>Number(a.split('|')[0])-Number(b.split('|')[0])||Number(a.split('|')[1])-Number(b.split('|')[1]));
  const at=new Map(rows.map(r=>[`${r.configuration.stages}|${r.configuration.front_per_stage_ohm}|${r.configuration.tail_per_stage_ohm}|${r.configuration.recipe_id}`,r]));
  const cls=r=>!r.hard_constraints.declared_constraints_satisfied?'constraint':r.assessment.evaluation_status!=='EVALUABLE'?'indet':r.assessment.compliance_status==='PASS'?'pass':'fail';
  const glyph={pass:'✓',fail:'×',indet:'?',constraint:'!'};
  return `<div class="matrix" style="--cols:${pairs.length}"><div class="mx-corner">Stages</div>${pairs.map(p=>{const [f,t,recipe]=p.split('|');return `<div class="mx-col"><b>${fmt(Number(f))} Ω</b><small>front · tail ${tailLabel({tail_per_stage_ohm:Number(t),recipe_id:recipe})} Ω</small></div>`;}).join('')}
  ${stages.map(n=>`<div class="mx-row">${n}</div>${pairs.map(p=>{const r=at.get(`${n}|${p}`);if(!r)return '<div class="mx-cell none" aria-hidden="true"></div>';const c=cls(r);return `<button class="mx-cell ${c} ${r.candidate_id===selectedId?'selected':''} ${r.rank===1?'first':''}" data-candidate="${esc(r.candidate_id)}" title="#${r.rank} · ${n} stages · ${r.configuration.front_per_stage_ohm}/${tailLabel(r)} Ω · ${c==='pass'?'compliant':c==='fail'?'not compliant':c==='indet'?'indeterminate':'constraint not met'}${r.score?` · J ${fmt(r.score.J,1,4)}`:''}"><span class="mx-rank">#${r.rank}</span><span class="mx-glyph" aria-hidden="true">${glyph[c]}</span></button>`;}).join('')}`).join('')}</div>`;
}

// Front/peak deviation vs tail deviation; the dashed box is the unchanged tolerance window.
export function toleranceScatter(rows,p,selectedId){
  const fk=frontKey(p),pts=rows.filter(r=>r.score?.components?.[fk]&&r.score?.components?.T2_s).map(r=>({r,x:r.score.components[fk].deviation_pct,y:r.score.components.T2_s.deviation_pct,crest:r.score.components.crest?.within_limits}));
  if(!pts.length)return '<p class="muted small">No evaluable waveforms to plot.</p>';
  const ref=pts[0].r.score.components,tx=(ref[fk].limits[1]-ref[fk].target)/ref[fk].target*100,ty=(ref.T2_s.limits[1]-ref.T2_s.target)/ref.T2_s.target*100;
  const xs=pts.map(d=>d.x),ys=pts.map(d=>d.y);
  // Bounded window around the tolerance box; configurations beyond it are pinned to the edge and counted.
  const cap=(v,t)=>Math.max(-4*t,Math.min(4*t,v)),x0=Math.max(-4*tx,Math.min(-tx*1.6,...xs)*1.08),x1=Math.min(4*tx,Math.max(tx*1.6,...xs)*1.08),y0=Math.max(-4*ty,Math.min(-ty*1.6,...ys)*1.08),y1=Math.min(4*ty,Math.max(ty*1.6,...ys)*1.08);
  const beyond=pts.filter(d=>d.x<x0||d.x>x1||d.y<y0||d.y>y1).length;
  const W=560,H=360,L=54,R=14,T=16,B=44,sx=v=>L+(v-x0)/(x1-x0)*(W-L-R),sy=v=>T+(y1-v)/(y1-y0)*(H-T-B);
  const ticks=(a,b)=>{const s=(b-a)/5,m=10**Math.floor(Math.log10(s)),st=[1,2,5,10].map(k=>k*m).find(k=>k>=s);const o=[];for(let v=Math.ceil(a/st)*st;v<=b;v+=st)o.push(Math.round(v/st)*st);return o;};
  let g='';ticks(x0,x1).forEach(v=>g+=`<line class="grid" x1="${sx(v)}" x2="${sx(v)}" y1="${T}" y2="${H-B}"/><text class="tick" x="${sx(v)}" y="${H-B+16}" text-anchor="middle">${v}%</text>`);
  ticks(y0,y1).forEach(v=>g+=`<line class="grid" y1="${sy(v)}" y2="${sy(v)}" x1="${L}" x2="${W-R}"/><text class="tick" x="${L-8}" y="${sy(v)+4}" text-anchor="end">${v}%</text>`);
  const box=`<rect class="tol-window" x="${sx(-tx)}" y="${sy(ty)}" width="${sx(tx)-sx(-tx)}" height="${sy(-ty)-sy(ty)}"/><text class="window-label" x="${sx(-tx)+6}" y="${sy(ty)+14}">±${fmt(tx,1,0)}% ${p.request.impulse_type==='LI'?'T1':'Tp'} · ±${fmt(ty,1,0)}% T2</text>`;
  const dots=pts.map(({r,x,y,crest})=>{const c=statusTone(r.assessment.compliance_status),out=x<x0||x>x1||y<y0||y>y1,px=Math.max(x0,Math.min(x1,x)),py=Math.max(y0,Math.min(y1,y));return `<circle class="sc ${c} ${crest===false?'crest-out':''} ${out?'pinned':''} ${r.candidate_id===selectedId?'selected':''}" cx="${sx(px)}" cy="${sy(py)}" r="${r.candidate_id===selectedId?7:5}" data-candidate="${esc(r.candidate_id)}" tabindex="0" role="button" aria-label="#${r.rank}: ${p.request.impulse_type==='LI'?'T1':'Tp'} ${fmt(x,1,1)}%, T2 ${fmt(y,1,1)}%"><title>#${r.rank} · ${r.configuration.stages} stages · ${r.configuration.front_per_stage_ohm}/${tailLabel(r)} Ω\n${p.request.impulse_type==='LI'?'T1':'Tp'} ${signed(x,1)}% · T2 ${signed(y,1)}%${crest===false?' · crest outside band':''}${out?' · beyond plotted range':''}</title></circle>`;}).join('');
  return `<svg class="scatter" viewBox="0 0 ${W} ${H}" role="img" aria-label="Timing deviation of every evaluable configuration against the tolerance window">${g}<line class="axis-zero" x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${H-B}"/><line class="axis-zero" y1="${sy(0)}" y2="${sy(0)}" x1="${L}" x2="${W-R}"/>${box}${dots}${beyond?`<text class="window-label muted-label" x="${W-R-4}" y="${T+12}" text-anchor="end">${beyond} beyond plotted range · pinned to edge</text>`:''}<text class="axis-title" x="${L+(W-L-R)/2}" y="${H-6}" text-anchor="middle">${p.request.impulse_type==='LI'?'T1 front time':'Tp time to peak'} deviation from target</text><text class="axis-title" transform="translate(13 ${T+(H-T-B)/2}) rotate(-90)" text-anchor="middle">T2 deviation from target</text></svg>`;
}

export function funnel(p,rows){
  const h=rows.filter(r=>r.hard_constraints.declared_constraints_satisfied).length,s=p.search,max=Math.max(s.catalog_count,1);
  return `<div class="funnel">${[['Catalog configurations',s.catalog_count,'Declared profile × topology × scope'],['Evaluated',s.evaluated_count,`${s.pruned_count} pruned`],['Declared constraints met',h,'Charge, energy and stage limits'],['Waveform evaluable',s.evaluable_count,`${s.unsupported_count} unsupported / indeterminate`],['Numerically compliant',s.numeric_pass_count,'Crest, timing and tail inside limits']].map(([l,v,n],i)=>`<div class="fn-step ${i===4?'final':''}"><div class="fn-bar"><span style="width:${v/max*100}%"></span></div><div class="fn-text"><b class="num">${v}</b><span>${l}</span><small>${esc(n)}</small></div></div>`).join('')}</div>`;
}
