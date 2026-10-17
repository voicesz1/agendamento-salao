const copyButton = document.getElementById("copy-pix");
copyButton?.addEventListener("click", async () => {
  const key = document.getElementById("pix-key");
  const result = document.getElementById("copy-result");
  try {
    await navigator.clipboard.writeText(key.value);
    result.textContent = "Chave copiada. Confira o titular e o valor no aplicativo do banco.";
  } catch {
    key.focus();
    key.select();
    key.setSelectionRange(0, key.value.length);
    result.textContent = "Selecione e copie a chave acima para usar no seu banco.";
  }
});
