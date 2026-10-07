// Waveform plotting from saved arrays. Every plotted point and marker comes from the stored
// waveform and the original evaluator metrics; nothing is fitted, smoothed or invented.
import {esc,fmt} from './format.js';

const SERIES={target:{color:'#63758b',width:1.7,dash:'3 5'},reference:{color:'var(--c-ref)',width:2.2},alternative:{color:'var(--c-alt)',width:1.8,dash:'6 4'},measured:{color:'var(--c-measured)',width:1.6}};

function niceTicks(lo,hi,count=6){
  const span=hi-lo||1,raw=span/count,mag=10**Math.floor(Math.log10(raw)),norm=raw/mag;
  const step=(norm<1.5?1:norm<3?2:norm<7?5:10)*mag;const ticks=[];
  for(let v=Math.ceil(lo/step)*step;v<=hi+step*1e-9;v+=step)ticks.push(Math.abs(v)<step*1e-9?0:v);
  return ticks;
}
function lowerIndex(a,t){let l=0,r=a.length;while(l<r){const m=(l+r)>>1;if(a[m]<t)l=m+1;else r=m;}return l;}
function nearestIndex(a,t){let i=Math.min(lowerIndex(a,t),a.length-1);if(i>0&&Math.abs(a[i-1]-t)<Math.abs(a[i]-t))i--;return i;}

export function windowFor(wave,request,range){
  const m=wave.metrics,front=m[request.impulse_type==='LI'?'T1_s':'Tp_s'],end=wave.time_s.at(-1);
  if(range&&typeof range==='object')return [range.t0,range.t1];
  const xmin=Math.min(0,m.virtual_origin_s??0);let xmax=end;
  if(range==='front'&&m.t_peak_s)xmax=Math.min(end,Math.max(m.t_peak_s*1.65,(front??0)*2));
  else if(range==='tail'&&m.t50_falling_s)xmax=Math.min(end,m.t50_falling_s*1.4);
  return [xmin,xmax];
}

// Min/max decimation per horizontal pixel keeps every visible extreme of the stored samples.
function pathFor(ts,vs,x0,x1,sx,sy,pixels){
  const start=Math.max(0,lowerIndex(ts,x0)-1),end=Math.min(ts.length,lowerIndex(ts,x1)+2);const n=end-start;if(n<2)return '';
  const out=[];
  if(n<=pixels*3){for(let i=start;i<end;i++)out.push([ts[i],vs[i]]);}
  else{const bucket=n/pixels;for(let b=0;b<pixels;b++){const s=start+Math.floor(b*bucket),e=Math.min(end,start+Math.floor((b+1)*bucket));if(e<=s)continue;let lo=s,hi=s;for(let i=s;i<e;i++){if(vs[i]<vs[lo])lo=i;if(vs[i]>vs[hi])hi=i;}if(lo<hi){out.push([ts[lo],vs[lo]],[ts[hi],vs[hi]]);}else{out.push([ts[hi],vs[hi]],[ts[lo],vs[lo]]);}}}
  return out.map(([t,v],i)=>`${i?'L':'M'}${sx(t).toFixed(2)},${sy(v).toFixed(2)}`).join('');
}

