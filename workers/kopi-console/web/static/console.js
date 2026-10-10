const confirmDialog = document.getElementById("confirm");
const uploadForm = document.querySelector("[data-upload]");
const LEADING_SYMBOLS = /^[\s▶✓✗⚠·─]+/;
const COUNTER = /(\d+)\s*\/\s*(\d+)/g;
const SECONDS_PER_MINUTE = 60;
const ITEM_PREFIX = "kopi-item: ";
const ADDRESS_GROUPS = {
  service: "Services",
  computer: "On this computer",
  cloud: "Your own cloud",
};
const MENU_STEPS = {
  ArrowDown: 1,
  ArrowUp: -1,
};
const openedMenu = {menu: null, anchor: null, pick: null};

const THEME_NAMES = {
  system: "Theme: follows the system",
  light: "Theme: light",
  dark: "Theme: dark",
};

const AFTER_SEND = {
  run: showRun,
  stop: function () {},
  answer: clearAnswer,
};


// ---- Forms ----

document.addEventListener("submit", function (event) {
  const form = event.target;
  if (form.dataset.confirm && form.dataset.confirmed !== "yes") {
    event.preventDefault();
    askFirst(form);
    return;
  }
  form.dataset.confirmed = "";
  if (form.dataset.fetch) {
    event.preventDefault();
    sendForm(form);
  }
});

document.addEventListener("click", function (event) {
  if (event.target.tagName === "DIALOG") {
    event.target.close();
    return;
  }
  if (event.target.closest("[data-theme-toggle]")) {
    cycleTheme();
  }
  const opener = event.target.closest("[data-open]");
  if (opener) {
    document.getElementById(opener.dataset.open).showModal();
  }
  const closer = event.target.closest("[data-close]");
  if (closer) {
    closer.closest("dialog").close();
  }
  const runClose = event.target.closest("[data-run-close]");
  if (runClose) {
    closeRun(runClose.closest(".run"));
  }
  const dismiss = event.target.closest("[data-dismiss]");
  if (dismiss) {
    dismiss.closest(".snackbar").remove();
  }
});

function askFirst(form) {
  document.getElementById("confirm-text").textContent = form.dataset.confirm;
  document.getElementById("confirm-detail").textContent = form.dataset.confirmDetail || "";
  document.getElementById("confirm-button").textContent = form.dataset.confirmButton || "Run";
  confirmDialog.returnValue = "";
  confirmDialog.onclose = function () {
    if (confirmDialog.returnValue === "ok") {
      form.dataset.confirmed = "yes";
      form.requestSubmit();
    }
  };
  confirmDialog.showModal();
}

async function sendForm(form) {
  let data;
  try {
    const response = await fetch(form.action, {method: "POST", body: new FormData(form)});
    data = await response.json();
  } catch (error) {
    showMessage("The console did not accept that. Reload the page and try again.");
    return;
  }
  if (data.error) {
    showMessage(data.error);
    return;
  }
  AFTER_SEND[form.dataset.fetch](form, data);
}

function showRun(form, data) {
  const slot = document.getElementById(form.dataset.slot);
  slot.innerHTML = data.panel;
  followRun(slot.querySelector(".run"));
}

function clearAnswer(form) {
  form.elements.text.value = "";
  form.hidden = true;
}

function showMessage(text) {
  const old = document.querySelector(".snackbar:not(.copy-progress)");
  if (old) {
    old.remove();
  }
  const bar = document.createElement("div");
  bar.className = "snackbar";
  bar.setAttribute("role", "status");
  bar.textContent = text;
  document.body.append(bar);
}


// ---- Dropping files ----

async function uploadOneByOne(files) {
  const status = uploadForm.querySelector("[data-copy-status]");
  const count = status.querySelector(".copy-count");
  const name = status.querySelector(".copy-name");
  const bar = status.querySelector(".copy-bar span");
  status.hidden = false;
  for (let index = 0; index < files.length; index++) {
    count.textContent = `Adding ${index + 1} of ${files.length}`;
    name.textContent = files[index].name;
    bar.style.width = `${(100 * index) / files.length}%`;
    const body = new FormData();
    body.append("token", uploadForm.elements.token.value);
    body.append("file", files[index]);
    const reply = await fetch(uploadForm.action, {method: "POST", body: body});
    if (!reply.ok) {
      const data = await reply.json().catch(function () { return {}; });
      status.hidden = true;
      showMessage(data.error || `The console refused ${files[index].name}.`);
      return;
    }
  }
  window.location.reload();
}

