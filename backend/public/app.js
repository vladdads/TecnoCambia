(function () {
  const thumbs = document.querySelectorAll("[data-gallery-thumb]");
  const main = document.querySelector("[data-gallery-main]");
  if (thumbs.length && main) {
    thumbs.forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        const src = a.getAttribute("href");
        if (!src) return;
        main.setAttribute("src", src);
      });
    });
  }

  const typeSelect = document.querySelector("[data-listing-type]");
  const priceWrap = document.querySelector("[data-price-wrap]");
  const priceInput = document.querySelector("[data-price-input]");
  function syncPrice() {
    if (!typeSelect || !priceWrap) return;
    const t = typeSelect.value;
    const show = t === "sale";
    priceWrap.style.display = show ? "block" : "none";
    if (!show && priceInput) priceInput.value = "";
  }
  if (typeSelect) {
    typeSelect.addEventListener("change", syncPrice);
    syncPrice();
  }
})();

