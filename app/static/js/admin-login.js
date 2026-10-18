const passwordInput = document.getElementById("admin-password");
const passwordToggle = document.getElementById("toggle-admin-password");

passwordToggle?.addEventListener("click", () => {
  if (!passwordInput) return;

  const showPassword = passwordInput.type === "password";
  passwordInput.type = showPassword ? "text" : "password";
  passwordToggle.textContent = showPassword ? "Ocultar" : "Mostrar";
  passwordToggle.setAttribute("aria-pressed", String(showPassword));
  passwordToggle.setAttribute("aria-label", showPassword ? "Ocultar senha" : "Mostrar senha");
});
