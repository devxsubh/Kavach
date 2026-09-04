const ACCENTS = {
  sky: "#4ECDC4",
  coral: "#FF6B6B",
  lemon: "#FFD93D",
  lilac: "#B197FC",
  peach: "#FFA07A",
  mint: "#6BCF7F",
};

const SKIN = "#F4C7A8";
const INK = "#1A1320";

const LOOKS = {
  wizard: { h: "#6B5344", extra: { B: "#EDE4D4", T: "#FFD93D", R: "#C0392B" } },
  scientist: { h: "#4A2C17", extra: { g: "#1A1320", W: "#F4F1EA" } },
  hacker: { h: "#1A1320", extra: { v: "#4ECDC4", n: "#2A1F33" } },
  astronaut: { h: "#C8B8E8", extra: { H: "#E8E0F8", v: "#3D2E4A" } },
  "cat-villager": { h: "#E8A54B", extra: { C: "#FFC8A0", M: "#C0392B" } },
};

const SPRITES = {
  scientist: [
    "................",
    "....kkkkkkkk....",
    "...khhhhhhhhk...",
    "...khhsssshhk...",
    "...khsgEEgshk...",
    "...khhsssshhk...",
    "....kWWWWWWk....",
    "...kWWpaaapWWk..",
    "...kWWpppppWWk..",
    "...kWWWWWWWWk...",
    "....kWWWWWWk....",
    ".....kll.llk....",
    ".....kll.llk....",
    ".....kff.ffk....",
    "................",
    "................",
  ],
  hacker: [
    "................",
    "....kkkkkkkk....",
    "...knnnnnnnnk...",
    "...knhsssshnk...",
    "...knsvvssvnk...",
    "...knhsssshnk...",
    "....knnnnnnk....",
    "....kppppppk....",
    "...kppnnnnppk...",
    "...kppppppppk...",
    "....kppppppk....",
    ".....kll.llk....",
    ".....kll.llk....",
    ".....kff.ffk....",
    "................",
    "................",
  ],
  wizard: [
    ".......kk.......",
    "......kppk......",
    ".....kppppk.....",
    "....kppppppk....",
    ".....khhhhhk....",
    "....khsssshk....",
    "....khsEEshk....",
    "....khsssshk....",
    ".....kBBBBk.....",
    "....kppRRppk....",
    "...kppTppTppk...",
    "...kppppppppk...",
    "....kppppppk....",
    ".....kll.llk....",
    ".....kff.ffk....",
    "................",
  ],
  astronaut: [
    "................",
    ".....kkkkkk.....",
    "....kHHHHHHk....",
    "....kHvEEvHk....",
    "....kHssssHk....",
    "....kHHHHHHk....",
    ".....kkkkkk.....",
    "....kppppppk....",
    "...kppaappaapk..",
    "...kppppppppk...",
    "....kppppppk....",
    ".....kll.llk....",
    ".....kll.llk....",
    ".....kff.ffk....",
    "................",
    "................",
  ],
  "cat-villager": [
    "................",
    "...kk......kk...",
    "...kCk....kCk...",
    "....khhhhhhk....",
    "....khsssshk....",
    "....khsEEshk....",
    "....khssMshk....",
    ".....kWWWWk.....",
    "....kppaaapk....",
    "...kppppppppk...",
    "...kppppppppk...",
    "....kppppppk....",
    ".....kll.llk....",
    ".....kff.ffk....",
    "................",
    "................",
  ],
};

const HOME = {
  /* Stand at chairs in front of desks (office %). */
  kernel: { x: 18, y: 32 },
  llm: { x: 50, y: 32 },
  buyer: { x: 12, y: 88 },
  seller: { x: 36, y: 88 },
};

const SPOTS = {
  entrance: { x: 8, y: 94 },
  kernelDoor: { x: 16, y: 40 },
  catalog: { x: 84, y: 52 },
  mailbox: { x: 84, y: 82 },
  vault: { x: 84, y: 22 },
  meetBuyer: { x: 28, y: 64 },
  meetSeller: { x: 48, y: 64 },
  intervene: { x: 38, y: 58 },
  advisorDoor: { x: 48, y: 40 },
};

function paletteFor(archetype, accent) {
  const primary = ACCENTS[accent] || ACCENTS.sky;
  const look = LOOKS[archetype] || LOOKS.scientist;
  return {
    k: INK,
    h: look.h,
    s: SKIN,
    E: INK,
    p: primary,
    a: "#FFFDF5",
    W: "#FFFDF5",
    l: "#3D2E4A",
    f: "#1A1320",
    B: "#EDE4D4",
    T: "#FFD93D",
    R: "#C0392B",
    g: "#1A1320",
    v: "#2A3344",
    n: "#2A1F33",
    H: "#E8E0F8",
    C: "#FFC8A0",
    M: "#C0392B",
    ...(look.extra || {}),
  };
}

function setRow(rows, i, value) {
  const next = rows.slice();
  next[i] = value;
  return next;
}

function poseRows(base, pose) {
  const rows = base.slice();
  const blinkAt = rows.findIndex((row) => row.includes("EE") || row.includes("vv"));
  if (pose === "idle2" && blinkAt >= 0) {
    rows[blinkAt] = rows[blinkAt].replace(/E/g, "s").replace(/v/g, "s");
    return rows;
  }
  if (pose === "walk1") {
    return setRow(setRow(rows, 13, ".....kll..lk...."), 14, ".....kff..fk....");
  }
  if (pose === "walk2") {
    return setRow(setRow(rows, 13, ".....kl..llk...."), 14, ".....kf..ffk....");
  }
  if (pose === "talk1" || pose === "talk2") {
    const mouth = rows.findIndex((row, i) => i >= 6 && i <= 8 && row.includes("ssss"));
    if (mouth >= 0) rows[mouth] = rows[mouth].replace("ssss", "sMMs");
    const body = 9;
    if (rows[body] && rows[body][1] === ".") {
      rows[body] = "k" + rows[body].slice(1);
      if (rows[body - 1] && rows[body - 1][2] === ".") {
        rows[body - 1] = rows[body - 1].slice(0, 2) + "k" + rows[body - 1].slice(3);
      }
    }
    if (pose === "talk2") {
      return setRow(setRow(rows, 13, ".....kll..lk...."), 14, ".....kff..fk....");
    }
    return rows;
  }
  return rows;
}

