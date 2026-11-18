const byId = (id) => document.getElementById(id);

const catalogView = byId("catalog-view");
const sellerView = byId("seller-view");
const sessionLabel = byId("session-label");
const signIn = byId("sign-in");
const signOut = byId("sign-out");
const authDialog = byId("auth-dialog");
const authForm = byId("auth-form");
const authSubmit = byId("auth-submit");
const authToggle = byId("auth-toggle");
const authFeedback = byId("auth-feedback");
const catalogSearch = byId("catalog-search");
const catalogList = byId("catalog-list");
const catalogState = byId("catalog-state");
const catalogCount = byId("catalog-count");
const catalogClear = byId("catalog-clear");
const catalogMore = byId("catalog-more");
const catalogBookingFeedback = byId("catalog-booking-feedback");
const bookingDialog = byId("booking-dialog");
const bookingForm = byId("booking-form");
const bookingSubmit = byId("booking-submit");
const bookingClose = byId("booking-close");
const bookingFeedback = byId("booking-feedback");
const bookingPending = byId("booking-pending");
const bookingRetry = byId("booking-retry");
const sellerGate = byId("seller-gate");
const sellerGateMessage = byId("seller-gate-message");
const sellerWorkspace = byId("seller-workspace");
const sellerFeedback = byId("seller-feedback");
const storeForm = byId("store-form");
const storeDetails = byId("store-details");
const batchForm = byId("batch-form");
const batchPlaceholder = byId("batch-placeholder");
const publishFeedback = byId("publish-feedback");
const publishedLink = byId("published-link");

