'use strict';
const $ = id => document.getElementById(id);
const api = () => window.pywebview.api;
const pick = a => a[Math.floor(Math.random() * a.length)];
function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
}

const S = {
    cur: null, hints: [], hi: 0, fails: 0, streak: 0, items: {},
    cfg: { theme: 'dark', char: 'goth', mascot_size: '180', mascot_on: '1', side_on: '1', asst_on: '1' },
};

/* ---------------- editor ---------------- */
const editor = CodeMirror.fromTextArea($('editor-textarea'), {
    mode: 'python', theme: 'trainer', lineNumbers: true, indentUnit: 4, tabSize: 4,
    matchBrackets: true, autoCloseBrackets: true, styleActiveLine: true,
    extraKeys: { 'Ctrl-Enter': run, 'Cmd-Enter': run, 'Ctrl-H': nextHint, Tab: cm => cm.replaceSelection('    ') },
});
editor.setValue('# Выбери задачу слева, чтобы начать\n');
let saveTimer = null;
editor.on('change', () => {
    if (!S.cur || S.cur.quiz) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => api().save_draft(editor.getValue()), 800);
});

/* ---------------- settings / layout ---------------- */
function applyCfg() {
    const c = S.cfg;
    document.documentElement.dataset.theme = c.theme;
    $('app').classList.toggle('no-side', c.side_on !== '1');
    $('app').classList.toggle('no-asst', c.asst_on !== '1');
    $('act-tasks').classList.toggle('active', c.side_on === '1');
    $('act-asst').classList.toggle('active', c.asst_on === '1');
    $('mascot-stage').hidden = $('char-ctl').hidden = c.mascot_on !== '1';
    Mascot.setSize(+c.mascot_size);
    editor.refresh();
}
function setCfg(k, v) {
    S.cfg[k] = String(v);
    applyCfg();
    api().set_setting(k, String(v)).catch(() => {});
}

/* ---------------- mascot: React/UI решает только КАКОЙ svg и КАКОГО размера ---------------- */
const Mascot = {
    list: [], cache: new Map(), token: 0,

    async init() {
        try { this.list = await api().list_characters(); } catch (e) { this.list = []; }
        if (!this.list.length) { $('mascot-stage').hidden = $('char-ctl').hidden = true; return; }
        const sel = $('char-select');
        sel.innerHTML = '';
        this.list.forEach(ch => sel.appendChild(new Option(ch.label, ch.id)));
        const id = this.list.some(c => c.id === S.cfg.char) ? S.cfg.char : this.list[0].id;
        await this.show(id);
        setTimeout(() => this.list.forEach(c => this.load(c.id).catch(() => {})), 1500); // прогрев кэша
    },

    async load(id) {
        if (this.cache.has(id)) return this.cache.get(id);
        const svg = await api().get_character(id);
        if (!svg) throw new Error('no svg');
        const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
        this.cache.set(id, url);
        return url;
    },

    async show(id) {
        const t = ++this.token;
        try {
            const url = await this.load(id);
            if (t !== this.token) return;            // выбран другой персонаж, пока грузился этот
            $('mascot-img').src = url;               // просто меняем src, анимация внутри SVG
            $('char-select').value = id;
        } catch (e) { /* оставляем текущего */ }
    },

    setSize(px) {
        $('mascot-img').style.width = px + 'px';     // только ширина, height:auto в CSS
        $('msize').value = px;
        $('msize-val').textContent = px + ' px';
    },

    say(text, ms = 4200) {
        const b = $('bubble');
        b.textContent = text;
        b.classList.add('show');
        clearTimeout(this._bt);
        this._bt = setTimeout(() => b.classList.remove('show'), ms);
    },
};
$('char-select').onchange = e => {
    Mascot.show(e.target.value); setCfg('char', e.target.value);
    api().assistant_welcome(chatCtx()).then(w => { if (w && w.bubble) Mascot.say(w.bubble); }).catch(() => {});
};
$('msize').oninput = e => Mascot.setSize(+e.target.value);
$('msize').onchange = e => setCfg('mascot_size', e.target.value);
$('mtoggle').onclick = () => setCfg('mascot_on', S.cfg.mascot_on === '1' ? '0' : '1');

