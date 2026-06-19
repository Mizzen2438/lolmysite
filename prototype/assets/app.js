/* ==========================================================
   NEONQ プロトタイプ 共通スクリプト
   サンプルデータの描画・フィルタ動作のみ(データは保存されない)
   ========================================================== */

"use strict";

// ---------- サンプルデータ ----------

const LANES = ["TOP", "JG", "MID", "ADC", "SUP"];

const RECRUITMENTS = [
  {
    id: 1,
    mode: "ランク(フレックス)",
    owner: { name: "Hikari#JP1", discord: "hikari_lol", rank: "ゴールド II" },
    slots: [
      { lane: "TOP", member: { name: "Hikari#JP1", discord: "hikari_lol" } },
      { lane: "JG", member: { name: "Mizore#222", discord: "mizore22" } },
      { lane: "MID", member: null },
      { lane: "ADC", member: null },
      { lane: "SUP", member: { name: "PoroSnax#JP1", discord: "porosnax" } },
    ],
    rankMin: "シルバー",
    rankMax: "プラチナ",
    startAt: "今日 22:00",
    duration: "2〜3時間",
    vc: "Discord VC(聞き専OK)",
    tags: ["エンジョイ", "聞き専OK", "社会人"],
    comment:
      "フレックス回せる方募集です!勝ち負けより楽しく。VCは聞き専でも大丈夫です。",
    status: "open",
    discordInvite: "https://discord.gg/xxxxxxx",
    applicants: [
      { name: "Yasuo一筋#JP1", discord: "yasuo_only", rank: "ゴールド IV", lane: "MID", comment: "ミッド行けます!よろしくお願いします" },
      { name: "ADC職人#JP2", discord: "adc_pro", rank: "プラチナ IV", lane: "ADC", comment: "22時から参加できます" },
    ],
  },
  {
    id: 2,
    mode: "ランク(デュオ)",
    owner: { name: "Soraka好き#JP1", discord: "soraka_main", rank: "ゴールド IV" },
    slots: [
      { lane: "SUP", member: { name: "Soraka好き#JP1", discord: "soraka_main" } },
      { lane: "ADC", member: null },
    ],
    rankMin: "ゴールド",
    rankMax: "ゴールド",
    startAt: "今日 21:00",
    duration: "2時間",
    vc: "なし(ゲーム内チャットのみ)",
    tags: ["ガチ", "テキストのみ"],
    comment: "ソロQデュオ相手募集。サポメインなのでADCの方歓迎です。",
    status: "open",
    discordInvite: "",
    applicants: [],
  },
  {
    id: 3,
    mode: "ARAM",
    owner: { name: "ぽんこつ#JP1", discord: "ponkotsu", rank: "アンランク" },
    slots: [
      { lane: "FILL", member: { name: "ぽんこつ#JP1", discord: "ponkotsu" } },
      { lane: "FILL", member: { name: "ねこまる#JP1", discord: "nekomaru" } },
      { lane: "FILL", member: { name: "GG3秒#JP1", discord: "gg3byo" } },
      { lane: "FILL", member: { name: "らんたん#JP1", discord: "rantan" } },
      { lane: "FILL", member: { name: "氷の人#JP1", discord: "koorinohito" } },
    ],
    rankMin: "指定なし",
    rankMax: "指定なし",
    startAt: "今日 23:00",
    duration: "1時間",
    vc: "Discord VC",
    tags: ["エンジョイ", "初心者歓迎", "深夜帯"],
    comment: "寝る前にARAMやりましょう〜。初心者さんも歓迎!",
    status: "filled",
    discordInvite: "https://discord.gg/yyyyyyy",
    applicants: [],
  },
  {
    id: 4,
    mode: "ノーマル(ドラフト)",
    owner: { name: "週末戦士#JP1", discord: "weekend_w", rank: "ブロンズ I" },
    slots: [
      { lane: "MID", member: { name: "週末戦士#JP1", discord: "weekend_w" } },
      { lane: "TOP", member: null },
      { lane: "JG", member: null },
      { lane: "ADC", member: null },
      { lane: "SUP", member: null },
    ],
    rankMin: "指定なし",
    rankMax: "シルバー",
    startAt: "明日 20:00",
    duration: "3時間",
    vc: "Discord VC(聞き専OK)",
    tags: ["エンジョイ", "初心者歓迎", "学生"],
    comment: "明日の夜にノーマル回すメンバー募集。ゆるくやりたい方どうぞ。",
    status: "open",
    discordInvite: "https://discord.gg/zzzzzzz",
    applicants: [],
  },
  {
    id: 5,
    mode: "ランク(フレックス)",
    owner: { name: "Climber#JP1", discord: "climber", rank: "プラチナ II" },
    slots: [
      { lane: "JG", member: { name: "Climber#JP1", discord: "climber" } },
      { lane: "TOP", member: null },
      { lane: "MID", member: null },
      { lane: "ADC", member: null },
      { lane: "SUP", member: null },
    ],
    rankMin: "プラチナ",
    rankMax: "ダイヤ",
    startAt: "今日 21:30",
    duration: "3時間以上",
    vc: "Discord VC(必須)",
    tags: ["ガチ"],
    comment: "本気でフレックス上げたい方のみ。レポート見せられる方歓迎。",
    status: "closed",
    discordInvite: "",
    applicants: [],
  },
];

