/* ==========================================
   CLIENT-SIDE FORM VALIDATION
   A thin, dependency-free layer that runs
   before the browser submits a form, so the
   customer finds out about an empty or
   malformed field without a page reload.

   This never replaces the server-side
   validation in views.py / forms.py — it
   only mirrors it for the rules that can be
   checked in the browser. The server is
   still the authority.

   Applied automatically to every non-GET form; GET search/filter forms are
   left alone. Opt a form out with data-no-validate, or a single field out
   with data-fv-ignore.

   Per-field extras
   ----------------
   data-fv-label      override the field name
                      shown in the message
   data-fv-required-when="reason:other"
                      required only while the
                      field <name> equals <value>
                      (pipe several accepted
                      values: "rating:1|2|3")
   data-fv-digits     digits only
   data-fv-phone      Nepali mobile number
   data-fv-min        / data-fv-max
                      extra numeric bounds
   data-fv-max-size   max file size in MB
   ========================================== */

(function () {
    "use strict";

    if (window.FormValidation) return;

    const PHONE_RE = /^9\d{9}$/;
    const SKIP_TYPES = {
        hidden: true,
        submit: true,
        button: true,
        reset: true,
        image: true
    };

    /* Humanize a field name: "bank_name" -> "Bank name" */
    function humanize(name) {
        const cleaned = String(name || "")
            .replace(/^.*\[(.*)\].*$/, "$1")
            .replace(/_/g, " ")
            .trim();

        if (!cleaned) return "This field";

        return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
    }

    /* Prefer an explicit label over guessing from the field name. */
    function labelFor(control) {
        if (control.dataset.fvLabel) return control.dataset.fvLabel;

        if (control.getAttribute("aria-label")) {
            return control.getAttribute("aria-label");
        }

        if (control.id) {
            const linked = document.querySelector(
                'label[for="' + CSS.escape(control.id) + '"]'
            );

            if (linked) return linked.textContent.trim();
        }

        /* Django's {{ form.field }} is often wrapped in a <p> with a
           sibling <label> that has no `for`, so fall back to the closest
           labelled ancestor. */
        let scope = control.parentElement;

        for (let depth = 0; depth < 3 && scope; depth += 1) {
            const label = scope.querySelector("label");

            if (label) {
                const text = label.textContent.trim();

                if (text && text.length <= 60) return text;
            }

            scope = scope.parentElement;
        }

        return humanize(control.name);
    }

    function isEmpty(control) {
        if (control.type === "file") {
            return !control.files || control.files.length === 0;
        }

        return String(control.value || "").trim() === "";
    }

    /* Django has already rendered its own error list for this field after
       a failed POST — don't stack a second message on top of it.

       The `is-invalid` check alone is not enough: showError() adds that
       same class, so treating it as "the server already said so" meant the
       first client-side failure disabled every later check on that field
       and the bad data went straight to the server. The class this layer
       adds is therefore tagged in data-fv-error and recognised as ours. */
    function hasServerError(control) {
        if (control.dataset.fvError !== undefined) return false;
        if (control.classList.contains("is-invalid")) return true;

        const scope = control.parentElement;

        if (scope && scope.querySelector(".errorlist")) return true;

        return false;
    }

    function isConditionallyRequired(control) {
        const rule = control.dataset.fvRequiredWhen;

        if (!rule) return false;

        const separator = rule.indexOf(":");

        if (separator === -1) return false;

        const fieldName = rule.slice(0, separator).trim();
        const expected = rule
            .slice(separator + 1)
            .split("|")
            .map(function (value) {
                return value.trim();
            });

        const other = control.form
            ? control.form.querySelector('[name="' + CSS.escape(fieldName) + '"]')
            : null;

        return Boolean(other) && expected.indexOf(other.value) !== -1;
    }

    function check(control) {
        const label = labelFor(control);

        /* --- required ------------------------------------------------ */
        if (control.hasAttribute("required") || isConditionallyRequired(control)) {
            if (isEmpty(control)) {
                return label + " is required.";
            }
        }

        if (isEmpty(control)) return null;

        const value = String(control.value).trim();

        /* --- type specific ------------------------------------------- */
        if (control.dataset.fvPhone !== undefined || control.type === "tel") {
            const digits = value.replace(/[^\d+]/g, "").replace(/^\+/, "");

            const local = digits.indexOf("977") === 0
                ? digits.slice(3)
                : digits.charAt(0) === "0"
                    ? digits.slice(1)
                    : digits;

            if (!PHONE_RE.test(local)) {
                return (
                    label +
                    " must be a valid Nepali mobile number " +
                    "(10 digits starting with 9)."
                );
            }
        }

        /* Mirrors validate_digits() on the server, which strips spaces and
           dashes before checking. Without this the browser would reject
           "1234 5678 9012" even though the server accepts it. */
        if (control.dataset.fvDigits !== undefined) {
            const digits = value.replace(/[\s-]+/g, "");

            if (digits && !/^\d+$/.test(digits)) {
                return label + " must contain digits only.";
            }
        }

        if (control.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
            return label + " must be a valid email address.";
        }

        if (control.type === "url" && !/^https?:\/\/.+/i.test(value)) {
            return label + " must be a valid URL starting with http:// or https://.";
        }

        if (control.type === "number") {
            const number = Number(value);

            if (Number.isNaN(number)) {
                return label + " must be a number.";
            }

            const min = control.min !== "" ? control.min : control.dataset.fvMin;
            const max = control.max !== "" ? control.max : control.dataset.fvMax;

            if (min !== undefined && min !== "" && number < Number(min)) {
                return label + " cannot be less than " + min + ".";
            }

            if (max !== undefined && max !== "" && number > Number(max)) {
                return label + " cannot be greater than " + max + ".";
            }
        }

        /* --- length -------------------------------------------------- */
        if (control.minLength > 0 && value.length < control.minLength) {
            return (
                label + " must be at least " + control.minLength + " characters long."
            );
        }

        if (control.maxLength > 0 && value.length > control.maxLength) {
            return label + " must be " + control.maxLength + " characters or fewer.";
        }

        if (control.pattern) {
            let pattern;

            try {
                pattern = new RegExp("^(?:" + control.pattern + ")$");
            } catch (error) {
                pattern = null;
            }

            if (pattern && !pattern.test(value)) {
                return (
                    label +
                    " is not in the expected format" +
                    (control.title ? " (" + control.title + ")" : "") +
                    "."
                );
            }
        }

        /* --- files ---------------------------------------------------- */
        if (control.type === "file" && control.files && control.files.length) {
            const maxMb = control.dataset.fvMaxSize;

            if (maxMb) {
                const limit = Number(maxMb) * 1024 * 1024;

                Array.prototype.forEach.call(control.files, function (file) {
                    if (file.size > limit) {
                        /* Surfaced below via the shared message slot. */
                        control.dataset.fvFileError =
                            label + " must be smaller than " + maxMb + " MB.";
                    }
                });

                if (control.dataset.fvFileError) {
                    const message = control.dataset.fvFileError;
                    delete control.dataset.fvFileError;
                    return message;
                }
            }

            if (control.accept) {
                const patterns = control.accept
                    .split(",")
                    .map(function (part) {
                        return part.trim().toLowerCase();
                    })
                    .filter(Boolean);

                const matches = Array.prototype.some.call(
                    control.files,
                    function (file) {
                        const type = (file.type || "").toLowerCase();

                        return patterns.some(function (pattern) {
                            if (pattern.charAt(0) === ".") {
                                return file.name.toLowerCase().endsWith(pattern);
                            }

                            if (pattern.endsWith("/*")) {
                                return type.indexOf(pattern.slice(0, -1)) === 0;
                            }

                            return type === pattern;
                        });
                    }
                );

                if (!matches) {
                    return label + " has an unsupported file type.";
                }
            }
        }

        return null;
    }

    /* ======================================
       ERROR SURFACING
       Bootstrap's own .invalid-feedback is
       reused so messages look native next to
       the rest of the form styling.
    ====================================== */

    function errorNodeFor(control, form) {
        const id = "fv-error-" + form.dataset.fvUid + "-" + control.name;

        let node = form.querySelector('#' + CSS.escape(id));

        if (node) return node;

        node = document.createElement("div");
        node.className = "invalid-feedback d-block";
        node.id = id;

        return node;
    }

    function showError(control, form, message) {
        const node = errorNodeFor(control, form);

        node.textContent = message;

        /* Marks the message as this layer's, not a server-rendered one. */
        control.dataset.fvError = "1";

        if (control.type === "file") {
            control.parentElement.appendChild(node);
        } else {
            control.insertAdjacentElement("afterend", node);
        }

        if (control.tagName === "SELECT" && control.classList.contains("rs-native")) {
            /* The real select is hidden by the custom dropdown, so the
               red outline has to go on the wrapper instead. */
            const wrapper = control.closest(".rs-wrapper");

            if (wrapper) wrapper.classList.add("rs-invalid");

            return;
        }

        control.classList.add("is-invalid");
    }

    function clearError(control, form) {
        delete control.dataset.fvError;
        control.classList.remove("is-invalid");

        const wrapper = control.closest(".rs-wrapper");

        if (wrapper) wrapper.classList.remove("rs-invalid");

        if (!form) return;

        const node = form.querySelector(
            '#fv-error-' + CSS.escape(form.dataset.fvUid) + "-" +
            CSS.escape(control.name)
        );

        if (node) node.remove();
    }

    function controlsIn(form) {
        return Array.prototype.filter.call(
            form.querySelectorAll("input, select, textarea"),
            function (control) {
                if (SKIP_TYPES[control.type]) return false;
                if (control.disabled || control.readOnly) return false;
                if (control.dataset.fvIgnore !== undefined) return false;

                /* Django's own hidden fields (e.g. a lat/lng pair) have
                   no visible input, so a required rule on them would
                   point the customer at nothing. */
                if (
                    control.type === "hidden" &&
                    !control.hasAttribute("required")
                ) {
                    return false;
                }

                return true;
            }
        );
    }

    function validateForm(form) {
        const controls = controlsIn(form);
        let firstInvalid = null;

        controls.forEach(function (control) {
            const message = check(control);

            if (!message) {
                clearError(control, form);
                return;
            }

            if (hasServerError(control)) {
                /* Django already explained this field after the last POST,
                   so don't stack a second message on top of it — but still
                   hold the submit, or the bad value would be posted again
                   with no new feedback. */
                if (!firstInvalid) firstInvalid = control;

                return;
            }

            showError(control, form, message);

            if (!firstInvalid) firstInvalid = control;
        });

        return firstInvalid;
    }

    /* ======================================
       INIT
    ====================================== */

    let uid = 0;

    function init(root) {
        const scope = root || document;

        scope.querySelectorAll("form").forEach(function (form) {
            if (form.dataset.fvBound === "1") return;
            if (form.hasAttribute("data-no-validate")) return;

            const method = (form.getAttribute("method") || "get").toLowerCase();

            /* Search / filter forms have nothing worth validating. */
            if (method === "get") return;

            form.dataset.fvBound = "1";
            form.dataset.fvUid = String((uid += 1));

            form.addEventListener("submit", function (event) {
                const firstInvalid = validateForm(form);

                if (!firstInvalid) return;

                event.preventDefault();
                event.stopPropagation();

                firstInvalid.focus({ preventScroll: true });
                firstInvalid.scrollIntoView({
                    behavior: "smooth",
                    block: "center"
                });
            });

            /* Live feedback: only re-check a field once it has already
               been flagged, so the customer isn't scolded while they are
               still typing their first character. */
            form.addEventListener(
                "blur",
                function (event) {
                    const control = event.target;

                    if (!control || !control.name) return;
                    if (hasServerError(control)) return;
                    if (!control.classList.contains("is-invalid")) {
                        if (!control.closest(".rs-invalid")) return;
                    }

                    const message = check(control);

                    if (message) {
                        showError(control, form, message);
                    } else {
                        clearError(control, form);
                    }
                },
                true
            );

            form.addEventListener("input", function (event) {
                const control = event.target;

                if (!control || !control.name) return;
                if (!control.classList.contains("is-invalid")) return;
                if (hasServerError(control)) return;

                const message = check(control);

                if (message) {
                    showError(control, form, message);
                } else {
                    clearError(control, form);
                }
            });
        });
    }

    window.FormValidation = { init: init, check: check };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            init();
        });
    } else {
        init();
    }
})();
