(function(){
  'use strict';
  const $=(id)=>document.getElementById(id);
  const STORAGE_KEY='goalgrid.editor.v1';
  const pickTypes=[
    {key:'goals',marketType:'goals25',market:'TOTAL GOALS',name:'Over 2.5 goals',title:'OVER 2.5 GOALS',line:()=>2.5,checked:'check-goals'},
    {key:'corners',marketType:'cornersFT',market:'FULL-TIME CORNERS',name:'Full-time corners',title:'FULL-TIME CORNERS',line:()=>Number($('corners-line').value),checked:'check-corners'},
    {key:'firsthalf',marketType:'corners1H',market:'FIRST-HALF CORNERS',name:'First-half corners',title:'FIRST-HALF CORNERS',line:()=>Number($('firsthalf-line').value),checked:'check-firsthalf'}
  ];
  const published=Array.isArray(window.GOALGRID_PICKS) ? window.GOALGRID_PICKS.filter(p=>!p.demo):[];
  let queue=[];
  try {const item=localStorage.getItem(STORAGE_KEY);queue=item===null ? published : JSON.parse(item);if(!Array.isArray(queue)) queue=published;}
  catch{queue=published;}
  function persist(){try {localStorage.setItem(STORAGE_KEY,JSON.stringify(queue));}catch{} }
  function numericValue(id){return $(id).value.trim();}
  function readModel(key,line){
    return GoalGridModel.calculate({
      homeFor:numericValue(key+'-home-for'),awayAllowed:numericValue(key+'-away-allow'),
      awayFor:numericValue(key+'-away-for'),homeAllowed:numericValue(key+'-home-allow'),line
    });
  }
  const computed=()=>pickTypes.map(item=>({...item,result:readModel(item.key,item.line())}));
  function estimates(){
    $('estimate-grid').innerHTML=computed().map(item=>{
      const r=item.result;
      return `<div class="estimate-card"><div class="estimate-market">${item.title} · OVER ${item.line()}</div><div class="estimate-number">${r?`${Math.round(r.probability*100)}<small>%</small>`:'—'}</div><p>${r?`Poisson input mean: ${r.mean.toFixed(2)} events. Experimental estimate, not a proven probability.`:'Complete all four input averages to calculate this market.'}</p>${!r?'<div class="estimate-missing">INPUT DATA NEEDED</div>':''}</div>`;
    }).join('');
  }
  function safeURL(value){try{const u=new URL(value);return ['https:','http:'].includes(u.protocol)?u.href:null;}catch{return null;}}
  function message(text,type=''){$('form-message').textContent=text;$('form-message').className='form-message '+type;}
  function clearInputs(){
    $('research-form').reset(); $('f-checked').value=new Date().toISOString().slice(0,10); estimates();
  }
  function addPicks(e){
    e.preventDefault();
    const home=$('f-home').value.trim(),away=$('f-away').value.trim(),league=$('f-league').value.trim(),kickoff=$('f-kickoff').value;
    const sampleHome=Number($('f-sample-home').value),sampleAway=Number($('f-sample-away').value);
    const note=$('f-note').value.trim(),source=safeURL($('f-source').value.trim());
    const extra=$('f-source-2').value.trim();
    if(!home||!away||!league||!kickoff||!Number.isFinite(Date.parse(kickoff))){message('Enter both teams, the league, and a valid kickoff date/time.','error');return;}
    if(home.toLowerCase()===away.toLowerCase()){message('The home and away teams must be different.','error');return;}
    if(!Number.isInteger(sampleHome)||!Number.isInteger(sampleAway)||sampleHome<6||sampleAway<6){message('For publication, use at least 6 recent home matches and 6 recent away matches.','error');return;}
    if(!source){message('Add at least one valid http(s) link to the statistics you used.','error');return;}
    if(extra&&!safeURL(extra)){message('The optional second source must also be a valid http(s) URL.','error');return;}
    if(note.length<35){message('Add at least 35 characters explaining the evidence, risk factors, and assumptions.','error');return;}
    const selected=computed().filter(item=>$(item.checked).checked);
    if(!selected.length){message('Select at least one market to publish.','error');return;}
    if(selected.some(item=>!item.result)){message('Complete all four statistical averages for every selected market.','error');return;}
    const ts=Date.now();
    const checkedAt=$('f-checked').value||new Date().toISOString().slice(0,10);
    const research={sampleHome,sampleAway,checkedAt,teamNews:$('f-team-news').value.trim(),note,
      sources:[source,...(extra?[safeURL(extra)]:[])]};
    const kickoffSAST=kickoff.length===16?kickoff+':00+02:00':kickoff+'+02:00';
    const newPicks=selected.map((item,i)=>({
      id:'gg-'+ts+'-'+i,home,away,league,kickoff:kickoffSAST,
      marketType:item.marketType,market:item.market,
      tip:`Over ${item.line()} ${item.marketType==='goals25'?'goals':item.marketType==='corners1H'?'first-half corners':'corners'}`,
      confidence:Math.round(item.result.probability*100),projectedTotal:Number(item.result.mean.toFixed(2)),
      reason:note,status:'pending',featured:queue.length===0&&i===0,demo:false,research:{...research}
    }));
    queue.push(...newPicks);persist();renderQueue();clearInputs();
    message(`${newPicks.length} researched pick(s) added to the local queue. Download data.js and redeploy to publish.`, 'success');
    $('stored-picks').scrollIntoView({behavior:'smooth',block:'start'});
  }
  function escapeHTML(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  function renderQueue(){
    if(!queue.length){$('stored-picks').innerHTML='<div class="queue-empty">No live picks in your draft yet. Demo matches are excluded from exports. Add a researched fixture above.</div>';return;}
    $('stored-picks').innerHTML=queue.map((p,i)=>`<div class="stored-pick" data-id="${escapeHTML(p.id)}"><div><strong>${escapeHTML(p.home)} vs ${escapeHTML(p.away)}</strong><small>${escapeHTML(p.league)} · ${escapeHTML(p.kickoff)}</small></div><div><span class="tip-title">${escapeHTML(p.tip)}</span><small>${p.confidence==null?'No estimate':`${Math.round(Number(p.confidence))}% provisional model estimate`}</small></div><label class="sr-only" for="result-${i}">Prediction result</label><select class="result-select" id="result-${i}" data-id="${escapeHTML(p.id)}"><option value="pending" ${p.status==='pending'?'selected':''}>Unsettled</option><option value="won" ${p.status==='won'?'selected':''}>Won</option><option value="lost" ${p.status==='lost'?'selected':''}>Lost</option><option value="void" ${p.status==='void'?'selected':''}>Void</option></select><button class="delete-pick" type="button" data-id="${escapeHTML(p.id)}">Remove</button></div>`).join('');
  }
  function exportData(){
    const output='// Apes Nation Football Prediction publication data — generated by editor.html.\nwindow.GOALGRID_PICKS = '+JSON.stringify(queue,null,2)+';\n';
    const url=URL.createObjectURL(new Blob([output],{type:'application/javascript;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download='data.js';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1200);
    $('queue-message').textContent=`Exported ${queue.length} real pick(s). Replace data.js in the website folder and redeploy it. Editing here does NOT update your live site.`;
  }
  document.querySelectorAll('#research-form input,#research-form select').forEach(el=>el.addEventListener('input',estimates));
  $('research-form').addEventListener('submit',addPicks);
  $('stored-picks').addEventListener('change',e=>{
    if(!e.target.classList.contains('result-select'))return;
    const pick=queue.find(p=>String(p.id)===e.target.dataset.id);
    if(pick){pick.status=e.target.value;persist();$('queue-message').textContent='Outcome saved in this browser. Download and redeploy to update the published site.';}
  });
  $('stored-picks').addEventListener('click',e=>{
    if(!e.target.classList.contains('delete-pick'))return;
    queue=queue.filter(p=>String(p.id)!==e.target.dataset.id);persist();renderQueue();
    $('queue-message').textContent='Pick removed from local draft. Download and redeploy to update the published site.';
  });
  $('export-btn').addEventListener('click',exportData);
  $('clear-btn').addEventListener('click',()=>{
    if(!window.confirm('Clear all picks in your local draft? This will not affect the published website.'))return;
    queue=[];persist();renderQueue();$('queue-message').textContent='Queue cleared in this browser. Download data.js and redeploy to remove published picks.';
  });
  $('f-checked').value=new Date().toISOString().slice(0,10);
  estimates();renderQueue();
})();
