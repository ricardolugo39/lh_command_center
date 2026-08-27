(() => {
    const sidebar = document.getElementById("ccc-sidebar");
    const toggle = document.getElementById("ccc-sidebar-toggle");
    if (!sidebar || !toggle) return;
    const expanded = window.localStorage.getItem("ccc-sidebar-expanded") === "true";
    sidebar.classList.toggle("is-expanded", expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.addEventListener("click", () => {
        const next = !sidebar.classList.contains("is-expanded");
        sidebar.classList.toggle("is-expanded", next);
        toggle.setAttribute("aria-expanded", String(next));
        window.localStorage.setItem("ccc-sidebar-expanded", String(next));
    });
})();
