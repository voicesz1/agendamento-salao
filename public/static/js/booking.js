<<<<<<< HEAD
const serviceSelect = document.getElementById("service_id");
const daySelect = document.getElementById("day");
const slotsBox = document.getElementById("slots");
const startInput = document.getElementById("start_time");

async function loadSlots() {
  startInput.value = "";
  const serviceId = serviceSelect.value;
  const day = daySelect.value;
  if (!serviceId || !day) {
    slotsBox.innerHTML = '<p class="hint">Selecione o serviço e o dia para ver os horários.</p>';
    return;
  }
  slotsBox.innerHTML = '<p class="hint">Carregando horários...</p>';
  const response = await fetch(`/api/horarios?servico=${serviceId}&dia=${day}`);
  const data = await response.json();
  if (!data.slots.length) {
    slotsBox.innerHTML = '<p class="hint">Não há horários livres neste dia. Tente outra data.</p>';
    return;
  }
  slotsBox.innerHTML = data.slots
    .map(
      (slot) =>
        `<button type="button" class="slot" data-time="${slot}">${slot}</button>`
    )
    .join("");
  slotsBox.querySelectorAll(".slot").forEach((button) => {
    button.addEventListener("click", () => {
      slotsBox.querySelectorAll(".slot").forEach((el) => el.classList.remove("chosen"));
      button.classList.add("chosen");
      startInput.value = button.dataset.time;
    });
  });
}

serviceSelect.addEventListener("change", loadSlots);
daySelect.addEventListener("change", loadSlots);
if (serviceSelect.value) loadSlots();

document.getElementById("booking-form").addEventListener("submit", (event) => {
  if (!startInput.value) {
    event.preventDefault();
    alert("Escolha um horário disponível.");
  }
});
=======
const serviceSelect = document.getElementById("service_id");
const daySelect = document.getElementById("day");
const slotsBox = document.getElementById("slots");
const startInput = document.getElementById("start_time");
const errorBox = document.getElementById("booking-error");
const submitButton = document.getElementById("booking-submit");
let slotController;

async function loadSlots() {
  slotController?.abort();
  const controller = new AbortController();
  slotController = controller;
  startInput.value = "";
  errorBox.hidden = true;
  const option = serviceSelect.selectedOptions[0];
  document.getElementById("booking-total").textContent = option?.dataset.price
    ? `R$ ${option.dataset.price}` : "Escolha um serviço";
  const serviceId = serviceSelect.value;
  const day = daySelect.value;
  if (!serviceId || !day) {
    slotsBox.setAttribute("aria-busy", "false");
    slotsBox.innerHTML = '<p class="hint">Selecione o serviço e o dia para ver os horários.</p>';
    return;
  }
  slotsBox.innerHTML = '<p class="hint">Carregando horários...</p>';
  slotsBox.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/horarios?servico=${encodeURIComponent(serviceId)}&dia=${encodeURIComponent(day)}`, { signal: controller.signal });
    if (!response.ok) throw new Error("Horários indisponíveis");
    const data = await response.json();
    if (!data.slots.length) {
      slotsBox.innerHTML = '<p class="hint">Não há horários livres neste dia. Tente outra data.</p>';
      return;
    }
    slotsBox.replaceChildren();
    data.slots.forEach((slot) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "slot";
      button.dataset.time = slot;
      button.textContent = slot;
      button.setAttribute("aria-pressed", "false");
      slotsBox.appendChild(button);
    });
    slotsBox.querySelectorAll(".slot").forEach((button) => {
      button.addEventListener("click", () => {
        slotsBox.querySelectorAll(".slot").forEach((el) => {
          el.classList.remove("chosen");
          el.setAttribute("aria-pressed", "false");
        });
        button.classList.add("chosen");
        button.setAttribute("aria-pressed", "true");
        startInput.value = button.dataset.time;
        errorBox.hidden = true;
      });
    });
  } catch (error) {
    if (error.name !== "AbortError") {
      slotsBox.replaceChildren();
      const message = document.createElement("p");
      message.className = "hint";
      message.textContent = "Não foi possível carregar os horários. Verifique sua conexão.";
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "btn ghost";
      retry.textContent = "Tentar novamente";
      retry.addEventListener("click", loadSlots);
      slotsBox.append(message, retry);
    }
  } finally {
    if (slotController === controller) slotsBox.setAttribute("aria-busy", "false");
  }
}

serviceSelect.addEventListener("change", loadSlots);
daySelect.addEventListener("change", loadSlots);
if (serviceSelect.value) loadSlots();

document.getElementById("booking-form").addEventListener("submit", (event) => {
  if (!startInput.value) {
    event.preventDefault();
    errorBox.textContent = "Escolha um horário disponível para continuar.";
    errorBox.hidden = false;
    slotsBox.querySelector("button")?.focus();
    return;
  }
  submitButton.disabled = true;
  submitButton.textContent = "Reservando seu horário…";
});

window.addEventListener("pageshow", () => {
  submitButton.disabled = false;
  submitButton.textContent = "Reservar meu horário →";
});
>>>>>>> 18a17922f68412df42a435d3021fd4f1037c0346
