document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", (event) => {
    const target = document.querySelector(anchor.getAttribute("href"));
    if (!target) {
      return;
    }
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

// Rollout selector: one player, the list swaps its source and caption.
const rollVideo = document.getElementById("roll-video");
const rollText = document.getElementById("roll-text");
const rollMeta = document.getElementById("roll-meta");
const rollItems = document.querySelectorAll(".roll-item[data-src]");

function selectRollout(item) {
  rollItems.forEach((other) => other.setAttribute("aria-pressed", String(other === item)));
  const outcome = item.querySelector(".roll-outcome").classList.contains("is-success") ? "success" : "failure";
  const domain = item.dataset.domain;
  const policy = item.querySelector(".roll-policy");
  rollMeta.innerHTML =
    `<span class="roll-task">${item.querySelector(".roll-task").textContent}</span>` +
    (policy ? `<span class="roll-policy">${policy.innerHTML}</span>` : "") +
    `<span class="roll-tag">${domain}</span>` +
    `<span class="roll-tag is-${outcome}">${outcome}</span>`;
  rollText.innerHTML = item.querySelector(".roll-caption").innerHTML;
  if (rollVideo.getAttribute("src") !== item.dataset.src) {
    rollVideo.setAttribute("src", item.dataset.src);
    rollVideo.play().catch(() => {});
  }
}

if (rollVideo && rollItems.length) {
  rollItems.forEach((item) => item.addEventListener("click", () => selectRollout(item)));
  selectRollout(document.querySelector('.roll-item[data-src][aria-pressed="true"]') || rollItems[0]);
}

// Sim/real switch on the replicated task cards.
document.querySelectorAll(".task-media").forEach((media) => {
  const video = media.querySelector("video");
  media.querySelectorAll(".media-switch button").forEach((button) => {
    button.addEventListener("click", () => {
      media.querySelectorAll(".media-switch button").forEach((other) => other.setAttribute("aria-pressed", String(other === button)));
      video.src = video.dataset[button.dataset.view];
      video.play().catch(() => {});
    });
  });
});

// Simulation failure explorer: task x policy x the stage a rollout ends in -> one evaluation rollout.
// Data (static/js/rollouts.js): per task the stage names and per policy the number of rollouts that end in each
// stage (index k = completed k stages; the last index is success) and one clip per stage.
const explorer = document.getElementById("explorer");
const rolloutData = window.DUOBENCH_ROLLOUTS;

if (explorer && rolloutData) {
  const exVideo = document.getElementById("ex-video");
  const exText = document.getElementById("ex-text");
  const exTrack = document.getElementById("ex-track");
  const exNote = document.getElementById("ex-note");
  const taskButtons = explorer.querySelectorAll(".ex-task");
  const policyButtons = explorer.querySelectorAll(".ex-policies button");
  const state = { task: "hinge_chest", policy: "act", stage: null };

  const pct = (count, total) => {
    const value = (100 * count) / total;
    return value > 0 && value < 1 ? value.toFixed(1) : String(Math.round(value));
  };

  // the stage where most rollouts end that also has a clip
  function defaultStage(run) {
    let best = null;
    run.counts.forEach((count, k) => {
      if (run.clips[k] && (best === null || count > run.counts[best])) {
        best = k;
      }
    });
    return best;
  }

  function render() {
    const task = rolloutData[state.task];
    const run = task[state.policy];
    const n = task.stages.length;
    if (state.stage === null || !run.clips[state.stage]) {
      state.stage = defaultStage(run);
    }
    taskButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.task === state.task)));
    policyButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.policy === state.policy)));

    exTrack.style.setProperty("--steps", n + 1);
    exTrack.replaceChildren(
      ...run.counts.map((count, k) => {
        const success = k === n;
        const step = document.createElement("button");
        step.type = "button";
        step.className = "ex-step" + (success ? " is-success" : "");
        step.disabled = !run.clips[k];
        step.setAttribute("aria-pressed", String(k === state.stage));
        const share = pct(count, run.total);
        step.innerHTML =
          `<span class="ex-step-name">${success ? "success" : `<b>${k + 1}</b> ${task.stages[k]}`}</span>` +
          `<span class="ex-step-bar" aria-hidden="true"><i style="width:${(100 * count) / run.total}%"></i></span>` +
          `<span class="ex-step-pct">${share}%</span>`;
        step.title = success
          ? `${share}% of the rollouts succeed`
          : `${share}% of the rollouts end here: they complete ${k} of ${n} stages and fail at "${task.stages[k]}"`;
        step.addEventListener("click", () => {
          state.stage = k;
          render();
        });
        return step;
      })
    );

    const policyName = explorer.querySelector(`.ex-policies [data-policy="${state.policy}"]`).innerHTML;
    exNote.hidden = !task.note;
    exNote.textContent = task.note || "";
    if (state.stage === null) {
      exVideo.hidden = true;
      exVideo.removeAttribute("src");
      exText.innerHTML = `No ${policyName} rollout on ${task.name} can be shown.`;
      return;
    }
    exVideo.hidden = false;
    const clip = run.clips[state.stage];
    const share = pct(run.counts[state.stage], run.total);
    if (state.stage === n) {
      exText.innerHTML = `<b>${policyName}</b> completes all ${n} stages of ${task.name}, as in ${share}% of its ${run.total} rollouts.`;
    } else {
      const done = state.stage === 0 ? "does not complete the first stage" : `completes ${state.stage} of ${n} stages`;
      exText.innerHTML =
        `<b>${policyName}</b> ${done} and fails at <b>${task.stages[state.stage]}</b>, ` +
        `like ${share}% of its ${run.total} rollouts on ${task.name}.`;
    }
    exText.innerHTML += ` <span class="ex-seed">Seed ${clip.seed}${clip.rerun ? ", from a repeat run of the same policy" : ""}.</span>`;
    if (exVideo.getAttribute("src") !== clip.src) {
      exVideo.setAttribute("src", clip.src);
      exVideo.play().catch(() => {});
    }
  }

  taskButtons.forEach((b) =>
    b.addEventListener("click", () => {
      state.task = b.dataset.task;
      state.stage = null;
      render();
    })
  );
  policyButtons.forEach((b) =>
    b.addEventListener("click", () => {
      state.policy = b.dataset.policy;
      render();
    })
  );
  render();
}
