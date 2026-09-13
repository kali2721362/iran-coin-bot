'use strict';

const CONFIG = {
    API_URL: 'https://yourdomain.up.railway.app/api/v1',
    BOT_USERNAME: 'IranCoinEarnBot',
    IRAN_TO_TON: 0.000002,
    MIN_WITHDRAW: 500,
    WITHDRAW_FEE: 0.05,
    MAX_ADS_DAY: 10
};

const S = {
    user: null,
    page: 'home',
    prevPage: null,
    cdInterval: null
};

const TG = window.Telegram?.WebApp;
if (TG) {
    TG.ready();
    TG.expand();
    TG.setHeaderColor('#141414');
    TG.setBackgroundColor('#0d0d0d');
}

const completedTaskIds = new Set();

async function init() {
    const tgUser = TG?.initDataUnsafe?.user;
    if (tgUser) {
        try {
            const res = await apiFetch('/user/init', 'POST', {
                initData: TG.initData || '',
                user: {
                    id: tgUser.id,
                    username: tgUser.username || '',
                    first_name: tgUser.first_name || 'User',
                    last_name: tgUser.last_name || ''
                }
            });
            if (res?.success) S.user = res.user;
        } catch (e) {
            console.warn('API not available, using demo mode');
        }
    }

    if (!S.user) {
        S.user = {
            id: 1,
            telegram_id: 123456789,
            username: 'User12345',
            first_name: 'User',
            balance: 1250,
            total_earned: 1250,
            referral_code: 'IRC75514',
            referral_count: 5,
            referral_earnings: 250,
            ton_wallet: null,
            total_ads_watched: 25,
            ads_watched_today: 2
        };
    }
}

function showApp(page) {
    document.getElementById('splash-screen').style.display = 'none';
    const app = document.getElementById('main-app');
    app.style.display = 'flex';
    app.style.flexDirection = 'column';
    app.style.minHeight = '100vh';
    navigate(page || 'home');
}

async function apiFetch(path, method, body) {
    method = method || 'GET';
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const r = await fetch(CONFIG.API_URL + path, opts);
    return r.json();
}

function navigate(page, isBack) {
    if (!isBack) S.prevPage = S.page;
    S.page = page;

    if (S.cdInterval) {
        clearInterval(S.cdInterval);
        S.cdInterval = null;
    }

    document.querySelectorAll('.bnav-btn').forEach(function(b) {
        b.classList.toggle('active', b.dataset.page === page);
    });

    const backBtn = document.getElementById('back-btn');
    if (backBtn) {
        backBtn.style.display = ['withdraw', 'tx-history'].includes(page) ? 'block' : 'none';
    }

    const content = document.getElementById('page-content');
    content.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'page-slide';

    if (page === 'home') renderHome(wrap);
    else if (page === 'ads') renderAds(wrap);
    else if (page === 'tasks') renderTasks(wrap);
    else if (page === 'wallet') renderWallet(wrap);
    else if (page === 'withdraw') renderWithdraw(wrap);
    else if (page === 'referral') renderReferral(wrap);
    else if (page === 'more') renderMore(wrap);
    else if (page === 'tx-history') renderTxHistory(wrap);
    else renderHome(wrap);

    content.appendChild(wrap);
}

function goBack() {
    navigate(S.prevPage || 'wallet', true);
}