function acceptedFiles(files) {
  const accepts = uploadForm.dataset.accepts.split(",");
  const kept = [];
  for (const file of files) {
    const lower = file.name.toLowerCase();
    if (accepts.some(function (suffix) { return lower.endsWith(suffix); })) {
      kept.push(file);
    }
  }
  return kept;
}

if (uploadForm) {
  uploadForm.querySelector("[data-pick-files]").addEventListener("change", function (event) {
    uploadOneByOne(Array.from(event.target.files));
  });
  document.addEventListener("dragover", function (event) {
    event.preventDefault();
    document.body.classList.add("dropping");
  });
  document.addEventListener("dragleave", function (event) {
    if (event.relatedTarget === null) {
      document.body.classList.remove("dropping");
    }
  });
  document.addEventListener("drop", function (event) {
    event.preventDefault();
    document.body.classList.remove("dropping");
    const files = acceptedFiles(Array.from(event.dataTransfer.files));
    if (files.length === 0) {
      showMessage(`This app takes ${uploadForm.dataset.accepts} files.`);
      return;
    }
    uploadOneByOne(files);
  });
}


// ---- Live runs ----

function wait(milliseconds) {
  return new Promise(function (resolve) {
    setTimeout(resolve, milliseconds);
  });
}

async function followRun(panel) {
  const log = panel.querySelector("[data-lines]");
  const pending = panel.querySelector("[data-pending]");
  let next = 0;
  while (panel.isConnected) {
    let data;
    try {
      const response = await fetch(panel.dataset.log + "?after=" + next);
      data = await response.json();
    } catch (error) {
      const status = panel.querySelector("[data-status]");
      status.textContent = "Console stopped";
      status.className = "status status-failed";
      return;
    }
    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 40;
    const received = data.lines.length;
    data.lines = takeItemEvents(panel, data.lines);
    if (data.lines.length > 0) {
      const chunk = document.createElement("span");
      chunk.textContent = data.lines.join("\n") + "\n";
      log.insertBefore(chunk, pending);
    }
    pending.textContent = data.partial;
    if (atBottom) {
      log.scrollTop = log.scrollHeight;
    }
    next = data.next;
    showState(panel, data);
    if (data.status !== "running" && received === 0) {
      return;
    }
    await wait(Number(panel.dataset.poll));
  }
}

function showLatestLine(panel, data) {
  const now = panel.querySelector("[data-now]");
  let latest = "";
  for (const line of data.lines.concat([data.partial])) {
    const plain = line.replace(LEADING_SYMBOLS, "").trim();
    if (plain) {
      latest = plain;
    }
  }
  now.hidden = data.status !== "running";
  if (latest) {
    now.textContent = latest;
  }
}

function latestCounter(lines) {
  let found = null;
  for (const line of lines) {
    for (const match of line.matchAll(COUNTER)) {
      const done = Number(match[1]);
      const total = Number(match[2]);
      if (total > 1 && done <= total) {
        found = {done: done, total: total};
      }
    }
  }
  return found;
}

function timeLeft(panel, counter) {
  const now = Date.now();
  if (!panel.dataset.paceTime || counter.done < Number(panel.dataset.paceDone)) {
    panel.dataset.paceTime = now;
    panel.dataset.paceDone = counter.done;
    return "";
  }
  const doneSince = counter.done - Number(panel.dataset.paceDone);
  if (doneSince < 1) {
    return "";
  }
  const secondsEach = (now - Number(panel.dataset.paceTime)) / 1000 / doneSince;
  const seconds = Math.round(secondsEach * (counter.total - counter.done));
  if (seconds < SECONDS_PER_MINUTE) {
    return ` · about ${Math.max(seconds, 1)}s left`;
  }
  return ` · about ${Math.round(seconds / SECONDS_PER_MINUTE)} min left`;
}

function takeItemEvents(panel, lines) {
  const shown = [];
  for (const line of lines) {
    if (line.startsWith(ITEM_PREFIX)) {
      const parts = line.slice(ITEM_PREFIX.length).split(" | ");
      showItem(panel, parts[0], parts[1], parts.slice(2).join(" | "));
    } else {
      shown.push(line);
    }
  }
  return shown;
}

