/* 采集猫 Web 控制台 —— 前端胶水层（无框架，无构建步骤） */
(() => {
  "use strict";

  const CSRF = window.CSRF || "";

  /* ------------------------------------------------------------ toast */
  function toast(msg, kind = "", ttl = 4200) {
    const box = document.getElementById("toast");
    if (!box) return;
    const el = document.createElement("div");
    el.className = "item " + kind;
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity .25s";
      setTimeout(() => el.remove(), 260);
    }, ttl);
  }

  /* ------------------------------------------------------------ actions */
  async function callAction(channel, action, value = "1") {
    const body = new FormData();
    body.set("channel", channel);
    body.set("action", action);
    body.set("value", value);
    body.set("csrf_token", CSRF);
    let res;
    try {
      res = await fetch("/api/action", { method: "POST", body, credentials: "same-origin" });
    } catch (e) {
      toast("请求失败：" + e, "err");
      return null;
    }
    if (res.status === 401) {
      location.href = "/login";
      return null;
    }
    let json = {};
    try { json = await res.json(); } catch (_) { /* ignore */ }
    const label = `${action}`;
    if (!res.ok) {
      toast(`${label} 失败：${json.error || res.status}`, "err", 6000);
      return json;
    }
    if (json.errors) {
      // 后端把真正的错误只写进 err 日志，这里把它顶出来
      toast(`${label} 后端报错：${String(json.errors).slice(0, 300)}`, "err", 9000);
    } else if (json.ok) {
      const d = json.data;
      const brief = d === "ok" || d == null ? "ok" : JSON.stringify(d).slice(0, 200);
      toast(`${label} → ${brief}`, "ok");
    } else {
      toast(`${label} 未确认（HTTP ${json.status}）`, "warn");
    }
    return json;
  }

  document.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-action]");
    if (!btn) return;
    ev.preventDefault();
    const channel = btn.dataset.channel;
    const action = btn.dataset.action;
    let value = btn.dataset.value ?? "1";
    if (btn.dataset.valueFrom) {
      const src = document.querySelector(btn.dataset.valueFrom);
      if (src) value = src.value;
    }
    if (btn.dataset.confirm && !confirm(btn.dataset.confirm)) return;
    btn.disabled = true;
    callAction(channel, action, value).finally(() => { btn.disabled = false; });
  });

  /* 表单式动作：<form data-action-form data-channel data-action> */
  document.addEventListener("submit", async (ev) => {
    const form = ev.target.closest("[data-action-form]");
    if (!form) return;
    ev.preventDefault();
    const channel = form.dataset.channel;
    const action = form.dataset.action;
    const field = form.querySelector("[name=value]");
    let value = field ? field.value : "1";
    const mode = form.dataset.valueMode || "raw";
    if (mode === "json") {
      try { value = JSON.stringify(JSON.parse(value)); }
      catch (e) { toast("JSON 格式错误：" + e.message, "err"); return; }
    } else if (mode === "number") {
      value = String(Number(value));
    }
    await callAction(channel, action, value);
    if (form.dataset.reload !== "no") setTimeout(() => location.reload(), 900);
  });

  /* --------------------------------------------------------- live state */
  const liveCells = new Map();
  function registerLive() {
    document.querySelectorAll("[data-live]").forEach((el) => {
      liveCells.set(el.dataset.live, el);
    });
  }

  function renderValue(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "string") return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    const s = JSON.stringify(v);
    return s.length > 400 ? s.slice(0, 400) + "…" : s;
  }

  function applyLive(bus, event, data) {
    const key = `${bus}.${event}`;
    const el = liveCells.get(key) || document.querySelector(`[data-live="${key}"]`);
    if (el) el.textContent = renderValue(data);
    // 通用日志窗口
    const log = document.getElementById("live-log");
    if (log) appendLog(log, `${event}: ${renderValue(data)}`);
    // 状态点
    if (event === "IsVip" && data && typeof data === "object") {
      const cell = document.querySelector(`[data-vip="${data.module_id}"]`);
      if (cell) {
        cell.textContent = data.is_vip ? "已开通" : "未开通";
        cell.className = "badge " + (data.is_vip ? "ok" : "err");
      }
    }
  }

  function appendLog(el, text) {
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 24;
    const line = document.createElement("div");
    if (/vip/i.test(text)) line.className = "vip";
    line.textContent = text;
    el.appendChild(line);
    while (el.childElementCount > 1500) el.removeChild(el.firstChild);
    if (atBottom) el.scrollTop = el.scrollHeight;
  }

  
