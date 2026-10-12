if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  });
}

let installPrompt = null;
const installButton = document.getElementById("install-app");
const installDialog = document.getElementById("install-dialog");
const DISMISSED_UNTIL_KEY = "salon-install-prompt-dismissed-until";

function appIsInstalled() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function showInstallDialog() {
  if (!installPrompt || !installDialog?.showModal || appIsInstalled()) return;
  const dismissedUntil = Number(localStorage.getItem(DISMISSED_UNTIL_KEY) || 0);
  if (Date.now() < dismissedUntil) return;
  if (!installDialog.open) installDialog.showModal();
}

function dismissInstallDialog() {
  localStorage.setItem(DISMISSED_UNTIL_KEY, String(Date.now() + 7 * 24 * 60 * 60 * 1000));
  installDialog?.close();
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  if (installButton) installButton.hidden = false;
  showInstallDialog();
});

async function promptToInstall() {
  if (!installPrompt) return;
  const promptEvent = installPrompt;
  promptEvent.prompt();
  const choice = await promptEvent.userChoice;
  installPrompt = null;
  installDialog?.close();
  if (choice?.outcome === "accepted" && installButton) installButton.hidden = true;
}

installButton?.addEventListener("click", promptToInstall);
document.getElementById("install-dialog-confirm")?.addEventListener("click", promptToInstall);
document.getElementById("install-dialog-later")?.addEventListener("click", dismissInstallDialog);
document.getElementById("install-dialog-close")?.addEventListener("click", dismissInstallDialog);

window.addEventListener("appinstalled", () => {
  if (installButton) installButton.hidden = true;
  installPrompt = null;
  installDialog?.close();
});
