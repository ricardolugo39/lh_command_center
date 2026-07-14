(() => {
    "use strict";

    const searchInput = document.getElementById("customer-search");
    const resultsContainer = document.getElementById("customer-results");

    const customerIdInput = document.getElementById("customer_id");
    const customerSiteIdInput = document.getElementById(
        "customer_site_id"
    );
    const salesRepInput = document.getElementById("sales_rep");

    const selectedCard = document.getElementById(
        "selected-customer-card"
    );
    const selectedName = document.getElementById(
        "selected-customer-name"
    );
    const selectedLocation = document.getElementById(
        "selected-customer-location"
    );
    const selectedAddress = document.getElementById(
        "selected-customer-address"
    );
    const clearCustomerButton = document.getElementById(
        "clear-customer"
    );

    if (!searchInput || !resultsContainer) {
        return;
    }

    let debounceTimer = null;
    let selectedCustomer = null;
    let activeResultIndex = -1;
    let currentResults = [];

    function clearResults() {
        resultsContainer.innerHTML = "";
        resultsContainer.classList.add("d-none");
        currentResults = [];
        activeResultIndex = -1;
    }

    function clearSelectedCustomer({
        keepSearchText = false,
    } = {}) {
        selectedCustomer = null;

        customerIdInput.value = "";
        customerSiteIdInput.value = "";
        salesRepInput.value = "";

        selectedName.textContent = "";
        selectedLocation.textContent = "";
        selectedAddress.textContent = "";

        selectedCard.style.display = "none";

        if (!keepSearchText) {
            searchInput.value = "";
        }
    }

    function selectCustomer(customer) {
        selectedCustomer = customer;

        customerIdInput.value = customer.customer_id || "";
        customerSiteIdInput.value = customer.customer_site_id || "";
        salesRepInput.value = customer.seller || "";

        searchInput.value = [
            customer.customer_name,
            customer.city,
        ]
            .filter(Boolean)
            .join(" — ");

        selectedName.textContent = customer.customer_name || "";

        selectedLocation.textContent = [
            customer.city,
            `NIT ${customer.customer_id}`,
        ]
            .filter(Boolean)
            .join(" · ");

        selectedAddress.textContent = customer.address || "";

        selectedCard.style.display = "block";

        clearResults();
    }

    function createResultElement(customer, index) {
        const item = document.createElement("button");

        item.type = "button";
        item.className = [
            "customer-result",
            "list-group-item",
            "list-group-item-action",
            "text-start",
        ].join(" ");

        item.dataset.index = String(index);

        const name = document.createElement("div");
        name.className = "fw-bold";
        name.textContent = customer.customer_name || "";

        const location = document.createElement("div");
        location.className = "text-secondary small mt-1";
        location.textContent = [
            customer.city,
            customer.address,
        ]
            .filter(Boolean)
            .join(" · ");

        const seller = document.createElement("div");
        seller.className = "text-secondary small mt-1";
        seller.textContent = customer.seller
            ? `Vendedor: ${customer.seller}`
            : "Sin vendedor asignado";

        item.appendChild(name);
        item.appendChild(location);
        item.appendChild(seller);

        item.addEventListener("click", () => {
            selectCustomer(customer);
        });

        return item;
    }

    function renderResults(customers) {
        clearResults();

        if (!customers.length) {
            const empty = document.createElement("div");

            empty.className = "p-3 text-secondary";
            empty.textContent = "No se encontraron clientes.";

            resultsContainer.appendChild(empty);
            resultsContainer.classList.remove("d-none");
            return;
        }

        currentResults = customers;

        const list = document.createElement("div");
        list.className = "list-group list-group-flush";

        customers.forEach((customer, index) => {
            list.appendChild(
                createResultElement(customer, index)
            );
        });

        resultsContainer.appendChild(list);
        resultsContainer.classList.remove("d-none");
    }

    function renderLoading() {
        resultsContainer.innerHTML = `
            <div class="p-3 text-secondary">
                Buscando clientes...
            </div>
        `;

        resultsContainer.classList.remove("d-none");
    }

    async function searchCustomers(query) {
        renderLoading();

        try {
            const response = await fetch(
                `/api/customers/search?q=${encodeURIComponent(query)}`,
                {
                    headers: {
                        Accept: "application/json",
                    },
                }
            );

            if (!response.ok) {
                throw new Error(
                    `Customer search failed: ${response.status}`
                );
            }

            const customers = await response.json();

            if (searchInput.value.trim() !== query) {
                return;
            }

            renderResults(customers);
        } catch (error) {
            console.error(error);

            resultsContainer.innerHTML = `
                <div class="p-3 text-danger">
                    No fue posible buscar clientes.
                </div>
            `;

            resultsContainer.classList.remove("d-none");
        }
    }

    function updateActiveResult() {
        const items = resultsContainer.querySelectorAll(
            ".customer-result"
        );

        items.forEach((item, index) => {
            item.classList.toggle(
                "active",
                index === activeResultIndex
            );
        });

        if (
            activeResultIndex >= 0
            && items[activeResultIndex]
        ) {
            items[activeResultIndex].scrollIntoView({
                block: "nearest",
            });
        }
    }

    searchInput.addEventListener("input", () => {
        const query = searchInput.value.trim();

        window.clearTimeout(debounceTimer);

        if (selectedCustomer) {
            clearSelectedCustomer({
                keepSearchText: true,
            });
        }

        if (query.length < 2) {
            clearResults();
            return;
        }

        debounceTimer = window.setTimeout(() => {
            searchCustomers(query);
        }, 300);
    });

    searchInput.addEventListener("keydown", (event) => {
        if (
            resultsContainer.classList.contains("d-none")
            || currentResults.length === 0
        ) {
            return;
        }

        if (event.key === "ArrowDown") {
            event.preventDefault();

            activeResultIndex = Math.min(
                activeResultIndex + 1,
                currentResults.length - 1
            );

            updateActiveResult();
        }

        if (event.key === "ArrowUp") {
            event.preventDefault();

            activeResultIndex = Math.max(
                activeResultIndex - 1,
                0
            );

            updateActiveResult();
        }

        if (
            event.key === "Enter"
            && activeResultIndex >= 0
        ) {
            event.preventDefault();

            selectCustomer(
                currentResults[activeResultIndex]
            );
        }

        if (event.key === "Escape") {
            clearResults();
        }
    });

    clearCustomerButton.addEventListener("click", () => {
        clearSelectedCustomer();
        clearResults();
        searchInput.focus();
    });

    document.addEventListener("click", (event) => {
        const clickedInsideLookup = (
            searchInput.contains(event.target)
            || resultsContainer.contains(event.target)
        );

        if (!clickedInsideLookup) {
            clearResults();
        }
    });
})();