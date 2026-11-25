const cartStorageKey = "obalai.demo.cart";
const statusLabels = {
  reserved: "Брондалған",
  accepted: "Расталған",
  rejected: "Қабылданбаған",
  ready: "Дайын",
  completed: "Аяқталған",
  cancelled: "Бас тартылған",
  expired: "Мерзімі өткен",
};

function renderPickupSvg(code) {
  const grid = 13;
  const size = 144;
  const margin = 12;
  const cell = Math.floor((size - margin * 2) / grid);
  let hash = 2166136261;
  for (let i = 0; i < code.length; i += 1) {
    hash ^= code.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  let rects = "";
  const isFinder = (r, c) =>
    (r < 4 && c < 4) || (r < 4 && c >= grid - 4) || (r >= grid - 4 && c < 4);

  for (let r = 0; r < grid; r += 1) {
    for (let c = 0; c < grid; c += 1) {
      let on = false;
      if (isFinder(r, c)) {
        const lr = r < 4 ? r : r - (grid - 4);
        const lc = c < 4 ? c : c - (grid - 4);
        on = lr === 0 || lr === 3 || lc === 0 || lc === 3 || (lr >= 1 && lr <= 2 && lc >= 1 && lc <= 2);
      } else {
        hash = Math.imul(hash ^ (r * 31 + c * 17 + 7), 16777619);
        on = (hash >>> 0) % 2 === 1;
      }
      if (on) {
        const x = margin + c * cell;
        const y = margin + r * cell;
        rects += `<rect x="${x}" y="${y}" width="${cell}" height="${cell}" fill="#244a31"/>`;
      }
    }
  }
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg"><rect width="${size}" height="${size}" rx="10" fill="#ffffff" stroke="#d9dacb"/>${rects}</svg>`;
}

export function createCheckout({
  api,
  getUser,
  getToken,
  setFeedback,
  errorText,
  money,
  quantity,
  date,
  units,
  createElement,
  onNavigate,
  onRequireBuyerAuth,
  onOrderCreated,
}) {
  const byId = (id) => document.getElementById(id);
  const navCart = byId("nav-cart");

  // Detail elements
  const detailFeedback = byId("detail-feedback");
  const detailUnit = byId("detail-unit");
  const detailDiscount = byId("detail-discount");
  const detailTitle = byId("detail-title");
  const detailDescription = byId("detail-description");
  const detailExpiry = byId("detail-expiry");
  const detailStock = byId("detail-stock");
  const detailPrice = byId("detail-price");
  const detailOldPrice = byId("detail-old-price");
  const detailSavings = byId("detail-savings");
  const detailStoreName = byId("detail-store-name");
  const detailStoreAddress = byId("detail-store-address");
  const detailBuyerControls = byId("detail-buyer-controls");
  const detailSellerNote = byId("detail-seller-note");
  const detailQty = byId("detail-qty");
  const detailQtyUnit = byId("detail-qty-unit");
  const detailAddCart = byId("detail-add-cart");
  const detailBuyNow = byId("detail-buy-now");
  const detailSwitchBuyer = byId("detail-switch-buyer");

  // Checkout elements
  const checkoutFeedback = byId("checkout-feedback");
  const checkoutEmpty = byId("checkout-empty");
  const checkoutBody = byId("checkout-body");
  const checkoutItems = byId("checkout-items");
  const checkoutClear = byId("checkout-clear");
  const pickupBox = byId("checkout-pickup-box");
  const pickupStore = byId("checkout-pickup-store");
  const pickupAddress = byId("checkout-pickup-address");
  const deliveryBox = byId("checkout-delivery-box");
  const deliveryInput = byId("checkout-delivery-address");
  const sumOriginal = byId("sum-original");
  const sumSavings = byId("sum-savings");
  const sumFulfill = byId("sum-fulfill");
  const sumTotal = byId("sum-total");
  const authNotice = byId("checkout-auth-notice");
  const authActions = byId("checkout-auth-actions");
  const checkoutLogin = byId("checkout-login");
  const checkoutRegister = byId("checkout-register");
  const checkoutConfirm = byId("checkout-confirm");

  // Confirmation elements
  const confirmQr = byId("confirm-qr");
  const confirmCode = byId("confirm-code");
  const confirmStatus = byId("confirm-status");
  const confirmStore = byId("confirm-store");
  const confirmAddress = byId("confirm-address");
  const confirmItems = byId("confirm-items");
  const confirmTotal = byId("confirm-total");
  const confirmSavings = byId("confirm-savings");

  let cart = loadCart();
  let activeDetailBatch = null;
  let pendingKey = null;
  let pendingSig = "";
  let busy = false;

  function loadCart() {
    try {
      const parsed = JSON.parse(sessionStorage.getItem(cartStorageKey) || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function saveCart() {
    try {
      sessionStorage.setItem(cartStorageKey, JSON.stringify(cart));
    } catch {
      // ignore storage failures
    }
    updateBadge();
  }

  function invalidatePending() {
    pendingKey = null;
    pendingSig = "";
  }

  function updateBadge() {
    if (navCart) navCart.textContent = `Себет (${cart.length})`;
  }

  function getFulfillment() {
    const checked = document.querySelector('input[name="fulfillment_method"]:checked');
    return checked?.value === "delivery" ? "delivery" : "pickup";
  }

  function addBatch(batch, qty = null) {
    const available = Number(batch.quantity_available);
    const defaultQty = available < 1 ? available : 1;
    const addQty = qty && Number(qty) > 0 ? Math.min(Number(qty), available) : defaultQty;
    if (cart.length > 0 && cart[0].storeId !== batch.store_id) {
      return {
        ok: false,
        message: `Себетте «${cart[0].storeName}» дүкенінің өнімдері бар. Бір тапсырысқа тек бір дүкеннің өнімдері кіреді — алдымен себетті рәсімдеңіз немесе тазартыңыз.`,
      };
    }
    const existing = cart.find((item) => item.batchId === batch.batch_id);
    if (existing) {
      existing.available = available;
      existing.quantity = Math.min(available, Number((Number(existing.quantity) + addQty).toFixed(3)));
    } else {
      cart.push({
        batchId: batch.batch_id,
        storeId: batch.store_id,
        storeName: batch.store.name,
        storeCity: batch.store.city,
        storeAddress: batch.store.address,
        name: batch.product.name,
        unit: batch.product.unit,
        regularPrice: Number(batch.regular_price),
        discountPrice: Number(batch.discount_price),
        available,
        quantity: Number(addQty.toFixed(3)),
      });
    }
    invalidatePending();
    saveCart();
    renderCheckout();
    return { ok: true, message: `«${batch.product.name}» себетке қосылды.` };
  }

  function openDetail(batch) {
    activeDetailBatch = batch;
    setFeedback(detailFeedback);
    const reg = Number(batch.regular_price);
    const disc = Number(batch.discount_price);
    const pct = reg > 0 && disc < reg ? Math.round(((reg - disc) / reg) * 100) : 0;
    const unit = units[batch.product.unit] || batch.product.unit;
    const avail = Number(batch.quantity_available);

    detailUnit.textContent = unit;
    detailDiscount.textContent = `−${pct}%`;
    detailDiscount.hidden = pct <= 0;
    detailTitle.textContent = batch.product.name;
    detailDescription.textContent = batch.product.description || "Сипаттама көрсетілмеген.";
    detailExpiry.textContent = `Жарамдылық мерзімі: ${date.format(new Date(batch.expires_at))}`;
    detailStock.textContent = `Қолжетімді қалдық: ${quantity.format(avail)} ${unit}`;
    detailPrice.textContent = `${money.format(disc)} ₸`;
    detailOldPrice.textContent = `${money.format(reg)} ₸`;
    detailOldPrice.hidden = reg <= disc;
    detailSavings.textContent = `Бірліктен үнем: ${money.format(Math.max(0, reg - disc))} ₸`;
    detailSavings.hidden = reg <= disc;
    detailStoreName.textContent = batch.store.name;
    detailStoreAddress.textContent = `${batch.store.city}, ${batch.store.address}`;
    detailQtyUnit.textContent = `(${unit})`;
    detailQty.max = String(avail);
    detailQty.value = avail < 1 ? String(avail) : "1";

    const isSeller = getUser()?.role === "seller";
    detailBuyerControls.hidden = isSeller;
    detailSellerNote.hidden = !isSeller;

    if (getUser()?.role === "buyer" && getToken()) {
      api(`/api/ai/events/view/${batch.batch_id}`, { method: "POST", authorized: true }).catch(() => {});
    }
    onNavigate("detail");
  }

  function updateSummary() {
    let orig = 0;
    let total = 0;
    for (const item of cart) {
      orig += item.regularPrice * item.quantity;
      total += item.discountPrice * item.quantity;
    }
    const savings = Math.max(0, orig - total);
    sumOriginal.textContent = `${money.format(orig)} ₸`;
    sumSavings.textContent = savings > 0 ? `−${money.format(savings)} ₸` : "0 ₸";
    sumFulfill.textContent = getFulfillment() === "pickup" ? "Алып кету (Тегін)" : "Жеткізу";
    sumTotal.textContent = `${money.format(total)} ₸`;
  }

  function syncAuthControls() {
    const user = getUser();
    const isBuyer = user?.role === "buyer" && Boolean(getToken());
    const isSeller = user?.role === "seller";
    checkoutConfirm.hidden = !isBuyer;
    authNotice.hidden = isBuyer;
    authActions.hidden = isBuyer;
    if (isBuyer) {
      checkoutConfirm.textContent = pendingKey ? "Броньды тексеру" : "Броньды растау →";
    } else if (isSeller) {
      authNotice.textContent =
        "Сіз сатушы аккаунтымен кірдіңіз. Брондау тек сатып алушыларға қолжетімді — сатып алушы аккаунтына ауыссаңыз, себет сақталады.";
      checkoutLogin.textContent = "Сатып алушы ретінде кіру";
    } else {
      authNotice.textContent =
        "Тапсырысты растау үшін сатып алушы ретінде кіріңіз немесе тіркеліңіз. Себеттегі өнімдер мен мекенжай сақталады.";
      checkoutLogin.textContent = "Кіру (себет сақталады)";
    }
  }

  function renderCheckout() {
    updateBadge();
    const hasItems = cart.length > 0;
    checkoutEmpty.hidden = hasItems;
    checkoutBody.hidden = !hasItems;
    checkoutItems.replaceChildren();
    if (!hasItems) return;

    pickupStore.textContent = cart[0].storeName;
    pickupAddress.textContent = `${cart[0].storeCity}, ${cart[0].storeAddress}`;

    for (const item of cart) {
      const unit = units[item.unit] || item.unit;
      const li = createElement("li", "checkout-item");
      const info = createElement("div", "checkout-item-info");
      info.append(
        createElement("strong", "", item.name),
        createElement("p", "product-meta", `${money.format(item.discountPrice)} ₸ / ${unit} · Қалдығы: ${quantity.format(item.available)} ${unit}`),
      );
      const controls = createElement("div", "checkout-item-controls");
      const qtyInput = createElement("input", "checkout-qty");
      qtyInput.type = "number";
      qtyInput.min = "0.001";
      qtyInput.step = item.unit === "kg" ? "0.5" : "1";
      qtyInput.max = String(item.available);
      qtyInput.value = String(item.quantity);
      qtyInput.addEventListener("change", () => {
        const next = Math.max(0.001, Math.min(item.available, Number(qtyInput.value) || 1));
        item.quantity = Number(next.toFixed(3));
        qtyInput.value = String(item.quantity);
        invalidatePending();
        saveCart();
        updateSummary();
      });
      const removeBtn = createElement("button", "button button-text button-small", "Өшіру");
      removeBtn.type = "button";
      removeBtn.addEventListener("click", () => {
        cart = cart.filter((c) => c.batchId !== item.batchId);
        invalidatePending();
        saveCart();
        renderCheckout();
      });
      controls.append(qtyInput, removeBtn);
      li.append(info, controls);
      checkoutItems.append(li);
    }

    const isPickup = getFulfillment() === "pickup";
    pickupBox.hidden = !isPickup;
    deliveryBox.hidden = isPickup;
    syncAuthControls();
    updateSummary();
  }

  function renderConfirmation(order) {
    const code = order.pickup_code || `OB-${order.id.slice(0, 8).toUpperCase()}`;
    confirmQr.innerHTML = renderPickupSvg(code);
    confirmCode.textContent = code;
    confirmStatus.textContent = statusLabels[order.status] || order.status;
    confirmStatus.dataset.status = order.status;
    confirmStore.textContent = order.store?.name || "Дүкен";
    if (order.fulfillment_method === "delivery") {
      confirmAddress.textContent = `Жеткізу мекенжайы: ${order.delivery_address || ""} · Дүкен: ${order.store?.city || ""}, ${order.store?.address || ""}`;
    } else {
      confirmAddress.textContent = `Алып кету мекенжайы: ${order.store?.city || ""}, ${order.store?.address || ""}`;
    }
    confirmItems.replaceChildren(
      ...(order.items || []).map((item) => {
        const unit = units[item.unit] || item.unit;
        return createElement(
          "li",
          "",
          `${item.product_name} × ${quantity.format(item.quantity)} ${unit} — ${money.format(item.line_total)} ₸`,
        );
      }),
    );
    confirmTotal.textContent = `Жалпы сома: ${money.format(order.total_amount)} ₸`;
    const savings = Number(order.savings_amount || 0);
    confirmSavings.textContent = `Сіздің үнеміңіз: ${money.format(savings)} ₸`;
    confirmSavings.hidden = savings <= 0;
  }

  async function submitCheckout() {
    if (busy || cart.length === 0) return;
    if (getUser()?.role !== "buyer" || !getToken()) {
      syncAuthControls();
      return;
    }
    const fulfillment = getFulfillment();
    const deliveryAddr = fulfillment === "delivery" ? deliveryInput.value.trim() : null;
    if (fulfillment === "delivery" && !deliveryAddr) {
      setFeedback(checkoutFeedback, "Жеткізу мекенжайын енгізіңіз.", "error");
      deliveryInput.focus();
      return;
    }

    const itemsPayload = cart.map((item) => ({
      batch_id: item.batchId,
      quantity: String(item.quantity),
    }));
    const sig = JSON.stringify({ itemsPayload, fulfillment, deliveryAddr });
    if (!pendingKey || pendingSig !== sig) {
      pendingKey = crypto.randomUUID();
      pendingSig = sig;
    }

    busy = true;
    checkoutConfirm.disabled = true;
    setFeedback(checkoutFeedback, "Тапсырыс рәсімделуде…");
    try {
      const body = {
        items: itemsPayload,
        fulfillment_method: fulfillment,
        payment_method: "pay_at_pickup",
      };
      if (fulfillment === "delivery") body.delivery_address = deliveryAddr;
      const order = await api("/api/orders", {
        method: "POST",
        authorized: true,
        idempotencyKey: pendingKey,
        body,
      });
      cart = [];
      invalidatePending();
      saveCart();
      setFeedback(checkoutFeedback);
      renderCheckout();
      renderConfirmation(order);
      onOrderCreated(order);
      onNavigate("confirmation");
    } catch (error) {
      if (error.status && [400, 403, 404, 409, 422].includes(error.status)) {
        invalidatePending();
        setFeedback(checkoutFeedback, errorText(error), "error");
      } else {
        checkoutConfirm.textContent = "Броньды тексеру";
        setFeedback(checkoutFeedback, "Бронь нәтижесі белгісіз. Сол сұрауды қайта жіберіп тексеріңіз.", "error");
      }
    } finally {
      busy = false;
      checkoutConfirm.disabled = false;
    }
  }

  document.querySelectorAll('input[name="fulfillment_method"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      invalidatePending();
      renderCheckout();
    });
  });
  deliveryInput?.addEventListener("input", invalidatePending);
  checkoutClear?.addEventListener("click", () => {
    cart = [];
    invalidatePending();
    setFeedback(checkoutFeedback);
    saveCart();
    renderCheckout();
  });
  checkoutConfirm?.addEventListener("click", submitCheckout);
  checkoutLogin?.addEventListener("click", () => onRequireBuyerAuth("login"));
  checkoutRegister?.addEventListener("click", () => onRequireBuyerAuth("register"));

  detailAddCart?.addEventListener("click", () => {
    if (!activeDetailBatch) return;
    const res = addBatch(activeDetailBatch, detailQty.value);
    setFeedback(detailFeedback, res.message, res.ok ? "success" : "error");
  });
  detailBuyNow?.addEventListener("click", () => {
    if (!activeDetailBatch) return;
    const res = addBatch(activeDetailBatch, detailQty.value);
    if (!res.ok) setFeedback(detailFeedback, res.message, "error");
    else onNavigate("checkout");
  });
  detailSwitchBuyer?.addEventListener("click", () => onRequireBuyerAuth("login", activeDetailBatch));

  updateBadge();
  return {
    addBatch,
    openDetail,
    renderCheckout,
    syncAuthControls,
    count: () => cart.length,
  };
}