/* ---------------- chat: офлайн-помощница ---------------- */
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const inlineMd = s => s.replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/(^|\s)_\(([^)]*)\)_/g, '$1<i>($2)</i>');
function md(text) {
    const parts = String(text).split(/```(?:python|py)?\n?([\s\S]*?)```/);
    return parts.map((p, i) => {
        if (i % 2) return '<pre><code>' + esc(p.replace(/\n$/, '')) + '</code></pre>';
        return esc(p).split(/\n{2,}/).map(block => {
            const lines = block.split('\n').filter(l => l.trim());
            if (!lines.length) return '';
            if (lines.every(l => /^\s*(?:[-*]\s|\d+\.\s)/.test(l))) {
                const tag = /^\s*\d+\./.test(lines[0]) ? 'ol' : 'ul';
                return `<${tag}>` + lines.map(l => '<li>' + inlineMd(l.replace(/^\s*(?:[-*]|\d+\.)\s/, '')) + '</li>').join('') + `</${tag}>`;
            }
            return '<p>' + lines.map(inlineMd).join('<br>') + '</p>';
        }).join('');
    }).join('');
}
function scrollChat() { $('chat').scrollTop = 1e9; }
function addMe(text) { $('chat').appendChild(el('div', 'msg me', text)); scrollChat(); }
function addBot(r) {
    const m = el('div', 'msg bot');
    m.innerHTML = md(r.reply || '');
    if (r.chips && r.chips.length) {
        const row = el('div', 'chiprow');
        r.chips.forEach(c => {
            const b = el('button', '', c.label);
            b.onclick = () => { row.remove(); ask(c.send, c.label); };
            row.appendChild(b);
        });
        m.appendChild(row);
    }
    $('chat').appendChild(m);
    scrollChat();
}
function chatCtx() {
    return { persona: S.cfg.char, code: editor.getValue(), output: $('output').textContent, status: $('output').className, fails: S.fails, streak: S.streak };
}
let asking = false;
async function ask(text, label) {
    text = String(text == null ? $('chat-input').value : text).trim().slice(0, 2000);
    if (!text || asking) return;
    asking = true;
    if (!text.startsWith('@')) $('chat-input').value = '';
    addMe(label || text);
    const typing = el('div', 'msg bot typing', '…');
    $('chat').appendChild(typing); scrollChat();
    const t0 = Date.now();
    let r = null;
    try { r = await api().ask_assistant(text, chatCtx()); } catch (e) { /* запасной ответ ниже */ }
    await new Promise(res => setTimeout(res, Math.max(0, 350 - (Date.now() - t0))));   // маленькая пауза, чтобы ответ не «выстреливал»
    typing.remove();
    asking = false;
    r = r || { reply: 'Что-то пошло не так. Спроси ещё раз.' };
    addBot(r);
    if (r.bubble) Mascot.say(r.bubble);
    if (r.action === 'hint') nextHint();
    else if (r.action === 'next') goNext();
    else if (r.action === 'run') run();
}
$('chat-send').onclick = () => ask();
$('chat-input').addEventListener('keydown', e => { if (e.key === 'Enter') ask(); });
[['💡 Подсказка', '@action:hint'], ['Объясни задачу', '@action:explain-task'], ['Проверь код', '@action:check-code']].forEach(([label, cmd]) => {
    const b = el('button', '', label);
    b.onclick = () => ask(cmd, label);
    $('chips').appendChild(b);
});
function scheduleIdle() {          // случайные реплики над персонажем
    setTimeout(async () => {
        if (document.hasFocus() && S.cfg.mascot_on === '1' && !$('bubble').classList.contains('show')) {
            try { const r = await api().assistant_idle(chatCtx()); if (r && r.bubble) Mascot.say(r.bubble, 7000); } catch (e) {}
        }
        scheduleIdle();
    }, 50000 + Math.random() * 70000);
}

/* ---------------- tasks tree ---------------- */
const KIND = { write: 'Напиши', fill: 'Допиши', bug: 'Найди баг', predict: 'Что выведет?' };
const TAGS = { fill: '___', bug: 'баг', predict: '?' };

async function buildMenu() {
    const menu = $('menu');
    menu.innerHTML = '';
    S.items = {};
    for (const cat of await api().get_categories()) {
        const head = el('div', 'cat');
        head.append(el('span', 'arr', '▼'), el('span', '', cat.label), el('span', 'cnt', String(cat.count)));
        const body = el('div', 'cat-body');
        head.onclick = () => { head.classList.toggle('closed'); body.classList.toggle('closed'); };
        menu.append(head, body);
        for (const t of await api().get_tasks_by_category(cat.key)) {
            const b = el('button', 'item' + (t.completed ? ' done' : ''));
            b.append(el('span', 'st'), el('span', 't', t.title));
            if (TAGS[t.kind]) b.append(el('span', 'k', TAGS[t.kind]));
            b.onclick = () => loadTask(cat.key, t.index);
            body.appendChild(b);
            S.items[cat.key + ':' + t.index] = b;
        }
    }
}
$('search').oninput = e => {
    const q = e.target.value.trim().toLowerCase();
    document.querySelectorAll('.item').forEach(b => {
        b.hidden = q && !b.textContent.toLowerCase().includes(q);
    });
    if (q) document.querySelectorAll('.cat,.cat-body').forEach(x => x.classList.remove('closed'));
};

