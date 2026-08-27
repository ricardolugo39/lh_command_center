(() => {
  "use strict";
  document.querySelectorAll(".ask-drop").forEach((zone) => {
    const input = zone.querySelector('input[type="file"]');
    if (!input) return;
    ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    }));
    ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragging");
    }));
    zone.addEventListener("drop", (event) => {
      if (event.dataTransfer?.files?.length) input.files = event.dataTransfer.files;
    });
  });
  const search = document.getElementById("ask-customer-search");
  const hidden = document.getElementById("ask-customer-id");
  const results = document.getElementById("ask-customer-results");
  const exclude = document.getElementById("ask-exclude-customer");
  if (search && hidden && results) {
    let timer;
    let request;
    let choices = [];
    let active = -1;
    let selectedLabel = search.value;
    const setExpanded = (expanded) => {
      search.setAttribute("aria-expanded", String(expanded));
    };
    const hide = () => {
      results.classList.add("d-none");
      results.innerHTML = "";
      choices = [];
      active = -1;
      setExpanded(false);
    };
    const choose = (customer) => {
      hidden.value = customer.workspace_customer_id;
      selectedLabel = customer.customer_name;
      search.value = selectedLabel;
      hide();
    };
    const highlight = () => {
      results.querySelectorAll("[role='option']").forEach((button, index) => {
        const selected = index === active;
        button.classList.toggle("active", selected);
        button.setAttribute("aria-selected", String(selected));
        if (selected) button.scrollIntoView({ block: "nearest" });
      });
    };
    const message = (text, className = "") => {
      results.innerHTML = "";
      const item = document.createElement("div");
      item.className = `ask-search-message ${className}`.trim();
      item.textContent = text;
      results.appendChild(item);
      results.classList.remove("d-none");
      setExpanded(true);
    };
    const render = (customers) => {
      choices = customers;
      active = -1;
      results.innerHTML = "";
      if (!customers.length) {
        message("No encontramos clientes con ese nombre o NIT.");
        return;
      }
      customers.forEach((customer, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "list-group-item list-group-item-action text-start";
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", "false");
        button.id = `ask-customer-option-${index}`;
        const name = document.createElement("strong");
        name.textContent = customer.customer_name;
        const identity = document.createElement("span");
        identity.textContent = customer.nit ? `NIT ${customer.nit}` : "Sin NIT";
        button.append(name, identity);
        button.addEventListener("click", () => choose(customer));
        results.appendChild(button);
      });
      results.classList.remove("d-none");
      setExpanded(true);
    };
    search.addEventListener("input", () => {
      if (search.value !== selectedLabel) hidden.value = "";
      clearTimeout(timer);
      request?.abort();
      const query = search.value.trim();
      if (query.length < 2) return hide();
      timer = setTimeout(async () => {
        request = new AbortController();
        const timeout = window.setTimeout(() => request.abort(), 8000);
        message("Buscando clientes…", "is-loading");
        try {
          const response = await fetch(
            `/api/customers/search?scope=workspace&limit=12&q=${encodeURIComponent(query)}`,
            { signal: request.signal }
          );
          if (!response.ok) throw new Error("search_failed");
          if (search.value.trim() === query) render(await response.json());
        } catch (error) {
          if (search.value.trim() === query) {
            message(
              error.name === "AbortError"
                ? "La búsqueda tardó demasiado. Intente con más letras o con el NIT."
                : "No fue posible consultar los clientes. Intente nuevamente."
            );
          }
        } finally {
          window.clearTimeout(timeout);
        }
      }, 200);
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") return hide();
      if (!choices.length) return;
      if (event.key === "ArrowDown") {
        active = Math.min(active + 1, choices.length - 1);
      } else if (event.key === "ArrowUp") {
        active = Math.max(active - 1, 0);
      } else if (event.key === "Enter" && active >= 0) {
        event.preventDefault();
        return choose(choices[active]);
      } else {
        return;
      }
      event.preventDefault();
      highlight();
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".ask-customer-combobox")) hide();
    });
    exclude?.addEventListener("click", () => {
      hidden.value = "exclude";
      search.value = "";
      hide();
    });
  }

  const executeForm = document.getElementById("ask-execute-form");
  const progress = document.getElementById("ask-execution-progress");
  const progressBar = document.getElementById("ask-progress-bar");
  const progressMessage = document.getElementById("ask-progress-message");
  const stages = [...document.querySelectorAll("[data-ask-stage]")];
  executeForm?.addEventListener("submit", () => {
    const button = document.getElementById("ask-execute-button");
    button?.setAttribute("disabled", "disabled");
    progress.hidden = false;
    document.body.classList.add("ask-is-executing");
    let current = 0;
    const showStage = () => {
      stages.forEach((stage, index) => {
        stage.classList.toggle("is-current", index === current);
        stage.classList.toggle("is-complete", index < current);
      });
      const label = stages[current]?.lastElementChild?.textContent;
      if (label) progressMessage.textContent = label;
      if (progressBar) {
        progressBar.style.width = `${((current + 1) / stages.length) * 100}%`;
      }
      if (current < stages.length - 1) {
        current += 1;
        window.setTimeout(showStage, 900);
      }
    };
    showStage();
  });

  const conversationForm = document.getElementById("ask-conversation-form");
  const conversationProgress = document.getElementById("ask-conversational-progress");
  const liveProgress = document.getElementById("ask-live-progress");
  const selectedFiles = document.getElementById("ask-selected-files");
  const conversationFiles = conversationForm?.querySelector('input[type="file"]');
  conversationFiles?.addEventListener("change", () => {
    if (!selectedFiles) return;
    selectedFiles.innerHTML = "";
    [...conversationFiles.files].slice(0, 3).forEach((file) => {
      const item = document.createElement("span");
      item.className = "ask-selected-file";
      item.textContent = file.name;
      selectedFiles.appendChild(item);
    });
    if (conversationFiles.files.length > 3) {
      const remaining = document.createElement("span");
      remaining.className = "ask-selected-file";
      remaining.textContent = `+${conversationFiles.files.length - 3}`;
      selectedFiles.appendChild(remaining);
    }
  });
  conversationForm?.addEventListener("submit", () => {
    conversationProgress.hidden = false;
    conversationForm.querySelector("button[type='submit']")?.setAttribute(
      "disabled", "disabled"
    );
    const phrases = [
      "Leyendo su mensaje y la evidencia disponible.",
      "Consultando las fuentes necesarias.",
      "Contrastando información y calculando hallazgos.",
      "Preparando una respuesta verificable.",
    ];
    let phrase = 0;
    window.setInterval(() => {
      phrase = Math.min(phrase + 1, phrases.length - 1);
      if (liveProgress) liveProgress.textContent = phrases[phrase];
    }, 1300);
  });
  const chat = document.getElementById("ask-chat");
  chat?.lastElementChild?.scrollIntoView({ block: "end" });
})();