function showItem(panel, state, name, detail) {
  const box = panel.querySelector("[data-progress]");
  const running = box.querySelector("[data-items-running]");
  const finished = box.querySelector("[data-items-finished]");
  if (state === "total") {
    box.hidden = false;
    box.dataset.total = name;
    box.dataset.finished = 0;
    box.dataset.failed = 0;
    running.replaceChildren();
    finished.replaceChildren();
    countItems(panel);
    return;
  }
  if (state === "done") {
    box.dataset.finished = name;
    countItems(panel);
    return;
  }
  let row = box.querySelector(`li[data-name="${CSS.escape(name)}"]`);
  if (!row) {
    row = document.createElement("li");
    row.dataset.name = name;
    row.innerHTML = '<span class="item-icon" aria-hidden="true"></span><span class="item-name"></span><span class="item-detail"></span>';
    row.querySelector(".item-name").textContent = name;
  }
  row.className = "item item-" + (state === "start" ? "running" : state);
  row.querySelector(".item-detail").textContent = detail;
  row.title = detail ? `${name}: ${detail}` : name;
  if (state === "start") {
    running.append(row);
    return;
  }
  finished.prepend(row);
  box.dataset.finished = Number(box.dataset.finished) + 1;
  if (state === "failed") {
    box.dataset.failed = Number(box.dataset.failed) + 1;
  }
  countItems(panel);
}

function countItems(panel) {
  const box = panel.querySelector("[data-progress]");
  const counter = {done: Number(box.dataset.finished), total: Number(box.dataset.total)};
  let text = `${counter.done} of ${counter.total} done`;
  if (Number(box.dataset.failed) > 0) {
    text += ` · ${box.dataset.failed} not accepted`;
  }
  if (counter.done < counter.total) {
    text += timeLeft(panel, counter);
  }
  panel.querySelector("[data-progress-count]").textContent = text;
  let share = 0;
  if (counter.total > 0) {
    share = (100 * counter.done) / counter.total;
  }
  panel.querySelector("[data-progress-bar]").style.width = `${share}%`;
}

function showProgress(panel, data) {
  const box = panel.querySelector("[data-progress]");
  if (box.dataset.total) {
    return;
  }
  const counter = latestCounter(data.lines.concat([data.partial]));
  if (counter === null) {
    return;
  }
  box.hidden = false;
  let text = `${counter.done} of ${counter.total}`;
  if (data.status === "running") {
    text += timeLeft(panel, counter);
  }
  panel.querySelector("[data-progress-count]").textContent = text;
  panel.querySelector("[data-progress-bar]").style.width = `${(100 * counter.done) / counter.total}%`;
}

async function refreshFiles() {
  const files = document.querySelector("[data-files]");
  if (!files) {
    return;
  }
  try {
    const response = await fetch(window.location.href);
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    const fresh = page.querySelector("[data-files]");
    if (fresh) {
      files.innerHTML = fresh.innerHTML;
    }
  } catch (error) {
    return;
  }
}

function showState(panel, data) {
  const status = panel.querySelector("[data-status]");
  let statusText = data.label;
  if (data.status === "failed" && data.exit_code !== null) {
    statusText += " · exit " + data.exit_code;
  }
  status.textContent = statusText;
  status.className = "status status-" + data.status;
  const before = panel.dataset.last;
  panel.dataset.last = data.status;
  if (before === undefined && data.status === "running") {
    buddyMood("running");
  }
  if (before === "running" && data.status !== "running") {
    buddyMood(data.status);
    refreshFiles();
  }
  showProgress(panel, data);
  panel.querySelector("[data-elapsed]").textContent = data.elapsed;
  showLatestLine(panel, data);

  const row = panel.closest("details");
  if (row) {
    const rowDot = row.querySelector("[data-dot]");
    rowDot.className = "dot dot-" + data.status;
    rowDot.hidden = false;
  }

  const stop = panel.querySelector('[data-fetch="stop"]');
  stop.hidden = data.cancel_url === null;
  if (data.cancel_url) {
    stop.action = data.cancel_url;
  }
  panel.querySelector("[data-run-close]").hidden = data.status === "running";
  if (data.status === "cancelled" && !panel.closest(".run-page")) {
    closeRun(panel);
    showMessage("Stopped.");
    return;
  }

  const answer = panel.querySelector('[data-fetch="answer"]');
  const asking = data.input_url !== null && data.partial.trim() !== "";
  if (asking) {
    answer.action = data.input_url;
  }
  answer.hidden = !asking;

  document.body.classList.toggle("busy", data.running_jobs > 0);
  const badge = document.querySelector("[data-running]");
  badge.textContent = data.running_jobs;
  badge.hidden = data.running_jobs === 0;
}

