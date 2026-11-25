const pageSize = 50;
const statusLabels = {
  reserved: "Брондалған",
  accepted: "Расталған",
  rejected: "Қабылданбаған",
  ready: "Дайын",
  completed: "Аяқталған",
  cancelled: "Бас тартылған",
  expired: "Мерзімі өткен",
};

export function createSellerOrders({ api, setFeedback, money, quantity, date, createElement }) {
  const list = document.getElementById("seller-orders-list");
  const state = document.getElementById("seller-orders-state");
  const actionFeedback = document.getElementById("seller-orders-action-feedback");
  const refresh = document.getElementById("seller-orders-refresh");
  const more = document.getElementById("seller-orders-more");
  const confirmations = new Map();
  let orders = [];
  let offset = 0;
  let hasMore = false;
  let generation = 0;
  let listRequest = null;

  function updateControls() {
    const loading = Boolean(listRequest);
    list.setAttribute("aria-busy", String(loading));
    refresh.disabled = loading;
    more.hidden = !hasMore;
    more.disabled = loading;
  }

  function render() {
    list.replaceChildren(...orders.map((order) => {
      const number = order.id.slice(0, 8);
      const currency = order.currency === "KZT" ? "₸" : order.currency;
      const card = createElement("li", "seller-order");
      const heading = createElement("div", "seller-order-heading");
      const status = createElement("span", "seller-order-status", statusLabels[order.status] || order.status);
      status.dataset.status = order.status;
      heading.append(createElement("h3", "", `Тапсырыс №${number}`), status);

      const meta = createElement("p", "seller-order-meta", `${date.format(new Date(order.created_at))} · Жалпы сома: ${money.format(order.total_amount)} ${currency}`);
      const items = createElement("ul", "seller-order-items");
      items.setAttribute("aria-label", "Тапсырыс құрамындағы партиялар");
      for (const item of order.items) {
        items.append(createElement("li", "", `Партия №${item.batch_id.slice(0, 8)} · Саны: ${quantity.format(item.quantity)} · Бірлік бағасы: ${money.format(item.unit_price)} ${currency}`));
      }
      card.append(heading, meta, items);

      if (order.status === "reserved") {
        const footer = createElement("div", "seller-order-footer");
        const button = createElement("button", "button button-primary button-small", "Растау");
        button.type = "button";
        button.disabled = confirmations.has(order.id);
        button.setAttribute("aria-label", `Растау, тапсырыс №${number}`);
        button.addEventListener("click", () => confirmOrder(order.id, button));
        footer.append(button);
        card.append(footer);
      }
      return card;
    }));
  }

  async function load({ append = false } = {}) {
    if (append && (!hasMore || listRequest)) return;
    listRequest?.abort();
    const request = new AbortController();
    listRequest = request;
    const start = append ? offset : 0;
    updateControls();
    setFeedback(state, orders.length ? "" : "Тапсырыстар жүктелуде…");
    try {
      const page = await api(`/api/seller/orders?limit=${pageSize}&offset=${start}`, {
        authorized: true,
        signal: request.signal,
      });
      if (listRequest !== request) return;
      const uniqueOrders = new Map((append ? orders : []).map((order) => [order.id, order]));
      for (const order of page) uniqueOrders.set(order.id, order);
      orders = [...uniqueOrders.values()];
      offset = start + page.length;
      hasMore = page.length === pageSize;
      render();
      setFeedback(state, orders.length ? "" : "Әзірге тапсырыстар жоқ.");
    } catch (error) {
      if (listRequest !== request) return;
      if (error.status === 404 || error.status === 403) {
        orders = [];
        offset = 0;
        hasMore = false;
        render();
        setFeedback(state, error.status === 404
          ? "Тапсырыстар бөлімі әлі қосылмаған."
          : "Тапсырыстарды көруге рұқсатыңыз жоқ.", "error");
      } else if (error.status !== 401 && error.name !== "AbortError") {
        setFeedback(state, "Тапсырыстар жүктелмеді. Қайта көріңіз.", "error");
      }
    } finally {
      if (listRequest === request) {
        listRequest = null;
        updateControls();
      }
    }
  }

  async function confirmOrder(id, button) {
    if (confirmations.has(id) || !orders.some((order) => order.id === id && order.status === "reserved")) return;
    const session = generation;
    const request = new AbortController();
    const hadFocus = document.activeElement === button;
    confirmations.set(id, request);
    button.disabled = true;
    setFeedback(actionFeedback, "Тапсырыс расталуда…");
    try {
      const response = await api(`/api/seller/orders/${encodeURIComponent(id)}/accept`, {
        method: "PATCH",
        authorized: true,
        signal: request.signal,
      });
      if (generation !== session) return;
      if (response.id !== id || response.status !== "accepted") {
        setFeedback(actionFeedback, "Растау нәтижесі белгісіз. Тапсырыстар тізімі жаңартылады.", "error");
      } else {
        orders = orders.map((order) => order.id === id ? { ...order, status: response.status } : order);
        render();
        setFeedback(actionFeedback, `№${id.slice(0, 8)} тапсырысы расталды.`, "success");
      }
      void load();
    } catch (error) {
      if (generation !== session || error.status === 401 || error.name === "AbortError") return;
      if (error.status === 404 || error.status === 409) {
        setFeedback(actionFeedback, "Бұл тапсырыстың күйі өзгерген. Тапсырыстар тізімі жаңартылады.", "error");
      } else {
        setFeedback(actionFeedback, "Растау нәтижесі белгісіз. Тапсырыстар тізімі жаңартылады.", "error");
      }
      void load();
    } finally {
      if (confirmations.get(id) === request) {
        confirmations.delete(id);
        render();
        if (hadFocus && document.activeElement === document.body) actionFeedback.focus();
      }
    }
  }

  function reset() {
    generation += 1;
    listRequest?.abort();
    listRequest = null;
    for (const request of confirmations.values()) request.abort();
    confirmations.clear();
    orders = [];
    offset = 0;
    hasMore = false;
    render();
    updateControls();
    setFeedback(state);
    setFeedback(actionFeedback);
  }

  refresh.addEventListener("click", () => {
    setFeedback(actionFeedback);
    void load();
  });
  more.addEventListener("click", () => load({ append: true }));
  return { load, reset };
}