function renderHome(c) {
    const u = S.user;
    const ton = ((u.balance || 0) * CONFIG.IRAN_TO_TON).toFixed(4);

    c.innerHTML =
        '<div class="home-page">' +
            '<div class="home-profile-row">' +
                '<div class="home-avatar">' +
                    '<div class="av-flag">' +
                        '<div class="avf-g"></div>' +
                        '<div class="avf-w">الله</div>' +
                        '<div class="avf-r"></div>' +
                    '</div>' +
                '</div>' +
                '<div class="home-user-info">' +
                    '<div class="home-user-name">' + (u.first_name || 'User') + '</div>' +
                    '<div class="home-user-sub">Together for a better future 🇮🇷</div>' +
                '</div>' +
            '</div>' +

            '<div class="balance-card">' +
                '<div class="balance-top">' +
                    '<div class="balance-coin-icon">' +
                        '<div class="bci-inner">' +
                            '<div class="s-g"></div>' +
                            '<div class="s-w">الله</div>' +
                            '<div class="s-r"></div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="balance-text">' +
                        '<div class="balance-label">Your Balance</div>' +
                        '<div class="balance-amount">' + fmtNum(u.balance) + ' <span>IRAN</span></div>' +
                        '<div class="balance-ton">≈ <b>' + ton + ' TON</b></div>' +
                    '</div>' +
                '</div>' +
                '<div class="balance-coin-label">IRAN</div>' +
            '</div>' +

            '<div class="quick-grid">' +
                '<button class="quick-card" onclick="navigate(\'ads\')">' +
                    '<div class="qc-icon green">▶</div>' +
                    '<div class="qc-title">Watch Ads</div>' +
                    '<div class="qc-reward">+5–20 IRAN</div>' +
                '</button>' +
                '<button class="quick-card" onclick="navigate(\'tasks\')">' +
                    '<div class="qc-icon gold">✓</div>' +
                    '<div class="qc-title">Tasks</div>' +
                    '<div class="qc-reward">+10–100 IRAN</div>' +
                '</button>' +
                '<button class="quick-card" onclick="navigate(\'referral\')">' +
                    '<div class="qc-icon blue">👥</div>' +
                    '<div class="qc-title">Invite Friends</div>' +
                    '<div class="qc-reward">+50 IRAN</div>' +
                '</button>' +
                '<button class="quick-card" onclick="navigate(\'more\')">' +
                    '<div class="qc-icon purple">🎁</div>' +
                    '<div class="qc-title">Daily Bonus</div>' +
                    '<div class="qc-reward">+10 IRAN</div>' +
                '</button>' +
            '</div>' +

            '<div class="more-ways-banner" onclick="navigate(\'tasks\')">' +
                '<div class="mwb-flag">' +
                    '<div class="mf-g"></div>' +
                    '<div class="mf-w"></div>' +
                    '<div class="mf-r"></div>' +
                '</div>' +
                '<div class="mwb-text">' +
                    '<div class="mwb-title">More ways to earn!</div>' +
                    '<div class="mwb-sub">Complete tasks, invite friends and get more IRAN coins.</div>' +
                '</div>' +
                '<span class="mwb-arrow">›</span>' +
            '</div>' +

            '<div class="tx-section">' +
                '<div class="tx-section-header">' +
                    '<span class="tx-section-title">Recent Transactions</span>' +
                    '<button class="view-all-btn" onclick="navigate(\'tx-history\')">View All</button>' +
                '</div>' +
                '<div class="tx-list" id="home-tx-list">' +
                    '<div class="spinner"></div>' +
                '</div>' +
            '</div>' +
        '</div>';

    loadHomeTx();
}

async function loadHomeTx() {
    const el = document.getElementById('home-tx-list');
    if (!el) return;

    try {
        const data = await apiFetch('/user/' + S.user.telegram_id + '/transactions');
        if (data && data.transactions && data.transactions.length > 0) {
            el.innerHTML = data.transactions.slice(0, 3).map(txHtml).join('');
            return;
        }
    } catch (e) {}

    el.innerHTML = demoTxHtml();
}

function demoTxHtml() {
    const items = [
        { icon: '▶', cls: 'earn', title: 'Watch Ad', time: '2 min ago', amount: '+50 IRAN', pos: true },
        { icon: '✓', cls: 'earn', title: 'Task Reward', time: '12 min ago', amount: '+150 IRAN', pos: true },
        { icon: '👥', cls: 'earn', title: 'Referral Bonus', time: '1 hour ago', amount: '+50 IRAN', pos: true }
    ];
    return items.map(function(tx) {
        return '<div class="tx-item">' +
            '<div class="tx-icon-wrap ' + tx.cls + '">' + tx.icon + '</div>' +
            '<div class="tx-info">' +
                '<div class="tx-title">' + tx.title + '</div>' +
                '<div class="tx-time">' + tx.time + '</div>' +
            '</div>' +
            '<div class="tx-amounts">' +
                '<div class="tx-iran ' + (tx.pos ? 'pos' : 'neg') + '">' + tx.amount + '</div>' +
                '<div class="tx-time-right">' + tx.time + '</div>' +
            '</div>' +
        '</div>';
    }).join('');
}

