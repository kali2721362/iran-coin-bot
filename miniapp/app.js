/* IRAN Coin Mini App - UI similar to provided screenshots */
'use strict';

const CONFIG = {
  API_URL: 'https://iran-coin-bot-production.up.railway.app/api/v1',
  BOT_USERNAME: 'IranCoinEarnBot',
  IRAN_TO_TON_RATE: 0.000002,
  CACHE_BUSTER: 'v1'
};

const TG = window.Telegram?.WebApp;

const state = {
  user: null,
  page: 'home',
  prev: null,
};

function qs(name){
  const u = new URL(location.href);
  return u.searchParams.get(name);
}

async function apiPost(path, body){
  const r = await fetch(CONFIG.API_URL + path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  return r.json();
}

async function apiGet(path){
  const r = await fetch(CONFIG.API_URL + path);
  return r.json();
}

function money(n){
  const x = Number(n || 0);
  return x.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function toast(msg, type='ok'){
  document.querySelectorAll('.toast').forEach(t=>t.remove());
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>{t.classList.remove('show'); setTimeout(()=>t.remove(), 250)}, 2400);
}

async function init(){
  if (TG){
    TG.ready();
    TG.expand();
    TG.setHeaderColor('#071018');
    TG.setBackgroundColor('#071018');
  }

  const tgUser = TG?.initDataUnsafe?.user;
  const ref = qs('ref');

  if (!tgUser){
    // fallback demo (should not happen inside Telegram)
    state.user = {
      telegram_id: 111111,
      first_name: 'User',
      username: '',
      balance: 0,
      total_earned: 0,
      referral_code: 'DEMO',
      referral_count: 0,
      referral_earnings: 0,
      ton_wallet: ''
    };
    return;
  }

  const payload = {
    initData: TG?.initData || '',
    user: {
      id: tgUser.id,
      username: tgUser.username || '',
      first_name: tgUser.first_name || 'User',
      last_name: tgUser.last_name || ''
    },
    ref: ref
  };

  const res = await apiPost('/user/init', payload);
  if (!res?.success) {
    toast('Server error. Try again.', 'err');
    return;
  }
  state.user = res.user;
}

function openApp(page){
  document.getElementById('splash').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  navTo(page || 'home');
}

function setBackVisible(v){
  const b = document.getElementById('backBtn');
  if (!b) return;
  b.classList.toggle('hidden', !v);
}

function navTo(page){
  state.prev = state.page;
  state.page = page;

  document.querySelectorAll('.nav-btn').forEach(btn=>{
    btn.classList.toggle('active', btn.dataset.page === page);
  });

  setBackVisible(page === 'withdraw');

  const root = document.getElementById('page');
  root.innerHTML = '';

  if (page === 'home') renderHome(root);
  else if (page === 'ads') renderAds(root);
  else if (page === 'tasks') renderTasks(root);
  else if (page === 'wallet') renderWallet(root);
  else if (page === 'withdraw') renderWithdraw(root);
  else if (page === 'more') renderMore(root);
  else renderHome(root);
}

function goBack(){
  navTo(state.prev || 'home');
}

/* HOME */
function renderHome(root){
  const u = state.user;
  const ton = (Number(u.balance||0) * CONFIG.IRAN_TO_TON_RATE).toFixed(4);

  root.innerHTML = `
    <div class="card">
      <div class="header-row">
        <div>
          <div class="h-title">IRAN Coin</div>
          <div class="h-sub">Together for a better future 🇮🇷</div>
        </div>
        <div style="opacity:.9;font-weight:900;color:rgba(255,255,255,.7)">${u.username ? '@'+u.username : ''}</div>
      </div>

      <div class="balance-card">
        <div class="coin-mini">
          <div class="inner">
            <div class="g"></div>
            <div class="w">الله</div>
            <div class="r"></div>
          </div>
        </div>
        <div class="balance-text">
          <div class="balance-label">Your Balance</div>
          <div class="balance-amount">${money(u.balance)} <span>IRAN</span></div>
          <div class="balance-ton">≈ <b>${ton} TON</b></div>
        </div>
      </div>

      <div class="grid">
        <div class="tile" onclick="navTo('ads')">
          <div class="t-ico green">▶</div>
          <div class="t-title">Watch Ads</div>
          <div class="t-sub">+5–20 IRAN</div>
        </div>

        <div class="tile" onclick="navTo('tasks')">
          <div class="t-ico gold">✓</div>
          <div class="t-title">Tasks</div>
          <div class="t-sub">+10–100 IRAN</div>
        </div>

        <div class="tile" onclick="navTo('more')">
          <div class="t-ico blue">👥</div>
          <div class="t-title">Invite Friends</div>
          <div class="t-sub">+50 IRAN</div>
        </div>

        <div class="tile" onclick="toast('Daily Bonus is UI only (optional feature).')">
          <div class="t-ico purple">🎁</div>
          <div class="t-title">Daily Bonus</div>
          <div class="t-sub">+10 IRAN</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:12px">
      <div class="header-row">
        <div class="h-title">Recent Transactions</div>
        <button class="btn" onclick="navTo('wallet')">View</button>
      </div>
      <div id="txBox" class="list"></div>
    </div>
  `;

  loadTxMini();
}

async function loadTxMini(){
  const box = document.getElementById('txBox');
  if (!box) return;
  box.innerHTML = `<div style="color:rgba(234,246,255,.55);font-weight:700">Loading...</div>`;

  const data = await apiGet(`/user/${state.user.telegram_id}/transactions`);
  const txs = data?.transactions || [];
  if (!txs.length){
    box.innerHTML = `<div style="color:rgba(234,246,255,.55);font-weight:700">No transactions yet.</div>`;
    return;
  }

  box.innerHTML = txs.slice(0,3).map(tx=>{
    const sign = tx.amount > 0 ? '+' : '';
    return `
      <div class="item">
        <div class="badge c3">⏱</div>
        <div class="item-info">
          <div class="item-title">${tx.description || tx.type}</div>
          <div class="item-meta"><span>${(tx.created_at||'').slice(0,19).replace('T',' ')}</span></div>
        </div>
        <div style="font-weight:900;color:${tx.amount>0?'#22c55e':'#ef4444'}">${sign}${money(Math.abs(tx.amount))} IRAN</div>
      </div>
    `;
  }).join('');
}

/* ADS */
const ADS_UI = [
  {id:1, icon:'📢', cls:'c1', title:'Crypto News', sec:30, rewardText:'+15 IRAN'},
  {id:2, icon:'🏛', cls:'c2', title:'Iranian Culture', sec:45, rewardText:'+20 IRAN'},
  {id:3, icon:'🌐', cls:'c3', title:'Web3 Projects', sec:60, rewardText:'+25 IRAN'},
  {id:4, icon:'🤖', cls:'c4', title:'Technology & AI', sec:45, rewardText:'+20 IRAN'},
  {id:5, icon:'✈️', cls:'c5', title:'Lifestyle & Travel', sec:30, rewardText:'+15 IRAN'},
];

function renderAds(root){
  root.innerHTML = `
    <div class="card">
      <div class="header-row">
        <div>
          <div class="h-title">Watch Ads</div>
          <div class="h-sub">Watch short ads and earn IRAN coins</div>
        </div>
      </div>
      <div class="list">
        ${ADS_UI.map(a=>`
          <div class="item">
            <div class="badge ${a.cls}">${a.icon}</div>
            <div class="item-info">
              <div class="item-title">${a.title}</div>
              <div class="item-meta">
                <span class="gold">${a.rewardText}</span>
                <span>⏱ ${a.sec} sec</span>
              </div>
            </div>
            <button class="btn" id="adBtn${a.id}" onclick="watchAd(${a.id})">Watch</button>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

async function watchAd(adId){
  const btn = document.getElementById(`adBtn${adId}`);
  if (btn) { btn.disabled = true; btn.textContent = '...'; }

  // call backend (real reward comes from server)
  const res = await apiPost('/ads/watch', { telegram_id: state.user.telegram_id, ad_id: adId });

  if (!res?.success){
    toast(res?.message || 'Cannot watch now.', 'err');
    if (btn) { btn.disabled = false; btn.textContent = 'Watch'; }
    return;
  }

  state.user.balance = res.new_balance;
  toast(`+${res.reward} IRAN added`, 'ok');
  if (TG) TG.HapticFeedback?.notificationOccurred('success');

  // refresh home balance if user returns
  if (btn) { btn.textContent = 'Done'; }
}

/* TASKS */
function renderTasks(root){
  root.innerHTML = `
    <div class="card">
      <div class="header-row">
        <div>
          <div class="h-title">Tasks</div>
          <div class="h-sub">Complete simple tasks and earn IRAN</div>
        </div>
      </div>
      <div id="taskBox" class="list"></div>
      <div style="margin-top:10px;color:rgba(234,246,255,.55);font-weight:700">
        More tasks coming soon. Follow our channel for updates.
      </div>
    </div>
  `;
  loadTasks();
}

function taskIcon(t){
  const type = (t.task_type || '').toLowerCase();
  if (type.includes('join')) return {ico:'✈️', cls:'c1'};
  if (type.includes('follow')) return {ico:'✕', cls:'c4'};
  if (type.includes('subscribe')) return {ico:'▶', cls:'c5'};
  if (type.includes('survey')) return {ico:'📋', cls:'c2'};
  return {ico:'✓', cls:'c3'};
}

async function loadTasks(){
  const box = document.getElementById('taskBox');
  box.innerHTML = `<div style="color:rgba(234,246,255,.55);font-weight:700">Loading...</div>`;
  const data = await apiGet(`/tasks/${state.user.telegram_id}`);
  const tasks = data?.tasks || [];
  if (!tasks.length){
    box.innerHTML = `<div style="color:rgba(234,246,255,.55);font-weight:700">No tasks.</div>`;
    return;
  }

  box.innerHTML = tasks.map(t=>{
    const ic = taskIcon(t);
    return `
      <div class="item">
        <div class="badge ${ic.cls}">${ic.ico}</div>
        <div class="item-info">
          <div class="item-title">${t.title}</div>
          <div class="item-meta">
            <span class="gold">+${t.reward} IRAN</span>
          </div>
        </div>
        <button class="btn" ${t.completed ? 'disabled' : ''} onclick="doTask(${t.id}, '${(t.task_url||'').replace(/'/g,'')}')">
          ${t.completed ? 'Done' : 'Start'}
        </button>
      </div>
    `;
  }).join('');
}

async function doTask(taskId, url){
  if (url){
    if (TG) TG.openTelegramLink(url);
    else window.open(url, '_blank');
  }

  const res = await apiPost('/tasks/complete', { telegram_id: state.user.telegram_id, task_id: taskId });
  if (!res?.success){
    toast(res?.message || 'Not verified yet.', 'err');
    return;
  }
  state.user.balance = res.new_balance;
  toast(`+${res.reward} IRAN added`, 'ok');
  await loadTasks();
}

/* WALLET */
function renderWallet(root){
  const u = state.user;
  const ton = (Number(u.balance||0) * CONFIG.IRAN_TO_TON_RATE).toFixed(4);

  root.innerHTML = `
    <div class="card">
      <div class="header-row">
        <div>
          <div class="h-title">Wallet</div>
          <div class="h-sub">Your IRAN coin balance and transactions</div>
        </div>
        <button class="btn" onclick="navTo('withdraw')">Withdraw</button>
      </div>

      <div class="balance-card">
        <div class="coin-mini">
          <div class="inner">
            <div class="g"></div>
            <div class="w">الله</div>
            <div class="r"></div>
          </div>
        </div>
        <div class="balance-text">
          <div class="balance-label">IRAN</div>
          <div class="balance-amount">${money(u.balance)} <span>IRAN</span></div>
          <div class="balance-ton">≈ <b>${ton} TON</b></div>
        </div>
      </div>

      <div class="header-row" style="margin-top:14px">
        <div class="h-title">Transaction History</div>
        <button class="btn" onclick="loadTxFull()">Refresh</button>
      </div>
      <div id="txFull" class="list"></div>
    </div>
  `;
  loadTxFull();
}

async function loadTxFull(){
  const box = document.getElementById('txFull');
  box.innerHTML = `<div style="color:rgba(234,246,255,.55);font-weight:700">Loading...</div>`;
  const data = await apiGet(`/user/${state.user.telegram_id}/transactions`);
  const txs = data?.transactions || [];
  if (!txs.length){
    box.innerHTML = `<div style="color:rgba(234,246,255,.55);font-weight:700">No transactions yet.</div>`;
    return;
  }
  box.innerHTML = txs.map(tx=>{
    const sign = tx.amount > 0 ? '+' : '';
    return `
      <div class="item">
        <div class="badge c3">⏱</div>
        <div class="item-info">
          <div class="item-title">${tx.description || tx.type}</div>
          <div class="item-meta"><span>${(tx.created_at||'').slice(0,19).replace('T',' ')}</span></div>
        </div>
        <div style="font-weight:900;color:${tx.amount>0?'#22c55e':'#ef4444'}">${sign}${money(Math.abs(tx.amount))} IRAN</div>
      </div>
    `;
  }).join('');
}

/* WITHDRAW */
function renderWithdraw(root){
  const u = state.user;
  root.innerHTML = `
    <div class="card">
      <div class="header-row">
        <div>
          <div class="h-title">Withdraw</div>
          <div class="h-sub">Transfer your IRAN coins to TON wallet</div>
        </div>
      </div>

      <div style="margin-top:10px">
        <div style="color:rgba(234,246,255,.65); font-weight:800; font-size:12px">TON Wallet Address</div>
        <input id="tonAddr" style="margin-top:8px;width:100%;padding:12px;border-radius:14px;border:1px solid rgba(255,255,255,.10);background:rgba(15,34,48,.75);color:#eaf6ff;outline:none"
               placeholder="UQ..." value="${u.ton_wallet || ''}">
      </div>

      <div style="margin-top:12px">
        <div style="color:rgba(234,246,255,.65); font-weight:800; font-size:12px">Amount (IRAN)</div>
        <input id="wdAmount" type="number" style="margin-top:8px;width:100%;padding:12px;border-radius:14px;border:1px solid rgba(255,255,255,.10);background:rgba(15,34,48,.75);color:#eaf6ff;outline:none"
               placeholder="Min 500" min="500">
      </div>

      <button class="btn" style="width:100%;margin-top:14px" onclick="requestWithdraw()">Request Withdrawal</button>
    </div>
  `;
}

async function requestWithdraw(){
  const addr = (document.getElementById('tonAddr')?.value || '').trim();
  const amount = Number(document.getElementById('wdAmount')?.value || 0);

  if (!addr) return toast('Enter TON address', 'err');
  if (!amount || amount < 500) return toast('Minimum is 500 IRAN', 'err');

  const res = await apiPost('/withdraw/request', {
    telegram_id: state.user.telegram_id,
    amount: amount,
    ton_address: addr
  });

  if (!res?.success){
    toast(res?.message || 'Withdraw failed', 'err');
    return;
  }
  state.user.balance = res.new_balance;
  toast('Withdraw request submitted', 'ok');
  navTo('wallet');
}

/* MORE / PROFILE */
function renderMore(root){
  const u = state.user;
  const refLink = `https://t.me/${CONFIG.BOT_USERNAME}?start=${u.referral_code}`;
  root.innerHTML = `
    <div class="card">
      <div class="header-row">
        <div>
          <div class="h-title">Profile & Settings</div>
          <div class="h-sub">Manage your account</div>
        </div>
      </div>

      <div class="item" style="margin-top:12px">
        <div class="badge c1">🇮🇷</div>
        <div class="item-info">
          <div class="item-title">${u.username ? '@'+u.username : u.first_name}</div>
          <div class="item-meta"><span class="gold">Verified</span></div>
        </div>
      </div>

      <div class="card" style="margin-top:12px">
        <div class="h-title" style="margin-bottom:8px">Invite Friends</div>
        <div style="color:rgba(234,246,255,.6);font-weight:700;font-size:12px">Your referral link</div>
        <div style="margin-top:8px; padding:10px; border-radius:12px; border:1px solid rgba(255,255,255,.10); background:rgba(15,34,48,.65); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          ${refLink}
        </div>
        <button class="btn" style="margin-top:10px" onclick="copyRef('${refLink.replace(/'/g,'')}')">Copy</button>
      </div>
    </div>
  `;
}

async function copyRef(txt){
  try{
    await navigator.clipboard.writeText(txt);
    toast('Copied', 'ok');
  }catch{
    toast('Copy failed', 'err');
  }
}

/* boot */
window.openApp = openApp;
window.navTo = navTo;
window.goBack = goBack;

window.addEventListener('DOMContentLoaded', async ()=>{
  await init();
});