const roles = { buyer: "Сатып алушы", seller: "Сатушы", admin: "Әкімші" };
const units = { piece: "дана", kg: "кг", portion: "порция" };
const locales = ["kk-KZ", "ru-KZ"];
const money = new Intl.NumberFormat(locales, {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const quantity = new Intl.NumberFormat(locales, { maximumFractionDigits: 3 });
const date = new Intl.DateTimeFormat(locales, {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  hourCycle: "h23",
});
const tokenKey = "obalai.demo.token";
const pageSize = 24;
const bookingAttempts = new Map();

let token = readToken();
let user = null;
let view = "";
let authMode = "login";
let authBusy = false;
let catalogRequest;
let catalogOffset = 0;
let catalogQuery = "";
let storeRequest = 0;
let publishedBatch = null;
let bookingDraft = null;
let pendingBooking = null;
let bookingBusy = false;

function readToken() {
  try {
    return sessionStorage.getItem(tokenKey);
  } catch {
    return null;
  }
}

function saveSession(nextToken, nextUser) {
  token = nextToken;
  user = nextUser;
  try {
    if (token) sessionStorage.setItem(tokenKey, token);
    else sessionStorage.removeItem(tokenKey);
  } catch {
    // Keep the current session usable when storage is unavailable.
  }
  storeRequest += 1;
  storeForm.reset();
  batchForm.reset();
  publishedBatch = null;
  publishedLink.hidden = true;
  setFeedback(publishFeedback);
  setFeedback(sellerFeedback);
  closeBooking();
  setFeedback(catalogBookingFeedback);
  renderSession();
}

class ApiError extends Error {
  constructor(status, detail) {
    super("API request failed");
    this.status = status;
    this.detail = detail;
  }
}

async function api(path, { method = "GET", body, authorized = false, signal, idempotencyKey } = {}) {
  const requestToken = authorized ? token : null;
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (requestToken) headers.Authorization = `Bearer ${requestToken}`;
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  const response = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    if (response.status === 401 && requestToken && requestToken === token) {
      saveSession(null, null);
      if (view === "seller") refreshStore();
      else if (view === "catalog") loadCatalog();
    }
    throw new ApiError(response.status, error.detail);
  }
  return response.json();
}

function errorText(error) {
  if (!(error instanceof ApiError)) return "Байланыс үзілді. Қайта көріңіз.";
  switch (error.detail) {
    case "Invalid email or password":
      return "Email немесе құпиясөз қате.";
    case "Email is already registered":
      return "Бұл email тіркелген. Жүйеге кіріңіз.";
    case "Seller already has a store":
      return "Бұл аккаунтта дүкен бар.";
    case "An active store is required":
      return "Партия жариялау үшін белсенді дүкен қажет.";
    case "Buyer role required":
      return "Брондау үшін сатып алушы ретінде кіріңіз.";
    case "Batch not found":
    case "Batch is not available":
      return "Бұл партия қазір қолжетімсіз.";
    case "Not enough stock":
      return "Қалған өнім саны жеткіліксіз.";
    case "Order total is too large":
      return "Бронь сомасы тым үлкен. Өнім санын азайтыңыз.";
    case "Idempotency key already used for a different reservation":
      return "Алдыңғы сұрау басқа броньға тиесілі. Қайта бастаңыз.";
    case "Invalid or expired token":
    case "Bearer token required":
      return "Сеанстың уақыты аяқталды. Қайта кіріңіз.";
    default:
      if (error.status === 403) return "Бұл әрекетке рұқсатыңыз жоқ.";
      if (error.status === 422) return "Енгізілген деректерді тексеріңіз.";
      return "Сұрау орындалмады. Қайта көріңіз.";
  }
}

function setFeedback(element, message = "", tone = "") {
  element.textContent = message;
  element.hidden = !message;
  element.dataset.tone = tone;
}

function buttonBusy(button, busy) {
  if (button) button.disabled = busy;
}

function field(form, name) {
  return form.elements.namedItem(name);
}

function formValues(form) {
  return Object.fromEntries(new FormData(form));
}

function renderSession() {
  signIn.hidden = user !== null;
  signOut.hidden = user === null;
  sessionLabel.hidden = user === null;
  sessionLabel.textContent = user ? `${roles[user.role] || user.email} · ${user.email}` : "";
  pendingBooking = user?.role === "buyer" ? readBookingAttempt(user.id) : null;
  bookingPending.hidden = !pendingBooking;
}

function setAuthMode(mode, role) {
  authMode = mode === "register" ? "register" : "login";
  const registering = authMode === "register";
  byId("auth-title").textContent = registering ? "Аккаунт ашу" : "Кіру";
  byId("auth-role").hidden = !registering;
  authForm.querySelectorAll("[name=role]").forEach((input) => {
    input.disabled = !registering;
  });
  if (role && field(authForm, "role")) field(authForm, "role").value = role;
  const password = field(authForm, "password");
  password.autocomplete = registering ? "new-password" : "current-password";
  password.minLength = registering ? 8 : 1;
  authSubmit.textContent = registering ? "Тіркелу" : "Кіру";
  authToggle.textContent = registering ? "Аккаунтым бар" : "Аккаунт ашу";
}

function openAuth(mode, role = view === "seller" ? "seller" : "buyer") {
  if (authBusy) return;
  authForm.reset();
  setAuthMode(mode, role);
  setFeedback(authFeedback);
  if (!authDialog.open) authDialog.showModal();
  field(authForm, "email").focus();
}

function closeAuth() {
  if (authBusy) return;
  authDialog.close();
  authForm.reset();
  setFeedback(authFeedback);
}

async function submitAuth(event) {
  event.preventDefault();
  if (authBusy) return;
  const { email, password, role } = formValues(authForm);
  const credentials = { email: email.trim(), password };
  setFeedback(authFeedback);
  authBusy = true;
  buttonBusy(authSubmit, true);
  buttonBusy(authToggle, true);
  let signedIn = false;
  let registered = false;
  try {
    if (authMode === "register") {
      await api("/api/auth/register", {
        method: "POST",
        body: { ...credentials, role: role || "buyer" },
      });
      registered = true;
    }
    const result = await api("/api/auth/login", { method: "POST", body: credentials });
    saveSession(result.access_token, result.user);
    signedIn = true;
  } catch (error) {
    if (registered) setAuthMode("login");
    setFeedback(authFeedback, errorText(error), "error");
  } finally {
    authBusy = false;
    buttonBusy(authSubmit, false);
    buttonBusy(authToggle, false);
  }
  if (signedIn) {
    closeAuth();
    if (view === "seller") refreshStore();
    else if (view === "catalog") loadCatalog();
  }
}

function readBookingAttempt(buyerId) {
  if (bookingAttempts.has(buyerId)) return bookingAttempts.get(buyerId);
  try {
    return JSON.parse(sessionStorage.getItem(`obalai.demo.booking.${buyerId}`));
  } catch {
    return null;
  }
}

function saveBookingAttempt(attempt) {
  pendingBooking = attempt;
  bookingPending.hidden = !attempt;
  bookingAttempts.set(user.id, attempt);
  try {
    const key = `obalai.demo.booking.${user.id}`;
    if (attempt) sessionStorage.setItem(key, JSON.stringify(attempt));
    else sessionStorage.removeItem(key);
  } catch {
    // The current tab can still retry while storage is unavailable.
  }
}

function openBooking(draft) {
  if (user?.role !== "buyer" || !token || bookingBusy) return;
  if (pendingBooking && draft && pendingBooking.batchId !== draft.batchId) {
    bookingRetry.focus();
    return;
  }
  bookingDraft = pendingBooking || draft;
  if (!bookingDraft) return;
  const input = field(bookingForm, "quantity");
  const available = Number(bookingDraft.available);
  const unit = units[bookingDraft.unit] || bookingDraft.unit;
  input.max = bookingDraft.available;
  input.value = pendingBooking?.quantity || (available < 1 ? bookingDraft.available : "1");
  input.readOnly = Boolean(pendingBooking);
  byId("booking-product").textContent = bookingDraft.name;
  byId("booking-available").textContent = pendingBooking
    ? "Алдыңғы сұрауды сол санмен қайталаңыз."
    : `Қалдығы: ${quantity.format(available)} ${unit}`;
  bookingSubmit.textContent = pendingBooking ? "Броньды тексеру" : "Брондау";
  setFeedback(bookingFeedback);
  if (!bookingDialog.open) bookingDialog.showModal();
  if (pendingBooking) bookingSubmit.focus();
  else input.focus();
}

function closeBooking() {
  if (bookingDialog.open) bookingDialog.close();
  bookingDraft = null;
  bookingForm.reset();
  setFeedback(bookingFeedback);
}

async function submitBooking(event) {
  event.preventDefault();
  if (bookingBusy || !bookingDraft || !token || user?.role !== "buyer") return;
  const requestToken = token;
  const input = field(bookingForm, "quantity");
  const attempt = pendingBooking || { ...bookingDraft, quantity: input.value, key: crypto.randomUUID() };
  saveBookingAttempt(attempt);
  bookingBusy = true;
  input.readOnly = true;
  buttonBusy(bookingSubmit, true);
  buttonBusy(bookingClose, true);
  buttonBusy(bookingRetry, true);
  setFeedback(bookingFeedback, "Бронь жіберілуде…");
  try {
    const order = await api("/api/orders", {
      method: "POST",
      authorized: true,
      idempotencyKey: attempt.key,
      signal: AbortSignal.timeout(20000),
      body: { batch_id: attempt.batchId, quantity: attempt.quantity },
    });
    if (requestToken !== token) return;
    const unit = units[attempt.unit] || attempt.unit;
    const receipt = `«${attempt.name}» брондалды. №${order.id.slice(0, 8)} · ${quantity.format(order.quantity)} ${unit} · ${money.format(order.total_amount)} ₸.`;
    saveBookingAttempt(null);
    closeBooking();
    setFeedback(catalogBookingFeedback, receipt, "success");
    if (view === "catalog") {
      catalogBookingFeedback.focus();
      loadCatalog();
    }
  } catch (error) {
    if (requestToken !== token) {
      if (!token && error instanceof ApiError && error.status === 401) {
        setFeedback(catalogBookingFeedback, "Қайта кіріп, алдыңғы броньды тексеріңіз.", "error");
      }
      return;
    }
    const rejected = error instanceof ApiError && [400, 403, 404, 409, 422].includes(error.status);
    if (rejected) {
      saveBookingAttempt(null);
      closeBooking();
      setFeedback(catalogBookingFeedback, errorText(error), "error");
      if (view === "catalog") {
        catalogBookingFeedback.focus();
        loadCatalog();
      }
    } else {
      bookingSubmit.textContent = "Броньды тексеру";
      setFeedback(bookingFeedback, "Бронь нәтижесі белгісіз. Осы сұрауды қайта жіберіп тексеріңіз.", "error");
    }
  } finally {
    bookingBusy = false;
    buttonBusy(bookingSubmit, false);
    buttonBusy(bookingClose, false);
    buttonBusy(bookingRetry, false);
  }
}

function createElement(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = value;
  return element;
}

function productCard(batch) {
  const card = createElement("article", "product-card");
  const discount = Number(batch.regular_price) - Number(batch.discount_price);
  const discountPercent = discount > 0 ? Math.round(discount / Number(batch.regular_price) * 100) : 0;
  const unit = units[batch.product.unit] || batch.product.unit;
  const mark = createElement("div", "product-mark");
  mark.append(createElement("span", "", unit));
  if (discountPercent > 0) {
    mark.append(createElement("span", "product-discount", `−${discountPercent}%`));
  }

  const copy = createElement("div", "product-copy");
  copy.append(createElement("h3", "", batch.product.name));
  if (batch.product.description) {
    copy.append(createElement("p", "product-description", batch.product.description));
  }
  copy.append(createElement("p", "product-meta", `${batch.store.name} · ${batch.store.city}`));

  const price = createElement("div", "product-price");
  price.append(createElement("strong", "", `${money.format(batch.discount_price)} ₸`));
  if (discount > 0) price.append(createElement("del", "", `${money.format(batch.regular_price)} ₸`));

  copy.append(price);
  copy.append(
    createElement("p", "product-stock", `Қалдығы: ${quantity.format(batch.quantity_available)} ${unit}`),
    createElement("p", "product-expiry", `Жарамды: ${date.format(new Date(batch.expires_at))}`),
  );
  if (user?.role === "buyer") {
    const book = createElement("button", "button button-primary button-small product-booking", "Брондау");
    book.type = "button";
    book.setAttribute("aria-haspopup", "dialog");
    book.setAttribute("aria-label", `${batch.product.name} тауарын брондау`);
    book.addEventListener("click", () => openBooking({
      batchId: batch.batch_id,
      name: batch.product.name,
      unit: batch.product.unit,
      available: batch.quantity_available,
    }));
    copy.append(book);
  }
  card.append(mark, copy);
  return card;
}

async function loadCatalog({ append = false } = {}) {
  catalogRequest?.abort();
  const request = new AbortController();
  catalogRequest = request;
  if (!append) {
    catalogOffset = 0;
    catalogQuery = field(catalogSearch, "q").value.trim();
    catalogList.replaceChildren();
    catalogCount.textContent = "";
    catalogCount.hidden = true;
  }
  catalogClear.hidden = catalogQuery.length === 0;
  if (catalogMore) catalogMore.hidden = true;
  setFeedback(catalogState, "Каталог жүктелуде…", "loading");
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(catalogOffset) });
  if (catalogQuery) params.set("q", catalogQuery);
  try {
    const batches = await api(`/api/catalog?${params}`, { signal: request.signal });
    if (catalogRequest !== request) return;
    catalogList.append(...batches.map(productCard));
    catalogOffset += batches.length;
    catalogCount.textContent = `${catalogOffset} ұсыныс`;
    catalogCount.hidden = catalogOffset === 0;
    if (catalogMore) catalogMore.hidden = batches.length < pageSize;
    if (catalogOffset === 0) {
      const message = catalogQuery ? "Іздеу нәтижесі табылмады." : "Қазір қолжетімді партиялар жоқ.";
      setFeedback(catalogState, message, "empty");
    } else {
      setFeedback(catalogState);
    }
  } catch (error) {
    if (error.name === "AbortError" || catalogRequest !== request) return;
    if (append && catalogMore) catalogMore.hidden = false;
    setFeedback(catalogState, errorText(error), "error");
  }
}