function closeRun(panel) {
  const body = new FormData();
  body.append("token", panel.querySelector('input[name="token"]').value);
  fetch(panel.querySelector("[data-run-close]").dataset.runClose, {method: "POST", body: body});
  panel.remove();
}

for (const panel of document.querySelectorAll(".run")) {
  followRun(panel);
}

async function keepRegionFresh(region) {
  let delay = Number(region.dataset.live);
  while (delay > 0) {
    await wait(delay);
    let page;
    try {
      const response = await fetch(window.location.href);
      page = new DOMParser().parseFromString(await response.text(), "text/html");
    } catch (error) {
      return;
    }
    const fresh = page.querySelector("[data-region]");
    if (!fresh) {
      return;
    }
    region.innerHTML = fresh.innerHTML;
    delay = Number(fresh.dataset.live || 0);
  }
}

const liveRegion = document.querySelector("[data-live]");
if (liveRegion) {
  keepRegionFresh(liveRegion);
}


// ---- Theme ----

function cycleTheme() {
  const now = savedTheme();
  const next = THEME_CHOICES[(THEME_CHOICES.indexOf(now) + 1) % THEME_CHOICES.length];
  saveTheme(next);
  applyTheme(next);
  labelThemeButton();
}

function labelThemeButton() {
  const button = document.querySelector("[data-theme-toggle]");
  button.setAttribute("aria-label", THEME_NAMES[savedTheme()]);
  button.title = THEME_NAMES[savedTheme()];
}

labelThemeButton();

for (const select of document.querySelectorAll("select")) {
  enhanceSelect(select);
}
document.addEventListener("click", handleMenuClick);
document.addEventListener("keydown", handleMenuKeys);
document.addEventListener("scroll", closeMenuOnScroll, true);
window.addEventListener("resize", closeMenu);


// ---- Dropdown menus ----

function handleMenuClick(event) {
  const option = event.target.closest(".menu-option");
  if (option) {
    chooseOption(option);
    return;
  }
  if (event.target.closest(".menu")) {
    return;
  }
  const opener = event.target.closest(".select-button, [data-pick-address], [data-list-models]");
  const sameOpener = opener !== null && opener === openedMenu.anchor;
  closeMenu();
  if (opener === null || sameOpener) {
    return;
  }
  if (opener.matches(".select-button")) {
    showSelectMenu(opener);
  } else if (opener.matches("[data-pick-address]")) {
    showAddressMenu(opener);
  } else {
    showModelMenu(opener);
  }
}

function handleMenuKeys(event) {
  if (openedMenu.menu === null) {
    if (event.key === "ArrowDown" && event.target.matches(".select-button")) {
      event.preventDefault();
      showSelectMenu(event.target);
    }
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    const anchor = openedMenu.anchor;
    closeMenu();
    anchor.focus();
    return;
  }
  if (event.key === "Tab") {
    closeMenu();
    return;
  }
  const step = MENU_STEPS[event.key];
  if (step) {
    event.preventDefault();
    moveFocus(step);
  }
}

function openMenu(anchor, groups, chosen, pick) {
  const menu = document.createElement("div");
  menu.className = "menu";
  menu.setAttribute("role", "listbox");
  for (const group of groups) {
    if (group.label) {
      const heading = document.createElement("div");
      heading.className = "menu-group";
      heading.textContent = group.label;
      menu.append(heading);
    }
    for (const item of group.items) {
      menu.append(menuOption(item, chosen));
    }
  }
  const box = (anchor.closest(".combo") || anchor).getBoundingClientRect();
  menu.style.minWidth = box.width + "px";
  menu.classList.add("menu-fixed");
  menu.style.left = box.left + "px";
  (anchor.closest("dialog") || document.body).append(menu);
  const roomBelow = window.innerHeight - box.bottom;
  if (menu.offsetHeight + 8 > roomBelow && box.top > roomBelow) {
    menu.style.bottom = window.innerHeight - box.top + 4 + "px";
  } else {
    menu.style.top = box.bottom + 4 + "px";
  }
  anchor.setAttribute("aria-expanded", "true");
  openedMenu.menu = menu;
  openedMenu.anchor = anchor;
  openedMenu.pick = pick;
  const first = menu.querySelector('[aria-selected="true"]') || menu.querySelector(".menu-option");
  if (first) {
    first.focus({preventScroll: true});
    first.scrollIntoView({block: "nearest"});
  }
}