async function refreshProgress() {
    const p = await api().get_overall_progress();
    $('pfill').style.width = (p.total ? Math.round(p.completed / p.total * 100) : 0) + '%';
    $('plabel').textContent = p.completed + ' / ' + p.total;
    $('st-right').textContent = 'решено ' + p.completed + ' из ' + p.total;
}

async function loadTask(cat, index, review = false) {
    const t = await api().set_current_task(cat, index, review);
    if (t.error) return;
    const quiz = t.type === 'quiz';
    S.cur = { category: cat, index, quiz, review }; S.hints = t.hints || []; S.hi = 0; S.fails = 0;
    document.querySelectorAll('.item.active').forEach(b => b.classList.remove('active'));
    (S.items[cat + ':' + index] || el('i')).classList.add('active');

    $('title').textContent = t.title;
    $('tab-task').textContent = t.title;
    $('desc').textContent = t.description;
    $('badge').hidden = !t.completed;
    $('next-btn').hidden = !t.completed;
    $('hint-box').hidden = true;
    $('hint-btn').textContent = 'Подсказка 0/' + S.hints.length;
    $('dots').replaceChildren(...Array.from({ length: 5 }, (_, i) => el('i', i < (t.difficulty || 0) ? 'on' : '')));
    $('kind').hidden = !t.kind; $('kind').textContent = review ? 'Повторение' : (KIND[t.kind] || '');
    $('cheat-wrap').open = !review;                  // при повторении шпаргалка свёрнута: вспоминаем сами
    $('next-btn').textContent = review ? 'Следующее повторение →' : 'Дальше →';
    $('cheat-wrap').hidden = !t.cheat; $('cheat').textContent = t.cheat || '';
    $('hint-btn').hidden = $('reset-btn').hidden = $('run-btn').hidden = quiz;
    $('panel').classList.toggle('quiz', quiz);
    $('quiz').hidden = !quiz;
    $('quiz').replaceChildren();
    if (quiz) (t.options || []).forEach((text, i) => {
        const b = el('button', 'opt', text);
        b.onclick = () => answer(i, b);
        $('quiz').appendChild(b);
    });
    editor.setOption('readOnly', quiz ? 'nocursor' : false);
    $('output').className = '';
    $('output').textContent = quiz ? 'Выбери вариант ответа.' : 'Нажми «Запустить», чтобы проверить решение.';
    $('run-meta').textContent = '';
    $('st-left').textContent = cat + ' · #' + (index + 1);
    editor.setValue(t.code || '');
    showView('task');
    editor.focus();
}

function nextHint() {
    if (!S.cur) return;
    const box = $('hint-box');
    if (!S.hints.length) { box.hidden = false; box.textContent = 'Для этой задачи подсказок нет.'; return; }
    if (S.hi < S.hints.length) S.hi++;
    box.hidden = false;
    box.textContent = S.hints.slice(0, S.hi).map((h, i) => (i + 1) + ') ' + h).join('\n\n');
    $('hint-btn').textContent = 'Подсказка ' + S.hi + '/' + S.hints.length;
}
$('hint-btn').onclick = nextHint;
$('reset-btn').onclick = async () => { const r = await api().reset_code(); editor.setValue(r.code || ''); };

async function run() {
    if (!S.cur) return;
    const out = $('output'), btn = $('run-btn');
    out.className = ''; out.textContent = '⏳ Проверяю…'; btn.disabled = true;
    let r;
    try { r = await api().check_code(editor.getValue()); }
    catch (e) { r = { status: 'error', output: 'Внутренняя ошибка проверки. Попробуй ещё раз.' }; }
    btn.disabled = false;
    out.textContent = r.output; out.className = r.status;
    $('run-meta').textContent = r.duration_ms != null ? r.duration_ms + ' мс' : '';
    finish(r);
}

