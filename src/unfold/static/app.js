"use strict";

const LEVELS = {
  highschool: "high school students",
  undergrad: "undergraduates",
  grad: "graduate students",
  expert: "experts",
};

const DOING = {
  paper: "Reading the paper",
  concepts: "Pulling out the key ideas",
  story: "Planning the story",
  storyboard: "Storyboarding every beat",
  voice: "Recording the narration",
  scenes: "Animating and reviewing scenes",
  video: "Assembling the video",
  review: "Reviewing the finished video",
  done: "Finished",
};

const SCENE_STATES = {
  planned: "Planned",
  voiced: "Narration recorded",
  coded: "Code written",
  rendered: "Rendered, waiting for review",
  revising: "Being revised",
  passed: "Passed review",
};

const SCORES = {
  clarity: "Clarity",
  visual: "Visuals",
  correctness: "Correctness",
  polish: "Polish",
  pacing: "Pacing",
  narration: "Narration",
};

const ACCENTS = { af: "American", am: "American", bf: "British", bm: "British" };
const LEGEND = ["rendered", "revising", "passed"];

const KEYS = [
  [
    "anthropic",
    "Anthropic",
    "Makes videos and answers questions. Not needed if you are signed in to Claude Code.",
    "sk-ant-…",
  ],
  ["openai", "OpenAI", "Adds OpenAI narration voices.", "sk-…"],
  [
    "elevenlabs",
    "ElevenLabs",
    "Adds the voices in your ElevenLabs account.",
    "Your ElevenLabs API key",
  ],
];

const app = document.getElementById("app");
const images = new Map();
const ruler = document.createElement("canvas").getContext("2d");
let stopPolling = () => {};

function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style") {
      for (const [name, v] of Object.entries(value)) el.style.setProperty(name, v);
    }
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key in el && typeof value !== "string") el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  el.append(...children.flat(Infinity).filter((c) => c != null && c !== false));
  return el;
}

async function api(path, { method = "GET", body, headers = {} } = {}) {
  const init = { method, headers: { ...headers } };
  if (method !== "GET") init.headers["X-Unfold"] = "1";
  if (body instanceof Blob) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `The server answered ${response.status}.`);
  return data;
}

function poll(task, ms) {
  let timer = null;
  let live = true;
  const tick = async () => {
    let again = true;
    try {
      again = await task();
    } catch (err) {
      console.error(err);
    }
    if (live && again !== false) timer = setTimeout(tick, ms);
  };
  stopPolling = () => {
    live = false;
    clearTimeout(timer);
  };
  timer = setTimeout(tick, ms);
}

