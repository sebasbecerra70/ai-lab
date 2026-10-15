// In-memory inventory domain: stock positions, days of cover, reservations and transfers.

export interface Warehouse {
  id: string;
  name: string;
  region: string;
}

export interface Sku {
  sku: string;
  name: string;
  unitCost: number;
  dailyDemand: Record<string, number>;
}

export interface StockRow {
  sku: string;
  warehouse: string;
  onHand: number;
  reserved: number;
}

export interface InventoryData {
  warehouses: Warehouse[];
  skus: Sku[];
  stock: StockRow[];
}

export class InventoryError extends Error {}

export interface Position extends StockRow {
  available: number;
  daysOfCover: number | null; // null when there is no demand
}

export class Inventory {
  private data: InventoryData;

  constructor(data: InventoryData) {
    // Deep copy so tool calls never mutate the caller's fixture.
    this.data = structuredClone(data);
  }

  get warehouses(): Warehouse[] {
    return this.data.warehouses;
  }

  private row(sku: string, warehouse: string): StockRow {
    this.sku(sku);
    if (!this.data.warehouses.some((w) => w.id === warehouse)) throw new InventoryError(`unknown warehouse ${warehouse}`);
    const r = this.data.stock.find((s) => s.sku === sku && s.warehouse === warehouse);
    if (!r) throw new InventoryError(`${sku} is not stocked at ${warehouse}`);
    return r;
  }

  sku(sku: string): Sku {
    const s = this.data.skus.find((x) => x.sku === sku);
    if (!s) throw new InventoryError(`unknown sku ${sku}`);
    return s;
  }

  position(sku: string, warehouse: string): Position {
    const r = this.row(sku, warehouse);
    const available = r.onHand - r.reserved;
    const demand = this.sku(sku).dailyDemand[warehouse] ?? 0;
    return { ...r, available, daysOfCover: demand > 0 ? Math.round((available / demand) * 10) / 10 : null };
  }

  positions(sku: string): Position[] {
    this.sku(sku);
    return this.data.stock.filter((s) => s.sku === sku).map((s) => this.position(sku, s.warehouse));
  }

  search(query: string): Sku[] {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    return this.data.skus.filter((s) => terms.every((t) => `${s.sku} ${s.name}`.toLowerCase().includes(t)));
  }

  lowStock(minDays: number): Position[] {
    return this.data.stock
      .map((r) => this.position(r.sku, r.warehouse))
      .filter((p) => p.daysOfCover !== null && p.daysOfCover < minDays)
      .sort((a, b) => (a.daysOfCover ?? 0) - (b.daysOfCover ?? 0));
  }

  reserve(sku: string, warehouse: string, qty: number): Position {
    if (!Number.isInteger(qty) || qty <= 0) throw new InventoryError("qty must be a positive integer");
    const r = this.row(sku, warehouse);
    if (r.onHand - r.reserved < qty) {
      throw new InventoryError(`only ${r.onHand - r.reserved} available of ${sku} at ${warehouse}`);
    }
    r.reserved += qty;
    return this.position(sku, warehouse);
  }

  transfer(sku: string, from: string, to: string, qty: number): { from: Position; to: Position } {
    if (from === to) throw new InventoryError("from and to must differ");
    if (!Number.isInteger(qty) || qty <= 0) throw new InventoryError("qty must be a positive integer");
    const src = this.row(sku, from);
    const dst = this.row(sku, to);
    // Never move reserved units: they are promised to orders at the source.
    if (src.onHand - src.reserved < qty) throw new InventoryError(`only ${src.onHand - src.reserved} available to transfer`);
    src.onHand -= qty;
    dst.onHand += qty;
    return { from: this.position(sku, from), to: this.position(sku, to) };
  }
}
