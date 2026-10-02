"use strict";
// Presentation only: backend grounding status remains authoritative.
const answerState = Object.freeze({
  classify(response) {
    if (!response || typeof response.text !== "string" || !response.text.trim()) return "error";
    return ["answered", "clarify", "unverified"].includes(response.status) ? response.status : "error";
  },
  set(host, status, label = true) {
    host.dataset.answerState = status;
    host.querySelectorAll(":scope > .answer-status").forEach(node => node.remove());
    const labels = { answered: "Answered", clarify: "More information needed", unverified: "Response needs review" };
    if (!label || !labels[status]) return;
    const badge = document.createElement("span");
    badge.className = "answer-status";
    if (status === "answered") {
      const check = document.createElement("span");
      check.textContent = "✓ ";
      check.setAttribute("aria-hidden", "true");
      badge.append(check);
    }
    badge.append(document.createTextNode(labels[status]));
    host.prepend(badge);
  },
  question(host, text) {
    const question = document.createElement("p");
    question.className = "answer-question";
    question.textContent = `Question: ${text}`;
    host.append(question);
  }
});
