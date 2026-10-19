(() => {
  "use strict";
  const storageKey = "salon-color-theme";
  const root = document.documentElement;
  let theme = "light";

  try {
    if (localStorage.getItem(storageKey) === "dark") theme = "dark";
  } catch {
    // The switch remains usable when browser storage is unavailable.
  }

  function applyTheme(value) {
    theme = value === "dark" ? "dark" : "light";
    root.dataset.theme = theme;
    const action = theme === "dark" ? "Usar tema claro" : "Usar tema escuro";
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      "content", theme === "dark" ? "#191518" : "#7b2843",
    );
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.hidden = false;
      button.setAttribute("aria-label", action);
      button.title = action;
      button.querySelector("[data-theme-label]").textContent = theme === "dark" ? "Tema claro" : "Tema escuro";
    });
  }

  // Run before the stylesheet so a saved dark theme does not flash white.
  applyTheme(theme);
  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(theme);
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        applyTheme(theme === "dark" ? "light" : "dark");
        try {
          localStorage.setItem(storageKey, theme);
        } catch {
          // Keep the chosen appearance for the current page.
        }
      });
    });
  });

  window.addEventListener("storage", (event) => {
    if (event.key === storageKey || event.key === null) applyTheme(event.newValue);
  });
})();