function renderStore(store) {
  storeForm.hidden = Boolean(store);
  storeDetails.hidden = !store;
  batchForm.hidden = !store || !store.is_active;
  batchPlaceholder.hidden = !batchForm.hidden;
  batchPlaceholder.textContent = store
    ? "Партия жариялау үшін дүкен белсенді болуы керек."
    : "Партия жариялау үшін алдымен дүкеніңізді қосыңыз.";
  buttonBusy(batchForm.querySelector("button[type=submit]"), batchForm.hidden);
  if (store) {
    byId("store-title").textContent = store.name;
    byId("store-location").textContent = `${store.city} · ${store.address}`;
  }
  setFeedback(sellerFeedback, store && !store.is_active ? "Дүкен белсенді емес." : "", "error");
}

async function refreshStore() {
  const generation = ++storeRequest;
  const isSeller = user?.role === "seller";
  sellerGate.hidden = isSeller;
  sellerWorkspace.hidden = !isSeller;
  if (sellerGateMessage) {
    sellerGateMessage.textContent = user && !isSeller
      ? "Партия жариялау үшін сатушы аккаунтымен кіріңіз."
      : "Дүкен ашып, өнім жариялау үшін сатушы аккаунтына кіріңіз.";
  }
  sellerGate.querySelectorAll("[data-auth]").forEach((button) => {
    button.hidden = Boolean(user);
  });
  if (!isSeller) return;
  storeForm.hidden = true;
  storeDetails.hidden = true;
  batchForm.hidden = true;
  batchPlaceholder.hidden = true;
  setFeedback(sellerFeedback, "Дүкен деректері жүктелуде…", "loading");
  try {
    const store = await api("/api/seller/store", { authorized: true });
    if (generation === storeRequest) renderStore(store);
  } catch (error) {
    if (generation !== storeRequest) return;
    if (error.status === 404) renderStore(null);
    else setFeedback(sellerFeedback, errorText(error), "error");
  }
}

