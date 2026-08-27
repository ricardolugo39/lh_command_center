(() => {
  "use strict";
  const search = document.getElementById("rfq-customer-search");
  const customerId = document.getElementById("rfq-customer-id");
  const results = document.getElementById("rfq-customer-results");
  const items = document.getElementById("rfq-items");
  const template = document.getElementById("rfq-item-template");
  const add = document.getElementById("add-rfq-item");
  if (!search || !customerId || !results || !items || !template) return;

  let timer;
  let choices = [];
  let active = -1;
  let selectedLabel = search.value;

  const hide = () => {
    results.classList.add("d-none");
    results.innerHTML = "";
    choices = [];
    active = -1;
  };
  const choose = (customer) => {
    customerId.value = customer.workspace_customer_id;
    selectedLabel = customer.customer_name;
    search.value = selectedLabel;
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
    if (search.value !== selectedLabel) customerId.value = "";
    clearTimeout(timer);
    const query = search.value.trim();
    if (query.length < 2) return hide();
    timer = setTimeout(async () => {
      const response = await fetch(
        `/api/customers/search?scope=workspace&limit=10&q=${encodeURIComponent(query)}`
      );
      render(response.ok ? await response.json() : []);
    }, 250);
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