const media = (name, path) => `/media/${encodeURIComponent(name)}/${path}`;
const backLink = () => h("a", { class: "back", href: "#/" }, "‹ All videos");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function clock(seconds) {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function ago(epoch) {
  const minutes = Math.round((Date.now() / 1000 - epoch) / 60);
  if (minutes < 1) return "just now";
  if (minutes < 90) return `${plural(minutes, "minute")} ago`;
  return `${plural(Math.round(minutes / 60), "hour")} ago`;
}

function listing(items) {
  if (items.length < 2) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

function voiceLabel(voice) {
  const [backend, rest = ""] = voice.split(":");
  const name = rest.split("@")[0];
  if (backend === "kokoro") {
    const [kind, who] = name.split("_");
    return who ? `${who[0].toUpperCase()}${who.slice(1)} (${ACCENTS[kind] || "Kokoro"})` : name;
  }
  if (backend === "openai") return `${name[0].toUpperCase()}${name.slice(1)} (OpenAI)`;
  return backend === "say" ? `${name} (macOS)` : voice;
}

function fit(el) {
  const isSelect = el.tagName === "SELECT";
  const text = isSelect ? el.selectedOptions[0]?.textContent : el.value || el.placeholder;
  const style = getComputedStyle(el);
  ruler.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
  el.style.width = `${Math.ceil(ruler.measureText(text || "").width) + (isSelect ? 30 : 12)}px`;
}

function frame(name, path) {
  const src = media(name, path);
  if (!images.has(src)) images.set(src, h("img", { src, alt: "", loading: "lazy" }));
  return images.get(src);
}

function route() {
  stopPolling();
  app.replaceChildren();
  document.title = "Unfold";
  const match = location.hash.match(/^#\/v\/(.+)$/);
  if (match) showVideo(decodeURIComponent(match[1]));
  else if (location.hash === "#/keys") showKeys();
  else showLibrary();
  window.scrollTo(0, 0);
}

// Library

async function showLibrary() {
  const shelf = h("section", { class: "shelf", "aria-label": "Your videos" });
  app.append(brief(), shelf);
  let shown = "";
  const refresh = async () => {
    const videos = await api("/api/videos");
    const snapshot = JSON.stringify(videos);
    if (snapshot !== shown) {
      shown = snapshot;
      const empty = h("p", { class: "shelf__empty" }, "Your videos will appear here.");
      shelf.replaceChildren(...(videos.length ? videos.map(card) : [empty]));
    }
    return videos.some((v) => v.job?.state === "running");
  };
  if (await refresh()) poll(refresh, 5000);
}

function card(video) {
  const working = video.job?.state === "running";
  const image = (file, props) =>
    h("img", { src: media(video.name, file), alt: "", loading: "lazy", ...props });
  const cover = () => h("div", { class: "card__poster card__poster--making" },
    image("cover.png"), strip(video.scene_states));
  const poster = video.final && !working
    ? image("poster.jpg", { class: "card__poster" })
    : cover();
  return h(
    "a",
    { class: "card", href: `#/v/${encodeURIComponent(video.name)}` },
    poster,
    h("h2", { class: "card__title" }, video.title),
    h("p", { class: working ? "card__meta is-working" : "card__meta" }, cardLine(video)),
  );
}

function cardLine(video) {
  const state = video.job?.state;
  if (state === "running") return progressLine(video);
  if (video.final) {
    const length = video.duration ? `${clock(video.duration)} for ` : "For ";
    return `${length}${LEVELS[video.level] || video.level}`;
  }
  const doing = DOING[video.stage].toLowerCase();
  if (state === "failed") return `Stopped with an error while ${doing}`;
  if (state === "stopped") return `Stopped while ${doing}`;
  return `Paused before ${doing}`;
}

function progressLine(video) {
  if (video.stage !== "scenes") return DOING[video.stage];
  const passed = video.scene_states.filter((s) => s === "passed").length;
  return `${DOING.scenes}: ${passed} of ${video.scene_states.length} passed`;
}

function strip(states) {
  const blocks = states.map((state) => h("span", { "data-state": state }));
  return h("div", { class: "strip", "aria-hidden": "true" }, blocks);
}

function brief() {
  let uploaded = null;
  const source = h("input", {
    name: "source",
    autocomplete: "off",
    spellcheck: "false",
    placeholder: "arXiv link or ID, like 2307.15771",
    "aria-labelledby": "brief-title",
  });
  const picker = h("input", { type: "file", accept: "application/pdf,.pdf", hidden: true });
  const choose = h("button", { type: "button", class: "quiet" }, "Choose a PDF");
  const paper = h("div", { class: "brief__paper" }, source, choose, picker);
  const levels = Object.entries(LEVELS).map(([value, label]) =>
    h("option", { value, selected: value === "grad" }, label));
  const level = h("select", { name: "level", "aria-label": "Audience" }, levels);
  const minutes = h("input", {
    type: "number",
    name: "minutes",
    min: 1,
    max: 20,
    value: 5,
    "aria-label": "Minutes",
  });
  const focus = h("input", {
    type: "text",
    name: "focus",
    placeholder: "the whole paper",
    "aria-label": "Focus",
  });
  const voice = h(
    "select",
    { name: "voice", "aria-label": "Narrator" },
    h("option", { value: "" }, "default voice"),
  );
  const submit = h("button", { class: "button button--primary", type: "submit" }, "Make video");
  const note = h("p", { class: "brief__note", role: "status" });

  const say = (text, isError = false) => {
    note.className = isError ? "brief__note error" : "brief__note";
    note.textContent = text;
  };

  const usePdf = async (file) => {
    if (!file) return;
    say(`Uploading ${file.name}…`);
    try {
      const saved = await api("/api/papers", {
        method: "POST",
        body: file,
        headers: { "X-Filename": encodeURIComponent(file.name) },
      });
      uploaded = saved.source;
      source.value = file.name;
      source.readOnly = true;
      choose.textContent = "Use a link instead";
      say("");
    } catch (err) {
      say(err.message, true);
    }
  };

  choose.addEventListener("click", () => {
    if (!uploaded) return picker.click();
    uploaded = null;
    source.value = "";
    source.readOnly = false;
    choose.textContent = "Choose a PDF";
    source.focus();
  });
  picker.addEventListener("change", () => usePdf(picker.files[0]));
  paper.addEventListener("dragover", (event) => {
    event.preventDefault();
    paper.classList.add("is-dragging");
  });
  paper.addEventListener("dragleave", () => paper.classList.remove("is-dragging"));
  paper.addEventListener("drop", (event) => {
    event.preventDefault();
    paper.classList.remove("is-dragging");
    usePdf(event.dataTransfer.files[0]);
  });

  const fitted = [level, focus, voice];
  for (const el of fitted) {
    el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => fit(el));
  }
  requestAnimationFrame(() => fitted.forEach(fit));

  api("/api/voices").then((voices) => {
    voice.firstChild.textContent = voiceLabel(voices.default);
    const group = (label, list) => {
      const named = (v) => (typeof v === "string"
        ? { value: v, name: voiceLabel(v) }
        : { value: v.value, name: `${v.name} (ElevenLabs)` });
      const options = list
        .map(named)
        .filter((v) => v.value !== voices.default)
        .map((v) => h("option", { value: v.value }, v.name));
      return options.length ? h("optgroup", { label }, options) : null;
    };
    voice.append(...[
      group("Kokoro, on this Mac", voices.kokoro),
      group("macOS", voices.say),
      group("OpenAI", voices.openai),
      group("ElevenLabs", voices.elevenlabs),
    ].filter(Boolean));
    fit(voice);
  });

  const start = async (event) => {
    event.preventDefault();
    submit.disabled = true;
    say(uploaded ? "Reading the PDF…" : "Downloading the paper from arXiv…");
    try {
      const made = await api("/api/videos", {
        method: "POST",
        body: {
          source: uploaded || source.value,
          level: level.value,
          minutes: minutes.value,
          focus: focus.value,
          voice: voice.value,
        },
      });
      location.hash = `#/v/${encodeURIComponent(made.name)}`;
    } catch (err) {
      say(err.message, true);
      submit.disabled = false;
    }
  };

  return h(
    "form",
    { class: "brief", onsubmit: start },
    h("h1", { id: "brief-title" }, "Make a video from a paper"),
    paper,
    h("p", { class: "brief__sentence" },
      "Explain it to ", level, " in about ", minutes, " minutes, ",
      "focusing on ", focus, ", narrated by ", voice, "."),
    h("div", { class: "brief__actions" }, submit, note),
  );
}

// Keys

async function showKeys() {
  document.title = "Keys – Unfold";
  const rows = h("div", { class: "keys" });
  app.append(
    backLink(),
    h("h1", { class: "title" }, "Your keys"),
    h("p", { class: "byline" },
      "Unfold runs on your own accounts. Keys are saved on this Mac in ",
      "~/.config/unfold/keys.json, readable only by you, and each is sent only to the ",
      "service it belongs to."),
    rows,
  );
  const render = (status) =>
    rows.replaceChildren(...KEYS.map((entry) => keyRow(entry, status[entry[0]], render)));
  render(await api("/api/keys"));
}

function keyRow([provider, name, use, placeholder], info, render) {
  const input = h("input", {
    type: "password",
    autocomplete: "off",
    spellcheck: "false",
    placeholder,
    "aria-label": `${name} key`,
  });
  const where = info.source === "environment" ? "Set in your environment" : "Saved";
  const state = info.set ? `${where}, ends in ${info.ends}` : "Not set";
  const note = h("p", { class: "key__note", role: "status" }, state);
  const save = async (key) => {
    try {
      render(await api("/api/keys", { method: "POST", body: { provider, key } }));
    } catch (err) {
      note.className = "key__note error";
      note.textContent = err.message;
    }
  };
  const submit = (event) => {
    event.preventDefault();
    if (input.value.trim()) save(input.value);
  };
  const remove = info.source === "saved"
    ? h("button", { class: "button", type: "button", onclick: () => save("") }, "Remove")
    : null;
  return h(
    "form",
    { class: "key", onsubmit: submit },
    h("div", null, h("h2", null, name), h("p", null, use)),
    h("div", { class: "key__field" },
      input, h("button", { class: "button button--primary", type: "submit" }, "Save"), remove),
    note,
  );
}

// One video

async function showVideo(name) {
  let video;
  try {
    video = await api(`/api/videos/${encodeURIComponent(name)}`);
  } catch (err) {
    app.append(backLink(), h("p", { class: "error" }, err.message));
    return;
  }
  document.title = `${video.title} – Unfold`;
  if (video.final && video.job?.state !== "running") watch(video);
  else making(video);
}

function header(video) {
  const authors = video.authors.length > 3
    ? `${video.authors.slice(0, 2).join(", ")} and ${video.authors.length - 2} others`
    : listing(video.authors);
  const paper = video.paper_title || video.title;
  const link = /^https?:\/\//i.test(video.url || "") ? video.url : null;
  return [
    backLink(),
    h("h1", { class: "title" }, video.title),
    h("p", { class: "byline" },
      "From ",
      link ? h("a", { href: link, target: "_blank", rel: "noopener noreferrer" }, paper) : paper,
      authors && ` by ${authors}`,
      video.published && `, ${video.published.slice(0, 4)}`,
      "."),
  ];
}

function spansFromChapters(video) {
  const marks = video.chapters.chapters;
  if (!marks.length) return spansFromScenes(video.scenes);
  const total = video.chapters.duration || marks.at(-1).start + (video.scenes.at(-1)?.seconds || 0);
  return marks.map((mark, i) => ({
    start: mark.start,
    end: i + 1 < marks.length ? marks[i + 1].start : total,
    title: mark.title,
    scene: video.scenes[i],
  }));
}

function spansFromScenes(scenes) {
  let t = 0;
  return scenes.map((scene) => {
    const span = { start: t, end: t + scene.seconds, title: scene.title, scene };
    t = span.end;
    return span;
  });
}

function timeline(name, spans, { onPick, showState = false } = {}) {
  const head = h("div", { class: "timeline__playhead", hidden: true });
  const blocks = spans.map((span, i) => {
    const length = Math.max(span.end - span.start, 0.5).toFixed(2);
    const state = span.scene?.state;
    const label = showState
      ? `Scene ${i + 1}, ${span.title}: ${SCENE_STATES[state] || state}`
      : `${span.title}, at ${clock(span.start)}`;
    return h(
      "button",
      {
        class: "scene",
        type: "button",
        style: { "--length": length },
        "data-state": showState ? state : null,
        title: label,
        "aria-label": label,
        tabindex: onPick ? null : "-1",
        onclick: onPick ? () => onPick(span) : null,
      },
      span.scene?.frame ? frame(name, span.scene.frame) : null,
    );
  });
  const now = onPick ? h("p", { class: "timeline__now" }) : null;
  const track = h("div", { class: "timeline__track" }, blocks, head);
  const el = h("div", { class: "timeline" }, track, now);

  let current = -1;
  const update = (t) => {
    const i = spans.findIndex((span) => t >= span.start && t < span.end);
    if (i < 0) return;
    if (i !== current) {
      blocks[current]?.classList.remove("is-current");
      blocks[i].classList.add("is-current");
      current = i;
      if (now) now.textContent = `Chapter ${i + 1} of ${spans.length}: ${spans[i].title}`;
    }
    const block = blocks[i];
    const share = (t - spans[i].start) / (spans[i].end - spans[i].start);
    head.hidden = false;
    head.style.left = `${block.offsetLeft + share * block.offsetWidth}px`;
  };
  return { el, update };
}

function transcript(lines, spans, seek) {
  const scroll = h("div", { class: "transcript__scroll" });
  const items = lines.map((line) =>
    h("button", { class: "line", type: "button", onclick: () => seek(line.start) }, line.text));
  let next = 0;
  for (const span of spans) {
    const heading = h("button", { type: "button", onclick: () => seek(span.start) }, span.title);
    scroll.append(h("h3", null, heading));
    while (next < lines.length && lines[next].start < span.end - 0.01) scroll.append(items[next++]);
  }
  scroll.append(...items.slice(next));
  if (!lines.length) {
    scroll.append(h("p", { class: "feed__empty" }, "No transcript for this video."));
  }

  let current = -1;
  const update = (t) => {
    const i = lines.findIndex((line) => t >= line.start && t < line.end);
    if (i < 0 || i === current) return;
    items[current]?.classList.remove("is-current");
    items[i].classList.add("is-current");
    current = i;
    scroll.scrollTo({ top: items[i].offsetTop - scroll.clientHeight / 3 });
  };
  return { el: h("aside", { class: "transcript", "aria-label": "Transcript" }, scroll), update };
}

// Questions while watching

function inline(text, seek) {
  const parts = [];
  const pattern = /\[(\d+):(\d{2})\]|\*\*([^*]+)\*\*|\*([^*\s][^*]*)\*|`([^`]+)`/g;
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    parts.push(text.slice(last, m.index));
    if (m[1]) {
      const at = Number(m[1]) * 60 + Number(m[2]);
      const label = `${m[1]}:${m[2]}`;
      parts.push(h("button", { class: "stamp", type: "button", onclick: () => seek(at) }, label));
    } else if (m[3]) parts.push(h("strong", null, m[3]));
    else if (m[4]) parts.push(h("em", null, m[4]));
    else parts.push(h("code", null, m[5]));
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return parts;
}

function richText(text, seek) {
  return text.trim().split(/\n{2,}/).map((block) => {
    const lines = block.split("\n");
    const bullet = /^\s*([-*•]|\d+\.) /;
    if (lines.every((line) => bullet.test(line))) {
      const items = lines.map((line) => h("li", null, inline(line.replace(bullet, ""), seek)));
      return h("ul", null, items);
    }
    return h("p", null, inline(block, seek));
  });
}

async function streamAnswer(name, payload, onEvent, signal) {
  const response = await fetch(`/api/videos/${encodeURIComponent(name)}/ask`, {
    method: "POST",
    headers: { "X-Unfold": "1", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `The server answered ${response.status}.`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end;
    while ((end = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, end).trim();
      buffer = buffer.slice(end + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
}

function remembered(name) {
  try {
    return JSON.parse(localStorage.getItem(`unfold:questions:${name}`)) || [];
  } catch {
    return [];
  }
}

function remember(name, asked) {
  try {
    localStorage.setItem(`unfold:questions:${name}`, JSON.stringify(asked.slice(0, 30)));
  } catch {
    // private windows and full storage just mean the questions are not kept
  }
}

function questions(video, player, spans) {
  const asked = remembered(video.name);
  const hint = h("p", { class: "ask__hint" });
  const chips = h("div", { class: "ask__chips" });
  const input = h("input", {
    name: "question",
    autocomplete: "off",
    placeholder: "Ask about what you're watching",
    "aria-label": "Your question",
  });
  const submit = h("button", { class: "button button--primary", type: "submit" }, "Ask");
  const thread = h("ol", { class: "thread", "aria-live": "polite" });
  let suggested = null;
  let scene = -1;
  let running = null;

  const seek = (t) => {
    player.currentTime = t;
    player.play();
  };
  const sceneAt = (t) => Math.max(0, spans.findIndex((span) => t >= span.start && t < span.end));

  const card = (item, { latest = false } = {}) => {
    const answer = h("div", { class: "qa__a" }, item.a ? richText(item.a, seek) : null);
    const when = h("button", { class: "qa__when", type: "button", onclick: () => seek(item.at) },
      `Asked at ${clock(item.at)}, during ${item.title}`);
    const play = () => player.play();
    const resume = latest
      ? h("button", { class: "quiet", type: "button", onclick: play }, "Keep watching")
      : null;
    const el = h("li", { class: "qa" }, h("p", { class: "qa__q" }, item.q), when, answer, resume);
    return { el, answer };
  };

  const showChips = () => {
    const id = video.scenes[scene]?.id;
    const list = suggested?.[id] || [];
    const chip = (q) => h("button", { class: "chip", type: "button", onclick: () => ask(q) }, q);
    chips.replaceChildren(...list.map(chip));
  };

  const ask = async (question) => {
    question = question.trim();
    if (!question || running) return;
    player.pause();
    input.value = "";
    const at = player.currentTime;
    const item = { q: question, a: "", at, title: spans[sceneAt(at)]?.title || "the video" };
    const { el, answer } = card(item, { latest: true });
    thread.querySelectorAll(".qa .quiet").forEach((b) => b.remove());
    thread.prepend(el);
    answer.classList.add("is-writing");
    running = new AbortController();
    submit.textContent = "Stop";
    const history = asked.slice(0, 3).reverse();
    let finished = false;
    try {
      await streamAnswer(video.name, { question, at, history }, (event) => {
        if (event.text) {
          item.a += event.text;
          answer.replaceChildren(...richText(item.a, seek));
        } else if (event.done) {
          finished = true;
        } else if (event.error) {
          answer.append(h("p", { class: "error" }, event.error));
        }
      }, running.signal);
    } catch (err) {
      answer.append(h("p", { class: err.name === "AbortError" ? "qa__stopped" : "error" },
        err.name === "AbortError" ? "Stopped." : err.message));
    } finally {
      answer.classList.remove("is-writing");
      running = null;
      submit.textContent = "Ask";
      if (finished) {
        asked.unshift(item);
        remember(video.name, asked);
      }
    }
  };

  const loadSuggestions = async () => {
    const url = `/api/videos/${encodeURIComponent(video.name)}/questions`;
    let state = await api(url);
    if (state.state === "missing") state = await api(url, { method: "POST" });
    if (state.state === "working") {
      hint.textContent = "Writing suggested questions for each scene…";
      setTimeout(loadSuggestions, 3000);
      return;
    }
    if (state.state === "ready") {
      suggested = state.scenes;
      hint.textContent = "Suggested for this scene";
      showChips();
    } else {
      hint.textContent = "";
    }
  };
  loadSuggestions().catch(() => (hint.textContent = ""));

  asked.forEach((item) => thread.append(card(item).el));
  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);
    if (event.key === "/" && !typing) {
      event.preventDefault();
      input.focus();
    }
  });

  const form = h("form", {
    class: "ask__bar",
    onsubmit: (event) => {
      event.preventDefault();
      if (running) running.abort();
      else ask(input.value);
    },
  }, input, submit);

  return {
    el: h("section", { class: "ask", "aria-label": "Ask about the video" },
      hint, chips, form, thread),
    update(t) {
      const i = sceneAt(t);
      if (i !== scene) {
        scene = i;
        showChips();
      }
    },
  };
}

function watch(video) {
  const player = h(
    "video",
    {
      class: "player",
      controls: true,
      preload: "metadata",
      poster: media(video.name, "poster.jpg"),
      src: media(video.name, `final/${encodeURIComponent(video.final)}`),
    },
    h("track", {
      kind: "captions",
      src: media(video.name, "captions.vtt"),
      srclang: "en",
      label: "English",
    }),
  );
  const seek = (t) => {
    player.currentTime = t;
    player.play();
  };
  const spans = spansFromChapters(video);
  const line = timeline(video.name, spans, { onPick: (span) => seek(span.start) });
  const text = transcript(video.transcript, spans, seek);
  const asking = questions(video, player, spans);
  player.addEventListener("timeupdate", () => {
    line.update(player.currentTime);
    text.update(player.currentTime);
    asking.update(player.currentTime);
  });
  app.append(
    ...header(video),
    h("div", { class: "watch" },
      h("div", { class: "watch__main" }, player, line.el), text.el, asking.el),
    about(video),
  );
  line.update(0);
  asking.update(0);
}

function sentence(parts) {
  const text = listing(parts);
  return text ? `${text[0].toUpperCase()}${text.slice(1)}.` : "";
}

function mathSummary(counts) {
  const parts = [];
  if (counts.matched) {
    const verb = counts.matched === 1 ? "matches" : "match";
    parts.push(`${plural(counts.matched, "equation")} ${verb} the paper`);
  }
  if (counts.verified) parts.push(`${plural(counts.verified, "added step")} checked with SymPy`);
  if (counts.unchecked) parts.push(`${plural(counts.unchecked, "step")} to read yourself`);
  if (counts.FAILED) parts.push(`${counts.FAILED} failed the check`);
  if (counts.illustration) parts.push(plural(counts.illustration, "illustration"));
  return sentence(parts) || "No equations on screen.";
}

function about(video) {
  const scores = video.review?.scores;
  const file = (name) => media(video.name, `final/${encodeURIComponent(name)}`);
  const claim = (heading, text) =>
    [h("h2", null, heading), h("p", { class: "about__claim" }, text)];
  const link = (href, label, props) => h("a", { class: "button", href, ...props }, label);
  const mathClass = video.math.FAILED || video.math.unchecked ? "error" : null;
  return h(
    "section",
    { class: "about" },
    h("div", null,
      video.question && claim("The question", video.question),
      video.insight && claim("The answer", video.insight)),
    h("div", null,
      scores && [
        h("h2", null, "Reviewer's scores"),
        h("dl", { class: "scores" },
          Object.entries(SCORES).filter(([key]) => key in scores).map(([key, label]) => [
            h("dt", null, label),
            h("dd", { "aria-label": `${scores[key]} out of 5` },
              [1, 2, 3, 4, 5].map((n) => h("span", { class: n <= scores[key] ? "is-on" : null }))),
          ])),
      ],
      h("h2", null, "Math on screen"),
      h("p", { class: mathClass }, mathSummary(video.math)),
      h("h2", null, "Files"),
      h("div", { class: "files" },
        link(file(video.final), "Download video", { download: video.final }),
        link(file(video.final.replace(/\.mp4$/, ".srt")), "Subtitles", { download: "" }),
        link(media(video.name, "paper/paper.pdf"), "Paper", { target: "_blank" }))),
  );
}

// Making a video

function making(video) {
  const status = h("div", { class: "status" });
  const steps = h("ol", { class: "stages" });
  const scenes = h("section", { "aria-label": "Scenes" });
  const feed = h("ol", { class: "feed" });
  app.append(
    ...header(video),
    status,
    h("div", { class: "making" },
      h("section", { "aria-label": "Steps" }, steps),
      h("div", null, scenes, h("section", null, h("h2", null, "Latest steps"), feed))),
  );

  let shown = {};
  const render = (v) => {
    showStatus(status, v);
    steps.replaceChildren(...v.stages.map((stage, i) => {
      const isCurrent = !stage.done && v.stages.slice(0, i).every((s) => s.done);
      const state = stage.done ? "is-done" : isCurrent ? "is-current" : null;
      return h("li", { class: state }, stage.label);
    }));
    const sceneKey = JSON.stringify(v.scenes);
    if (sceneKey !== shown.scenes) {
      shown.scenes = sceneKey;
      const passed = v.scenes.filter((s) => s.state === "passed").length;
      scenes.replaceChildren(...(v.scenes.length ? [
        h("h2", null, `Scenes, ${passed} of ${v.scenes.length} passed review`),
        timeline(v.name, spansFromScenes(v.scenes), { showState: true }).el,
        h("ul", { class: "legend" },
          LEGEND.map((state) => h("li", { "data-state": state }, SCENE_STATES[state]))),
      ] : []));
    }
    const feedKey = JSON.stringify(v.activity);
    if (feedKey !== shown.feed) {
      shown.feed = feedKey;
      const pinned = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 40;
      feed.replaceChildren(...(v.activity.length
        ? v.activity.map((item) => h("li", { class: `feed__${item.kind}` }, item.text))
        : [h("li", { class: "feed__empty" }, "Claude's steps will show up here once it starts.")]));
      if (pinned) feed.scrollTop = feed.scrollHeight;
    }
  };

  render(video);
  if (video.job?.state !== "running") return;
  poll(async () => {
    const v = await api(`/api/videos/${encodeURIComponent(video.name)}`);
    if (v.job?.state !== "running") {
      route();
      return false;
    }
    render(v);
    return true;
  }, 3000);
}

function showStatus(status, video) {
  const job = video.job;
  const key = JSON.stringify([job?.state, progressLine(video), job?.message]);
  if (status.dataset.key === key) {
    const since = status.querySelector(".status__since");
    if (since && job?.state === "running") since.textContent = `Started ${ago(job.started)}`;
    return;
  }
  status.dataset.key = key;
  const act = (action) => async (event) => {
    event.target.disabled = true;
    try {
      await api(`/api/videos/${encodeURIComponent(video.name)}/${action}`, { method: "POST" });
      route();
    } catch (err) {
      status.append(h("p", { class: "error" }, err.message));
      event.target.disabled = false;
    }
  };
  const button = (label, action) =>
    h("button", { class: "button", type: "button", onclick: act(action) }, label);
  const line = (dot, text) => h("p", null, h("span", { class: `dot dot--${dot}` }), text);

  if (job?.state === "running") {
    status.replaceChildren(
      line("running", progressLine(video)),
      h("p", { class: "status__since" }, `Started ${ago(job.started)}`),
      button("Stop", "stop"),
    );
  } else if (job?.state === "failed") {
    status.replaceChildren(line("failed", "Stopped with an error"), button("Try again", "start"),
      job.message && h("p", { class: "status__since" }, job.message.slice(0, 400)));
  } else if (job?.state === "stopped") {
    const doing = DOING[video.stage].toLowerCase();
    status.replaceChildren(line("idle", `Stopped while ${doing}`), button("Continue", "start"));
  } else if (job?.state === "done") {
    const ended = "The last run ended before the video was done";
    status.replaceChildren(line("idle", ended), button("Continue", "start"));
  } else {
    status.replaceChildren(line("idle", "Not started yet"), button("Start", "start"));
  }
}

window.addEventListener("hashchange", route);
route();
