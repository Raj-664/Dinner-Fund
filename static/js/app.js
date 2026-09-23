document.addEventListener("DOMContentLoaded", function () {
  var themeButtons = [
    document.getElementById("themeToggle"),
    document.getElementById("mobileThemeToggle")
  ].filter(Boolean);

  function applyTheme(theme) {
    var isDark = theme === "dark";
    document.body.classList.toggle("dark-theme", isDark);
    document.documentElement.style.colorScheme = isDark ? "dark" : "light";
    themeButtons.forEach(function (button) {
      button.setAttribute("aria-pressed", isDark ? "true" : "false");
      button.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
      button.classList.toggle("is-dark", isDark);
    });
  }

  var savedTheme = "light";
  try { savedTheme = localStorage.getItem("dinner-fund-theme") || "light"; }
  catch (error) { savedTheme = "light"; }
  applyTheme(savedTheme);

  themeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var nextTheme = document.body.classList.contains("dark-theme") ? "light" : "dark";
      applyTheme(nextTheme);
      try { localStorage.setItem("dinner-fund-theme", nextTheme); } catch (error) {}
    });
  });

  document.querySelectorAll(".flash").forEach(function (flash) {
    var close = flash.querySelector(".flash-close");
    if (close) close.addEventListener("click", function () { flash.remove(); });
    setTimeout(function () {
      if (!flash.isConnected) return;
      flash.style.transition = "opacity .3s, transform .3s";
      flash.style.opacity = "0";
      flash.style.transform = "translateY(-6px)";
      setTimeout(function () { if (flash.isConnected) flash.remove(); }, 300);
    }, 4000);
  });

  document.querySelectorAll("form.form").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var valid = true;
      form.querySelectorAll("input[required]").forEach(function (input) {
        if (!input.value || !input.value.trim()) {
          valid = false; input.style.borderColor = "#dc2626";
        } else input.style.borderColor = "";
      });
      if (!valid) event.preventDefault();
    });
  });

  document.querySelectorAll('input[type="number"]').forEach(function (input) {
    input.addEventListener("input", function () {
      if (input.value !== "" && Number(input.value) < 0) input.value = Math.abs(Number(input.value));
    });
  });
});
