/* Admin dashboard: filters, customers, transactions, statistics, reports. */
(function () {
  const globalMessage = document.getElementById("global-message");
  const filterBar = document.getElementById("filter-bar");
  let currentPage = "dashboard";

  // ---------- filters (date range + customer) ----------
  function filterParams(extra) {
    const params = new URLSearchParams(extra || {});
    const start = document.getElementById("f-start").value;
    const end = document.getElementById("f-end").value;
    const customer = document.getElementById("f-customer").value;
    if (start) params.set("start", start);
    if (end) params.set("end", end);
    if (customer) params.set("customer_id", customer);
    return params;
  }

  async function loadCustomerOptions() {
    const data = await api("/api/admin/customers");
    const select = document.getElementById("f-customer");
    select.innerHTML = '<option value="">All customers</option>' + data.rows.map((c) =>
      '<option value="' + esc(c.user_id) + '">' + esc(c.name) + " (ID " + esc(c.user_id) + ")</option>").join("");
  }

  // ---------- page switching ----------
  const loaders = {
    dashboard: loadDashboard,
    customers: loadCustomers,
    transactions: loadTransactions,
    statistics: loadStatistics,
    reports: loadReports
  };

  function showPage(name) {
    currentPage = name;
    document.querySelectorAll(".page").forEach((p) => { p.hidden = p.id !== "page-" + name; });
    document.querySelectorAll(".nav").forEach((n) => n.classList.toggle("active", n.dataset.page === name));
    filterBar.hidden = name === "customers";
    showMessage(globalMessage, "");
    loaders[name]().catch((error) => showMessage(globalMessage, error.message, "error"));
  }
  document.querySelectorAll(".nav").forEach((button) =>
    button.addEventListener("click", () => showPage(button.dataset.page)));
  document.getElementById("f-apply").addEventListener("click", () => showPage(currentPage));

  // ---------- dashboard ----------
  async function loadDashboard() {
    const data = await api("/api/admin/overview?" + filterParams().toString());
    const k = data.kpis;
    setText("k-customers", k.total_customers);
    setText("k-active", k.active_customers);
    setText("k-income", rupee(k.total_income));
    setText("k-expenses", rupee(k.total_expenses));
    setText("k-savings", rupee(k.total_savings));
    setText("k-avg-income", rupee(k.avg_income));
    setText("k-avg-expenses", rupee(k.avg_expenses));
    setText("k-highest", rupee(k.highest_expense));

    Charts.incomeVsExpenses(document.getElementById("c-monthly"), data.monthly);
    Charts.savingsTrend(document.getElementById("c-trend"), data.monthly);
    Charts.categoryPie(document.getElementById("c-pie"), data.categories);
    Charts.bar(document.getElementById("c-top"), "Top 5 Customers by Expenses",
               data.top_customers, "name", "total_expense", "Expenses (₹)");
    Charts.bar(document.getElementById("c-income"), "Customer-wise Income",
               data.income_by_customer, "name", "total_income", "Income (₹)");
    Charts.histogram(document.getElementById("c-hist"), data.expense_amounts);
  }

  // ---------- customers ----------
  async function loadCustomers() {
    const search = document.getElementById("c-search").value;
    const data = await api("/api/admin/customers?" + new URLSearchParams({ search }).toString());
    renderTable(document.getElementById("table-customers"), [
      { label: "ID", key: "user_id", num: true },
      { label: "Name", key: "name" },
      { label: "Email", key: "email" },
      { label: "Status", key: "status" },
      { label: "Joined", key: "created_at" },
      { label: "", html: (row) => '<button class="btn secondary small" data-view="' + esc(row.user_id) + '">Details</button>' }
    ], data.rows, "No customers found.");
  }
  document.getElementById("c-search-btn").addEventListener("click", () =>
    loadCustomers().catch((error) => showMessage(globalMessage, error.message, "error")));

  async function showCustomerDetail(id) {
    const data = await api("/api/admin/customers/" + encodeURIComponent(id) + "/summary");
    const t = data.totals;
    const nextStatus = data.info.status === "Active" ? "Blocked" : "Active";
    const box = document.getElementById("customer-detail");
    box.hidden = false;
    box.innerHTML =
      "<h2>" + esc(data.info.name) + "</h2>" +
      "<p>Email: " + esc(data.info.email) + "<br>Status: <strong>" + esc(data.info.status) +
      "</strong><br>Joined: " + esc(data.info.created_at) + "</p>" +
      '<div class="cards">' +
      '<div class="card"><span>Income</span><strong>' + esc(rupee(t.income)) + "</strong></div>" +
      '<div class="card"><span>Expenses</span><strong>' + esc(rupee(t.expenses)) + "</strong></div>" +
      '<div class="card"><span>Net savings</span><strong>' + esc(rupee(t.net_savings)) + "</strong></div>" +
      '<div class="card"><span>Savings %</span><strong>' + esc(t.savings_pct.toFixed(2)) + "%</strong></div>" +
      "</div>" +
      '<button class="btn" data-status="' + esc(nextStatus) + '" data-id="' + esc(id) + '">' +
      (nextStatus === "Blocked" ? "Block this customer" : "Activate this customer") + "</button>";
  }

  document.getElementById("table-customers").addEventListener("click", (event) => {
    const id = event.target.dataset.view;
    if (id) showCustomerDetail(id).catch((error) => showMessage(globalMessage, error.message, "error"));
  });

  document.getElementById("customer-detail").addEventListener("click", async (event) => {
    const status = event.target.dataset.status;
    const id = event.target.dataset.id;
    if (!status) return;
    try {
      await api("/api/admin/customers/" + encodeURIComponent(id) + "/status",
                { method: "POST", body: { status } });
      await showCustomerDetail(id);
      await loadCustomers();
      await loadCustomerOptions();
    } catch (error) {
      showMessage(globalMessage, error.message, "error");
    }
  });

  // ---------- transactions ----------
  async function loadTransactions() {
    const type = document.getElementById("t-type").value;
    const params = filterParams(type ? { type } : {});
    const data = await api("/api/admin/transactions?" + params.toString());
    params.set("format", "csv");
    document.getElementById("t-download").href = "/api/admin/transactions?" + params.toString();
    renderTable(document.getElementById("table-transactions"), [
      { label: "ID", key: "transaction_id", num: true },
      { label: "Customer", key: "customer" },
      { label: "Date", key: "date" },
      { label: "Type", key: "type" },
      { label: "Amount", key: "amount", money: true },
      { label: "Description", key: "description" }
    ], data.rows);
  }
  document.getElementById("t-type").addEventListener("change", () =>
    loadTransactions().catch((error) => showMessage(globalMessage, error.message, "error")));

  // ---------- statistics ----------
  async function loadStatistics() {
    const data = await api("/api/admin/statistics?" + filterParams().toString());
    const cards = document.getElementById("stats-cards");
    const notes = document.getElementById("stats-notes");
    if (!data.stats) {
      cards.innerHTML = '<p class="muted">No expense records for the selected filters.</p>';
      notes.innerHTML = "";
    } else {
      const s = data.stats;
      const items = [
        ["Records", String(s.count)], ["Total", rupee(s.total)],
        ["Mean (average)", rupee(s.mean)], ["Median (middle)", rupee(s.median)],
        ["Mode (top category)", s.mode_category], ["Minimum", rupee(s.min)],
        ["Maximum", rupee(s.max)], ["Standard deviation", rupee(s.std_dev)],
        ["Variance (₹²)", Number(s.variance).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })]
      ];
      cards.innerHTML = items.map((i) =>
        '<div class="card"><span>' + esc(i[0]) + "</span><strong>" + esc(i[1]) + "</strong></div>").join("");
      notes.innerHTML = data.notes.map((n) => "<li>" + esc(n) + "</li>").join("");
    }
    Charts.histogram(document.getElementById("s-hist"), data.expense_amounts);
    renderTable(document.getElementById("table-per-customer"), [
      { label: "Customer", key: "name" },
      { label: "Total expenses", key: "total_expense", money: true }
    ], data.per_customer, "No data.");
  }

  // ---------- reports ----------
  async function loadReports() {
    const base = filterParams();
    const csv = new URLSearchParams(base.toString());
    csv.set("format", "csv");
    ["monthly", "customers", "categories"].forEach((name) => {
      document.getElementById("dl-" + name).href = "/api/admin/reports/" + name + "?" + csv.toString();
    });
    const [monthly, customers, categories] = await Promise.all(
      ["monthly", "customers", "categories"].map((name) =>
        api("/api/admin/reports/" + name + "?" + base.toString())));

    renderTable(document.getElementById("table-r-monthly"), [
      { label: "Month", key: "month" },
      { label: "Income", key: "income", money: true },
      { label: "Expenses", key: "expenses", money: true },
      { label: "Net savings", key: "net_savings", money: true },
      { label: "Savings %", key: "savings_pct", num: true },
      { label: "Recorded savings", key: "recorded_savings", money: true }
    ], monthly.rows);
    renderTable(document.getElementById("table-r-customers"), [
      { label: "Customer", key: "name" },
      { label: "Status", key: "status" },
      { label: "Income", key: "total_income", money: true },
      { label: "Expenses", key: "total_expenses", money: true },
      { label: "Net savings", key: "net_savings", money: true },
      { label: "Savings %", key: "savings_pct", num: true },
      { label: "Recorded savings", key: "recorded_savings", money: true }
    ], customers.rows);
    renderTable(document.getElementById("table-r-categories"), [
      { label: "Category", key: "category" },
      { label: "Total", key: "total", money: true },
      { label: "Records", key: "records", num: true },
      { label: "Average", key: "average", money: true },
      { label: "Share %", key: "share_pct", num: true }
    ], categories.rows);
  }

  // ---------- start ----------
  setupLogout();
  api("/api/me").then((me) => setText("user-name", me.name)).catch(() => {});
  loadCustomerOptions().catch((error) => showMessage(globalMessage, error.message, "error"));
  showPage("dashboard");
})();
