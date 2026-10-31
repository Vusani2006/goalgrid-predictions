/* Apes Nation VIP: optional protected account + predictions via Supabase RLS.
 * Payment checkout intentionally not present until secure webhook integration.
 * No VIP predictions or private keys are embedded in public static files.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const settings = window.GOALGRID_CONFIG || {};
  const configured = /^https:\/\/[a-z0-9-]+\.supabase\.co\/?$/i.test(settings.supabaseUrl || '') &&
    typeof settings.supabaseAnonKey === 'string' && settings.supabaseAnonKey.length > 30;
  const setup = $('vip-setup-message');
  const wrap = $('vip-auth-wrap');
  const msg = $('vip-auth-message');
  const state = $('vip-member-state');
  const box = $('vip-picks');
  if (!configured) return;
  if (!window.supabase?.createClient) {
    setup.textContent = 'Member sign-in is unavailable because the authentication library did not load. Please retry with an internet connection.';
    return;
  }
  const db = window.supabase.createClient(settings.supabaseUrl.replace(/\/$/, ''), settings.supabaseAnonKey);
  setup.hidden = true;
  wrap.hidden = false;
  let previousId = null;
  let busy = false;
  function say(message, isError=false) {
    msg.textContent = message;
    msg.classList.toggle('vip-error', isError);
  }
  function hidePrivate() { box.replaceChildren(); box.hidden = true; state.hidden = true; }
  async function loadPrivate(user) {
    hidePrivate();
    $('vip-auth-guest').hidden = !!user;
    $('vip-auth-user').hidden = !user;
    $('vip-auth-email').textContent = user ? `Signed in: ${user.email || 'Member'}` : '';
    if (!user) { say('Sign in or create a free account to check VIP access. You will not be charged.'); return; }
    say('Checking owner status and active membership…');
    const [ownerResult, memberResult] = await Promise.all([
      db.from('site_owner').select('user_id').eq('user_id', user.id).maybeSingle(),
      db.from('vip_memberships').select('status,expires_at').eq('user_id', user.id).maybeSingle()
    ]);
    if (ownerResult.error || memberResult.error) {
      say('Cannot securely verify VIP access. Check that the latest Supabase SQL setup was applied.', true);
      return;
    }
    // Database row-level security, NOT this display check, controls access to private picks.
    const isOwner = ownerResult.data?.user_id === user.id;
    const membership = memberResult.data;
    const isActive = membership?.status === 'active' &&
      Number.isFinite(Date.parse(membership.expires_at)) && Date.parse(membership.expires_at) > Date.now();
    state.hidden = false;
    if (!isOwner && !isActive) {
      state.textContent = 'No active VIP subscription on this account. VIP costs R150 per month, but online checkout is not yet connected. A verified payment and member activation are required; do not send money until the checkout is officially enabled.';
      say('Account ready. No active VIP access.');
      return;
    }
    state.textContent = isOwner
      ? 'APES NATION OWNER — permanent complimentary VIP access. No R150 monthly subscription is required for this account.'
      : `VIP access active until ${new Date(membership.expires_at).toLocaleDateString('en-ZA',{dateStyle:'medium'})}. Monthly VIP price: R150. Estimates are never guarantees.`;
    const { data: predictions, error } = await db.from('vip_predictions')
      .select('id,home,away,league,kickoff,market,tip,confidence,projected_total,reason,status,final_score,research')
      .order('kickoff',{ ascending:false }).limit(100);
    if (error) { say('VIP database access failed. Please contact the site owner.', true); return; }
    box.hidden = false;
    if (!predictions?.length) {
      box.appendChild(make('p','No private VIP picks have been published yet. Your membership is active, but new researched picks require sufficient data.'));
      say('VIP access confirmed.'); return;
    }
    for (const p of predictions) {
      const article = make('article', '', 'vip-private-pick');
      const league = make('div', `${p.league || 'FOOTBALL'} · ${p.market || 'PREDICTION'}`, 'vip-pick-meta');
      const title = make('h4', `${p.home || '?'} vs ${p.away || '?'}`);
      const tip = make('p', p.tip || 'No selection available', 'vip-pick-tip');
      const date = Number.isFinite(Date.parse(p.kickoff)) ? new Date(p.kickoff).toLocaleString('en-ZA',{timeZone:'Africa/Johannesburg',dateStyle:'medium',timeStyle:'short'})+' SAST' : 'Kickoff not provided';
      const confidence = p.confidence == null ? 'No estimate' : `${p.confidence}% uncalibrated estimate`;
      const details = make('p', `${date} · ${confidence} · ${String(p.status || 'pending').toUpperCase()}`, 'vip-pick-meta');
      const reason = make('p', p.reason || 'No research note supplied');
      article.append(league,title,tip,details,reason);
      if (p.final_score) article.append(make('p', `Final score: ${p.final_score}`, 'vip-pick-meta'));
      if (p.research && typeof p.research === 'object') {
        const research = p.research;
        article.append(make('p', `Sample: ${research.sampleHome || '?'} home and ${research.sampleAway || '?'} away league matches. ${research.note || ''}`, 'vip-pick-meta'));
      }
      box.append(article);
    }
    say(`${predictions.length} private prediction record(s) loaded securely${isOwner ? ' for the site owner' : ''}.`);
  }
  function make(tag, value='', classes='') {
    const node = document.createElement(tag);
    node.textContent = value;
    if (classes) node.className = classes;
    return node;
  }
  async function submit(kind) {
    if (busy) return;
    const email = $('vip-email').value.trim();
    const password = $('vip-password').value;
    if (!email || password.length < 6) { say('Enter a valid email and a password of at least 6 characters.',true); return; }
    busy = true;
    say(kind === 'register' ? 'Creating account…' : 'Signing in…');
    try {
      const options = { emailRedirectTo: `${location.origin}${location.pathname}#membership` };
      const { data, error } = kind === 'register' ?
        await db.auth.signUp({email,password,options}) : await db.auth.signInWithPassword({email,password});
      if (error) throw error;
      $('vip-password').value = '';
      if (kind === 'register' && !data.session) say('Account created. Check your email for a confirmation link, then sign in. No payment taken.');
      else if (data.user) await loadPrivate(data.user);
    } catch (e) { say(e.message || 'Authentication failed. Please retry.',true); }
    finally { busy = false; }
  }
  $('vip-auth-form').addEventListener('submit', e => { e.preventDefault(); submit('login'); });
  $('vip-signup').addEventListener('click', () => submit('register'));
  $('vip-signout').addEventListener('click', async () => {
    const {error} = await db.auth.signOut();
    if (error) say('Sign-out failed. Please retry.',true);
    else { previousId=null; hidePrivate(); await loadPrivate(null); }
  });
  db.auth.getUser().then(({data,error}) => {
    if (error) { say('Sign in to your account.'); return; }
    previousId=data.user?.id || null;
    loadPrivate(data.user);
  }).catch(()=>say('Could not connect to the member service. Check your internet connection.',true));
  db.auth.onAuthStateChange((event, session) => {
    // Avoid waiting on Supabase calls inside the auth callback.
    const user = session?.user || null;
    if (event === 'SIGNED_OUT') { previousId=null; hidePrivate(); loadPrivate(null); }
    if ((event === 'SIGNED_IN' || event === 'USER_UPDATED') && user && previousId !== user.id) {
      previousId = user.id;
      setTimeout(() => loadPrivate(user),0);
    }
  });
})();
