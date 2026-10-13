document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".delete-form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const confirmed = window.confirm(
        "Delete this patient and their associated demo prescriptions and bills?"
      );
      if (!confirmed) event.preventDefault();
    });
  });

  const navLinks = document.querySelectorAll(".nav-link");
  const setActiveLink = () => {
    const hash = window.location.hash || "#overview";
    navLinks.forEach((link) => {
      link.classList.toggle("active", link.getAttribute("href") === hash);
    });
  };
  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      navLinks.forEach((item) => item.classList.remove("active"));
      link.classList.add("active");
    });
  });
  window.addEventListener("hashchange", setActiveLink);
  setActiveLink();

  document.querySelectorAll(".flash").forEach((flash) => {
    window.setTimeout(() => {
      flash.style.transition = "opacity .4s";
      flash.style.opacity = "0";
      window.setTimeout(() => flash.remove(), 450);
    }, 5000);
  });
});
