(() => {
    document.querySelectorAll(".cp-row[data-href]").forEach((row) => {
        const open = () => window.location.assign(row.dataset.href);
        row.addEventListener("click", (event) => {
            if (!event.target.closest("a,button,.dropdown-menu")) open();
        });
        row.addEventListener("keydown", (event) => {
            if (event.key === "Enter") open();
        });
    });
})();