function txHtml(tx) {
    const icons = { earn_ad: '▶', earn_task: '✓', earn_referral: '👥', withdraw: '↑', bonus: '🎁' };
    const icon = icons[tx.type] || '💰';
    const cls = tx.amount > 0 ? 'earn' : 'spend';
    const pos = tx.amount > 0;
    const amt = (pos ? '+' : '') + fmtNum(Math.abs(tx.amount)) + ' IRAN';
    const t = fmtDate(tx.created_at);
    return '<div class="tx-item">' +
        '<div class="tx-icon-wrap ' + cls + '">' + icon + '</div>' +
        '<div class="tx-info">' +
            '<div class="tx-title">' + (tx.description || tx.type) + '</div>' +
            '<div class="tx-time">' + t + '</div>' +
        '</div>' +
        '<div class="tx-amounts">' +
            '<div class="tx-iran ' + (pos ? 'pos' : 'neg') + '">' + amt + '</div>' +
            '<div class="tx-time-right">' + t + '</div>' +
        '</div>' +
    '</div>';
}

const ADS_DATA = [
    { id: 1, icon: '📢', cls: 'c1', title: 'Crypto News', reward: 15, duration: 5 },
    { id: 2, icon: '🏛', cls: 'c2', title: 'Iranian Culture', reward: 20, duration: 5 },
    { id: 3, icon: '🌐', cls: 'c3', title: 'Web3 Projects', reward: 25, duration: 5 },
    { id: 4, icon: '🤖', cls: 'c4', title: 'Technology & AI', reward: 20, duration: 5 },
    { id: 5, icon: '✈️', cls: 'c5', title: 'Lifestyle & Travel', reward: 15, duration: 5 }
];

function renderAds(c) {
    const u = S.user;
    const watched = u.ads_watched_today || 0;
    const pct = (watched / CONFIG.MAX_ADS_DAY) * 100;

    const adItems = ADS_DATA.map(function(ad) {
        return '<div class="ad-item">' +
            '<div class="ad-thumb ' + ad.cls + '">' + ad.icon + '</div>' +
            '<div class="ad-info">' +
                '<div class="ad-title">' + ad.title + '</div>' +
                '<div class="ad-meta">' +
                    '<span class="ad-reward">+' + ad.reward + ' IRAN</span>' +
                    '<span class="ad-duration">⏱ ' + ad.duration + ' sec</span>' +
                '</div>' +
            '</div>' +
            '<button class="watch-btn" id="watch-btn-' + ad.id + '" onclick="watchAd(' + ad.id + ',' + ad.reward + ',' + ad.duration + ')">' +
                'Watch' +
            '</button>' +
        '</div>';
    }).join('');

    c.innerHTML =
        '<div class="ads-page">' +
            '<div class="page-header-card">' +
                '<div class="phc-icon green-bg" style="font-size:28px">▶</div>' +
                '<div class="phc-info">' +
                    '<div class="phc-title">Watch Ads</div>' +
                    '<div class="phc-sub">Watch short ads and earn IRAN coins</div>' +
                '</div>' +
            '</div>' +
            '<div class="ad-list">' + adItems + '</div>' +
            '<div class="daily-bonus-bar">' +
                '<div class="dbb-top">' +
                    '<span class="dbb-icon">🎁</span>' +
                    '<span class="dbb-text">Watch ads daily and get bonus!</span>' +
                    '<span class="dbb-count" id="dbb-count">' + watched + '/' + CONFIG.MAX_ADS_DAY + '</span>' +
                '</div>' +
                '<div class="dbb-bar">' +
                    '<div class="dbb-fill" id="dbb-fill" style="width:' + pct + '%"></div>' +
                '</div>' +
            '</div>' +
        '</div>';
}

