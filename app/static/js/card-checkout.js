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

  function getSdkErrorCode(error) {
    const causes = Array.isArray(error?.cause) ? error.cause : [error?.cause];
    const code = causes
      .map((cause) => cause && typeof cause === "object" ? cause.code : "")
      .find((value) => typeof value === "string" && value.length > 0);
    return code || "";
  }

  function cardErrorMessage(code) {
    const messages = {
      fields_setup_failed: "Os campos seguros do cartão não carregaram. Atualize a página e tente novamente.",
      get_payment_methods_failed: "Não foi possível carregar as opções de cartão. Tente novamente em instantes.",
      card_token_creation_failed: "O Mercado Pago não validou os dados do cartão. Confira número, validade, código de segurança e titular.",
      get_identification_types_failed: "Não foi possível carregar os tipos de documento. Atualize a página e tente novamente.",
      get_card_bin_payment_methods_failed: "Não foi possível identificar a bandeira do cartão. Confira o número informado.",
      get_card_issuers_failed: "Não foi possível identificar o banco emissor. Tente novamente ou use outro cartão.",
      get_payment_installments_failed: "Não foi possível consultar as parcelas para este cartão. Tente novamente.",
      missing_payment_information: "Faltam dados do cartão ou do parcelamento. Confira os campos e tente novamente.",
    };
    return messages[code] || "Não foi possível validar o cartão. Confira os campos e tente novamente.";
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
      onError: (error) => {
        // The SDK error contains diagnostic causes, not card form values. Log only
        // the cause code so production logs/console never receive payment data.
        const code = getSdkErrorCode(error);
        console.warn("Mercado Pago Card Payment Brick error", code || "unknown");
        showError(cardErrorMessage(code));
      },
    },
  }).catch(() => {
    loading.hidden = true;
    showError("Não foi possível abrir o formulário seguro do Mercado Pago. Atualize a página para tentar novamente.");
  });
})();
