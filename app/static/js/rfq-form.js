(() => {
  "use strict";
  const search = document.getElementById("rfq-customer-search");
  const customerId = document.getElementById("rfq-customer-id");
  const newCustomerName = document.getElementById("rfq-new-customer-name");
  const results = document.getElementById("rfq-customer-results");
  const useNew = document.getElementById("rfq-use-new-customer");
  const status = document.getElementById("rfq-customer-status");
  const items = document.getElementById("rfq-items");
  const template = document.getElementById("rfq-item-template");
  const add = document.getElementById("add-rfq-item");
  if (!search || !customerId || !results || !items || !template) return;

  let timer;
  let choices = [];
  let active = -1;
  let selectedLabel = search.value;
  let requestSequence = 0;
  let controller;

  const hide = () => {
    results.classList.add("d-none");
    results.innerHTML = "";
    choices = [];
    active = -1;
  };
  const choose = (customer) => {
    customerId.value = customer.workspace_customer_id;
    newCustomerName.value = "";
    selectedLabel = customer.customer_name;
    search.value = selectedLabel;
    status.textContent = `Cliente seleccionado: ${selectedLabel}`;
    useNew.classList.add("d-none");
    hide();
  };
  const chooseNew = () => {
    const name = search.value.trim();
    if (name.length < 2) return;
    customerId.value = "";
    newCustomerName.value = name;
    selectedLabel = name;
    status.textContent = `Cliente nuevo: ${name}`;
    useNew.classList.add("d-none");
    hide();
  };
  const highlight = () => {
    results.querySelectorAll("button").forEach((button, index) => {
      button.classList.toggle("active", index === active);
    });
  };
  const render = (customers) => {
    choices = customers;
    results.innerHTML = "";
    customers.forEach((customer) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "list-group-item list-group-item-action text-start";
      button.style.backgroundColor = "#fff";
      const name = document.createElement("strong");
      name.textContent = customer.customer_name;
      const identity = document.createElement("div");
      identity.className = "small text-secondary";
      identity.textContent = [
        customer.nit ? `NIT: ${customer.nit}` : "",
        customer.erp_id ? `ERP ID: ${customer.erp_id}` : "",
        customer.city || "",
      ].filter(Boolean).join(" · ");
      button.append(name, identity);
      button.addEventListener("click", () => choose(customer));
      results.appendChild(button);
    });
    results.classList.toggle("d-none", customers.length === 0);
  };
  search.addEventListener("input", () => {
    if (search.value !== selectedLabel) {
      customerId.value = "";
      newCustomerName.value = "";
      status.textContent = "Seleccione un resultado o registre un cliente nuevo.";
    }
    clearTimeout(timer);
    const query = search.value.trim();
    useNew.textContent = `+ Usar “${query}” como cliente nuevo`;
    useNew.classList.toggle("d-none", query.length < 2);
    if (query.length < 2) return hide();
    timer = setTimeout(async () => {
      const sequence = ++requestSequence;
      if (controller) controller.abort();
      controller = new AbortController();
      try {
        const response = await fetch(
          `/api/customers/search?scope=workspace&limit=8&q=${encodeURIComponent(query)}`,
          { signal: controller.signal }
        );
        if (sequence === requestSequence) {
          render(response.ok ? await response.json() : []);
        }
      } catch (error) {
        if (error.name !== "AbortError") hide();
      }
    }, 250);
  });
  useNew.addEventListener("click", chooseNew);
  document.addEventListener("click", (event) => {
    if (!search.parentElement.contains(event.target)) hide();
  });
  search.addEventListener("keydown", (event) => {
    if (!choices.length) return;
    if (event.key === "ArrowDown") active = Math.min(active + 1, choices.length - 1);
    else if (event.key === "ArrowUp") active = Math.max(active - 1, 0);
    else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      return choose(choices[active]);
    } else if (event.key === "Escape") return hide();
    else return;
    event.preventDefault();
    highlight();
  });

  const addItem = () => {
    items.appendChild(template.content.cloneNode(true));
  };
  add.addEventListener("click", addItem);
  items.addEventListener("click", (event) => {
    const remove = event.target.closest(".remove-rfq-item");
    if (!remove) return;
    if (items.querySelectorAll(".rfq-item").length > 1) {
      remove.closest(".rfq-item").remove();
    }
  });
  addItem();
})();
