'use strict';

const CONFIG = {
  API_URL: 'https://iran-coin-bot-production.up.railway.app/api/v1',
  BOT_USERNAME: 'IranCoinEarnBot',
  IRAN_TO_TON_RATE: 0.000002
};

const TG = window.Telegram?.WebApp;
const state = { user: null, page: 'home', prev: null, energy: 1000, maxEnergy: 1000 };

const TAP_BTN_IMG = 'https://i.postimg.cc/pT3Y09k9/iran-3d-map-miner-btn.jpg';

function money(n){
  return Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function toast(msg, type='ok'){
  document.querySelectorAll('.toast').forEach(t=>t.remove());
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.style.cssText = `position:fixed; top:20px; left:50%; transform:translateX(-50%); background:${type==='ok'?'#10b981':'#ef4444'}; color:white; padding:12px 24px; border-radius:30px; font-weight:bold; z-index:9999; font-size:14px; box-shadow:0 4px 15px rgba(0,0,0,0.5);`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(()=>t.remove(), 2500);
}

async function apiPost(path, body){
  const r = await fetch(CONFIG.API_URL + path, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})
  });
  return r.json();
}

async function apiGet(path){
  const r = await fetch(CONFIG.API_URL + path);
  return r.json();
}

async function init(){
  if (TG){ TG.ready(); TG.expand(); TG.setHeaderColor('#040911'); TG.setBackgroundColor('#040911'); }
  const tgUser = TG?.initDataUnsafe?.user;
  if (!tgUser){
    state.user = { telegram_id: 111111, first_name: 'User', username: 'demo', balance: 0 };
    return;
  }
  const payload = {
    initData: TG?.initData || '',
    user: { id: tgUser.id, username: tgUser.username || '', first_name: tgUser.first_name || 'User' }
  };
  try {
    const res = await apiPost('/user/init', payload);
    state.user = res?.user || { telegram_id: tgUser.id, balance: 0 };
  } catch (e) {
    state.user = { telegram_id: tgUser.id, balance: 0 };
  }
}

function openApp(page){
  document.getElementById('splash')?.classList.add('hidden');
  document.getElementById('app')?.classList.remove('hidden');
  navTo(page || 'home');
}

function navTo(page){
  state.prev = state.page;
  state.page = page;

  document.querySelectorAll('.nav-btn').forEach(btn=>{
    btn.classList.toggle('active', btn.dataset.page === page);
  });

  const b = document.getElementById('backBtn');
  if (b) b.classList.toggle('hidden', page === 'home');

  const root = document.getElementById('page');
  if (!root) return;
  root.innerHTML = '';

  if (page === 'home') renderHome(root);
  else if (page === 'ads') renderAds(root);
  else if (page === 'miner') renderMiner(root);
  else if (page === 'tasks') renderTasks(root);
  else if (page === 'wallet') renderWallet(root);
  else if (page === 'withdraw') renderWithdraw(root);
  else renderHome(root);
}

function goBack(){ navTo(state.prev || 'home'); }

