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
const rollItems = document.querySelectorAll(".roll-item");

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
  selectRollout(document.querySelector('.roll-item[aria-pressed="true"]') || rollItems[0]);
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