async function watchAd(adId, reward, duration) {
    const btn = document.getElementById('watch-btn-' + adId);
    if (!btn || btn.classList.contains('disabled')) return;

    if ((S.user.ads_watched_today || 0) >= CONFIG.MAX_ADS_DAY) {
        showToast('Daily limit reached! Come back tomorrow.', 'warning');
        return;
    }

    btn.classList.add('disabled');
    let sec = duration;
    btn.textContent = sec + 's';

    const t = setInterval(function() {
        sec--;
        if (btn) btn.textContent = sec > 0 ? sec + 's' : '...';
        if (sec <= 0) clearInterval(t);
    }, 1000);

    await sleep(duration * 1000);
    clearInterval(t);

    try {
        const res = await apiFetch('/ads/watch', 'POST', { telegram_id: S.user.telegram_id, ad_id: adId });
        if (res && res.success) {
            S.user.balance = res.new_balance;
            S.user.ads_watched_today = res.ads_watched_today;
        } else {
            throw new Error('api error');
        }
    } catch (e) {
        S.user.balance = (S.user.balance || 0) + reward;
        S.user.ads_watched_today = (S.user.ads_watched_today || 0) + 1;
    }

    S.user.total_ads_watched = (S.user.total_ads_watched || 0) + 1;
    showToast('🎉 +' + reward + ' IRAN earned!', 'success');
    if (TG && TG.HapticFeedback) TG.HapticFeedback.notificationOccurred('success');

    if (btn) {
        btn.textContent = '✓ Done';
        btn.style.background = '#2a2a2a';
        btn.style.color = '#666';
    }

    const cnt = document.getElementById('dbb-count');
    const fill = document.getElementById('dbb-fill');
    const w = S.user.ads_watched_today;
    if (cnt) cnt.textContent = w + '/' + CONFIG.MAX_ADS_DAY;
    if (fill) fill.style.width = (w / CONFIG.MAX_ADS_DAY * 100) + '%';
}

const TASKS_DATA = [
    { id: 1, icon: '✈️', cls: 'tg', title: 'Join our Telegram channel', reward: 50, url: 'https://t.me/IranCoinChannel' },
    { id: 2, icon: '✕', cls: 'tw', title: 'Follow on X (Twitter)', reward: 50, url: 'https://twitter.com/IranCoin' },
    { id: 3, icon: '▶', cls: 'yt', title: 'Subscribe to YouTube', reward: 75, url: 'https://youtube.com/@IranCoin' },
    { id: 4, icon: '◆', cls: 'dc', title: 'Join Discord', reward: 50, url: 'https://discord.gg/IranCoin' },
    { id: 5, icon: '📋', cls: 'sv', title: 'Complete Survey', reward: 100, url: 'https://irancoin.io/survey' }
];

function renderTasks(c) {
    c.innerHTML =
        '<div class="tasks-page">' +
            '<div class="page-header-card">' +
                '<div class="phc-icon gold-bg" style="font-size:28px">✓</div>' +
                '<div class="phc-info">' +
                    '<div class="phc-title">Tasks</div>' +
                    '<div class="phc-sub">Complete simple tasks and earn IRAN</div>' +
                '</div>' +
            '</div>' +
            '<div class="task-list" id="task-list">' + buildTaskList() + '</div>' +
            '<div class="more-tasks-card">' +
                '<div class="mtc-icon">🔔</div>' +
                '<div class="mtc-title">More tasks coming soon!</div>' +
                '<div style="font-size:12px;color:var(--text3);margin-top:4px">Follow our channel for updates.</div>' +
            '</div>' +
        '</div>';
}

function buildTaskList() {
    return TASKS_DATA.map(function(t) {
        const done = completedTaskIds.has(t.id);
        return '<div class="task-item ' + (done ? 'completed' : '') + '" id="task-item-' + t.id + '">' +
            '<div class="task-thumb ' + t.cls + '">' + t.icon + '</div>' +
            '<div class="task-info">' +
                '<div class="task-title">' + t.title + '</div>' +
                '<div class="task-reward">✦ +' + t.reward + ' IRAN</div>' +
            '</div>' +
            '<button class="start-task-btn ' + (done ? 'done-btn' : '') + '" ' +
                'id="task-btn-' + t.id + '" ' +
                (done ? 'disabled' : 'onclick="doTask(' + t.id + ')"') + '>' +
                (done ? '✓ Done' : 'Start') +
            '</button>' +
        '</div>';
    }).join('');
}