const STATUS_LABEL = {
  open: { text: "募集中", cls: "badge-status-open" },
  filled: { text: "成立", cls: "badge-status-filled" },
  closed: { text: "締切", cls: "badge-status-closed" },
};

// ---------- 共通ヘルパー ----------

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function openSlots(r) {
  return r.slots.filter((s) => !s.member);
}

function slotHtml(r) {
  return (
    '<div class="slot-list">' +
    r.slots
      .map((s) =>
        s.member
          ? `<span class="slot filled">${esc(s.lane)} ✓</span>`
          : `<span class="slot wanted">${esc(s.lane)} 募集中</span>`
      )
      .join("") +
    "</div>"
  );
}

function rankRange(r) {
  if (r.rankMin === r.rankMax) return r.rankMin;
  return `${r.rankMin}〜${r.rankMax}`;
}

function mockAction(message) {
  alert(message + "\n\n(プロトタイプのためデータは保存されません)");
}

// ---------- S-01 募集一覧 ----------

function renderRecruitList() {
  const listEl = document.getElementById("recruit-list");
  if (!listEl) return;

  const mode = document.getElementById("f-mode").value;
  const rank = document.getElementById("f-rank").value;
  const lane = document.getElementById("f-lane").value;
  const openOnly = document.getElementById("f-open").checked;

  const items = RECRUITMENTS.filter((r) => {
    if (mode && r.mode !== mode) return false;
    if (rank && r.rankMin !== rank && r.rankMax !== rank && rankRange(r).indexOf(rank) === -1) return false;
    if (lane && !openSlots(r).some((s) => s.lane === lane || s.lane === "FILL")) return false;
    if (openOnly && r.status !== "open") return false;
    return true;
  });

  if (items.length === 0) {
    listEl.innerHTML = '<li class="empty">条件に合う募集が見つかりませんでした。</li>';
    return;
  }

  listEl.innerHTML = items
    .map((r) => {
      const st = STATUS_LABEL[r.status];
      return `
      <li>
        <a class="recruit-card" href="recruit-detail.html?id=${r.id}">
          <div class="head">
            <span class="badge badge-mode">${esc(r.mode)}</span>
            <span class="badge badge-rank">${esc(rankRange(r))}</span>
            <span class="badge ${st.cls}">${st.text}</span>
            <span class="title">${esc(r.comment.slice(0, 40))}${r.comment.length > 40 ? "…" : ""}</span>
          </div>
          ${slotHtml(r)}
          <div class="meta">
            <span>🕘 ${esc(r.startAt)}(${esc(r.duration)})</span>
            <span>🎧 ${esc(r.vc)}</span>
            <span>👤 ${esc(r.owner.name)}</span>
          </div>
          <div>${r.tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div>
        </a>
      </li>`;
    })
    .join("");
}

function initListPage() {
  const listEl = document.getElementById("recruit-list");
  if (!listEl) return;
  ["f-mode", "f-rank", "f-lane", "f-open"].forEach((id) => {
    document.getElementById(id).addEventListener("change", renderRecruitList);
  });
  renderRecruitList();
}

// ---------- S-02 募集詳細 ----------

function getRecruitFromQuery() {
  const id = Number(new URLSearchParams(location.search).get("id")) || 1;
  return RECRUITMENTS.find((r) => r.id === id) || RECRUITMENTS[0];
}

