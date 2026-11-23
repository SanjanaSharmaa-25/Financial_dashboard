/* Helpers shared by every page: API calls, formatting, tables and charts. */

// ---------- talking to the Flask backend ----------
async function api(path, options) {
  const opts = Object.assign({ credentials: "same-origin", headers: {} }, options || {});
  if (opts.body && typeof opts.body !== "string") {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const response = await fetch(path, opts);
  let data = null;
  try { data = await response.json(); } catch (e) { /* no JSON body */ }
  if (response.status === 401 && !path.startsWith("/api/login")) {
    window.location.href = "/";          // session ended: go back to login
    throw new Error("Please log in.");
  }
  if (!response.ok) {
    throw new Error((data && data.error) || "Something went wrong.");
  }
  return data;
}

// ---------- formatting ----------
function rupee(value) {
  return "₹" + Number(value || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  });
}

// Escape text before putting it in HTML. This stops XSS attacks.
function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function localToday() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}

function setText(id, text) { document.getElementById(id).textContent = text; }

function showMessage(element, text, type) {
  element.textContent = text || "";
  element.className = "message " + (type || "");
}

// ---------- tables ----------
// columns: [{label, key, money, num, html(row)}]
function renderTable(container, columns, rows, emptyText) {
  if (!rows || !rows.length) {
    container.innerHTML = '<p class="muted">' + esc(emptyText || "No records found.") + "</p>";
    return;
  }
  const head = columns.map((c) => "<th" + (c.money || c.num ? ' class="num"' : "") + ">" + esc(c.label) + "</th>").join("");
  const body = rows.map((row) => "<tr>" + columns.map((c) => {
    let cell;
    if (c.html) cell = c.html(row);                       // html() must escape its own text
    else if (c.money) cell = esc(rupee(row[c.key]));
    else cell = esc(row[c.key]);
    return "<td" + (c.money || c.num ? ' class="num"' : "") + ">" + cell + "</td>";
  }).join("") + "</tr>").join("");
  container.innerHTML = '<div class="table-wrap"><table><thead><tr>' + head +
    "</tr></thead><tbody>" + body + "</tbody></table></div>";
}

// ---------- charts (Plotly.js) ----------
function noData(el, text) {
  if (typeof Plotly !== "undefined") Plotly.purge(el);
  el.innerHTML = '<p class="muted">' + esc(text || "No data yet.") + "</p>";
  el.dataset.empty = "1";
}

function plot(el, traces, layout) {
  if (typeof Plotly === "undefined") {
    noData(el, "Chart library could not load. Check your internet connection.");
    return;
  }
  if (el.dataset.empty) { el.innerHTML = ""; delete el.dataset.empty; }
  const base = { margin: { t: 55, r: 20, b: 60, l: 70 }, legend: { orientation: "h", y: -0.2 } };
  Plotly.react(el, traces, Object.assign(base, layout), { responsive: true, displaylogo: false });
}

const Charts = {
  incomeVsExpenses(el, monthly) {
    if (!monthly.length) return noData(el);
    const months = monthly.map((m) => m.month);
    plot(el, [
      { type: "bar", name: "Income", x: months, y: monthly.map((m) => m.income) },
      { type: "bar", name: "Expenses", x: months, y: monthly.map((m) => m.expenses) }
    ], { title: { text: "Monthly Income vs Expenses" }, barmode: "group",
         xaxis: { title: { text: "Month" }, type: "category" }, yaxis: { title: { text: "Amount (₹)" } } });
  },
  savingsTrend(el, monthly) {
    if (!monthly.length) return noData(el);
    const months = monthly.map((m) => m.month);
    plot(el, [
      { type: "scatter", mode: "lines+markers", name: "Net savings (Income - Expenses)",
        x: months, y: monthly.map((m) => m.net_savings) },
      { type: "scatter", mode: "lines+markers", name: "Recorded savings",
        x: months, y: monthly.map((m) => m.recorded_savings) }
    ], { title: { text: "Monthly Savings Trend" },
         xaxis: { title: { text: "Month" }, type: "category" }, yaxis: { title: { text: "Amount (₹)" } } });
  },
  categoryPie(el, categories) {
    if (!categories.length) return noData(el);
    plot(el, [{ type: "pie", hole: 0.4, labels: categories.map((c) => c.category),
                values: categories.map((c) => c.total) }],
         { title: { text: "Expenses by Category" } });
  },
  bar(el, title, rows, xKey, yKey, yLabel) {
    if (!rows.length) return noData(el);
    plot(el, [{ type: "bar", x: rows.map((r) => r[xKey]), y: rows.map((r) => r[yKey]) }],
         { title: { text: title }, yaxis: { title: { text: yLabel } } });
  },
  histogram(el, amounts) {
    if (!amounts.length) return noData(el);
    plot(el, [{ type: "histogram", x: amounts, nbinsx: 20 }],
         { title: { text: "Distribution of Expense Amounts" },
           xaxis: { title: { text: "Amount (₹)" } }, yaxis: { title: { text: "Number of expenses" } } });
  }
};

// ---------- logout (used by both dashboards) ----------
function setupLogout() {
  const button = document.getElementById("logout");
  if (!button) return;
  button.addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    window.location.href = "/";
  });
}
