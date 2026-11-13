(function () {
  "use strict";

  const root = document.documentElement;
  const themeButton = document.getElementById("theme-toggle");

  function currentTheme() {
    return root.dataset.theme === "dark" ? "dark" : "light";
  }

  function syncThemeButton() {
    if (!themeButton) return;
    themeButton.setAttribute(
      "aria-label",
      currentTheme() === "dark" ? "Aktifkan tema terang" : "Aktifkan tema gelap"
    );
  }

  if (themeButton) {
    syncThemeButton();
    themeButton.addEventListener("click", function () {
      const next = currentTheme() === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try {
        localStorage.setItem("travelkita-theme", next);
      } catch (error) {
        /* ignore */
      }
      syncThemeButton();
    });
  }

  function focusComposer(text) {
    const textarea = document.getElementById("message");
    if (!textarea) return;
    textarea.value = text;
    textarea.focus();
    textarea.setSelectionRange(text.length, text.length);
    const composer = document.getElementById("chat-form");
    if (composer) composer.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  document.addEventListener("click", function (event) {
    const suggestion = event.target.closest(".suggestion");
    if (suggestion && suggestion.dataset.question) {
      focusComposer(suggestion.dataset.question);
      return;
    }

    const copyButton = event.target.closest("[data-copy-target]");
    if (copyButton) {
      const target = document.getElementById(copyButton.dataset.copyTarget);
      if (!target) return;
      const text = target.textContent || "";
      const done = function () {
        const previous = copyButton.textContent;
        copyButton.textContent = "Tersalin";
        setTimeout(function () {
          copyButton.textContent = previous;
        }, 1400);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(done);
      } else {
        done();
      }
      return;
    }

    const drawerTrigger = event.target.closest("[data-open-drawer]");
    if (drawerTrigger) {
      const dialog = document.getElementById("source-drawer");
      const title = document.getElementById("source-title");
      if (dialog && title) {
        title.textContent = drawerTrigger.dataset.sourceTitle || "Detail sumber";
        if (!dialog.open) dialog.showModal();
      }
      return;
    }

    const closeButton = event.target.closest("[data-close-drawer]");
    if (closeButton) {
      const dialog = document.getElementById("source-drawer");
      if (dialog && dialog.open) dialog.close();
    }
  });

  const dialog = document.getElementById("source-drawer");
  if (dialog) {
    dialog.addEventListener("click", function (event) {
      const rect = dialog.getBoundingClientRect();
      const inside =
        event.clientX >= rect.left &&
        event.clientX <= rect.right &&
        event.clientY >= rect.top &&
        event.clientY <= rect.bottom;
      if (!inside) dialog.close();
    });
  }

  function scrollConversation() {
    const conversation = document.getElementById("conversation");
    if (!conversation) return;
    conversation.scrollTop = conversation.scrollHeight;
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "conversation") {
      const empty = event.detail.target.querySelector(".empty-state");
      if (event.detail.target.querySelector(".turn") && empty) empty.remove();
      scrollConversation();
    }
  });

  document.body.addEventListener("htmx:afterRequest", function (event) {
    const form = event.target;
    if (!form || form.id !== "chat-form") return;
    const textarea = document.getElementById("message");
    if (event.detail && event.detail.successful && textarea) {
      textarea.value = "";
      textarea.focus();
    }
  });

  document.body.addEventListener("htmx:responseError", function (event) {
    const target = event.detail && event.detail.target;
    if (target && target.id === "conversation") {
      scrollConversation();
    }
  });
})();