function renderDetailPage() {
  const root = document.getElementById("detail-root");
  if (!root) return;
  const r = getRecruitFromQuery();
  const st = STATUS_LABEL[r.status];

  const members = r.slots
    .map((s) => {
      if (s.member) {
        return `
        <div class="member-row">
          <span class="avatar">${esc(s.member.name.charAt(0))}</span>
          <div>
            <div class="name">${esc(s.member.name)}</div>
            <div class="sub">Discord: ${esc(s.member.discord)}</div>
          </div>
          <span class="spacer"></span>
          <span class="slot filled">${esc(s.lane)}</span>
        </div>`;
      }
      return `
      <div class="member-row">
        <span class="avatar">?</span>
        <div><div class="name" style="color: var(--text-dim);">募集中</div></div>
        <span class="spacer"></span>
        <span class="slot wanted">${esc(s.lane)}</span>
      </div>`;
    })
    .join("");

  const laneOptions = openSlots(r)
    .map((s) => `<option value="${esc(s.lane)}">${esc(s.lane)}</option>`)
    .join("");

  const discordSection =
    r.status === "filled"
      ? `
      <div class="discord-box">
        <h2>🎉 募集成立!Discord に集合しましょう</h2>
        <p style="font-size: 0.88rem;">参加者のみに表示される招待リンクです。開始時刻までに VC へ集合してください。</p>
        <a class="btn btn-discord" href="${esc(r.discordInvite)}" onclick="event.preventDefault(); mockAction('Discord 招待リンクを開きます');">Discord サーバーに参加する</a>
      </div>`
      : `
      <div class="discord-box">
        <h2>🔒 Discord 集合案内</h2>
        <p class="locked-note">サーバー招待リンクは、応募が承認され募集が成立すると、参加者にのみ表示されます。</p>
      </div>`;

  const applySection =
    r.status === "open"
      ? `
      <div class="panel">
        <h2>この募集に応募する</h2>
        <div class="form-grid">
          <div class="form-row">
            <label for="apply-lane">希望レーン</label>
            <select id="apply-lane">${laneOptions}</select>
          </div>
          <div class="form-row">
            <label for="apply-comment">ひとことコメント(任意)</label>
            <textarea id="apply-comment" placeholder="例: 22時から参加できます。よろしくお願いします!"></textarea>
          </div>
          <button class="btn btn-gold btn-block" onclick="mockAction('応募しました。募集主の承認をお待ちください。')">応募する</button>
          <p class="hint" style="color: var(--text-dim); font-size: 0.78rem; margin: 0;">
            応募すると、あなたのプロフィール(ランク・レーン・評価)が募集主に表示されます。
          </p>
        </div>
      </div>`
      : `<div class="panel"><p class="empty">この募集は現在応募を受け付けていません(${st.text})。</p></div>`;

  root.innerHTML = `
    <div class="detail-head">
      <span class="badge badge-mode">${esc(r.mode)}</span>
      <span class="badge ${st.cls}">${st.text}</span>
      <h1>${esc(r.comment)}</h1>
    </div>
    <div>${r.tags.map((t) => `<span class="tag">#${esc(t)}</span>`).join("")}</div>

    <div class="panel">
      <h2>募集条件</h2>
      <dl class="kv">
        <dt>対象ランク帯</dt><dd>${esc(rankRange(r))}</dd>
        <dt>開始予定</dt><dd>${esc(r.startAt)}</dd>
        <dt>想定プレイ時間</dt><dd>${esc(r.duration)}</dd>
        <dt>ボイスチャット</dt><dd>${esc(r.vc)}</dd>
        <dt>募集主</dt><dd>${esc(r.owner.name)}(${esc(r.owner.rank)})</dd>
      </dl>
    </div>

    <div class="panel">
      <h2>参加メンバー(${r.slots.filter((s) => s.member).length}/${r.slots.length})</h2>
      ${members}
    </div>

    ${discordSection}
    ${applySection}

    <div style="text-align: center; margin: 20px 0;">
      <button class="btn btn-ghost btn-sm" onclick="mockAction('この募集を通報しました。運営が内容を確認します。')">⚠ この募集を通報する</button>
    </div>
  `;
}

// ---------- S-04 マイページ(応募者の承認管理) ----------

function renderMyPage() {
  const root = document.getElementById("applicant-list");
  if (!root) return;
  const r = RECRUITMENTS[0]; // サンプル: 自分の募集 = id 1

  if (r.applicants.length === 0) {
    root.innerHTML = '<p class="empty">まだ応募はありません。</p>';
    return;
  }

  root.innerHTML = r.applicants
    .map(
      (a) => `
    <div class="member-row">
      <span class="avatar">${esc(a.name.charAt(0))}</span>
      <div>
        <div class="name">${esc(a.name)} <span class="sub">(${esc(a.rank)} / 希望: ${esc(a.lane)})</span></div>
        <div class="sub">「${esc(a.comment)}」</div>
      </div>
      <span class="spacer"></span>
      <button class="btn btn-primary btn-sm" onclick="mockAction('${esc(a.name)} さんを承認しました。参加者に追加されます。')">承認</button>
      <button class="btn btn-ghost btn-sm" onclick="mockAction('${esc(a.name)} さんを見送りました。')">見送り</button>
    </div>`
    )
    .join("");
}

// ---------- 初期化 ----------

document.addEventListener("DOMContentLoaded", () => {
  initListPage();
  renderDetailPage();
  renderMyPage();
});
