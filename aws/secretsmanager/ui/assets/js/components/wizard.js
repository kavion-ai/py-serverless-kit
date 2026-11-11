// A multi-step form with the step list on the left, like "Store a new secret" on AWS.
//
//   wizard({
//     steps: [{ title, render: () => node, validate: () => true|false|Promise }],
//     submitLabel: "Store", onSubmit: async () => {}, onCancel: () => {},
//   }) -> element
// validate() runs before "Next"; the last step's button calls onSubmit (errors are shown above the buttons).

import { h, mount } from "../core/dom.js";
import { button } from "./button.js";

export function wizard({ steps, submitLabel = "Submit", onSubmit, onCancel }) {
  let at = 0;
  const list = h("ol", { class: "steps", "aria-label": "Steps" });
  const main = h("div", { class: "w-main" });
  const error = h("div", { class: "f-error", role: "alert" });
  const rendered = new Map(); // keep each step's DOM so its inputs survive Previous / Next

  function drawSteps() {
    list.replaceChildren(...steps.map((s, i) => h("li", {
      class: i === at ? "on" : i < at ? "done" : "",
      "aria-current": i === at ? "step" : undefined,
    }, h("b", {}, `Step ${i + 1}`), i < at
      ? h("a", { href: "#", onclick: (e) => { e.preventDefault(); go(i); } }, s.title)
      : h("span", {}, s.title))));
  }

  async function go(next) {
    error.textContent = "";
    if (next > at) {
      for (let i = at; i < next; i += 1) {
        const ok = steps[i].validate ? await steps[i].validate() : true;
        if (!ok) {
          at = i;
          draw();
          return;
        }
      }
    }
    at = next;
    if (steps[at].fresh) rendered.delete(at);
    draw();
    window.scrollTo({ top: 0 });
  }

  function draw() {
    drawSteps();
    if (!rendered.has(at)) rendered.set(at, steps[at].render());
    const last = at === steps.length - 1;
    mount(main,
      h("h1", {}, steps[at].title),
      steps[at].description ? h("div", { class: "muted" }, steps[at].description) : null,
      rendered.get(at),
      error,
      h("div", { class: "w-actions" },
        button("Cancel", { variant: "link", onClick: onCancel }),
        at ? button("Previous", { onClick: () => go(at - 1) }) : null,
        last
          ? button(submitLabel, {
            variant: "primary",
            onClick: async () => {
              error.textContent = "";
              try {
                await onSubmit();
              } catch (err) {
                error.textContent = err.text || err.message;
              }
            },
          })
          : button("Next", { variant: "primary", onClick: () => go(at + 1) })));
  }

  draw();
  return h("div", { class: "wizard" }, h("nav", {}, list), main);
}
