(() => {
  "use strict";

  const root = document.getElementById("card-payment");
  const container = document.getElementById("cardPaymentBrick_container");
  const loading = document.getElementById("card-payment-loading");
  const result = document.getElementById("card-payment-result");
  if (!root || !container || !loading || !result) return;

  function showError(message) {
    result.textContent = message;
    result.classList.add("alert");
  }

  if (!window.MercadoPago) {
    loading.hidden = true;
    showError("Não foi possível carregar o formulário do Mercado Pago. Atualize a página ou tente novamente mais tarde.");
    return;
  }

  const publicKey = root.dataset.publicKey;
  const amount = Number(root.dataset.amount);
  if (!publicKey || !Number.isFinite(amount) || amount <= 0) {
    loading.hidden = true;
    showError("O formulário de pagamento não está configurado. Entre em contato com o salão.");
    return;
  }

  const theme = document.documentElement.dataset.theme === "dark" ? "dark" : "default";
  const mp = new window.MercadoPago(publicKey, { locale: "pt-BR" });
  const bricksBuilder = mp.bricks({ theme });

  bricksBuilder.create("cardPayment", "cardPaymentBrick_container", {
    initialization: { amount },
    customization: {
      visual: {
        texts: { formTitle: "Cartão de crédito ou débito" },
      },
      paymentMethods: {
        // Allow both credit and debit cards
        minInstallments: 1,
        maxInstallments: 12,
      },
    },
    callbacks: {
      onReady: () => {
        loading.hidden = true;
      },
      onSubmit: async (formData) => {
        result.textContent = "Enviando pagamento para autorização…";
        result.classList.remove("alert");
        try {
          const response = await fetch(root.dataset.endpoint, {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": root.dataset.csrf,
            },
            body: JSON.stringify(formData),
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(data.detail || "Não foi possível iniciar o pagamento. Confira os dados e tente novamente.");
          }
          if (data.redirect) {
            window.location.assign(data.redirect);
            return data;
          }
          throw new Error("Não recebemos a confirmação do pagamento. Atualize a página para consultar a reserva.");
        } catch (error) {
          showError(error.message || "Não foi possível enviar o pagamento. Tente novamente.");
          throw error;
        }
      },
      onError: () => {
        showError("Não foi possível validar o cartão. Confira os campos e tente novamente.");
      },
    },
  }).catch(() => {
    loading.hidden = true;
    showError("Não foi possível abrir o formulário seguro do Mercado Pago. Atualize a página para tentar novamente.");
  });
})();
