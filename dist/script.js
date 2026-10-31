(function () {
  'use strict';
  const picks = Array.isArray(window.GOALGRID_PICKS) ? [...window.GOALGRID_PICKS] : [];
  const $ = (id) => document.getElementById(id);
  const fmtDate = new Intl.DateTimeFormat('en-ZA', { timeZone: 'Africa/Johannesburg', day: '2-digit', month: 'short', year: 'numeric' });
  const fmtTime = new Intl.DateTimeFormat('en-ZA', { timeZone: 'Africa/Johannesburg', hour: '2-digit', minute: '2-digit', hour12: false });
  const todayKey = (d) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Johannesburg', year:'numeric', month:'2-digit', day:'2-digit' }).format(d);
  const formatKickoff = (iso) => { const d = new Date(iso); return isNaN(d.getTime()) ? 'DATE TBA' : `${fmtDate.format(d)} • ${fmtTime.format(d)} SAST`; };
  const escapeHTML = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const letters = (s) => String(s || '').trim().split(/\s+/).slice(0,2).map(w => w[0]).join('').toUpperCase() || 'FC';
  const statusName = {pending:'UNSETTLED', won:'WON', lost:'LOST', void:'VOID'};
  const validStatus = (s) => ['pending','won','lost','void'].includes(s) ? s : 'pending';
  let filter = 'all'; let league = 'all'; let market = 'all';
  picks.sort((a,b) => new Date(a.kickoff) - new Date(b.kickoff));
  const safeURL = (s) => { try { const u = new URL(String(s)); return /^https?:$/.test(u.protocol) ? u.href : null; } catch { return null; } };

  function renderFeatured() {
    const match = picks.find(p => p.featured) || picks.find(p => p.status === 'pending') || picks[0];
    $('hero-date').textContent = new Intl.DateTimeFormat('en-ZA', { day:'2-digit',month:'short',year:'numeric',timeZone:'Africa/Johannesburg' }).format(new Date()).toUpperCase();
    if (!match) { $('featured-sample').hidden = true; return; }
    $('featured-league').textContent = match.league || 'MATCH INSIGHT';
    $('featured-home').textContent = match.home;
    $('featured-away').textContent = match.away;
    $('featured-home-badge').textContent = letters(match.home);
    $('featured-away-badge').textContent = letters(match.away);
    $('featured-tip').textContent = match.tip;
    $('featured-reason').textContent = match.reason;
    $('featured-date').textContent = formatKickoff(match.kickoff).toUpperCase();
    $('featured-sample').hidden = !match.demo;
  }
  function renderStats() {
    $('stat-picks').textContent = String(picks.length).padStart(2,'0');
    $('stat-leagues').textContent = String(new Set(picks.map(p => p.league).filter(Boolean)).size).padStart(2,'0');
    const won = picks.filter(p => p.status === 'won').length;
    const lost = picks.filter(p => p.status === 'lost').length;
    const voided = picks.filter(p => p.status === 'void').length;
    $('stat-hit').textContent = won + lost ? `${Math.round(100 * won / (won + lost))}%` : '—';
    $('results-total').textContent = won + lost + voided;
    $('results-won').textContent = won;
    $('results-lost').textContent = lost;
    $('results-void').textContent = voided;
    const evalBox=$('backtest-summary');
    if (evalBox) {
      const backtest=window.GOALGRID_BACKTEST||{};
      const assessed=Object.entries(backtest.markets||{})
        .filter(([,v])=>v.verifiedEnough && v.observations>=50 && v.hitRate!=null)
        .map(([market,v])=>`${market}: ${Math.round(100*v.hitRate)}% success in ${v.observations} historical simulated selections (Brier ${v.brier})`);
      evalBox.textContent=assessed.length ?
        'Historical walk-forward MODEL tests (not published picks): '+assessed.join(' • ')+'. Results do not guarantee future accuracy.' :
        'Historical model validation is collecting real matches. At least 50 settled historical model selections per market are required before reporting a backtest success rate.';
    }
    $('demo-banner').hidden = !picks.some(p => p.demo);
    const meta=window.GOALGRID_META||{};
    $('automation-banner').hidden = Boolean(meta.automated && meta.updatedAt && picks.length > 0);
    $('automation-message').textContent = meta.message || 'Automation not connected yet.';
    if (meta.automated && meta.updatedAt) { $('last-updated').textContent = 'AUTO-UPDATED ' + new Date(meta.updatedAt).toLocaleString('en-ZA',{timeZone:'Africa/Johannesburg',dateStyle:'medium',timeStyle:'short'}) + ' SAST'; }
    $('copyright-year').textContent = new Date().getFullYear();
    if (!(window.GOALGRID_META||{}).updatedAt) $('last-updated').textContent = 'KICKOFFS DISPLAYED IN SOUTH AFRICAN TIME';
  }
  function renderLeagues() {
    [...new Set([...(window.GOALGRID_META?.selectedLeagues || []), ...picks.map(p => p.league)].filter(Boolean))].sort().forEach(l => {
      const option = document.createElement('option'); option.value = l; option.textContent = l;
      $('league-select').appendChild(option);
    });
  }
  function researchHTML(p) {
    if (p.demo) return '<div class="research-note demo-note">DEMO · No actual match research is attached to this preview.</div>';
    const inputs = p.research || {};
    const evidence = [
      ['MODEL INPUT', p.projectedTotal == null ? null : `${Number(p.projectedTotal).toFixed(2)} expected ${['goals25','resultFT','twoUP'].includes(p.marketType) ? 'goals' : 'corners'}`],
      ['DATA SAMPLE', inputs.sampleHome && inputs.sampleAway ? `${inputs.sampleHome} home / ${inputs.sampleAway} away matches` : null],
      ['FT SCORE', p.finalScore || null],
      ['LAST CHECKED', inputs.checkedAt || null],
      ['TEAM NEWS', inputs.teamNews || null],
      ['PLAYING STYLE', inputs.playingStyles || null],
      ['CONFIRMED XIs', inputs.lineupStatus || 'Not checked / unavailable'],
      ['WITH/WITHOUT', inputs.withWithout || null],
      ['SQUAD CHECK', inputs.dataQuality || null]
    ].filter(([,v]) => v != null && v !== '');
    const sources = (Array.isArray(inputs.sources) ? inputs.sources : [])
      .map(s => safeURL(s)).filter(Boolean).slice(0,4)
      .map((u,i) => `<a href="${escapeHTML(u)}" target="_blank" rel="noopener noreferrer">Source ${i+1} ↗</a>`).join('');
    return `<details class="research-details"><summary>VIEW RESEARCH & SOURCES <span>+</span></summary>
      <div class="research-inside">${evidence.map(([k,v])=>`<div class="research-line"><b>${k}</b><span>${escapeHTML(v)}</span></div>`).join('')}
      <p>${escapeHTML(inputs.note || 'Match assumptions not provided. Always verify the inputs and team news before relying on this estimate.')}</p>
      ${sources ? `<div class="research-links">${sources}</div>` : '<small>No supporting source links supplied.</small>'}
      <small>Model output is an unvalidated estimate, not a calibrated probability.</small></div></details>`;
  }
  function renderPicks() {
    const now = todayKey(new Date());
    const list = picks.filter(p => {
      const dt = new Date(p.kickoff); const key = isNaN(dt.getTime()) ? '' : todayKey(dt);
      if (league !== 'all' && p.league !== league) return false;
      if (market !== 'all' && p.marketType !== market) return false;
      if (filter === 'today' && (key !== now || p.status !== 'pending')) return false;
      if (filter === 'upcoming' && (key < now || p.status !== 'pending')) return false;
      if (filter === 'results' && p.status === 'pending') return false;
      return true;
    });
    $('pick-count').textContent = `${list.length} ${list.length === 1 ? 'PICK' : 'PICKS'}`;
    $('empty-state').hidden = list.length > 0;
    $('pick-grid').innerHTML = list.map((p,i) => {
      const status = validStatus(p.status);
      const estimate = p.demo || p.confidence == null || p.confidence === '' || !Number.isFinite(Number(p.confidence)) ? null : Math.round(Math.max(0,Math.min(100,Number(p.confidence))));
      return `<article class="pick-card" style="--stagger:${Math.min(i,9)*55}ms">
        <div class="card-head"><span class="card-league">${escapeHTML(p.league)}</span><span class="card-status ${status}"><span class="card-status-dot"></span>${statusName[status]}</span></div>
        <div class="card-matchup"><div class="card-team"><span class="team-logo">${escapeHTML(letters(p.home))}</span><strong>${escapeHTML(p.home)}</strong></div><span class="card-vs">VS</span><div class="card-team away"><span class="team-logo">${escapeHTML(letters(p.away))}</span><strong>${escapeHTML(p.away)}</strong></div></div>
        <div class="card-date">◷ &nbsp;${escapeHTML(formatKickoff(p.kickoff))}</div>
        <div class="card-pick"><div><span class="market-label">${escapeHTML(p.market)}</span><div class="pick-tip">${escapeHTML(p.tip)}</div></div>${estimate === null ? '' : `<div class="confidence"><strong>${estimate}%</strong><span>MODEL EST.</span></div>`}</div>
        <div class="card-reason">${escapeHTML(p.reason)}</div>
        ${researchHTML(p)}
        <div class="card-bottom"><span>${p.demo ? '◈ EXAMPLE ONLY' : '◈ RESEARCH-LED ESTIMATE'}</span><button class="share-pick" type="button" data-id="${escapeHTML(p.id)}" aria-label="Copy prediction for ${escapeHTML(p.home)} versus ${escapeHTML(p.away)}">COPY PICK <span>↗</span></button></div>
      </article>`;
    }).join('');
  }
  // Membership switch changes the visible section, not authorization.
  // VIP forecasts must NEVER be embedded in this publicly served JavaScript or data.js.
  function selectTier(value) {
    const vip = value === 'vip';
    $('free-board').hidden = vip;
    $('vip-board').hidden = !vip;
    document.querySelectorAll('.tier-tab').forEach(tab => {
      const selected = tab.dataset.tier === value;
      tab.classList.toggle('active', selected);
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
  }
  document.querySelectorAll('.tier-tab').forEach(tab => tab.addEventListener('click', () => selectTier(tab.dataset.tier)));
  document.querySelectorAll('a[href="#membership"]').forEach(link => link.addEventListener('click', () => selectTier('vip')));
  window.addEventListener('hashchange', () => { if (window.location.hash === '#membership') selectTier('vip'); });
  if (window.location.hash === '#membership') selectTier('vip');
  document.querySelectorAll('.market-tab').forEach(tab => tab.addEventListener('click', () => {
    market = tab.dataset.market;
    document.querySelectorAll('.market-tab').forEach(el => el.classList.toggle('active',el === tab)); renderPicks();
  }));
  document.querySelectorAll('.filter-tab').forEach(tab => tab.addEventListener('click', () => {
    filter = tab.dataset.filter;
    document.querySelectorAll('.filter-tab').forEach(el => el.classList.toggle('active',el === tab)); renderPicks();
  }));
  $('league-select').addEventListener('change',e=>{league=e.target.value;renderPicks();});
  $('reset-filters').addEventListener('click',()=>{
    filter='all'; league='all'; market='all'; $('league-select').value='all';
    document.querySelectorAll('.filter-tab').forEach(el=>el.classList.toggle('active',el.dataset.filter==='all'));
    document.querySelectorAll('.market-tab').forEach(el=>el.classList.toggle('active',el.dataset.market==='all')); renderPicks();
  });
  $('pick-grid').addEventListener('click',async e=>{
    const button=e.target.closest('.share-pick'); if(!button)return;
    const match=picks.find(p=>String(p.id)===button.dataset.id); if(!match)return;
    const output=`${match.home} vs ${match.away}\n${match.league}\n${formatKickoff(match.kickoff)}\nSelection: ${match.tip}\n${match.reason}${match.demo ? '\nEXAMPLE ONLY — not a real fixture' : ''}\nApes Nation Football Prediction — No guaranteed outcomes.`;
    try { await navigator.clipboard.writeText(output); const old=button.innerHTML; button.textContent='COPIED ✓'; setTimeout(()=>button.innerHTML=old,1800); }
    catch { window.prompt('Copy this prediction:',output); }
  });
  renderFeatured();renderStats();renderLeagues();renderPicks();
})();
