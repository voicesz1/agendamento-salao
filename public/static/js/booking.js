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
