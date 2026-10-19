if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
  });
}

let installPrompt = null;
const installButton = document.getElementById("install-app");
const installDialog = document.getElementById("install-dialog");
const installDescription = document.getElementById("install-dialog-description");
const installConfirmButton = document.getElementById("install-dialog-confirm");
const DISMISSED_UNTIL_KEY = "salon-install-prompt-dismissed-until";

function appIsInstalled() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

function hideInstallControlsWhenInstalled() {
  if (!appIsInstalled()) return;
  if (installButton) installButton.hidden = true;
  document.querySelectorAll("[data-install-app]").forEach((button) => { button.hidden = true; });
}

hideInstallControlsWhenInstalled();

function getDismissedUntil() {
  try {
    return Number(localStorage.getItem(DISMISSED_UNTIL_KEY) || 0);
  } catch {
    return 0;
  }
}

function showInstallDialog({ force = false } = {}) {
  if (!installDialog?.showModal || appIsInstalled()) return;
  const dismissedUntil = getDismissedUntil();
  if (!force && Date.now() < dismissedUntil) return;
  if (installPrompt) {
    installDescription.textContent = "Tenha o agendamento do salão na tela inicial para acessar com mais praticidade.";
    installConfirmButton.textContent = "Instalar agora";
  } else {
    const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
    const isAndroid = /android/i.test(navigator.userAgent);
    if (isIos) {
      installDescription.textContent = "No Safari, toque em Compartilhar e escolha ‘Adicionar à Tela de Início’ para instalar o aplicativo.";
    } else if (isAndroid) {
      installDescription.textContent = "No Chrome, abra o menu ⋮ e toque em ‘Instalar app’ ou ‘Adicionar à tela inicial’.";
    } else {
      installDescription.textContent = "Abra este site no Chrome para Android ou Safari no iPhone e use o menu do navegador para instalar o aplicativo.";
    }
    installConfirmButton.textContent = "Entendi";
  }
  if (!installDialog.open) installDialog.showModal();
}

function dismissInstallDialog() {
  try {
    localStorage.setItem(DISMISSED_UNTIL_KEY, String(Date.now() + 7 * 24 * 60 * 60 * 1000));
  } catch {
    // The dialog can still close when browser storage is unavailable.
  }
  installDialog?.close();
}

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  showInstallDialog();
});

async function promptToInstall() {
  if (!installPrompt) {
    showInstallDialog({ force: true });
    return;
  }
  const promptEvent = installPrompt;
  promptEvent.prompt();
  const choice = await promptEvent.userChoice;
  installPrompt = null;
  installDialog?.close();
  if (choice?.outcome === "accepted" && installButton) installButton.hidden = true;
}

installButton?.addEventListener("click", promptToInstall);
document.querySelectorAll("[data-install-app]").forEach((button) => {
  button.addEventListener("click", promptToInstall);
});
installConfirmButton?.addEventListener("click", () => {
  if (installPrompt) promptToInstall();
  else installDialog?.close();
});
document.getElementById("install-dialog-later")?.addEventListener("click", dismissInstallDialog);
document.getElementById("install-dialog-close")?.addEventListener("click", dismissInstallDialog);

window.addEventListener("appinstalled", () => {
  hideInstallControlsWhenInstalled();
  installPrompt = null;
  installDialog?.close();
});