function menuOption(item, chosen) {
  const option = document.createElement("button");
  option.type = "button";
  option.className = "menu-option";
  option.setAttribute("role", "option");
  option.setAttribute("aria-selected", String(item.value === chosen));
  option.dataset.value = item.value;
  const label = document.createElement("span");
  label.textContent = item.label;
  option.append(label);
  if (item.detail) {
    const detail = document.createElement("span");
    detail.className = "menu-detail";
    detail.textContent = item.detail;
    option.append(detail);
  }
  return option;
}

function closeMenuOnScroll(event) {
  if (openedMenu.menu && !openedMenu.menu.contains(event.target)) {
    closeMenu();
  }
}

function closeMenu() {
  if (openedMenu.menu === null) {
    return;
  }
  openedMenu.menu.remove();
  openedMenu.anchor.setAttribute("aria-expanded", "false");
  openedMenu.menu = null;
  openedMenu.anchor = null;
  openedMenu.pick = null;
}

function chooseOption(option) {
  const anchor = openedMenu.anchor;
  const pick = openedMenu.pick;
  closeMenu();
  pick(option.dataset.value);
  anchor.focus();
}

function moveFocus(step) {
  const options = Array.from(openedMenu.menu.querySelectorAll(".menu-option"));
  const now = options.indexOf(document.activeElement);
  const next = Math.min(Math.max(now + step, 0), options.length - 1);
  options[next].focus();
}

function enhanceSelect(select) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "select-button";
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", "false");
  button.append(document.createElement("span"));
  select.classList.add("visually-hidden");
  select.tabIndex = -1;
  select.after(button);
  showChoice(select, button);
  select.addEventListener("change", function () {
    showChoice(select, button);
  });
}

function showChoice(select, button) {
  const option = select.options[select.selectedIndex];
  const choice = option ? option.textContent : "";
  button.firstChild.textContent = choice;
  const field = select.closest("label");
  const name = field && field.querySelector("span") ? field.querySelector("span").textContent : select.getAttribute("aria-label");
  button.setAttribute("aria-label", (name || "Choice") + ": " + choice);
}

function showSelectMenu(button) {
  const select = button.previousElementSibling;
  const items = [];
  for (const option of select.options) {
    items.push({value: option.value, label: option.textContent, detail: option.dataset.detail || ""});
  }
  openMenu(button, [{label: "", items: items}], select.value, function (value) {
    select.value = value;
    select.dispatchEvent(new Event("change", {bubbles: true}));
  });
}

function showAddressMenu(button) {
  const addresses = JSON.parse(document.getElementById("addresses").textContent);
  const checked = button.closest(".model-card").querySelector('input[type="radio"]:checked');
  const route = checked ? checked.value : "";
  const groups = [];
  for (const name in ADDRESS_GROUPS) {
    if (route && route !== name) {
      continue;
    }
    const items = [];
    for (const address of addresses[name]) {
      items.push({value: address.value, label: address.label, detail: address.value});
    }
    if (items.length > 0) {
      groups.push({label: ADDRESS_GROUPS[name], items: items});
    }
  }
  if (groups.length === 0) {
    showMessage("No server deployed yet. Deploy one with kopi-editor's deploy command.");
    return;
  }
  const input = button.closest(".combo").querySelector("input");
  openMenu(button, groups, input.value, function (value) {
    input.value = value;
  });
}

async function showModelMenu(button) {
  const input = button.closest(".combo").querySelector("input");
  const form = new FormData();
  form.append("token", document.querySelector('input[name="token"]').value);
  form.append("app", button.dataset.app);
  form.append("base_url", button.closest(".model-card").querySelector("[data-address]").value);
  const label = button.textContent;
  button.textContent = "Looking…";
  button.disabled = true;
  let data;
  try {
    const response = await fetch(button.dataset.listUrl, {method: "POST", body: form});
    data = await response.json();
  } catch (error) {
    data = {error: "The console did not answer. Reload the page and try again."};
  }
  button.textContent = label;
  button.disabled = false;
  if (data.error) {
    showMessage(data.error);
    return;
  }
  const items = [];
  for (const name of data.models) {
    items.push({value: name, label: name, detail: ""});
  }
  openMenu(button, [{label: "", items: items}], input.value, function (value) {
    input.value = value;
  });
}