function renderHome(root){
  const u = state.user || {};
  const ton = (Number(u.balance||0) * CONFIG.IRAN_TO_TON_RATE).toFixed(4);

  root.innerHTML = `
    <div class="card">
      <div class="row">
        <div>
          <div class="title">IRAN Coin</div>
          <div class="sub">Earn • Play • Withdraw 🇮🇷</div>
        </div>
        <div style="opacity:.8;font-weight:800;">${u.username ? '@'+u.username : ''}</div>
      </div>

      <div class="balance">
        <div class="coin-sm"><img src="${TAP_BTN_IMG}" style="border-radius:50%;" /></div>
        <div class="btxt">
          <div class="blabel">Your Balance</div>
          <div class="bamount">${money(u.balance)} <span>IRAN</span></div>
          <div class="bton">≈ ${ton} TON</div>
        </div>
      </div>

      <div class="grid">
        <div class="tile" onclick="navTo('miner')">
          <div class="tico">⛏</div><div class="tname">Tap Miner</div><div class="tsub">Tap & Earn</div>
        </div>
        <div class="tile" onclick="navTo('ads')">
          <div class="tico">▶</div><div class="tname">Watch Ads</div><div class="tsub">+5-20 IRAN</div>
        </div>
        <div class="tile" onclick="navTo('tasks')">
          <div class="tico">✓</div><div class="tname">Tasks</div><div class="tsub">+10-100 IRAN</div>
        </div>
        <div class="tile" onclick="claimStreak()">
          <div class="tico">🎁</div><div class="tname">Daily Bonus</div><div class="tsub">+10 IRAN</div>
        </div>
      </div>
    </div>

    <div class="card" style="text-align:center;">
      <div class="title">🎡 Daily Lucky Spin</div>
      <div class="sub" style="margin-bottom:15px;">Test your luck every 24 hours!</div>

      <div style="position: relative; width: 220px; height: 220px; margin: 0 auto;">
        <div style="position: absolute; top: -10px; left: 50%; transform: translateX(-50%); width: 0; height: 0; border-left: 10px solid transparent; border-right: 10px solid transparent; border-top: 20px solid #ef4444; z-index: 10;"></div>
        <canvas id="wheelCanvas" width="220" height="220" style="border-radius: 50%; transition: transform 4s cubic-bezier(0.15, 0.85, 0.35, 1.2); box-shadow: 0 0 20px rgba(0,0,0,0.5);"></canvas>
      </div>

      <button id="spinBtn" class="btn" onclick="spinWheel()" style="width:100%; margin-top:20px; padding:14px; font-size:16px;">Spin Now! 🎰</button>
    </div>
  `;

  setTimeout(() => { drawWheel(); }, 50);
}

function renderMiner(root){
  const u = state.user || {};
  root.innerHTML = `
    <div class="card" style="text-align:center; padding: 25px 20px;">
      <div class="title" style="font-size:22px;">⛏ Tap-Tap Miner</div>
      <div class="sub" style="margin-bottom:10px;">Tap the Iran map miner to earn IRAN!</div>

      <div class="bamount" id="minerBal" style="margin:15px 0; font-size:32px;">${money(u.balance)} <span>IRAN</span></div>

      <div class="tap-area">
        <div id="tapCoin" class="tap-miner-btn" onclick="handleTap(event)"></div>
      </div>

      <div style="margin-top:15px;">
        <div class="row">
          <span style="font-size:13px; color:#cbd5e1; font-weight:bold;">⚡ Energy</span>
          <span style="font-size:13px; font-weight:900; color:#f8fafc;" id="energyText">${state.energy} / ${state.maxEnergy}</span>
        </div>
        <div class="energy-bar">
          <div class="energy-fill" id="energyFill" style="width:${(state.energy/state.maxEnergy)*100}%;"></div>
        </div>
      </div>
    </div>
  `;
}

function handleTap(e){
  if (state.energy <= 0) {
    toast("Out of energy! Please wait for recharge.", "err");
    return;
  }
  state.energy -= 1;
  state.user.balance += 1;

  const balEl = document.getElementById('minerBal');
  if (balEl) balEl.innerHTML = `${money(state.user.balance)} <span>IRAN</span>`;
  
  const textEl = document.getElementById('energyText');
  if (textEl) textEl.innerText = `${state.energy} / ${state.maxEnergy}`;

  const fillEl = document.getElementById('energyFill');
  if (fillEl) fillEl.style.width = `${(state.energy/state.maxEnergy)*100}%`;

  const float = document.createElement('div');
  float.className = 'floating-num';
  float.innerText = '+1';
  float.style.left = `${e.clientX - 15}px`;
  float.style.top = `${e.clientY - 40}px`;
  document.body.appendChild(float);
  setTimeout(()=>float.remove(), 800);

  if (TG) TG.HapticFeedback?.impactOccurred('light');
}

setInterval(() => {
  if (state.energy < state.maxEnergy) {
    state.energy = Math.min(state.maxEnergy, state.energy + 2);
    const textEl = document.getElementById('energyText');
    if (textEl) textEl.innerText = `${state.energy} / ${state.maxEnergy}`;
    const fillEl = document.getElementById('energyFill');
    if (fillEl) fillEl.style.width = `${(state.energy/state.maxEnergy)*100}%`;
  }
}, 1000);

const rewards = ["10", "20", "50", "100", "200", "500"];
const colors = ["#f59e0b", "#3b82f6", "#10b981", "#8b5cf6", "#ec4899", "#ef4444"];
let currentRotation = 0;

