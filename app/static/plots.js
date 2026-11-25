import {element} from './client.js';

function block(target,className,content) {
  const node=element('div',content,{class:className});
  target.append(node);
  return node;
}

export function visualize(report,selected) {
  const target=document.querySelector('#visual');
  target.replaceChildren();
  const measurement=report.cases?.find(row=>row.case===selected)?.measure;
  if (!measurement) {block(target,'chart-note','选择有计算值的分组');return;}
  const e=measurement.evidence;

  const graph=block(target,'survival-curve');
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 400 132'); svg.setAttribute('aria-label','按在险人数修正的仍未领取率');
  svg.setAttribute('role','img'); graph.append(svg);
  const line=document.createElementNS(svg.namespaceURI,'path');
  const maxAge=Math.max(1,e.horizon,...e.curve.map(row=>row.age));
  const steps=e.curve.map(row=>`H ${8+384*row.age/maxAge} V ${8+112*(1-row.remaining_bp/10000)}`);
  line.setAttribute('d',`M 8 8 ${steps.join(' ')} H 392`); svg.append(line);
  const ticks=block(target,'curve-labels');
  for(const row of e.curve) block(ticks,'curve-tick',`${row.age} · ${(row.remaining_bp/100).toFixed(2)}%`);
}