async function submitStore(event) {
  event.preventDefault();
  const requestToken = token;
  const button = storeForm.querySelector("button[type=submit]");
  buttonBusy(button, true);
  setFeedback(sellerFeedback);
  const { name, address, city } = formValues(storeForm);
  try {
    const store = await api("/api/seller/store", {
      method: "POST",
      authorized: true,
      body: { name: name.trim(), address: address.trim(), city: city.trim() },
    });
    if (requestToken !== token) return;
    renderStore(store);
    setFeedback(sellerFeedback, "Дүкен ашылды. Енді партия жариялауға болады.", "success");
    field(batchForm, "product_name").focus();
  } catch (error) {
    if (requestToken !== token) return;
    if (error.status === 409) await refreshStore();
    else setFeedback(sellerFeedback, errorText(error), "error");
  } finally {
    buttonBusy(button, false);
  }
}

async function submitBatch(event) {
  event.preventDefault();
  const values = formValues(batchForm);
  const expiresAt = new Date(values.expires_at);
  publishedLink.hidden = true;
  if (!Number.isFinite(expiresAt.getTime()) || expiresAt.getTime() <= Date.now()) {
    setFeedback(publishFeedback, "Жарамдылық мерзімі болашақ уақытты көрсетуі керек.", "error");
    return;
  }
  if (Number(values.discount_price) > Number(values.regular_price)) {
    setFeedback(publishFeedback, "Жеңілдік бағасы бастапқы бағадан аспауы керек.", "error");
    return;
  }
  const requestToken = token;
  const button = batchForm.querySelector("button[type=submit]");
  buttonBusy(button, true);
  setFeedback(publishFeedback);
  try {
    const result = await api("/api/seller/batches", {
      method: "POST",
      authorized: true,
      body: {
        product: {
          name: values.product_name.trim(),
          unit: values.unit,
          description: values.description?.trim() || null,
        },
        quantity: values.quantity,
        regular_price: values.regular_price,
        discount_price: values.discount_price,
        expires_at: expiresAt.toISOString(),
      },
    });
    if (requestToken !== token) return;
    publishedBatch = result;
    batchForm.reset();
    setFeedback(publishFeedback, `«${result.product.name}» каталогта жарияланды.`, "success");
    publishedLink.hidden = false;
  } catch (error) {
    if (requestToken === token) setFeedback(publishFeedback, errorText(error), "error");
  } finally {
    buttonBusy(button, false);
  }
}