async function doTask(taskId) {
    const task = TASKS_DATA.find(function(t) { return t.id === taskId; });
    if (!task) return;

    const btn = document.getElementById('task-btn-' + taskId);
    if (btn) { btn.textContent = '...'; btn.disabled = true; }

    if (task.url) {
        if (TG && TG.openTelegramLink) TG.openTelegramLink(task.url);
        else window.open(task.url, '_blank');
    }

    await sleep(3000);

    try {
        const res = await apiFetch('/tasks/complete', 'POST', {
            telegram_id: S.user.telegram_id,
            task_id: taskId
        });
        if (res && res.success) {
            S.user.balance = res.new_balance;
            completedTaskIds.add(taskId);
            showToast('🎉 +' + task.reward + ' IRAN earned!', 'success');
            if (TG && TG.HapticFeedback) TG.HapticFeedback.notificationOccurred('success');
        } else {
            completedTaskIds.add(taskId);
            S.user.balance = (S.user.balance || 0) + task.reward;
            showToast('🎉 +' + task.reward + ' IRAN earned!', 'success');
        }
    } catch (e) {
        completedTaskIds.add(taskId);
        S.user.balance = (S.user.balance || 0) + task.reward;
        showToast('🎉 +' + task.reward + ' IRAN earned!', 'success');
    }

    const list = document.getElementById('task-list');
    if (list) list.innerHTML = buildTaskList();
}

function renderWallet(c) {
    const u = S.user;
    const ton = ((u.balance || 0) * CONFIG.IRAN_TO_TON).toFixed(4);

    c.innerHTML =
        '<div class="wallet-page">' +
            '<div class="page-header-card">' +
                '<div class="phc-icon gold-bg" style="font-size:28px">👛</div>' +
                '<div class="phc-info">' +
                    '<div class="phc-title">Wallet</div>' +
                    '<div class="phc-sub">Your IRAN coin balance and transactions</div>' +
                '</div>' +
            '</div>' +
            '<div class="wallet-balance-card">' +
                '<div class="wbc-coin">' +
                    '<div class="wbc-coin-inner">' +
                        '<div class="cs-g"></div>' +
                        '<div class="cs-w">الله</div>' +
                        '<div class="cs-r"></div>' +
                    '</div>' +
                '</div>' +
                '<div class="wbc-label">IRAN</div>' +
                '<div class="wbc-amount">' + fmtNum(u.balance) + ' <span class="wba-unit">IRAN</span></div>' +
                '<div class="wbc-ton">◎ ' + ton + ' TON</div>' +
            '</div>' +
            '<div class="wallet-actions">' +
                '<button class="withdraw-main-btn" onclick="navigate(\'withdraw\')">🚀 Withdraw</button>' +
                '<button class="tx-history-btn" onclick="navigate(\'tx-history\')">⏱ Transaction History</button>' +
            '</div>' +
            '<div class="tx-section">' +
                '<div class="tx-section-header">' +
                    '<span class="tx-section-title">Recent Transactions</span>' +
                    '<button class="view-all-btn" onclick="navigate(\'tx-history\')">View All</button>' +
                '</div>' +
                '<div class="tx-list" id="wallet-tx-list"><div class="spinner"></div></div>' +
            '</div>' +
        '</div>';

    loadWalletTx();
}

async function loadWalletTx() {
    const el = document.getElementById('wallet-tx-list');
    if (!el) return;
    try {
        const data = await apiFetch('/user/' + S.user.telegram_id + '/transactions');
        if (data && data.transactions && data.transactions.length > 0) {
            el.innerHTML = data.transactions.slice(0, 5).map(txHtml).join('');
            return;
        }
    } catch (e) {}
    el.innerHTML = demoTxHtml();
}

function renderTxHistory(c) {
    c.innerHTML =
        '<div class="wallet-page">' +
            '<div class="tx-section">' +
                '<div class="tx-section-header">' +
                    '<span class="tx-section-title">All Transactions</span>' +
                '</div>' +
                '<div class="tx-list" id="all-tx-list"><div class="spinner"></div></div>' +
            '</div>' +
        '</div>';
    loadAllTx();
}

async function loadAllTx() {
    const el = document.getElementById('all-tx-list');
    if (!el) return;
    try {
        const data = await apiFetch('/user/' + S.user.telegram_id + '/transactions');
        if (data && data.transactions && data.transactions.length > 0) {
            el.innerHTML = data.transactions.map(txHtml).join('');
            return;
        }
    } catch (e) {}
    el.innerHTML = '<div class="empty-state">No transactions yet 🌱</div>';
}

