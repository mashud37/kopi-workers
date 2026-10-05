const confirmDialog = document.getElementById("confirm");
const uploadForm = document.querySelector("[data-upload]");
const LEADING_SYMBOLS = /^[\s▶✓✗⚠·─]+/;

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
    if (data.status !== "running" && data.lines.length === 0) {
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

function showState(panel, data) {
  const status = panel.querySelector("[data-status]");
  let statusText = data.label;
  if (data.status === "failed" && data.exit_code !== null) {
    statusText += " · exit " + data.exit_code;
  }
  status.textContent = statusText;
  status.className = "status status-" + data.status;
  panel.querySelector("[data-elapsed]").textContent = data.elapsed;
  showLatestLine(panel, data);

  const rowDot = panel.closest("details").querySelector("[data-dot]");
  rowDot.className = "dot dot-" + data.status;
  rowDot.hidden = false;

  const stop = panel.querySelector('[data-fetch="stop"]');
  stop.hidden = data.cancel_url === null;
  if (data.cancel_url) {
    stop.action = data.cancel_url;
  }
  panel.querySelector("[data-run-close]").hidden = data.status === "running";
  if (data.status === "cancelled") {
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