export function drawWaveform(element,{series,request,row,range='tail',markers=true,constructions=true,height=380,onZoom=null}){
  if(!element)return;
  const primary=series[0].wave,m=primary.metrics,pol=request.polarity,isLI=request.impulse_type==='LI';
  const W=Math.max(320,Math.round(element.clientWidth||900)),H=height,L=62,R=18,T=40,B=40,PW=W-L-R,PH=H-T-B;
  let [xmin,xmax]=windowFor(primary,request,range);if(!(xmax>xmin))xmax=xmin+1e-6;
  const ms=xmax>2e-3,tScale=ms?1e-3:1e-6,tUnit=ms?'ms':'µs';
  const bounds=row?.score?.components?.crest?.limits?.map(v=>v*pol);
  let lo=0,hi=0;
  for(const s of series){const ts=s.wave.time_s,vs=s.wave.voltage_V,a=Math.max(0,lowerIndex(ts,xmin)-1),b=Math.min(ts.length,lowerIndex(ts,xmax)+1);for(let i=a;i<b;i++){if(vs[i]<lo)lo=vs[i];if(vs[i]>hi)hi=vs[i];}}
  if(bounds){lo=Math.min(lo,...bounds);hi=Math.max(hi,...bounds);}
  const pad=(hi-lo)*.1||1;lo-=pol>0?pad*.4:pad;hi+=pol>0?pad:pad*.4;
  const sx=t=>L+(t-xmin)/(xmax-xmin)*PW,sy=v=>T+(hi-v)/(hi-lo)*PH;
  let svg='';
  for(const v of niceTicks(lo/1000,hi/1000,6))svg+=`<line class="grid" x1="${L}" x2="${W-R}" y1="${sy(v*1000)}" y2="${sy(v*1000)}"/><text class="tick" x="${L-10}" y="${sy(v*1000)+4}" text-anchor="end">${fmt(v,1,0)}</text>`;
  for(const t of niceTicks(xmin/tScale,xmax/tScale,Math.max(4,Math.round(PW/110))))svg+=`<line class="grid" y1="${T}" y2="${T+PH}" x1="${sx(t*tScale)}" x2="${sx(t*tScale)}"/><text class="tick" x="${sx(t*tScale)}" y="${T+PH+18}" text-anchor="middle">${fmt(t,1,3)}</text>`;
  svg+=`<line class="axis-zero" x1="${L}" x2="${W-R}" y1="${sy(0)}" y2="${sy(0)}"/>`;
  if(bounds){const y1=sy(Math.max(...bounds)),y2=sy(Math.min(...bounds));svg+=`<rect class="crest-band" x="${L}" y="${y1}" width="${PW}" height="${Math.max(1,y2-y1)}"/><line class="target-line" x1="${L}" x2="${W-R}" y1="${sy(request.target_crest_V*pol)}" y2="${sy(request.target_crest_V*pol)}"/><text class="band-label" x="${W-R-6}" y="${(pol>0?y1-5:y2+12)}" text-anchor="end">Allowed crest band · target ${fmt(request.target_crest_V,1000)} kV</text>`;}
  let plot='';
  [...series].reverse().forEach(s=>{const st=SERIES[s.kind]??SERIES.reference;plot+=`<path d="${pathFor(s.wave.time_s,s.wave.voltage_V,xmin,xmax,sx,sy,PW)}" fill="none" stroke="${st.color}" stroke-width="${st.width}" ${st.dash?`stroke-dasharray="${st.dash}"`:''} stroke-linejoin="round"/>`;});
  let marks='';
  if(markers){
    const C=m.crest_magnitude_V*pol;
    if(constructions&&isLI&&m.T1_s&&m.virtual_origin_s!=null){const o=m.virtual_origin_s,t1=o+m.T1_s;marks+=`<line class="construction" x1="${sx(o)}" y1="${sy(0)}" x2="${sx(t1)}" y2="${sy(C)}"/>`;}
    const spec=isLI?[['virtual_origin_s','O₁ virtual origin',0],['t30_s','30%',.3],['t90_s','90%',.9],['t_peak_s','Peak',1],['t50_falling_s','50% falling',.5]]:[['beginning_s','Beginning',0],['t30_s','30%',.3],['t90_s','90%',.9],['t_peak_s','Peak · Tp',1],['t50_falling_s','50% falling',.5]];
    // Greedy label lanes: a label is drawn only where it fits; every marker line and dot is always drawn.
    const visible=spec.filter(([k])=>m[k]!=null&&m[k]>=xmin&&m[k]<=xmax),laneEnd=[-1e9,-1e9];
    visible.forEach(([k,label,f])=>{const x=sx(m[k]),y=sy(C*f),w=label.length*6.4+8,lane=laneEnd.findIndex(e=>x>=e);
      marks+=`<line class="marker-line" x1="${x}" x2="${x}" y1="${T+(lane<0?4:lane*13-2)}" y2="${T+PH}"/><circle class="marker-dot" cx="${x}" cy="${y}" r="4"><title>${esc(label)}: ${fmt(m[k],1e-6,3)} µs</title></circle>`;
      if(lane>=0){laneEnd[lane]=x+w;marks+=`<text class="marker-label" x="${x+4}" y="${T-6+lane*13}">${esc(label)}</text>`;}});
    if(constructions){
      const origin=isLI?m.virtual_origin_s:m.beginning_s;
      if(m.T2_s&&origin!=null&&m.t50_falling_s<=xmax){const y=sy(C*.5)+(pol>0?16:-10),a=sx(Math.max(origin,xmin)),b=sx(m.t50_falling_s);marks+=`<g class="dimension"><line x1="${a}" x2="${b}" y1="${y}" y2="${y}"/><line x1="${a}" x2="${a}" y1="${y-5}" y2="${y+5}"/><line x1="${b}" x2="${b}" y1="${y-5}" y2="${y+5}"/><text x="${(a+b)/2}" y="${y-6}" text-anchor="middle">T2 = ${fmt(m.T2_s,1e-6,3)} µs</text></g>`;}
      if(isLI&&m.T1_s&&m.t90_s<=xmax&&sx(m.virtual_origin_s+m.T1_s)-sx(m.virtual_origin_s)>40){const o=m.virtual_origin_s,a=sx(o),b=sx(o+m.T1_s),y=sy(C)+(pol>0?-12:12);marks+=`<g class="dimension"><line x1="${a}" x2="${b}" y1="${y}" y2="${y}"/><line x1="${a}" x2="${a}" y1="${y-5}" y2="${y+5}"/><line x1="${b}" x2="${b}" y1="${y-5}" y2="${y+5}"/><text x="${b+6}" y="${y+4}">T1 = ${fmt(m.T1_s,1e-6,3)} µs</text></g>`;}
      if(!isLI&&m.Tp_s&&m.t_peak_s<=xmax&&sx(m.t_peak_s)-sx(m.beginning_s??0)>110){const a=sx(Math.max(m.beginning_s??0,xmin)),b=sx(m.t_peak_s),y=sy(C)+(pol>0?-12:12);marks+=`<g class="dimension"><line x1="${a}" x2="${b}" y1="${y}" y2="${y}"/><line x1="${a}" x2="${a}" y1="${y-5}" y2="${y+5}"/><line x1="${b}" x2="${b}" y1="${y-5}" y2="${y+5}"/><text x="${Math.max(a+4,(a+b)/2)}" y="${y-6}" text-anchor="middle">Tp = ${fmt(m.Tp_s,1e-6,3)} µs</text></g>`;}
    }
  }
  const label=`${esc(request.impulse_type)} waveform, signed DUT voltage in kV against time in ${tUnit}. ${series.map(s=>esc(s.label)).join('; ')}.`;
  element.innerHTML=`<div class="wave"><svg class="wave-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${label}"><defs><clipPath id="clip-${element.id}"><rect x="${L}" y="${T-30}" width="${PW}" height="${PH+30}"/></clipPath></defs>${svg}<g clip-path="url(#clip-${element.id})">${plot}${marks}</g><text class="axis-title" x="${L+PW/2}" y="${H-4}" text-anchor="middle">Time (${tUnit})</text><text class="axis-title" transform="translate(14 ${T+PH/2}) rotate(-90)" text-anchor="middle">Signed DUT voltage (kV)</text><g class="hover-layer"><line class="crosshair" y1="${T}" y2="${T+PH}" x1="-10" x2="-10"/><circle class="hover-dot" r="4.5" cx="-10" cy="-10"/></g><rect class="zoom-rect" x="0" y="${T}" width="0" height="${PH}"/><rect class="hit" x="${L}" y="${T}" width="${PW}" height="${PH}"/></svg><div class="readout" hidden></div></div>`;
  const svgEl=element.querySelector('svg'),hit=svgEl.querySelector('.hit'),cross=svgEl.querySelector('.crosshair'),dot=svgEl.querySelector('.hover-dot'),readout=element.querySelector('.readout'),zoom=svgEl.querySelector('.zoom-rect');
  const toT=ev=>{const r=svgEl.getBoundingClientRect();return xmin+((ev.clientX-r.left)*W/r.width-L)/PW*(xmax-xmin);};
  let dragStart=null;
  hit.addEventListener('pointermove',ev=>{
    const t=toT(ev),i=nearestIndex(primary.time_s,t),tt=primary.time_s[i],v=primary.voltage_V[i],x=sx(tt);
    cross.setAttribute('x1',x);cross.setAttribute('x2',x);dot.setAttribute('cx',x);dot.setAttribute('cy',sy(v));
    const extra=series.slice(1).map(s=>{const j=nearestIndex(s.wave.time_s,tt);return `<div><i class="sw ${s.kind}"></i>${esc(s.label)} <b>${fmt(s.wave.voltage_V[j],1000,3)} kV</b></div>`;}).join('');
    readout.innerHTML=`<div class="ro-head">Nearest stored sample #${i.toLocaleString()}</div><div><i class="sw reference"></i>t <b>${fmt(tt,1e-6,3)} µs</b></div><div>V <b>${fmt(v,1000,3)} kV</b> · ${fmt(Math.abs(v)/m.crest_magnitude_V*100,1,1)}% of crest</div>${extra}`;
    readout.hidden=false;readout.classList.toggle('left',x>W*.62);
    if(dragStart!==null){const a=Math.min(dragStart,x),b=Math.max(dragStart,x);zoom.setAttribute('x',a);zoom.setAttribute('width',b-a);}
  });
  hit.addEventListener('pointerleave',()=>{readout.hidden=true;cross.setAttribute('x1',-10);cross.setAttribute('x2',-10);dot.setAttribute('cx',-10);});
  if(onZoom){
    hit.addEventListener('pointerdown',ev=>{const r=svgEl.getBoundingClientRect();dragStart=(ev.clientX-r.left)*W/r.width;hit.setPointerCapture(ev.pointerId);});
    hit.addEventListener('pointerup',ev=>{if(dragStart===null)return;const r=svgEl.getBoundingClientRect(),end=(ev.clientX-r.left)*W/r.width,a=Math.min(dragStart,end),b=Math.max(dragStart,end);dragStart=null;zoom.setAttribute('width',0);if(b-a>8)onZoom({t0:xmin+(a-L)/PW*(xmax-xmin),t1:xmin+(b-L)/PW*(xmax-xmin)});});
    hit.addEventListener('dblclick',()=>onZoom(null));
  }
}