function renderWithdraw(c) {
    const u = S.user;
    const ton = ((u.balance || 0) * CONFIG.IRAN_TO_TON).toFixed(4);
    const minTon = (CONFIG.MIN_WITHDRAW * CONFIG.IRAN_TO_TON).toFixed(3);

    c.innerHTML =
        '<div class="withdraw-page">' +
            '<div class="page-header-card">' +
                '<div class="phc-icon green-bg" style="font-size:28px">↑</div>' +
                '<div class="phc-info">' +
                    '<div class="phc-title">Withdraw</div>' +
                    '<div class="phc-sub">Transfer your IRAN coins to TON wallet</div>' +
                '</div>' +
            '</div>' +
            '<div class="wd-balance-card">' +
                '<div class="wd-coin">' +
                    '<div class="wd-coin-inner">' +
                        '<div class="wci-g"></div>' +
                        '<div class="wci-w">الله</div>' +
                        '<div class="wci-r"></div>' +
                    '</div>' +
                '</div>' +
                '<div class="wd-label">Your Balance</div>' +
                '<div class="wd-amount">' + fmtNum(u.balance) + ' <span class="wda-unit">IRAN</span></div>' +
                '<div class="wd-ton">≈ ' + ton + ' TON</div>' +
            '</div>' +
            '<div class="wd-form">' +
                '<div class="wd-min-info">' +
                    '<div>' +
                        '<div class="wd-min-label">Minimum withdrawal</div>' +
                        '<div class="wd-min-ton">= ' + minTon + ' TON</div>' +
                    '</div>' +
                    '<div class="wd-min-value">' + CONFIG.MIN_WITHDRAW + '.00 IRAN</div>' +
                '</div>' +
                '<div>' +
                    '<label class="form-label">Withdraw to TON Wallet</label>' +
                    '<div class="ton-input-wrap">' +
                        '<input type="text" id="wd-address" class="ton-input" ' +
                            'placeholder="Enter your TON wallet address" ' +
                            'value="' + (u.ton_wallet || '') + '">' +
                        '<button class="paste-btn" onclick="pasteAddr()">📋</button>' +
                    '</div>' +
                '</div>' +
                '<div>' +
                    '<label class="form-label">Amount (IRAN)</label>' +
                    '<div class="ton-input-wrap">' +
                        '<input type="number" id="wd-amount" class="ton-input" ' +
                            'placeholder="Min ' + CONFIG.MIN_WITHDRAW + '" ' +
                            'min="' + CONFIG.MIN_WITHDRAW + '" ' +
                            'oninput="updateWdPreview()">' +
                    '</div>' +
                '</div>' +
                '<div id="wd-preview" style="display:none;background:var(--bg3);border-radius:10px;padding:13px;font-size:12px;color:var(--text2);line-height:2.2"></div>' +
                '<div class="network-row">' +
                    '<div class="network-icon">T</div>' +
                    '<span class="network-name">TON (The Open Network)</span>' +
                    '<span class="network-arrow">›</span>' +
                '</div>' +
                '<button class="request-wd-btn" id="wd-btn" onclick="requestWithdraw()">Request Withdrawal</button>' +
            '</div>' +
        '</div>';
}

function updateWdPreview() {
    const amount = parseFloat(document.getElementById('wd-amount').value || 0);
    const preview = document.getElementById('wd-preview');
    if (!preview) return;

    if (amount >= CONFIG.MIN_WITHDRAW) {
        const fee = amount * CONFIG.WITHDRAW_FEE;
        const net = amount - fee;
        const ton = (net * CONFIG.IRAN_TO_TON).toFixed(6);
        preview.style.display = 'block';
        preview.innerHTML =
            'Amount: <b style="color:#fff">' + fmtNum(amount) + ' IRAN</b><br>' +
            'Fee (' + (CONFIG.WITHDRAW_FEE * 100) + '%): <b style="color:#ef4444">-' + fmtNum(fee) + ' IRAN</b><br>' +
            'You receive: <b style="color:var(--green)">' + fmtNum(net) + ' IRAN = ' + ton + ' TON</b>';
    } else {
        preview.style.display = 'none';
    }
}

