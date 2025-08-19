// server.js
// Gas Station B2B – Step 1 (Single-file API)
// Run: node server.js  (PORT=8080 default)

import express from "express";
import cors from "cors";

const app = express();
app.use(cors());
app.use(express.json());

// ---- Config (edit as you grow) ----
const COMMISSION_RATE = 0.10;       // 10%
const DELIVERY_FEE_CENTS = 1900;    // $19
const STORE_NET_DAYS = 15;          // Net-15 to stores
const SUPPLIER_NET_DAYS = 30;       // Net-30 from suppliers

// ---- Demo Data (in-memory for Step 1) ----
const suppliers = [
  { id: "sup-core", name: "Core Supplier", net_days: SUPPLIER_NET_DAYS },
];

const warehouses = [
  // North MS / Memphis metro (good for fast pilot)
  { id: "wh-southaven", supplier_id: "sup-core", name: "Southaven, MS DC", lat: 34.9889, lon: -90.0126, address: { city: "Southaven", state: "MS" } },
  // Central MS
  { id: "wh-jackson", supplier_id: "sup-core", name: "Jackson, MS Hub",    lat: 32.2988, lon: -90.1848, address: { city: "Jackson", state: "MS" } },
  // Gulf Coast
  { id: "wh-gulfport", supplier_id: "sup-core", name: "Gulfport, MS Hub",  lat: 30.3674, lon: -89.0928, address: { city: "Gulfport", state: "MS" } },
];

const products = [
  // cost_cents = your buy price; app charges cost + delivery; your revenue = commission on subtotal
  { id: "p-redbull24",  sku: "RB-24",  name: "Red Bull 8.4oz (24pk)",  unit: "case", cost_cents: 2699 },
  { id: "p-doritos12",  sku: "DO-12",  name: "Doritos Nacho (12pk)",   unit: "case", cost_cents: 1799 },
  { id: "p-water24",    sku: "WT-24",  name: "Bottled Water (24pk)",   unit: "case", cost_cents:  899 },
  { id: "p-lidscups",   sku: "LC-100", name: "Cups + Lids (100ct)",    unit: "case", cost_cents:  649 },
];

const stores = [
  // Example stores; add more or POST /stores to insert dynamically in future steps
  { id: "st-oxford",   owner_name: "Jay",  business_name: "Quick Fuel Oxford",  email: "oxford@example.com",  lat: 34.3665, lon: -89.5192, credit_terms_days: STORE_NET_DAYS, credit_limit_cents: 200000, current_ar_cents: 0 },
  { id: "st-jackson",  owner_name: "Raj",  business_name: "Capitol C-Store",    email: "jackson@example.com", lat: 32.2988, lon: -90.1848, credit_terms_days: STORE_NET_DAYS, credit_limit_cents: 200000, current_ar_cents: 0 },
  { id: "st-gulfport", owner_name: "Sam",  business_name: "Coast Gas & Go",     email: "gulfport@example.com",lat: 30.3674, lon: -89.0928, credit_terms_days: STORE_NET_DAYS, credit_limit_cents: 200000, current_ar_cents: 0 },
];

// Simple “tables”
const orders = [];
const invoices = [];
const settlements = [];

// ---- Utils ----
const R = 6371; // km
const toRad = d => d * Math.PI / 180;
function distanceKm(a, b) {
  const dLat = toRad(b.lat - a.lat), dLon = toRad(b.lon - a.lon);
  const la = toRad(a.lat), lb = toRad(b.lat);
  const h = Math.sin(dLat/2)**2 + Math.cos(la)*Math.cos(lb)*Math.sin(dLon/2)**2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function nearestWarehouse(store) {
  const pick = warehouses
    .map(w => ({ w, d: distanceKm({ lat: store.lat, lon: store.lon }, { lat: w.lat, lon: w.lon }) }))
    .sort((a, b) => a.d - b.d)[0];
  return pick?.w;
}
function priceOrder(subtotalCents) {
  const commission_cents = Math.round(subtotalCents * COMMISSION_RATE);
  const delivery_fee_cents = DELIVERY_FEE_CENTS;
  const total_cents = subtotalCents + delivery_fee_cents; // store pays subtotal + delivery; your revenue is commission + delivery fee if you keep it
  return { commission_cents, delivery_fee_cents, total_cents };
}
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }

