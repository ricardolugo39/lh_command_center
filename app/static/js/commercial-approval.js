(() => {
  const panel = document.querySelector("[data-approval-calculator]");
  if (!panel) return;

  const discount = panel.querySelector("[name='approved_discount']");
  const unitOutput = panel.querySelector("[data-approved-unit]");
  const totalOutput = panel.querySelector("[data-approved-total]");
  const differenceOutput = panel.querySelector("[data-amount-difference]");
  const currency = panel.dataset.currency || "COP";
  const listPrice = Number(panel.dataset.listPrice);
  const quantity = Number(panel.dataset.quantity);
  const currentAmount = Number(panel.dataset.currentAmount);
  const hasCurrentAmount = panel.dataset.hasCurrent === "true";

  const format = (value) => Number.isFinite(value)
    ? `${currency} ${value.toLocaleString("es-CO", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`
    : "—";

  const refresh = () => {
    const value = Number(discount.value);
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      unitOutput.textContent = totalOutput.textContent = differenceOutput.textContent = "—";
      return;
    }
    const unit = Math.round((listPrice * (1 - value / 100) + Number.EPSILON) * 100) / 100;
    const total = Math.round((unit * quantity + Number.EPSILON) * 100) / 100;
    unitOutput.textContent = format(unit);
    totalOutput.textContent = format(total);
    if (!hasCurrentAmount) {
      differenceOutput.textContent = "La oportunidad todavía no tiene un monto registrado. Al aprobar, se establecerá este valor como monto vigente.";
      return;
    }
    const difference = total - currentAmount;
    const percent = currentAmount ? difference / currentAmount * 100 : 0;
    differenceOutput.textContent = `${format(difference)} (${percent.toLocaleString("es-CO", {minimumFractionDigits: 2, maximumFractionDigits: 2})}%)`;
  };

  discount.addEventListener("input", refresh);
  refresh();
})();