async function pasteAddr() {
    try {
        const text = await navigator.clipboard.readText();
        const el = document.getElementById('wd-address');
        if (el) el.value = text;
    } catch (e) {}
}

async function requestWithdraw() {
    const address = (document.getElementById('wd-address').value || '').trim();
    const amount = parseFloat(document.getElementById('wd-amount').value || 0);
    const btn = document.getElementById('wd-btn');

    if (!address) { showToast('Enter your TON wallet address', 'warning'); return; }
    if (amount < CONFIG.MIN_WITHDRAW) { showToast('Minimum ' + CONFIG.MIN_WITHDRAW + ' IRAN', 'warning'); return; }
    if ((S.user.balance || 0) < amount) { showToast('Insufficient balance', 'error'); return; }

    if (btn) { btn.textContent = '⏳ Processing...'; btn.disabled = true; }

    try {
        const res = await apiFetch('/withdraw/request', 'POST', {
            telegram_id: S.user.telegram_id,
            amount: amount,
            ton_address: address
        });

        if (res && res.success) {
            S.user.balance = res.new_balance;
            showToast('✅ ' + (res.ton_amount || 0).toFixed(4) + ' TON sent!', 'success');
            if (TG && TG.HapticFeedback) TG.HapticFeedback.notificationOccurred('success');
            setTimeout(function() { navigate('wallet'); }, 1500);
        } else {
            showToast((res && res.message) || 'Withdrawal failed', 'error');
            if (btn) { btn.textContent = 'Request Withdrawal'; btn.disabled = false; }
        }
    } catch (e) {
        showToast('Server error. Try again later.', 'error');
        if (btn) { btn.textContent = 'Request Withdrawal'; btn.disabled = false; }
    }
}

function renderReferral(c) {
    const u = S.user;
    const link = 'https://t.me/' + CONFIG.BOT_USERNAME + '?start=' + u.referral_code;

    c.innerHTML =
        '<div class="referral-page">' +
            '<div class="page-header-card">' +
                '<div class="phc-icon blue-bg" style="font-size:28px">👥</div>' +
                '<div class="phc-info">' +
                    '<div class="phc-title">Invite Friends</div>' +
                    '<div class="phc-sub">Get more IRAN by inviting your friends</div>' +
                '</div>' +
            '</div>' +
            '<div class="referral-hero">' +
                '<div class="ref-hero-icon">👥🇮🇷</div>' +
                '<div class="ref-hero-title">Invite & Earn</div>' +
                '<div class="ref-hero-sub">Share your link and earn for every friend who joins</div>' +
            '</div>' +
            '<div class="ref-link-box">' +
                '<div class="ref-link-label">Your referral link</div>' +
                '<div class="ref-link-input-row">' +
                    '<span class="ref-link-text" id="ref-link-txt">' + link + '</span>' +
                    '<button class="copy-icon-btn" onclick="copyRef()">📋</button>' +
                '</div>' +
            '</div>' +
            '<div class="ref-rewards">' +
                '<div class="ref-reward-card">' +
                    '<span class="rrc-icon">🏆</span>' +
                    '<div>' +
                        '<div class="rrc-amount">+ 50 IRAN</div>' +
                        '<div class="rrc-label">Invite reward</div>' +
                    '</div>' +
                '</div>' +
                '<div class="ref-reward-card">' +
                    '<span class="rrc-icon">🎁</span>' +
                    '<div>' +
                        '<div class="rrc-amount">+ 25 IRAN</div>' +
                        '<div class="rrc-label">Friend\'s reward</div>' +
                    '</div>' +
                '</div>' +
            '</div>' +
            '<div class="referrals-section">' +
                '<div class="rs-header">' +
                    '<span class="rs-icon">👥</span>' +
                    '<span class="rs-title">Your Referrals</span>' +
                    '<span class="rs-count">' + (u.referral_count || 0) + '</span>' +
                '</div>' +
                '<div>' +
                    ((u.referral_count || 0) > 0
                        ? '<div class="empty-state" style="color:var(--green)">✅ ' + u.referral_count + ' friends joined!</div>'
                        : '<div class="empty-state">No referrals yet.<br>Share your link to start earning! 🚀</div>') +
                '</div>' +
            '</div>' +
        '</div>';
}

