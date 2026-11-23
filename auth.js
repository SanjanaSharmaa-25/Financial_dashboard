/* Login and register page. */
(function () {
  const tabs = document.querySelectorAll(".tab");
  const forms = document.querySelectorAll(".auth-form");

  function showTab(formId) {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === formId));
    forms.forEach((f) => { f.hidden = f.id !== formId; });
  }
  tabs.forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));

  // Customer and admin login
  ["customer-form", "admin-form"].forEach((id) => {
    const form = document.getElementById(id);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = form.querySelector(".message");
      try {
        const result = await api("/api/login", {
          method: "POST",
          body: { email: form.elements.email.value, password: form.elements.password.value, role: form.dataset.role }
        });
        window.location.href = result.redirect;
      } catch (error) {
        showMessage(message, error.message, "error");
      }
    });
  });

  // Register
  const registerForm = document.getElementById("register-form");
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = registerForm.querySelector(".message");
    try {
      const result = await api("/api/register", {
        method: "POST",
        body: { name: registerForm.elements.name.value, email: registerForm.elements.email.value,
                password: registerForm.elements.password.value }
      });
      registerForm.reset();
      showMessage(message, result.message, "success");
    } catch (error) {
      showMessage(message, error.message, "error");
    }
  });
})();