function drawWheel() {
    const canvas = document.getElementById("wheelCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const slices = rewards.length;
    const sliceAngle = (2 * Math.PI) / slices;

    ctx.clearRect(0, 0, 220, 220);

    rewards.forEach((reward, i) => {
        const angle = i * sliceAngle;
        ctx.beginPath();
        ctx.fillStyle = colors[i];
        ctx.moveTo(110, 110);
        ctx.arc(110, 110, 105, angle, angle + sliceAngle);
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = "#040911";
        ctx.stroke();

        ctx.save();
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 14px Inter, sans-serif";
        ctx.translate(110 + Math.cos(angle + sliceAngle / 2) * 75, 110 + Math.sin(angle + sliceAngle / 2) * 75);
        ctx.rotate(angle + sliceAngle / 2 + Math.PI / 2);
        ctx.fillText(reward, -ctx.measureText(reward).width / 2, 0);
        ctx.restore();
    });
}

async function spinWheel() {
    const btn = document.getElementById("spinBtn");
    if (btn) { btn.disabled = true; btn.style.opacity = "0.6"; }

    try {
        const res = await apiPost(`/spin/${state.user?.telegram_id || "111111"}`, {});
        if (!res.success) {
            toast(res.detail || "Must wait 24 hours!", "err");
            if (btn) { btn.disabled = false; btn.style.opacity = "1"; }
            return;
        }

        const sliceAngle = 360 / rewards.length;
        const targetIndex = res.reward_index;
        const stopAngle = 360 - (targetIndex * sliceAngle) - (sliceAngle / 2) - 90;
        currentRotation += (360 * 5) + (stopAngle - (currentRotation % 360));
        
        const canvas = document.getElementById("wheelCanvas");
        if (canvas) canvas.style.transform = `rotate(${currentRotation}deg)`;

        setTimeout(() => {
            toast(`🎉 +${res.reward_amount} IRAN Won!`, "ok");
            if (state.user) state.user.balance = res.new_balance;
            navTo('home');
        }, 4200);
    } catch (err) {
        toast("Error spinning wheel", "err");
        if (btn) { btn.disabled = false; btn.style.opacity = "1"; }
    }
}

function renderTasks(root){
  root.innerHTML = `
    <div class="card" style="padding-bottom:30px;">
      <div class="title" style="margin-bottom:20px; font-size:20px;">📋 Tasks</div>
      <div id="taskBox">Loading...</div>
    </div>
  `;
  loadTasks();
}

async function loadTasks(){
  const box = document.getElementById('taskBox');
  if (!box) return;
  try {
    const data = await apiGet(`/tasks/${state.user?.telegram_id || "111111"}`);
    const tasks = data?.tasks || [];
    box.innerHTML = tasks.map(t => `
      <div class="list-item">
        <div class="list-item-left">
          <div class="list-icon c1">▶</div>
          <div>
            <div class="list-title">${t.title}</div>
            <div class="list-reward">+${t.reward} IRAN</div>
          </div>
        </div>
        <button class="btn" id="btn-task-${t.id}" ${t.completed?'disabled':''} onclick="doTask(${t.id}, '${t.task_url}')">
          ${t.completed?'Done':'Join'}
        </button>
      </div>
    `).join('');
  } catch(e) { box.innerText = "Error loading tasks."; }
}

async function doTask(taskId, url){
  const btn = document.getElementById(`btn-task-${taskId}`);
  if (btn && btn.innerText.trim() === "Join") {
    if (url) { if (TG && TG.openTelegramLink) TG.openTelegramLink(url); else window.open(url, '_blank'); }
    btn.innerText = "Check";
    btn.style.background = "#f59e0b";
    return;
  }
  btn.innerText = "...";
  const res = await apiPost('/tasks/complete', { telegram_id: state.user.telegram_id, task_id: taskId });
  if (res?.success) {
    state.user.balance = res.new_balance;
    toast(`🎉 +${res.reward} IRAN Claimed!`, 'ok');
    loadTasks();
  } else {
    toast(res?.message || 'Please join the channel first!', 'err');
    btn.innerText = "Check";
  }
}

function renderAds(root){
  const ADS = [ {id:1, title:'Watch Short Video', reward:20}, {id:2, title:'Discover New App', reward:20} ];
  root.innerHTML = `
    <div class="card" style="padding-bottom:30px;">
      <div class="title" style="margin-bottom:20px; font-size:20px;">📺 Watch Ads</div>
      ${ADS.map(a=>`
        <div class="list-item">
          <div class="list-item-left">
            <div class="list-icon c2">📽</div>
            <div>
              <div class="list-title">${a.title}</div>
              <div class="list-reward">+${a.reward} IRAN</div>
            </div>
          </div>
          <button class="btn" onclick="watchAd(${a.id})">Watch</button>
        </div>
      `).join('')}
    </div>
  `;
}

async function watchAd(adId){
  const res = await apiPost('/ads/watch', { telegram_id: state.user.telegram_id, ad_id: adId });
  if (res?.success){
    state.user.balance = res.new_balance;
    toast(`+${res.reward} IRAN Earned!`, 'ok');
  }
}

function renderWallet(root){
  const u = state.user || {};
  root.innerHTML = `
    <div class="card" style="text-align:center; padding:30px 20px;">
      <div class="title" style="font-size:20px; margin-bottom:20px;">Wallet</div>
      <div class="bamount" style="font-size:36px; margin-bottom:10px;">${money(u.balance)} <span>IRAN</span></div>
      <button class="btn" style="width:100%; font-size:16px; padding:16px; margin-top:20px;" onclick="navTo('withdraw')">🚀 Withdraw to TON</button>
    </div>
  `;
}

function renderWithdraw(root){
  root.innerHTML = `
    <div class="card">
      <div class="title" style="margin-bottom:20px;">Withdraw to TON Wallet</div>
      <div style="font-size:13px; color:#94a3b8; margin-bottom:8px;">TON Wallet Address</div>
      <input id="tonAddr" style="width:100%; padding:14px; margin-bottom:20px; border-radius:12px; border:1px solid #1e293b; background:#040911; color:white; font-size:14px;" placeholder="UQ..." />
      <div style="font-size:13px; color:#94a3b8; margin-bottom:8px;">Amount (Min: 10,000 IRAN)</div>
      <input id="wdAmount" type="number" style="width:100%; padding:14px; margin-bottom:20px; border-radius:12px; border:1px solid #1e293b; background:#040911; color:white; font-size:14px;" placeholder="10000" />
      <button class="btn" style="width:100%; padding:14px; font-size:16px;" onclick="requestWithdraw()">Request Withdrawal</button>
    </div>
  `;
}

async function requestWithdraw(){
  const addr = document.getElementById('tonAddr')?.value?.trim();
  const amount = Number(document.getElementById('wdAmount')?.value || 0);
  if (!addr) return toast('Please enter TON wallet address', 'err');
  if (amount < 10000) return toast('Minimum withdrawal is 10,000 IRAN', 'err');
  const res = await apiPost('/withdraw/request', { telegram_id: state.user.telegram_id, amount, ton_address: addr });
  if (res?.success){
    state.user.balance = res.new_balance;
    toast('Withdrawal requested successfully!', 'ok');
    navTo('wallet');
  } else { toast(res?.message || 'Withdrawal failed', 'err'); }
}

async function claimStreak(){
  const res = await apiPost(`/streak/claim/${state.user?.telegram_id || "111111"}`, {});
  if (res?.success) {
    toast(`🎉 +${res.reward} IRAN Bonus Claimed!`, 'ok');
    state.user.balance = res.new_balance;
    navTo('home');
  } else { toast(res?.message || 'Daily reward already claimed today.', 'err'); }
}

function shareReferral(){
  const link = `https://t.me/${CONFIG.BOT_USERNAME}?start=ref_${state.user?.telegram_id}`;
  const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent("🚀 Play IRAN Coin Mini App & Earn Rewards!")}`;
  if (TG?.openTelegramLink) TG.openTelegramLink(shareUrl);
  else window.open(shareUrl, '_blank');
}

window.openApp = openApp;
window.navTo = navTo;
window.goBack = goBack;
window.watchAd = watchAd;
window.doTask = doTask;
window.requestWithdraw = requestWithdraw;
window.spinWheel = spinWheel;
window.shareReferral = shareReferral;
window.claimStreak = claimStreak;
window.handleTap = handleTap;

window.addEventListener('DOMContentLoaded', async ()=>{ await init(); });