async function copyRef() {
    const el = document.getElementById('ref-link-txt');
    const link = el ? el.textContent : '';
    try {
        await navigator.clipboard.writeText(link);
    } catch (e) {
        if (el) {
            const range = document.createRange();
            range.selectNode(el);
            window.getSelection().removeAllRanges();
            window.getSelection().addRange(range);
        }
    }
    showToast('✅ Link copied!', 'success');
    if (TG && TG.HapticFeedback) TG.HapticFeedback.impactOccurred('light');
}

function renderMore(c) {
    const u = S.user;

    c.innerHTML =
        '<div class="more-page">' +
            '<div class="page-header-card">' +
                '<div class="phc-icon purple-bg" style="font-size:28px">⚙️</div>' +
                '<div class="phc-info">' +
                    '<div class="phc-title">Profile & Settings</div>' +
                    '<div class="phc-sub">Manage your account</div>' +
                '</div>' +
            '</div>' +
            '<div class="profile-card">' +
                '<div class="profile-avatar">' +
                    '<div class="pav-flag">' +
                        '<div class="pg"></div>' +
                        '<div class="pw">الله</div>' +
                        '<div class="pr"></div>' +
                    '</div>' +
                '</div>' +
                '<div>' +
                    '<div class="profile-name">' + (u.first_name || 'User') + '</div>' +
                    '<div class="verified-badge">✔ Verified</div>' +
                '</div>' +
            '</div>' +
            '<div class="settings-section">' +
                '<div class="settings-item">' +
                    '<div class="si-icon">👤</div>' +
                    '<span class="si-label">Account Settings</span>' +
                    '<span class="si-arrow">›</span>' +
                '</div>' +
                '<div class="settings-item">' +
                    '<div class="si-icon">🔔</div>' +
                    '<span class="si-label">Notifications</span>' +
                    '<div class="si-toggle" onclick="this.classList.toggle(\'off\')"></div>' +
                '</div>' +
                '<div class="settings-item">' +
                    '<div class="si-icon">🌐</div>' +
                    '<span class="si-label">Language</span>' +
                    '<span class="si-value">English</span>' +
                    '<span class="si-arrow">›</span>' +
                '</div>' +
                '<div class="settings-item">' +
                    '<div class="si-icon">❓</div>' +
                    '<span class="si-label">Help & Support</span>' +
                    '<span class="si-arrow">›</span>' +
                '</div>' +
                '<div class="settings-item">' +
                    '<div class="si-icon">ℹ️</div>' +
                    '<span class="si-label">About IRAN Coin</span>' +
                    '<span class="si-arrow">›</span>' +
                '</div>' +
            '</div>' +
            '<div class="brand-footer">' +
                '<div class="bf-logo">' +
                    '<div class="bfl-flag">' +
                        '<div class="bg"></div>' +
                        '<div class="bw"></div>' +
                        '<div class="br"></div>' +
                    '</div>' +
                '</div>' +
                '<div>' +
                    '<div class="bf-title">IRAN Coin</div>' +
                    '<div class="bf-sub">Together for a better future 🇮🇷</div>' +
                '</div>' +
            '</div>' +
        '</div>';
}

function fmtNum(n) {
    if (!n && n !== 0) return '0.00';
    return parseFloat(n).toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function fmtDate(d) {
    if (!d) return '';
    try {
        const dt = new Date(d);
        const diff = Date.now() - dt.getTime();
        const m = Math.floor(diff / 60000);
        if (m < 1) return 'just now';
        if (m < 60) return m + ' min ago';
        const h = Math.floor(m / 60);
        if (h < 24) return h + ' hour' + (h > 1 ? 's' : '') + ' ago';
        return dt.toLocaleDateString();
    } catch (e) { return ''; }
}

function sleep(ms) {
    return new Promise(function(r) { setTimeout(r, ms); });
}

function showToast(msg, type) {
    type = type || 'info';
    document.querySelectorAll('.toast').forEach(function(t) { t.remove(); });
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    document.body.appendChild(el);
    requestAnimationFrame(function() { el.classList.add('show'); });
    setTimeout(function() {
        el.classList.remove('show');
        setTimeout(function() { el.remove(); }, 350);
    }, 3000);
}

window.addEventListener('DOMContentLoaded', init);