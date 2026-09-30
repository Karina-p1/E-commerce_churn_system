/* ==========================================
   RESPONSIVE CUSTOM SELECT
   Turns a plain <select> into the same custom
   dropdown used in complaint_form.html, but with
   viewport awareness so the option list never
   floods out of the screen.

   The original select is kept in the DOM (hidden),
   so Django validation, form POST and any existing
   JS listening for "change" are untouched.

   Usage
   -----
   Put  data-responsive-select  on the <select> itself
   or on any container (a <form> works well) and every
   <select> inside it gets enhanced.
========================================== */

(function () {
    "use strict";

    if (window.RsSelect) return;

    const ARROW =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<polyline points="6 9 12 15 18 9" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round" />' +
        "</svg>";

    const GAP = 5;
    const EDGE = 10;
    const MIN_HEIGHT = 96;

    let current = null;

    function closeAll() {
        document
            .querySelectorAll(".rs-wrapper.open")
            .forEach(function (wrapper) {
                wrapper.classList.remove("open", "rs-up");

                const trigger = wrapper.querySelector(".rs-trigger");
                if (trigger) {
                    trigger.setAttribute("aria-expanded", "false");
                }
            });

        current = null;
    }

    function open(wrapper) {
        closeAll();

        wrapper.classList.add("open");
        current = wrapper;

        const trigger = wrapper.querySelector(".rs-trigger");
        if (trigger) trigger.setAttribute("aria-expanded", "true");

        position();
    }

    /* Flip the menu upwards when there is not enough room
       below, then clamp it to the space that is left. */
    function position() {
        if (!current) return;

        const wrapper = current;
        const menu = wrapper.querySelector(".rs-menu");
        const trigger = wrapper.querySelector(".rs-trigger");
        if (!menu || !trigger) return;

        const rect = trigger.getBoundingClientRect();
        const viewport =
            window.innerHeight || document.documentElement.clientHeight;

        const below = viewport - rect.bottom - EDGE - GAP;
        const above = rect.top - EDGE - GAP;

        const cap = Math.floor(Math.min(240, viewport * 0.45));
        const needed = Math.min(menu.scrollHeight, cap);

        wrapper.classList.toggle(
            "rs-up",
            below < needed && above > below
        );

        const space = wrapper.classList.contains("rs-up") ? above : below;
        menu.style.maxHeight = Math.max(MIN_HEIGHT, Math.min(cap, space)) + "px";

        /* Keep the selected option in view */
        const selected = menu.querySelector(".rs-option.selected");
        if (!selected) return;

        const top = selected.offsetTop;
        const bottom = top + selected.offsetHeight;

        if (top < menu.scrollTop) {
            menu.scrollTop = top;
        } else if (bottom > menu.scrollTop + menu.clientHeight) {
            menu.scrollTop = bottom - menu.clientHeight;
        }
    }

    function enhance(select) {
        if (!select || select.dataset.rsEnhanced === "1") return;
        if (select.multiple || select.size > 1) return;
        if (!select.parentNode) return;

        select.dataset.rsEnhanced = "1";

        const classes = select.className.trim();

        /* --- wrapper -------------------------------------------------
           Reuses the select's classes so the site's own layout and
           media queries still apply, only the box is dropped. */
        const wrapper = document.createElement("div");
        wrapper.className = "rs-wrapper" + (classes ? " " + classes : "");

        select.parentNode.insertBefore(wrapper, select);
        wrapper.appendChild(select);

        select.classList.add("rs-native");
        select.setAttribute("tabindex", "-1");

        /* --- trigger -------------------------------------------------
           Reuses the same classes, so the trigger looks exactly like
           the select it replaced. */
        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "rs-trigger" + (classes ? " " + classes : "");
        trigger.setAttribute("aria-haspopup", "listbox");
        trigger.setAttribute("aria-expanded", "false");

        if (select.getAttribute("aria-label")) {
            trigger.setAttribute(
                "aria-label",
                select.getAttribute("aria-label")
            );
        }

        const label = document.createElement("span");
        label.className = "rs-label";

        const arrow = document.createElement("span");
        arrow.className = "rs-arrow";
        arrow.innerHTML = ARROW;

        trigger.appendChild(label);
        trigger.appendChild(arrow);

        wrapper.appendChild(trigger);

        /* --- menu ---------------------------------------------------- */

        const menu = document.createElement("div");
        menu.className = "rs-menu";
        menu.setAttribute("role", "listbox");

        wrapper.appendChild(menu);

        Array.prototype.forEach.call(select.options, function (option) {
            const button = document.createElement("button");

            button.type = "button";
            button.className = "rs-option";
            button.setAttribute("role", "option");
            button.textContent = option.text;
            button.dataset.value = option.value;

            if (option.disabled) {
                button.classList.add("disabled");
            }

            button.addEventListener("click", function () {
                if (option.disabled) return;

                select.value = option.value;
                wrapper.classList.remove("rs-invalid");

                /* Tell Django, and any other listener on the page,
                   that the field changed */
                select.dispatchEvent(
                    new Event("change", { bubbles: true })
                );

                closeAll();
                trigger.focus();
            });

            menu.appendChild(button);
        });

        function sync() {
            const option = select.options[select.selectedIndex];

            label.textContent = option ? option.text : "";

            menu.querySelectorAll(".rs-option").forEach(function (item) {
                const active = item.dataset.value === select.value;

                item.classList.toggle("selected", active);
                item.setAttribute(
                    "aria-selected",
                    active ? "true" : "false"
                );
            });

            if (select.value !== "") {
                wrapper.classList.remove("rs-invalid");
            }
        }

        select.addEventListener("change", sync);
        sync();

        /* --- open / close ------------------------------------------- */

        trigger.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();

            if (wrapper.classList.contains("open")) {
                closeAll();
                return;
            }

            open(wrapper);
        });
    }

    /* ======================================
       REQUIRED FIELD GUARD
       The real select is hidden, so show the
       error on the custom dropdown instead of
       letting the browser point at a 1px input.
    ====================================== */

    window.addEventListener(
        "invalid",
        function (event) {
            const select = event.target;

            if (!select || select.tagName !== "SELECT") return;
            if (!select.classList.contains("rs-native")) return;

            const wrapper = select.closest(".rs-wrapper");
            if (!wrapper) return;

            event.preventDefault();

            wrapper.classList.add("rs-invalid");
            open(wrapper);

            const trigger = wrapper.querySelector(".rs-trigger");
            if (trigger) trigger.focus();
        },
        true
    );

    /* ======================================
       GLOBAL CLOSING
    ====================================== */

    document.addEventListener("click", function (event) {
        if (!current) return;
        if (current.contains(event.target)) return;

        closeAll();
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && current) {
            const trigger = current.querySelector(".rs-trigger");

            closeAll();
            if (trigger) trigger.focus();
            return;
        }

        if (event.key === "Tab") closeAll();
    });

    window.addEventListener("resize", position);

    window.addEventListener(
        "scroll",
        function (event) {
            if (!current) return;
            if (current.querySelector(".rs-menu") === event.target) return;

            position();
        },
        true
    );

    /* ======================================
       INIT
    ====================================== */

    function init(root) {
        const scope = root || document;

        scope
            .querySelectorAll("[data-responsive-select]")
            .forEach(function (node) {
                if (node.tagName === "SELECT") {
                    enhance(node);
                    return;
                }

                node.querySelectorAll("select").forEach(enhance);
            });
    }

    window.RsSelect = { init: init };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init();
        });
    } else {
        init();
    }
})();