/* ---------- 登录状态（后端在等什么） ---------- */
function renderLoginState(login) {
  const label = document.getElementById("login-state-label");
  const hint = document.getElementById("login-state-hint");
  const age = document.getElementById("login-state-age");
  if (!login) return;
  const map = {
    logged_in: "ok",
    wait_code: "warn",
    wait_password: "warn",
    wait_phone: "warn",
    idle: "",
    logged_out: "",
  };
  if (label) {
    label.textContent = login.label || login.state;
    label.className = "badge " + (map[login.state] || "");
  }
  if (hint) hint.textContent = login.hint || "";
  if (age) age.textContent = login.age == null ? "" : "（" + login.age + " 秒前）";

  document.querySelectorAll("[data-need-state]").forEach(function (form) {
    const need = form.getAttribute("data-need-state");
    const ok = login.state === need;
    form.classList.toggle("state-blocked", !ok);
    let note = form.querySelector(".state-note");
    if (!ok) {
      if (!note) {
        note = document.createElement("p");
        note.className = "small muted state-note";
        form.appendChild(note);
      }
      note.textContent = "当前状态不是「" + (need === "wait_code" ? "等待验证码"
        : need === "wait_password" ? "等待二次验证密码" : "等待手机号") + "」，提交会被后端忽略。";
    } else if (note) {
      note.remove();
    }
  });
}

function setDot(id, ok, text) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = "dot " + (ok ? "ok" : "bad");
  }

  function connectStream() {
    const es = new EventSource("/api/stream");
    es.addEventListener("hello", (ev) => {
      setDot("live-ws", true, "已连接");
      try {
        const snap = JSON.parse(ev.data);
        Object.entries(snap.buses || {}).forEach(([bus, payload]) => {
          Object.entries(payload).forEach(([k, v]) => applyLive(bus, k, v));
        });
      } catch (_) { /* ignore */ }
    });
    es.addEventListener("event", (ev) => {
      setDot("live-ws", true, "已连接");
      try {
        const rec = JSON.parse(ev.data);
        applyLive(rec.bus, rec.event, rec.data);
      } catch (_) { /* ignore */ }
    });
    es.onerror = () => setDot("live-ws", false, "断开");
  }

  /* ------------------------------------------------------------- polling */
  async function pollHealth() {
    try {
      const r = await fetch("/api/state", { credentials: "same-origin" });
      if (r.status === 401) { location.href = "/login"; return; }
      const j = await r.json();
      setDot("live-backend", !!j.backend_ok, j.backend_ok ? "正常" : "无响应");
      renderLoginState(j.login);
      if (j.snapshot) setDot("live-ws", !!j.snapshot.connected, j.snapshot.connected ? "已连接" : "断开");
      if (j.is_vip) {
        Object.entries(j.is_vip).forEach(([id, ok]) => {
          const cell = document.querySelector(`[data-vip="${id}"]`);
          if (cell) {
            cell.textContent = ok ? "已开通" : "未开通";
            cell.className = "badge " + (ok ? "ok" : "err");
          }
        });
      }
    } catch (_) {
      setDot("live-backend", false, "无法访问");
    }
  }

  async function refreshLog(kind, target) {
    const el = document.getElementById(target);
    if (!el) return;
    const r = await fetch(`/api/logs?kind=${kind}&lines=400`, { credentials: "same-origin" });
    if (!r.ok) return;
    const j = await r.json();
    el.textContent = (j.lines || []).join("\n");
    el.scrollTop = el.scrollHeight;
  }

  window.CJ = { toast, callAction, refreshLog, pollHealth };

  document.addEventListener("DOMContentLoaded", () => {
    registerLive();
    connectStream();
    pollHealth();
    setInterval(pollHealth, 10000);
    document.querySelectorAll("[data-log]").forEach((el) => {
      refreshLog(el.dataset.log, el.id);
      setInterval(() => refreshLog(el.dataset.log, el.id), 4000);
    });
  });
})();

/* ------------------------------------------------------------------ 主题切换 */
(function () {
  var KEY = 'cj-theme';
  var root = document.documentElement;
  var btn = document.getElementById('btn-theme');
  function apply(t) {
    root.setAttribute('data-theme', t);
    if (btn) btn.textContent = t === 'light' ? '浅色' : '深色';
    try { localStorage.setItem(KEY, t); } catch (e) {}
  }
  apply(root.getAttribute('data-theme') || 'dark');
  if (btn) {
    btn.addEventListener('click', function () {
      apply(root.getAttribute('data-theme') === 'light' ? 'dark' : 'light');
    });
  }
})();