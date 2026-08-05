/* Shared renderer for complete ML App client-module reference pages.
 * A page supplies window.MLAPP_REFERENCE before loading this file. */
(function () {
  const spec = window.MLAPP_REFERENCE;
  if (!spec) return;
  const esc = (value) => String(value ?? "").replace(/[&<>\"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));
  const code = (value) => `<pre><code>${esc(value)}</code></pre>`;
  const argumentsTable = (items = []) => items.length ? `<div class="section-title">Arguments</div><table class="arguments-table"><thead><tr><th>Argument</th><th>Meaning</th></tr></thead><tbody>${items.map(([name, text]) => `<tr><td><code>${esc(name)}</code></td><td>${esc(text)}</td></tr>`).join("")}</tbody></table>` : "<p class=\"small\">No arguments.</p>";
  const api = (value) => value
    ? `<details class="api-call"><summary>Show example direct API call</summary>${code(value)}</details>`
    : `<p class="note small">This is a client-side convenience method; it has no separate HTTP endpoint.</p>`;
  const method = (item) => `<details><summary><code>${esc(item.name)}(...)</code><span>${esc(item.summary)}</span></summary><div class="method-body"><p>${esc(item.description || item.summary)}</p>${argumentsTable(item.args)}<div class="section-title">Python</div>${code(item.example)}${api(item.api)}</div></details>`;
  const values = (items = []) => items.map((item) => `<details><summary>▸ ${esc(item.name)} <span>— ${esc(item.summary)}</span></summary><table><thead><tr><th>Value</th><th>Meaning</th></tr></thead><tbody>${item.rows.map(([name, text]) => `<tr><td>${esc(name)}</td><td>${esc(text)}</td></tr>`).join("")}</tbody></table></details>`).join("");
  document.title = `${spec.title} · ML App Client Reference`;
  document.getElementById("reference").innerHTML = `
    <a class="small" href="index.html">← Client reference</a>
    <div class="eyebrow">ML App / Python SDK / ${esc(spec.eyebrow || spec.title)}</div>
    <h1>${esc(spec.title)}</h1>
    <p>${esc(spec.intro)}</p>
    <div class="card grid">${(spec.concepts || []).map((item) => `<div class="concept"><h3>${esc(item.title)}</h3><p>${esc(item.text)}</p></div>`).join("")}</div>
    <h2>Accepted values</h2>
    <div class="card"><p class="small">Open a parameter to see the values and constraints used by the request workflow.</p><div class="value-details">${values(spec.values)}</div></div>
    ${spec.sections.map((section) => `<h2>${esc(section.title)}</h2><div class="methods">${section.methods.map(method).join("")}</div>`).join("")}
    <h2>Runnable example</h2>
    <div class="card"><p>${esc(spec.notebookText || "Use the API lifecycle notebook for an end-to-end workflow that includes this module.")}</p><p><a href="${esc(spec.notebook || "../../examples/API-usage/Example01_master.ipynb")}">${esc(spec.notebookLabel || "Open the related notebook →")}</a></p></div>`;
}());