function finish(r) {
    if (r.status === 'success') {
        S.fails = 0;
        toast(r.srs_days ? `Повторено! Следующий раз через ${r.srs_days} дн.` : 'Задача решена');
        refreshReview();
        $('badge').hidden = false; $('next-btn').hidden = false;
        const b = S.items[S.cur.category + ':' + S.cur.index];
        if (b) b.classList.add('done');
        refreshProgress();
        S.streak++;
        api().assistant_event('success', chatCtx()).then(r => { if (r && r.bubble) Mascot.say(r.bubble); }).catch(() => {});
    } else {
        S.streak = 0;
        if (++S.fails >= 2) api().assistant_event('fail', chatCtx()).then(r => { if (r && r.reply) { addBot(r); Mascot.say(r.bubble); } }).catch(() => {});
    }
}
async function answer(i, btn) {
    if (!S.cur || !S.cur.quiz) return;
    let r;
    try { r = await api().check_answer(i); } catch (e) { r = { status: 'error', output: 'Внутренняя ошибка проверки.' }; }
    const out = $('output');
    out.textContent = r.output; out.className = r.status;
    if (r.status === 'success') {
        btn.classList.add('ok');
        document.querySelectorAll('.opt').forEach(b => b.disabled = true);
    } else {
        btn.classList.add('bad'); btn.disabled = true;
    }
    finish(r);
}
$('run-btn').onclick = run;
async function goNext() {
    if (S.cur && S.cur.review) return startReview();
    const n = await api().get_next_task();
    if (n) loadTask(n.category, n.index); else toast('Все задачи решены!');
}
$('next-btn').onclick = goNext;

/* ---------------- повторение ---------------- */
async function refreshReview() {
    try {
        const st = await api().get_review_status();
        $('review-box').hidden = !st.due;
        $('rv-text').textContent = 'Повторение на сегодня: ' + st.due;
    } catch (e) {}
}
async function startReview() {
    const it = await api().start_review();
    if (!it) { toast('На сегодня повторять нечего'); refreshReview(); return; }
    loadTask(it.category, it.index, true);
}
$('rv-start').onclick = startReview;

/* ---------------- views / stats ---------------- */
function showView(v) {
    $('task-view').hidden = v !== 'task';
    $('stats-view').hidden = v !== 'stats';
    $('tab-task').classList.toggle('active', v === 'task');
    $('tab-stats').classList.toggle('active', v === 'stats');
    if (v === 'task') editor.refresh(); else loadStats();
}
$('tab-task').onclick = () => showView('task');
$('tab-stats').onclick = $('act-stats').onclick = () => showView('stats');
$('act-tasks').onclick = () => setCfg('side_on', S.cfg.side_on === '1' ? '0' : '1');
$('act-asst').onclick = () => setCfg('asst_on', S.cfg.asst_on === '1' ? '0' : '1');
$('act-theme').onclick = () => setCfg('theme', S.cfg.theme === 'dark' ? 'light' : 'dark');

async function loadStats() {
    const s = await api().get_stats();
    $('s-done').textContent = s.completed; $('s-att').textContent = s.total_attempts;
    $('s-rate').textContent = s.success_rate + '%'; $('s-total').textContent = s.total_tasks;
    $('s-streak').textContent = s.streak_days; $('s-due').textContent = s.review_due;
    $('cats').replaceChildren(...s.by_category.map(c => {
        const row = el('div', 'catrow'), bar = el('div', 'catbar'), fill = el('i');
        fill.style.width = (c.total ? c.done / c.total * 100 : 0) + '%';
        bar.appendChild(fill);
        row.append(el('span', '', c.label), bar, el('b', '', c.done + '/' + c.total));
        return row;
    }));
    const by = {};
    (s.by_day || []).forEach(x => by[x.date] = x.count);
    const days = Array.from({ length: 14 }, (_, i) => {
        const d = new Date(); d.setDate(d.getDate() - (13 - i));
        return d.toISOString().slice(0, 10);
    });
    const max = Math.max(1, ...days.map(d => by[d] || 0));
    $('chart').replaceChildren(...days.map(d => {
        const col = el('div', 'col'), bar = el('i');
        bar.style.height = ((by[d] || 0) / max * 100) + '%';
        bar.title = d + ': ' + (by[d] || 0);
        col.append(bar, el('small', '', d.slice(5)));
        return col;
    }));
}

/* ---------------- misc ---------------- */
function toast(msg) {
    const t = $('toast');
    t.textContent = msg; t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2200);
}
document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    const k = e.key.toLowerCase();
    if (k === 'b') { e.preventDefault(); $('act-tasks').click(); }
    else if (k === 'j') { e.preventDefault(); $('act-asst').click(); }
    else if (k === 'enter') { e.preventDefault(); run(); }
});

/* ---------------- boot ---------------- */
window.addEventListener('pywebviewready', async () => {
    try { Object.assign(S.cfg, await api().get_settings()); } catch (e) {}
    applyCfg();
    await buildMenu();
    await refreshProgress();
    refreshReview();
    const last = await api().get_last_position();       // сначала быстрое: восстановить последнюю задачу
    if (last) await loadTask(last.category, last.index);
    Mascot.init();                                      // чиби и помощница грузятся в фоне, интерфейс уже живой
    api().assistant_welcome(chatCtx()).then(w => {
        addBot(w);
        if (w.bubble) setTimeout(() => Mascot.say(w.bubble), 800);
    }).catch(() => {});
    scheduleIdle();
});