function spriteSVG(rows, pal, size) {
  const cell = size / 16;
  let rects = "";
  rows.forEach((row, y) => {
    [...row].forEach((ch, x) => {
      if (ch === "." || !pal[ch]) return;
      rects += `<rect x="${x * cell}" y="${y * cell}" width="${cell}" height="${cell}" fill="${pal[ch]}"/>`;
    });
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges">${rects}</svg>`;
}

function framesFor(archetype, accent, size) {
  const base = SPRITES[archetype] || SPRITES.scientist;
  const pal = paletteFor(archetype, accent);
  return {
    idle: [spriteSVG(base, pal, size), spriteSVG(poseRows(base, "idle2"), pal, size)],
    walk: [spriteSVG(poseRows(base, "walk1"), pal, size), spriteSVG(poseRows(base, "walk2"), pal, size)],
    talk: [spriteSVG(poseRows(base, "talk1"), pal, size), spriteSVG(poseRows(base, "talk2"), pal, size)],
  };
}

function stationSVG(kind) {
  const maps = {
    catalog: { fill: "#8B6F47", bars: "#FFD93D" },
    mailbox: { fill: "#FF6B6B", bars: "#FFFDF5" },
    vault: { fill: "#3D2E4A", bars: "#FFD93D" },
    board: { fill: "#C9A66B", bars: "#6BCF7F" },
  };
  const c = maps[kind] || maps.catalog;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" shape-rendering="crispEdges">
    <rect width="16" height="16" fill="#1A1320"/>
    <rect x="1" y="1" width="14" height="14" fill="${c.fill}"/>
    <rect x="3" y="3" width="4" height="4" fill="${c.bars}"/>
    <rect x="9" y="3" width="4" height="4" fill="${c.bars}"/>
    <rect x="3" y="9" width="10" height="4" fill="#FFF8E7"/>
  </svg>`;
}

function envelopeSVG() {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 12" shape-rendering="crispEdges">
    <rect width="16" height="12" fill="#1A1320"/>
    <rect x="1" y="1" width="14" height="10" fill="#FFFDF5"/>
    <rect x="1" y="1" width="14" height="2" fill="#FFD93D"/>
    <rect x="7" y="5" width="2" height="2" fill="#1A1320"/>
  </svg>`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function money(minor) {
  if (!minor && minor !== 0) return "—";
  return `₹${(minor / 100).toFixed(2)}`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const audio = {
  ctx: null,
  muted: localStorage.getItem("kavach-mute") === "1",
  ensure() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  tone(freq, dur, type = "square", gain = 0.045) {
    if (this.muted) return;
    try {
      this.ensure();
    } catch {
      return;
    }
    const osc = this.ctx.createOscillator();
    const amp = this.ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    amp.gain.setValueAtTime(gain, this.ctx.currentTime);
    amp.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + dur);
    osc.connect(amp);
    amp.connect(this.ctx.destination);
    osc.start();
    osc.stop(this.ctx.currentTime + dur);
  },
  talk() { this.tone(720, 0.05); this.tone(980, 0.04); },
  step() { this.tone(140, 0.035, "triangle", 0.02); },
  mail() { this.tone(520, 0.06); this.tone(780, 0.08); },
  alarm() {
    this.tone(196, 0.14);
    window.setTimeout(() => this.tone(155, 0.16), 110);
    window.setTimeout(() => this.tone(196, 0.18), 230);
  },
  success() {
    this.tone(523, 0.09);
    window.setTimeout(() => this.tone(659, 0.09), 90);
    window.setTimeout(() => this.tone(784, 0.16), 180);
  },
};

const state = {
  floor: null,
  selected: "kernel",
  running: false,
  speech: {},
  place: {},
  posePhase: null,
  view: "floor",
  inspect: null,
};

function setTicker(text) {
  const el = document.getElementById("ticker");
  if (el) el.textContent = text;
}

function setBanner(text) {
  const el = document.getElementById("phaseBanner");
  if (el) el.textContent = text;
}

function setDoor(open) {
  document.querySelector(".room-kernel")?.classList.toggle("door-open", open);
}

function setWatching(on) {
  document.getElementById("office")?.classList.toggle("kernel-watching", on);
}

function focusCamera(ids, zoom = 1.06) {
  const office = document.getElementById("office");
  if (!office) return;
  const pts = (ids || []).map((id) => state.place[id]).filter(Boolean);
  if (!pts.length) {
    office.style.setProperty("--cam-x", "0px");
    office.style.setProperty("--cam-y", "0px");
    office.style.setProperty("--cam-z", "1");
    return;
  }
  const cx = pts.reduce((sum, p) => sum + p.x, 0) / pts.length;
  const cy = pts.reduce((sum, p) => sum + p.y, 0) / pts.length;
  office.style.setProperty("--cam-x", `${((50 - cx) * 0.45).toFixed(1)}px`);
  office.style.setProperty("--cam-y", `${((50 - cy) * 0.35).toFixed(1)}px`);
  office.style.setProperty("--cam-z", String(zoom));
}

function shineOn(id) {
  const office = document.getElementById("office");
  const spot = document.getElementById("spotlight");
  const here = state.place[id];
  if (!office || !spot || !here) return;
  office.classList.add("lit");
  office.style.setProperty("--spot-x", `${here.x}%`);
  office.style.setProperty("--spot-y", `${here.y}%`);
}

function burst(x, y, kind, count = 8) {
  const fx = document.getElementById("fx");
  if (!fx) return;
  for (let i = 0; i < count; i += 1) {
    const pix = document.createElement("i");
    pix.className = `pix ${kind}`;
    pix.style.left = `${x}%`;
    pix.style.top = `${y}%`;
    pix.style.setProperty("--dx", `${Math.round(Math.random() * 48 - 24)}px`);
    pix.style.setProperty("--dy", `${Math.round(Math.random() * -36 - 8)}px`);
    fx.appendChild(pix);
    window.setTimeout(() => pix.remove(), 560);
  }
}

function puffAt(id, kind = "dust", count = 3) {
  const node = actorEl(id);
  const office = document.getElementById("office");
  if (!node || !office) return;
  const floor = office.getBoundingClientRect();
  const box = node.getBoundingClientRect();
  const x = ((box.left + box.width / 2 - floor.left) / floor.width) * 100;
  const y = ((box.bottom - 8 - floor.top) / floor.height) * 100;
  burst(x, y, kind, count);
}

function shakeFloor() {
  const canvas = document.querySelector(".floor-canvas");
  if (!canvas) return;
  canvas.classList.add("shaking");
  window.setTimeout(() => canvas.classList.remove("shaking"), 560);
}

function markSpeaker(who) {
  document.querySelectorAll(".actor").forEach((node) => {
    node.classList.toggle("speaking", node.dataset.agent === who);
  });
  if (who) shineOn(who);
}

function typeInto(node, text) {
  const typed = node.querySelector(".typed");
  if (!typed) {
    node.insertAdjacentHTML("beforeend", `<span class="typed">${escapeHtml(text)}</span>`);
    return;
  }
  typed.textContent = "";
  const step = Math.max(1, Math.ceil(text.length / 24));
  let i = 0;
  const tick = () => {
    i = Math.min(text.length, i + step);
    typed.textContent = text.slice(0, i);
    if (i < text.length) window.setTimeout(tick, 16);
  };
  tick();
}

function syncSoundBtn() {
  const btn = document.getElementById("soundBtn");
  if (!btn) return;
  btn.textContent = audio.muted ? "SFX OFF" : "SFX ON";
  btn.setAttribute("aria-pressed", audio.muted ? "false" : "true");
}

const els = {
  seller: () => document.getElementById("seller"),
  rails: () => document.getElementById("rails"),
  goal: () => document.getElementById("goal"),
  budget: () => document.getElementById("budget"),
  outcome: () => document.getElementById("outcome"),
  story: () => document.getElementById("story"),
  meta: () => document.getElementById("meta"),
  file: () => document.getElementById("agentFile"),
  actors: () => document.getElementById("actors"),
  strip: () => document.getElementById("strip"),
  envelope: () => document.getElementById("envelope"),
  talk: () => document.getElementById("talk"),
  beat: () => document.getElementById("beat"),
};

function overlayFor(status) {
  if (status === "thinking") return `<span class="overlay dots"></span>`;
  if (status === "blocked") return `<span class="overlay">!</span>`;
  if (status === "success") return `<span class="overlay">*</span>`;
  return "";
}

function framesMarkup(archetype, accent) {
  const frames = framesFor(archetype, accent, 64);
  return ["idle", "walk", "talk"].map((pose) =>
    `<div class="frames pose-${pose}">${frames[pose].join("")}</div>`
  ).join("");
}

function actorEl(id) {
  return document.querySelector(`.actor-${id}`);
}

function renderActors(agents) {
  const host = els.actors();
  host.innerHTML = agents.map((agent) => {
    const selected = agent.id === state.selected ? "selected" : "";
    const ghost = agent.status.status === "ghost" ? "ghost" : "";
    const home = HOME[agent.id] || HOME.buyer;
    return `<button type="button" class="actor actor-${agent.id} pose-idle face-right ${selected} ${ghost}" data-agent="${agent.id}" style="--accent:${ACCENTS[agent.accent]};--x:${home.x}%;--y:${home.y}%;--z:${10 + Math.round(home.y)};--walk:0ms">
      <div class="actor-bubble" hidden></div>
      <div class="tag-float ${agent.status.status}">${escapeHtml(agent.status.label)}</div>
      ${overlayFor(agent.status.status)}
      <div class="sprite-wrap">${framesMarkup(agent.archetype, agent.accent)}</div>
      <div class="shadow"></div>
      <div class="nameplate">${escapeHtml(agent.name)}${agent.id === "kernel" ? " ★" : ""}</div>
    </button>`;
  }).join("");
  agents.forEach((agent) => {
    state.place[agent.id] = { ...(HOME[agent.id] || HOME.buyer) };
  });
  const kernel = agents.find((a) => a.id === "kernel");
  const portrait = document.getElementById("kernelPortrait");
  if (portrait && kernel) {
    portrait.innerHTML = spriteSVG(SPRITES.wizard, paletteFor("wizard", kernel.accent), 48);
  }
}

function renderStrip(agents) {
  const host = els.strip();
  host.innerHTML = agents.map((agent) => {
    const selected = agent.id === state.selected ? "active" : "";
    const prop = (agent.properties || []).slice(0, 2).map((p) => p[1]).join(" · ");
    const god = agent.id === "kernel" ? `<span class="god">GOD</span>` : "";
    return `<button type="button" class="panel strip-card ${selected}" data-agent="${agent.id}" style="--accent:${ACCENTS[agent.accent]}">
      <div class="row">
        <div class="avatar">${spriteSVG((SPRITES[agent.archetype] || SPRITES.scientist), paletteFor(agent.archetype, agent.accent), 40)}</div>
        <div class="who">
          <div class="name">${escapeHtml(agent.name)}${god}</div>
          <div class="chip ${agent.status.status}"><span class="px"></span>${escapeHtml(agent.status.label)}</div>
        </div>
      </div>
      <div class="meta">${escapeHtml(prop)}</div>
      <div class="bar"><i></i></div>
    </button>`;
  }).join("");
}

function sectionBlock(title, inner, open) {
  return `<section class="section ${open ? "" : "closed"}">
    <button type="button" class="toggle"><span class="dot"></span>${escapeHtml(title)}</button>
    <div class="body">${inner}</div>
  </section>`;
}

function dl(obj) {
  const rows = Object.entries(obj || {}).map(([k, v]) =>
    `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(String(v))}</dd>`
  ).join("");
  return `<dl class="kv">${rows}</dl>`;
}

function renderFile(agent) {
  const host = els.file();
  if (!agent) {
    host.innerHTML = `<p class="file-blurb">Click a person on the floor to open that agent's file.</p>`;
    return;
  }
  const s = agent.sections || {};
  const skills = (s.skills || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  host.style.setProperty("--accent", ACCENTS[agent.accent]);
  const compact = host.classList.contains("compact");
  host.innerHTML = `
    <div class="file-head">
      <span class="accent-dot"></span>
      <div>
        <div class="name">${escapeHtml(agent.name)}</div>
        <div class="role">${escapeHtml(agent.title)}${compact ? " · click to open file" : " · click to hide"}</div>
      </div>
    </div>
    <p class="file-blurb">${escapeHtml(agent.blurb || "")}</p>
    ${sectionBlock("Identity", dl(s.identity), true)}
    ${sectionBlock("Goal", dl(s.goal), true)}
    ${sectionBlock("Runtime", dl(s.runtime), false)}
    ${sectionBlock("Skills", `<ul class="skills">${skills}</ul>`, false)}
    ${sectionBlock("Autonomy", dl(s.autonomy), true)}
  `;
}

function selectAgent(id) {
  state.selected = id;
  const agents = state.floor?.agents || [];
  const agent = agents.find((a) => a.id === id);
  document.querySelectorAll(".actor").forEach((node) => {
    node.classList.toggle("selected", node.dataset.agent === id);
  });
  renderStrip(agents);
  renderFile(agent);
}

function openAgentStation(id) {
  selectAgent(id);
  if (id === "kernel") openInspect("kernel");
  else if (id === "llm") openInspect("advisor");
  else if (id === "buyer" || id === "seller") openInspect("hall", { spot: "desks" });
}

function setPose(id, pose) {
  const node = actorEl(id);
  if (!node || node.classList.contains("walking")) return;
  node.classList.remove("pose-idle", "pose-walk", "pose-talk");
  node.classList.add(`pose-${pose}`);
}

function face(id, dir) {
  const node = actorEl(id);
  if (!node) return;
  node.classList.toggle("face-left", dir === "left");
  node.classList.toggle("face-right", dir !== "left");
}

function faceEachOther(a, b) {
  const pa = state.place[a];
  const pb = state.place[b];
  if (!pa || !pb) return;
  face(a, pa.x <= pb.x ? "right" : "left");
  face(b, pb.x < pa.x ? "right" : "left");
}

function walkDuration(from, to) {
  const dist = Math.hypot(to.x - from.x, to.y - from.y);
  return Math.max(560, Math.min(1500, dist * 18));
}

function setPlace(id, spot, { instant = false, dash = false } = {}) {
  const node = actorEl(id);
  if (!node) return 0;
  const prev = state.place[id] || spot;
  const base = instant ? 0 : walkDuration(prev, spot);
  const ms = dash && base ? Math.max(280, Math.round(base * 0.55)) : base;
  if (!instant && Math.abs(spot.x - prev.x) > 0.4) {
    face(id, spot.x < prev.x ? "left" : "right");
  }
  node.style.setProperty("--walk", `${ms}ms`);
  node.style.setProperty("--x", `${spot.x}%`);
  node.style.setProperty("--y", `${spot.y}%`);
  node.style.setProperty("--z", String(10 + Math.round(spot.y)));
  state.place[id] = { x: spot.x, y: spot.y };
  node.classList.toggle("dashing", Boolean(dash && !instant));
  if (!instant && ms > 0) {
    node.classList.add("walking");
    node.classList.remove("pose-idle", "pose-talk");
    node.classList.add("pose-walk");
  }
  return ms;
}

async function walkTo(id, spot, opts = {}) {
  const ms = setPlace(id, spot, opts);
  if (ms) {
    const hops = Math.max(2, Math.round(ms / 220));
    for (let i = 0; i < hops; i += 1) {
      puffAt(id, opts.dash ? "gold" : "dust", opts.dash ? 4 : 2);
      audio.step();
      await sleep(ms / hops);
    }
  }
  const node = actorEl(id);
  if (node) {
    node.classList.remove("walking");
    node.classList.remove("dashing");
  }
  setPose(id, "idle");
}

async function walkKernelTo(spot, opts = {}) {
  const here = state.place.kernel;
  if (!here) return walkTo("kernel", spot, opts);
  const inOffice = here.y < 38;
  const goingOut = spot.y >= 40;
  if (inOffice && goingOut) {
    setDoor(true);
    await walkTo("kernel", SPOTS.kernelDoor, opts);
  }
  if (!inOffice && spot.y < 38) await walkTo("kernel", SPOTS.kernelDoor, opts);
  await walkTo("kernel", spot, opts);
  if (spot.y < 38) setDoor(false);
}

function setBreach(on) {
  const el = document.getElementById("breach");
  const office = document.getElementById("office");
  if (el) el.hidden = !on;
  if (office) {
    office.classList.toggle("alerting", on);
    if (on) office.classList.remove("cleared");
  }
  if (on) {
    setWatching(false);
    setBanner("BREACH");
    audio.alarm();
    shakeFloor();
  }
}

function paintActor(agent) {
  const node = actorEl(agent.id);
  if (!node) return;
  node.classList.toggle("selected", agent.id === state.selected);
  node.classList.toggle("ghost", agent.status.status === "ghost");
  const tag = node.querySelector(".tag-float");
  if (tag) {
    tag.className = `tag-float ${agent.status.status}`;
    tag.textContent = agent.status.label;
  }
  const overlay = node.querySelector(".overlay");
  const next = overlayFor(agent.status.status);
  if (next && overlay) overlay.outerHTML = next;
  else if (next && !overlay) node.insertAdjacentHTML("afterbegin", next);
  else if (!next && overlay) overlay.remove();
  const strip = document.querySelector(`#strip [data-agent="${agent.id}"]`);
  if (strip) {
    const stripChip = strip.querySelector(".chip");
    if (stripChip) {
      stripChip.className = `chip ${agent.status.status}`;
      stripChip.innerHTML = `<span class="px"></span>${escapeHtml(agent.status.label)}`;
    }
  }
  const line = document.getElementById("kernelLine");
  if (agent.id === "kernel" && line) {
    line.textContent = agent.status.status === "ghost"
      ? "Kernel is disarmed — attacks can land"
      : `${agent.name} runs the floor`;
  }
}

function setAgentStatus(id, status, label) {
  const agent = state.floor?.agents.find((a) => a.id === id);
  if (!agent) return;
  agent.status = { status, label: label || status };
  paintActor(agent);
}

function fillSellers(items, selected) {
  const el = els.seller();
  el.innerHTML = "";
  items.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.label || `${s.id} · ${s.attack_name || "clean"}`;
    el.appendChild(opt);
  });
  el.value = selected;
  if (!el.value && items[0]) el.value = items[0].id;
}

function setOutcome(kind, title, detail) {
  const el = els.outcome();
  el.className = `panel ${kind}`;
  el.innerHTML = `<div class="title">${escapeHtml(title)}</div><div class="detail">${escapeHtml(detail || "")}</div>`;
}

function setMeta(rows) {
  const el = els.meta();
  if (!rows || !rows.length) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  el.hidden = false;
  el.innerHTML = rows.map(([k, v]) => `<div><span>${escapeHtml(k)}</span>${escapeHtml(v || "—")}</div>`).join("");
}

function setBeat(text) {
  const value = text || "";
  const el = els.beat();
  if (el) el.textContent = value;
  const chatBeat = document.getElementById("chatBeat");
  if (chatBeat) chatBeat.textContent = value || "Transcript of the floor conversation.";
}

function setFloorView(mode) {
  const next = mode === "chat" ? "chat" : "floor";
  state.view = next;
  const wrap = document.getElementById("floorWrap");
  const pane = document.getElementById("talkPane");
  if (wrap) wrap.dataset.view = next;
  if (pane) pane.hidden = next !== "chat";
  document.querySelectorAll(".view-btn").forEach((btn) => {
    const active = btn.dataset.view === next;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
  });
  if (next === "chat") {
    const host = els.talk();
    const last = host && host.querySelector(".msg:last-child");
    if (last) last.scrollIntoView({ block: "end" });
  }
}

function closeInspect() {
  state.inspect = null;
  const panel = document.getElementById("inspect");
  if (panel) panel.hidden = true;
  document.querySelectorAll(".hot-spot.active-spot").forEach((n) => n.classList.remove("active-spot"));
}

function stationPayload(id) {
  return state.floor?.world?.stations?.[id] || null;
}

function renderInspectBody(id, spot) {
  const data = stationPayload(id);
  if (!data) {
    return `<p class="inspect-empty">Nothing loaded for this station yet.</p>`;
  }
  if (id === "catalog") {
    if (!(data.items || []).length) {
      return `<p class="inspect-empty">Shelf is empty for this hire.</p>`;
    }
    return data.items.map((item) => `
      <article class="inspect-card">
        <div class="title">${escapeHtml(item.title)}</div>
        <div class="meta">${escapeHtml(item.price)} · stock ${item.stock} · ${escapeHtml(String(item.category || "—"))}${item.wireless ? " · wireless" : ""}</div>
        <div class="desc">${escapeHtml(item.description || "")}</div>
        <div class="meta">${item.reviews ? `${item.reviews} reviews${item.synthetic_reviews ? ` (${item.synthetic_reviews} synthetic)` : ""}` : "no reviews"}</div>
      </article>
    `).join("");
  }
  if (id === "mailbox") {
    if (!(data.messages || []).length) {
      return `<p class="inspect-empty">${escapeHtml(data.empty_hint || "Mailbox empty.")}</p>`;
    }
    return data.messages.map((msg) => `
      <div class="inspect-mail ${escapeHtml(msg.who)}">
        <div class="who">${escapeHtml(msg.kind)} · ${escapeHtml(msg.who)}</div>
        <div class="text">${escapeHtml(msg.text)}</div>
      </div>
    `).join("");
  }
  if (id === "vault") {
    const orders = (data.orders || []).map((o) => `
      <article class="inspect-card">
        <div class="title">${escapeHtml(o.id)}</div>
        <div class="meta">${escapeHtml(o.state)} · ${escapeHtml(o.amount)} · ${escapeHtml(o.seller_id)}</div>
        <div class="desc">product ${escapeHtml(o.product_id)}</div>
      </article>
    `).join("") || `<p class="inspect-empty">No orders in the vault yet.</p>`;
    return `
      <div class="inspect-stats">
        <div class="inspect-stat"><span class="k">wallet</span><span class="v">${escapeHtml(data.wallet)}</span></div>
        <div class="inspect-stat"><span class="k">available</span><span class="v">${escapeHtml(data.available)}</span></div>
        <div class="inspect-stat"><span class="k">on hold</span><span class="v">${escapeHtml(data.held)}</span></div>
        <div class="inspect-stat"><span class="k">rail</span><span class="v">${escapeHtml(data.payment_rail || "—")}</span></div>
      </div>
      ${orders}
    `;
  }
  if (id === "board") {
    if (!(data.events || []).length) {
      return `<p class="inspect-empty">${escapeHtml(data.empty_hint || "Board is blank.")}</p>`;
    }
    return data.events.slice().reverse().map((ev) => `
      <article class="inspect-card">
        <div class="title">#${ev.seq} · ${escapeHtml(ev.event_type)}</div>
        <div class="meta">${escapeHtml(ev.actor)} · hash ${escapeHtml(ev.hash)}</div>
        <div class="desc">${escapeHtml(JSON.stringify(ev.payload || {}))}</div>
      </article>
    `).join("");
  }
  if (id === "kernel") {
    const rules = (data.rules || []).map((r) => `
      <div class="inspect-rule"><code>${escapeHtml(r.id)}</code><span>${escapeHtml(r.label)}</span></div>
    `).join("");
    return `
      <div class="inspect-stats">
        <div class="inspect-stat"><span class="k">guardrails</span><span class="v">${escapeHtml(data.guardrails)}</span></div>
        <div class="inspect-stat"><span class="k">moves money</span><span class="v">yes</span></div>
      </div>
      ${rules}
    `;
  }
  if (id === "advisor") {
    return `
      <div class="inspect-stats">
        <div class="inspect-stat"><span class="k">mode</span><span class="v">${escapeHtml(data.mode)}</span></div>
        <div class="inspect-stat"><span class="k">backend</span><span class="v">${escapeHtml(data.backend)}</span></div>
      </div>
      <article class="inspect-card">
        <div class="title">${escapeHtml(data.llm || "Advisor")}</div>
        <div class="desc">Output is validated and clamped. Garbage → deterministic fallback. Never writes DB rows.</div>
      </article>
    `;
  }
  if (id === "hall") {
    const spots = data.spots || [];
    const focus = spot ? spots.find((s) => s.id === spot) : null;
    const list = (focus ? [focus] : spots).map((s) => `
      <article class="inspect-card">
        <div class="title">${escapeHtml(s.name)}</div>
        <div class="desc">${escapeHtml(s.detail)}</div>
      </article>
    `).join("");
    return list || `<p class="inspect-empty">Empty hall.</p>`;
  }
  return `<p class="inspect-empty">Unknown station.</p>`;
}

function openInspect(id, { spot = null, source = null } = {}) {
  const data = stationPayload(id);
  const panel = document.getElementById("inspect");
  if (!panel || !data) return;
  state.inspect = id;
  document.querySelectorAll(".hot-spot.active-spot").forEach((n) => n.classList.remove("active-spot"));
  if (source) source.classList.add("active-spot");
  else {
    document.querySelectorAll(`[data-inspect="${id}"]`).forEach((n) => n.classList.add("active-spot"));
  }
  document.getElementById("inspectKicker").textContent = "inside · " + id;
  document.getElementById("inspectTitle").textContent = data.name || id;
  document.getElementById("inspectBlurb").textContent = data.blurb || "";
  document.getElementById("inspectBody").innerHTML = renderInspectBody(id, spot);
  panel.hidden = false;
  setBeat(`Opened ${data.name || id}`);
  setTicker(`inspecting ${id}`);
  if (id === "kernel") selectAgent("kernel");
  if (id === "advisor") selectAgent("llm");
}


function hideBubbles() {
  document.querySelectorAll(".actor-bubble").forEach((node) => {
    node.hidden = true;
    node.innerHTML = "";
  });
  markSpeaker(null);
}

function clearTalk() {
  els.talk().innerHTML = "";
  state.speech = {};
  hideBubbles();
  setBeat("Listening…");
}

function messagesFromStep(step) {
  const title = (step.title || "").replace(/^\d+[a-z]?\. /, "");
  const detail = step.detail || "";
  const msgs = [];
  const buyer = detail.match(/Buyer: "([\s\S]*?)"/);
  const seller = detail.match(/Seller: "([\s\S]*?)"/);
  const decision = detail.match(/Buyer decision \(([^)]+)\): ([^\n]+)/);
  if (buyer) msgs.push({ who: "buyer", text: buyer[1], kind: "say" });
  if (seller) msgs.push({ who: "seller", text: seller[1], kind: "say" });
  if (decision) {
    msgs.push({ who: "buyer", text: `decision (${decision[1]}): ${decision[2].trim()}`, kind: "aside" });
  }
  if (!buyer) {
    const accept = detail.match(/Buyer accepts [^\n.]+/);
    if (accept) msgs.unshift({ who: "buyer", text: accept[0], kind: "aside" });
  }
  if (!msgs.length) {
    const who = ["checkout", "refuse", "done"].includes(step.phase) ? "kernel" : "narrator";
    const text = detail ? `${title} — ${detail}` : title;
    msgs.push({ who, text, kind: "beat" });
  }
  return msgs;
}

function showSpeech(who, text) {
  if (!text) return;
  hideBubbles();
  const node = document.querySelector(`.actor-${who} .actor-bubble`);
  if (!node) return;
  state.speech[who] = text;
  node.hidden = false;
  const label = who === "kernel" ? "kernel" : who;
  node.innerHTML = `<div class="tag">${escapeHtml(label)}</div><span class="typed"></span>`;
  typeInto(node, text);
  markSpeaker(who);
  audio.talk();
}

function appendTalk(msg, { fresh = true } = {}) {
  const host = els.talk();
  host.querySelectorAll(".msg.fresh").forEach((n) => n.classList.remove("fresh"));
  const row = document.createElement("div");
  row.className = `msg ${msg.who}${msg.kind === "aside" ? " aside" : ""}${fresh ? " fresh" : ""}`;
  const label = msg.who === "buyer" ? "buyer" : msg.who === "seller" ? "seller" : msg.who === "kernel" ? "kernel" : "";
  row.innerHTML = `${label ? `<div class="who">${label}</div>` : ""}<div class="bubble">${escapeHtml(msg.text)}</div>`;
  host.appendChild(row);
  row.scrollIntoView({ block: "end", behavior: "smooth" });
  if (msg.kind === "say") {
    showSpeech(msg.who, msg.text);
    setPose(msg.who, "talk");
    ["buyer", "seller", "kernel"].forEach((id) => {
      if (id !== msg.who) setPose(id, "idle");
    });
    setTicker(`${msg.who} is talking on the floor`);
  } else if (msg.who === "kernel" && msg.kind === "beat") {
    showSpeech("kernel", msg.text);
    setPose("kernel", "talk");
    markSpeaker("kernel");
    setTicker("kernel is on the line");
  }
}

function pauseFor(msg) {
  if (msg.kind === "say") return 1100;
  if (msg.kind === "aside") return 700;
  if (msg.who === "kernel") return 900;
  return 320;
}

function flyEnvelope() {
  const env = els.envelope();
  const buyer = actorEl("buyer");
  const seller = actorEl("seller");
  const office = document.getElementById("office");
  if (!env || !buyer || !seller || !office) return;
  const f = office.getBoundingClientRect();
  const a = buyer.getBoundingClientRect();
  const b = seller.getBoundingClientRect();
  const x1 = a.left + a.width / 2 - f.left;
  const y1 = a.top + 20 - f.top;
  const x2 = b.left + b.width / 2 - f.left;
  const y2 = b.top + 20 - f.top;
  env.style.display = "block";
  env.classList.add("fly");
  env.animate(
    [
      { transform: `translate(${x1}px, ${y1}px) rotate(-8deg)` },
      { transform: `translate(${(x1 + x2) / 2}px, ${Math.min(y1, y2) - 36}px) rotate(18deg)` },
      { transform: `translate(${x2}px, ${y2}px) rotate(6deg)` },
    ],
    { duration: 520, easing: "linear" }
  );
  audio.mail();
  window.setTimeout(() => {
    env.style.display = "none";
    env.classList.remove("fly");
  }, 530);
}

function defaultStatus(id) {
  if (id === "llm") {
    const llm = state.floor?.agents.find((a) => a.id === "llm");
    if (llm && llm.properties?.some((p) => p[0] === "mode" && p[1] === "OFF")) {
      return ["ghost", "offline"];
    }
  }
  if (id === "kernel" && els.rails().value !== "true") return ["ghost", "disarmed"];
  return ["idle", "idle"];
}

function kernelArmed() {
  return defaultStatus("kernel")[0] !== "ghost";
}

function resetStatuses() {
  ["buyer", "seller", "kernel", "llm"].forEach((id) => {
    const [status, label] = defaultStatus(id);
    setAgentStatus(id, status, label);
  });
}

async function sendHome({ instant = false } = {}) {
  setBreach(false);
  setWatching(false);
  setDoor(false);
  hideBubbles();
  markSpeaker(null);
  document.getElementById("office")?.classList.remove("lit", "cleared", "alerting");
  focusCamera([], 1);
  setBanner("IDLE FLOOR");
  const jobs = Object.keys(HOME).map(async (id) => {
    if (instant) {
      setPlace(id, HOME[id], { instant: true });
      setPose(id, "idle");
      return;
    }
    if (id === "kernel") await walkKernelTo(HOME.kernel);
    else await walkTo(id, HOME[id]);
  });
  await Promise.all(jobs);
  face("kernel", "right");
  face("llm", "left");
  face("buyer", "right");
  face("seller", "left");
}

async function choreograph(phase) {
  if (phase === "setup" || phase === "intent") {
    setBanner("BRIEFING");
    setTicker("buyer walks to advisor");
    focusCamera(["buyer", "llm"], 1.04);
    setAgentStatus("buyer", "thinking", "asking");
    if (defaultStatus("llm")[0] !== "ghost") setAgentStatus("llm", "thinking", "thinking");
    await walkTo("buyer", SPOTS.advisorDoor);
    await walkTo("buyer", HOME.llm);
    faceEachOther("buyer", "llm");
    setPose("buyer", "talk");
    if (defaultStatus("llm")[0] !== "ghost") setPose("llm", "talk");
    shineOn("buyer");
    return;
  }
  if (phase === "discovery") {
    setBanner("CATALOG");
    setTicker("buyer is browsing the shelf");
    focusCamera(["buyer"], 1.05);
    setAgentStatus("buyer", "working", "browsing");
    setPose("llm", "idle");
    await walkTo("buyer", SPOTS.advisorDoor);
    await walkTo("buyer", SPOTS.catalog);
    face("buyer", "right");
    puffAt("buyer", "gold", 6);
    shineOn("buyer");
    return;
  }
  if (phase === "negotiate") {
    setBanner("NEGOTIATING");
    setTicker("buyer and seller meet on the floor");
    if (kernelArmed()) {
      setWatching(true);
      setAgentStatus("kernel", "waiting", "watching");
    }
    setAgentStatus("buyer", "working", "haggling");
    setAgentStatus("seller", "working", "quoting");
    await Promise.all([
      walkTo("buyer", SPOTS.meetBuyer),
      walkTo("seller", SPOTS.meetSeller),
    ]);
    focusCamera(["buyer", "seller"], 1.06);
    faceEachOther("buyer", "seller");
    setPose("buyer", "talk");
    setPose("seller", "talk");
    flyEnvelope();
    return;
  }
  if (phase === "agree") {
    setBanner("HANDSHAKE");
    setTicker("they think they have a deal");
    setAgentStatus("buyer", "success", "deal");
    setAgentStatus("seller", "waiting", "waiting");
    await Promise.all([
      walkTo("buyer", SPOTS.meetBuyer),
      walkTo("seller", SPOTS.meetSeller),
    ]);
    faceEachOther("buyer", "seller");
    puffAt("buyer", "mint", 8);
    puffAt("seller", "mint", 8);
    return;
  }
  if (phase === "checkout") {
    setBanner("VAULT CHECK");
    setTicker("buyer is at the kernel door");
    setWatching(false);
    setAgentStatus("kernel", "working", "checking");
    setAgentStatus("buyer", "waiting", "at the door");
    setDoor(true);
    await Promise.all([
      walkTo("buyer", SPOTS.kernelDoor),
      walkTo("seller", HOME.seller),
    ]);
    focusCamera(["kernel", "buyer"], 1.05);
    face("buyer", "left");
    setPose("kernel", "talk");
    shineOn("kernel");
    return;
  }
  if (phase === "refuse") {
    setAgentStatus("kernel", "blocked", "breach");
    setAgentStatus("buyer", "blocked", "stopped");
    setAgentStatus("seller", "blocked", "caught");
    if (kernelArmed()) {
      setTicker("kernel leaves the office");
      setBreach(true);
      setDoor(true);
      await walkKernelTo(SPOTS.intervene, { dash: true });
      await Promise.all([
        walkTo("buyer", SPOTS.meetBuyer),
        walkTo("seller", SPOTS.meetSeller),
      ]);
      focusCamera(["kernel", "buyer", "seller"], 1.07);
      face("kernel", "right");
      faceEachOther("buyer", "seller");
      setPose("kernel", "talk");
      markSpeaker("kernel");
      puffAt("kernel", "coral", 14);
      puffAt("seller", "coral", 8);
    }
    return;
  }
  if (phase === "done") {
    setBreach(false);
    document.getElementById("office")?.classList.add("cleared");
    setBanner("CLEARED");
    setTicker("kernel signed it off");
    audio.success();
    setAgentStatus("kernel", "success", "cleared");
    setAgentStatus("buyer", "success", "done");
    puffAt("buyer", "mint", 12);
    puffAt("kernel", "gold", 10);
    await walkKernelTo(HOME.kernel);
    await walkTo("buyer", HOME.buyer);
    await walkTo("seller", HOME.seller);
    setDoor(false);
    focusCamera([], 1);
    face("kernel", "right");
  }
}

async function applyPhase(phase) {
  if (state.posePhase !== phase && phase !== "refuse") resetStatuses();
  if (phase === "setup" || phase === "intent") {
    setAgentStatus("buyer", "thinking", "asking");
    if (defaultStatus("llm")[0] !== "ghost") setAgentStatus("llm", "thinking", "thinking");
  } else if (phase === "discovery") {
    setAgentStatus("buyer", "working", "browsing");
  } else if (phase === "negotiate") {
    setAgentStatus("buyer", "working", "haggling");
    setAgentStatus("seller", "working", "quoting");
    if (kernelArmed()) setAgentStatus("kernel", "waiting", "watching");
  } else if (phase === "agree") {
    setAgentStatus("buyer", "success", "deal");
    setAgentStatus("seller", "waiting", "waiting");
  } else if (phase === "checkout") {
    setAgentStatus("kernel", "working", "checking");
    setAgentStatus("buyer", "waiting", "at the door");
  } else if (phase === "refuse") {
    setAgentStatus("kernel", "blocked", "needs you");
    setAgentStatus("buyer", "blocked", "stopped");
    setAgentStatus("seller", "blocked", "caught");
  } else if (phase === "done") {
    setAgentStatus("kernel", "success", "success");
    setAgentStatus("buyer", "success", "success");
  }

  if (state.posePhase === phase) {
    if (phase === "negotiate") {
      faceEachOther("buyer", "seller");
      flyEnvelope();
    }
    return;
  }
  state.posePhase = phase;
  await choreograph(phase);
}

async function loadFloor() {
  const seller = els.seller().value || document.body.dataset.seller || "seller_04";
  const rails = els.rails().value === "true" ? "on" : "off";
  const goal = els.goal().value || "Find a wireless audio product";
  const budget = Number(els.budget().value || 15000);
  const qs = new URLSearchParams({
    seller_id: seller,
    goal,
    budget: String(budget),
    guardrails: rails,
  });
  const res = await fetch("/v1/floor?" + qs.toString());
  const data = await res.json();
  state.floor = data;
  state.posePhase = null;
  fillSellers(data.sellers, data.hired_seller_id);
  renderActors(data.agents);
  renderStrip(data.agents);
  const current = data.agents.find((a) => a.id === state.selected) || data.agents[2];
  state.selected = current.id;
  renderFile(current);
  selectAgent(state.selected);
  if (state.inspect) {
    openInspect(state.inspect);
  }
  return data;
}

async function refreshHealth() {
  const res = await fetch("/health");
  const data = await res.json();
  document.getElementById("railLabel").textContent = data.payment_label || data.payment_rail;
  document.getElementById("llmLabel").textContent = data.llm || "—";
  const talk = document.getElementById("talkModeLabel");
  if (talk) {
    const llm = String(data.llm || "");
    const llmOn = llm && !/^OFF/i.test(llm) && llm !== "—";
    talk.textContent = llmOn ? "live · LLM talk" : "live · rules talk";
  }
  const dot = document.getElementById("railDot");
  dot.className = "dot single " + (data.payment_rail === "razorpay" ? "on" : "off");
  document.getElementById("railsPill").textContent = els.rails().value === "true" ? "ON" : "OFF";
  return data;
}

async function replayStory(steps) {
  clearTalk();
  state.posePhase = null;
  for (let i = 0; i < steps.length; i += 1) {
    const step = steps[i];
    await applyPhase(step.phase);
    setBeat((step.title || "").replace(/^\d+[a-z]?\. /, ""));
    const msgs = messagesFromStep(step);
    for (const msg of msgs) {
      appendTalk(msg);
      await sleep(pauseFor(msg));
    }
  }
}

async function authorize() {
  const btn = document.getElementById("go");
  btn.disabled = true;
  state.running = true;
  setOutcome("idle", "Authorizing…", "Watch the floor — people walk, then they talk.");
  setMeta([]);
  clearTalk();
  setBreach(false);
  audio.ensure();
  state.posePhase = null;
  resetStatuses();
  await sendHome({ instant: true });
  setPlace("buyer", SPOTS.entrance, { instant: true });
  setBanner("ENTERING");
  setTicker("buyer is walking onto the floor");
  focusCamera(["buyer"], 1.04);
  appendTalk({ who: "narrator", text: "Buyer is walking onto the floor…", kind: "beat" }, { fresh: false });
  await walkTo("buyer", HOME.buyer);
  try {
    const res = await fetch("/v1/checkout/authorize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal: els.goal().value,
        budget: Number(els.budget().value || 15000),
        seller_id: els.seller().value,
        guardrails: els.rails().value === "true",
      }),
    });
    const data = await res.json();
    const setup = (data.story || []).find((s) => s.phase === "setup");
    const talkMatch = setup && /Talk:\s*([^·]+)/.exec(setup.detail || "");
    const talkEl = document.getElementById("talkModeLabel");
    if (talkEl) {
      talkEl.textContent = `live · ${(talkMatch ? talkMatch[1] : "rules talk").trim()}`;
    }
    await replayStory(data.story || []);
    await loadFloor();
    setMeta([
      ["Product", data.product_title],
      ["Attack", data.attack_class || "clean"],
      ["Guardrails", data.guardrails ? "ON" : "OFF"],
      ["Amount", data.amount_minor ? money(data.amount_minor) : "—"],
    ]);

    if (!data.allowed) {
      setOutcome("bad", "REFUSED · " + (data.refusal_rule || "blocked"), data.message || "Kernel blocked checkout. Razorpay was not called.");
      await applyPhase("refuse");
      setBeat("Kernel stepped in — read the last yellow line.");
      return;
    }
    if (!data.razorpay_order_id) {
      setOutcome("ok", "ALLOWED · simulated ledger", data.message || "Settled without Razorpay.");
      await applyPhase("done");
      setBeat("Deal closed on the simulated ledger.");
      return;
    }
    setOutcome("warn", "Kernel allowed", "Opening Razorpay Checkout…");
    await applyPhase("done");
    setBeat("Kernel allowed — checkout is opening.");
    const options = {
      key: data.razorpay_key_id,
      amount: data.amount_minor,
      currency: data.currency || "INR",
      name: "Kavach",
      description: data.product_title || "Guardrail-cleared checkout",
      order_id: data.razorpay_order_id,
      handler: async function (response) {
        const confirm = await fetch("/v1/checkout/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(response),
        });
        const settled = await confirm.json();
        if (!confirm.ok) {
          setOutcome("bad", "Capture failed", settled.detail || JSON.stringify(settled));
          return;
        }
        setOutcome("ok", "SETTLED via Razorpay", `Order ${settled.kavach_order_id} · ${settled.state}`);
        setMeta([
          ["Kavach order", settled.kavach_order_id],
          ["State", settled.state],
          ["Razorpay order", data.razorpay_order_id],
          ["Payment", response.razorpay_payment_id],
        ]);
      },
      theme: { color: "#1A1320" },
    };
    const rzp = new Razorpay(options);
    rzp.on("payment.failed", (resp) => {
      setOutcome("bad", "Payment failed", (resp.error && resp.error.description) || "Checkout failed");
    });
    rzp.open();
  } catch (err) {
    setOutcome("bad", "Request failed", String(err));
  } finally {
    btn.disabled = false;
    state.running = false;
  }
}