// ---- Routes ----
app.get("/health", (req, res) => {
  res.json({ ok: true, service: "b2b-gas-step1", time: new Date().toISOString() });
});

app.get("/suppliers", (req, res) => res.json(suppliers));
app.get("/warehouses", (req, res) => res.json(warehouses));
app.get("/products", (req, res) => res.json(products));
app.get("/stores", (req, res) => res.json(stores));

/**
 * Create order
 * body: { store_id, items:[{product_id, qty}], terms? "COD"|"NET15" }
 */
app.post("/orders", (req, res) => {
  try {
    const { store_id, items, terms } = req.body || {};
    if (!store_id || !Array.isArray(items) || items.length === 0) {
      return res.status(400).json({ error: "store_id and items[] required" });
    }
    const store = stores.find(s => s.id === store_id);
    if (!store) return res.status(404).json({ error: "store not found" });

    // load products
    let subtotal_cents = 0;
    const lines = items.map(row => {
      const p = products.find(pp => pp.id === row.product_id);
      if (!p) throw new Error(`product not found: ${row.product_id}`);
      const qty = Number(row.qty || 0);
      if (qty <= 0) throw new Error(`invalid qty for ${p.id}`);
      const line = p.cost_cents * qty;
      subtotal_cents += line;
      return { product_id: p.id, sku: p.sku, name: p.name, qty, unit_cost_cents: p.cost_cents, line_cents: line };
    });

    // pricing
    const { commission_cents, delivery_fee_cents, total_cents } = priceOrder(subtotal_cents);

    // credit policy
    const payment_terms = terms || (store.current_ar_cents + total_cents <= store.credit_limit_cents ? "NET15" : "COD");
    const due_at = payment_terms === "NET15" ? addDays(new Date(), STORE_NET_DAYS) : null;

    if (payment_terms === "NET15" && (store.current_ar_cents + total_cents) > store.credit_limit_cents) {
      return res.status(402).json({ error: "credit limit exceeded", current_ar_cents: store.current_ar_cents, limit_cents: store.credit_limit_cents, needed_cents: total_cents });
    }

    // route to nearest warehouse
    const wh = nearestWarehouse(store);
    if (!wh) return res.status(500).json({ error: "no warehouse available" });

    // create order
    const order = {
      id: `ord_${Date.now()}`,
      store_id: store.id,
      warehouse_id: wh.id,
      status: "confirmed", // pending -> confirmed -> shipped -> delivered -> invoiced -> paid
      items: lines,
      subtotal_cents,
      commission_cents,
      delivery_fee_cents,
      total_cents,
      payment_terms,
      placed_at: new Date().toISOString(),
      due_at: due_at ? due_at.toISOString() : null,
      eta_hours_max: 36
    };
    orders.push(order);

    // create invoice (store AR)
    invoices.push({
      id: `inv_${Date.now()}`,
      order_id: order.id,
      store_id: store.id,
      amount_cents: total_cents,
      due_at: order.due_at,
      status: payment_terms === "COD" ? "open" : "open"
    });

    // schedule supplier settlement (your AP) – using subtotal as cost proxy (95% if you want)
    settlements.push({
      id: `set_${Date.now()}`,
      supplier_id: wh.supplier_id,
      order_id: order.id,
      amount_cents: Math.round(subtotal_cents * 0.95), // proxy
      due_at: addDays(new Date(), SUPPLIER_NET_DAYS).toISOString(),
      status: "scheduled"
    });

    if (payment_terms === "NET15") {
      store.current_ar_cents += total_cents;
    }

    res.json({
      ok: true,
      order,
      assigned_warehouse: wh,
      note: "36-hr delivery SLA; Net-15 if within credit limit, else COD."
    });
  } catch (e) {
    res.status(400).json({ error: String(e.message || e) });
  }
});

app.get("/orders", (req, res) => res.json(orders));
app.get("/invoices", (req, res) => res.json(invoices));
app.get("/settlements", (req, res) => res.json(settlements));

// ---- Start ----
const PORT = process.env.PORT || 8080;
app.listen(PORT, () => {
  console.log(`B2B Step1 API running on :${PORT}`);
});