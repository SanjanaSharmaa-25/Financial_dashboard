/* Customer dashboard: switches pages, loads data, sends forms. */
(function () {
  const globalMessage = document.getElementById("global-message");

  // ---------- page switching ----------
  const loaders = {
    dashboard: loadDashboard,
    income: () => Promise.resolve(),
    expense: () => Promise.resolve(),
    savings: loadSavings,
    history: loadHistory
  };

  function showPage(name) {
    document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== "page-" + name; });
    document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("active", n.dataset.page === name));
    showMessage(globalMessage, "");
    loaders[name]().catch((error) => showMessage(globalMessage, error.message, "error"));
  }
  document.querySelectorAll(".nav").forEach((button) =>
    button.addEventListener("click", () => showPage(button.dataset.page)));

  // ---------- dashboard ----------
  async function loadDashboard() {
    const data = await api("/api/customer/summary");
    const t = data.totals;
    setText("kpi-income", rupee(t.income));
    setText("kpi-expenses", rupee(t.expenses));
    setText("kpi-net", rupee(t.net_savings));
    setText("kpi-pct", t.savings_pct.toFixed(2) + "%");
    setText("kpi-recorded", rupee(t.recorded_savings));
    setText("kpi-top-category", data.highest_category
      ? data.highest_category.category + " (" + rupee(data.highest_category.total) + ")" : "N/A");
    setText("kpi-avg-month", rupee(data.avg_monthly_expense));

    Charts.incomeVsExpenses(document.getElementById("chart-monthly"), data.monthly);
    Charts.savingsTrend(document.getElementById("chart-trend"), data.monthly);
    Charts.categoryPie(document.getElementById("chart-pie"), data.categories);

    renderTable(document.getElementById("table-monthly"), [
      { label: "Month", key: "month" },
      { label: "Income", key: "income", money: true },
      { label: "Expenses", key: "expenses", money: true },
      { label: "Net savings", key: "net_savings", money: true },
      { label: "Savings %", key: "savings_pct", num: true },
      { label: "Recorded savings", key: "recorded_savings", money: true }
    ], data.monthly, "No records yet. Add income and expenses to see your summary.");
  }

  // ---------- savings ----------
  async function loadSavings() {
    const data = await api("/api/customer/savings-by-goal");
    renderTable(document.getElementById("table-goals"), [
      { label: "Goal", key: "goal" },
      { label: "Saved", key: "saved", money: true }
    ], data.rows, "No savings yet.");
    Charts.bar(document.getElementById("chart-goals"), "Savings by Goal", data.rows, "goal", "saved", "Saved (₹)");
  }

  // ---------- history ----------
  async function loadHistory() {
    const params = new URLSearchParams();
    const start = document.getElementById("h-start").value;
    const end = document.getElementById("h-end").value;
    const type = document.getElementById("h-type").value;
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    if (type) params.set("type", type);
    const data = await api("/api/customer/history?" + params.toString());
    renderTable(document.getElementById("table-history"), [
      { label: "ID", key: "transaction_id", num: true },
      { label: "Date", key: "date" },
      { label: "Type", key: "type" },
      { label: "Amount", key: "amount", money: true },
      { label: "Description", key: "description" },
      { label: "", html: (row) => '<button class="btn danger" data-delete="' + esc(row.transaction_id) + '">Delete</button>' }
    ], data.rows);
  }
  document.getElementById("h-apply").addEventListener("click", () =>
    loadHistory().catch((error) => showMessage(globalMessage, error.message, "error")));

  document.getElementById("table-history").addEventListener("click", async (event) => {
    const id = event.target.dataset.delete;
    if (!id || !confirm("Delete this record? This cannot be undone.")) return;
    try {
      await api("/api/customer/transactions/" + encodeURIComponent(id), { method: "DELETE" });
      await loadHistory();
    } catch (error) {
      showMessage(globalMessage, error.message, "error");
    }
  });

  // ---------- forms ----------
  function setDates() {
    const today = localToday();
    document.querySelectorAll(".date-input").forEach((input) => { input.value = today; input.max = today; });
  }

  function bindForm(formId, url, buildBody) {
    const form = document.getElementById(formId);
    const message = form.querySelector(".message");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const result = await api(url, { method: "POST", body: buildBody(form) });
        showMessage(message, result.message, "success");
        form.reset();
        setDates();
        if (formId === "saving-form") loadSavings();
      } catch (error) {
        showMessage(message, error.message, "error");
      }
    });
  }

  // field(form, "name") reads one input by name
  const field = (form, name) => form.elements[name].value;

  bindForm("income-form", "/api/customer/income", (f) => ({
    source: field(f, "source"), amount: field(f, "amount"), date: field(f, "date"),
    description: field(f, "description") }));
  bindForm("expense-form", "/api/customer/expense", (f) => ({
    category: field(f, "category"), amount: field(f, "amount"), date: field(f, "date"),
    payment_method: field(f, "payment_method"), description: field(f, "description") }));
  bindForm("saving-form", "/api/customer/saving", (f) => ({
    goal: field(f, "goal"), amount: field(f, "amount"), date: field(f, "date") }));

  // ---------- start ----------
  setupLogout();
  setDates();
  api("/api/me").then((me) => setText("user-name", me.name)).catch(() => {});
  showPage("dashboard");
})();