function wire() {
  document.getElementById("envelope").innerHTML = envelopeSVG();
  ["catalog", "mailbox", "vault", "board"].forEach((id) => {
    const node = document.querySelector(`.st-${id} .sprite`);
    if (node) node.innerHTML = stationSVG(id);
  });

  document.body.addEventListener("click", (ev) => {
    const close = ev.target.closest("#inspectClose");
    if (close) {
      closeInspect();
      return;
    }
    const hot = ev.target.closest("[data-inspect]");
    if (hot && !ev.target.closest("#inspect")) {
      const agent = hot.dataset.agent;
      if (agent) selectAgent(agent);
      openInspect(hot.dataset.inspect, { spot: hot.dataset.spot || null, source: hot });
      return;
    }
    const desk = ev.target.closest("[data-agent]");
    if (desk && desk.classList.contains("actor")) {
      openAgentStation(desk.dataset.agent);
      return;
    }
    if (desk && !desk.dataset.inspect) {
      openAgentStation(desk.dataset.agent);
      return;
    }
    const toggle = ev.target.closest(".section > .toggle");
    if (toggle) toggle.parentElement.classList.toggle("closed");
    const fileHead = ev.target.closest("#agentFile .file-head");
    if (fileHead) {
      els.file().classList.toggle("compact");
      const agent = state.floor?.agents.find((a) => a.id === state.selected);
      if (agent) renderFile(agent);
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeInspect();
  });

  els.seller().addEventListener("change", () => {
    state.selected = "seller";
    loadFloor().catch(() => {});
  });
  els.rails().addEventListener("change", () => {
    document.getElementById("railsPill").textContent = els.rails().value === "true" ? "ON" : "OFF";
    loadFloor().catch(() => {});
  });
  els.goal().addEventListener("change", () => loadFloor().catch(() => {}));
  els.budget().addEventListener("change", () => loadFloor().catch(() => {}));

  document.getElementById("go").onclick = authorize;
  document.getElementById("viewFloor")?.addEventListener("click", () => setFloorView("floor"));
  document.getElementById("viewChat")?.addEventListener("click", () => setFloorView("chat"));
  setFloorView(state.view);
  document.getElementById("soundBtn").onclick = () => {
    audio.muted = !audio.muted;
    localStorage.setItem("kavach-mute", audio.muted ? "1" : "0");
    if (!audio.muted) audio.ensure();
    syncSoundBtn();
  };
  syncSoundBtn();
  document.getElementById("health").onclick = async () => {
    const data = await refreshHealth();
    setOutcome("idle", "Gateway healthy", `${data.payment_label} · ${data.llm}`);
    setMeta([
      ["Payment rail", data.payment_rail],
      ["Guardrails default", String(data.guardrails_default)],
      ["LLM", data.llm],
      ["OK", String(data.ok)],
    ]);
  };

  els.seller().value = document.body.dataset.seller || "seller_04";
  els.rails().value = document.body.dataset.guardrails || "true";
  document.getElementById("railsPill").textContent = els.rails().value === "true" ? "ON" : "OFF";

  loadFloor().catch(() => {});
  refreshHealth().catch(() => {});
}

document.addEventListener("DOMContentLoaded", wire);