function showView(nextView) {
  view = nextView === "seller" ? "seller" : "catalog";
  sellerView.hidden = view !== "seller";
  catalogView.hidden = view !== "catalog";
  document.querySelectorAll("nav [data-view]").forEach((link) => {
    if (link.dataset.view === view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (view === "seller") {
    closeBooking();
    refreshStore();
  } else {
    loadCatalog();
  }
}

function navigate(nextView, jumpToOffers = false) {
  const hash = nextView === "seller" ? "#seller" : jumpToOffers ? "#offers" : "#catalog";
  if (location.hash !== hash) history.pushState(null, "", hash);
  showView(nextView);
  if (jumpToOffers) byId("offers").scrollIntoView();
  else window.scrollTo(0, 0);
}

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-view], [data-auth], [data-auth-close]");
  if (!trigger) return;
  if (trigger.hasAttribute("data-auth-close")) {
    event.preventDefault();
    closeAuth();
  } else if (trigger.dataset.auth) {
    event.preventDefault();
    openAuth(trigger.dataset.auth, trigger.dataset.authRole);
  } else if (trigger !== publishedLink && trigger.dataset.view) {
    event.preventDefault();
    navigate(trigger.dataset.view);
  }
});

authForm.addEventListener("submit", submitAuth);
authToggle.addEventListener("click", (event) => {
  event.preventDefault();
  setAuthMode(authMode === "login" ? "register" : "login");
  setFeedback(authFeedback);
});
authDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  closeAuth();
});
authDialog.addEventListener("close", () => {
  authForm.reset();
});
signIn.addEventListener("click", (event) => {
  if (!signIn.dataset.auth) {
    event.preventDefault();
    openAuth("login");
  }
});
signOut.addEventListener("click", () => {
  saveSession(null, null);
  navigate("catalog");
});
catalogSearch.addEventListener("submit", (event) => {
  event.preventDefault();
  loadCatalog();
});
catalogClear.addEventListener("click", (event) => {
  event.preventDefault();
  catalogSearch.reset();
  loadCatalog();
  field(catalogSearch, "q").focus();
});
catalogMore?.addEventListener("click", () => loadCatalog({ append: true }));
bookingForm.addEventListener("submit", submitBooking);
bookingClose.addEventListener("click", () => {
  if (!bookingBusy) closeBooking();
});
bookingDialog.addEventListener("cancel", (event) => {
  event.preventDefault();
  if (!bookingBusy) closeBooking();
});
bookingRetry.addEventListener("click", () => openBooking());
storeForm.addEventListener("submit", submitStore);
batchForm.addEventListener("submit", submitBatch);
publishedLink.addEventListener("click", (event) => {
  event.preventDefault();
  if (publishedBatch) field(catalogSearch, "q").value = publishedBatch.product.name;
  navigate("catalog", true);
});
window.addEventListener("popstate", () => showView(location.hash === "#seller" ? "seller" : "catalog"));

async function start() {
  if (token) {
    try {
      user = await api("/api/auth/me", { authorized: true });
    } catch {
      saveSession(null, null);
    }
  }
  renderSession();
  showView(location.hash === "#seller" ? "seller" : "catalog");
}

start();
