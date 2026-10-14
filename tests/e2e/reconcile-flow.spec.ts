import path from "node:path";
import { expect, test, Page } from "@playwright/test";

const DEMO = path.resolve(__dirname, "../../demo");

test.describe.configure({ mode: "serial" });

async function setReviewer(page: Page, name = "revisora-e2e") {
  await page.goto("/");
  await page.getByLabel("Revisor").fill(name);
}

test("import -> reconcile -> review -> approve", async ({ page }) => {
  await setReviewer(page);

  // Empty state before any data
  await expect(page.getByText("Aún no hay datos")).toBeVisible();

  // 2. Import both CSVs through the UI
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Importar" }).click();
  await page.locator("#file-bank").setInputFiles(path.join(DEMO, "bank.csv"));
  await page.getByRole("button", { name: "Validar e importar" }).first().click();
  await expect(page.getByText(/importadas de \d+ filas válidas/).first()).toBeVisible();
  await expect(page.getByText(/1 duplicadas dentro del archivo/)).toBeVisible();
  await page.locator("#file-deposits").setInputFiles(path.join(DEMO, "deposits.csv"));
  await page.getByRole("button", { name: "Validar e importar" }).nth(1).click();
  await expect(page.getByText(/importadas de \d+ filas válidas/).nth(1)).toBeVisible();

  // Re-uploading the same file is a no-op, reported as such
  await page.locator("#file-bank").setInputFiles(path.join(DEMO, "bank.csv"));
  await page.getByRole("button", { name: "Validar e importar" }).first().click();
  await expect(page.getByText(/ya había sido importado/)).toBeVisible();

  // 3. Run reconciliation
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Conciliar" }).click();
  await page.getByRole("button", { name: "Ejecutar conciliación" }).click();
  await expect(page.getByTestId("run-result")).toContainText("completada");
  await expect(page.getByTestId("run-result")).toContainText("Vinculadas (R1): 40");

  // 1. Dashboard reflects the run
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByTestId("kpi-bank")).toHaveText("109");
  await expect(page.getByTestId("count-bank-MATCHED")).toHaveText("40");
  await expect(page.getByTestId("count-bank-AMBIGUOUS")).toHaveText("10");
  const queueBefore = Number(await page.getByTestId("kpi-queue").innerText());
  expect(queueBefore).toBeGreaterThan(40);

  // 6. Review queue: approve one SUGGESTED case
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Revisión" }).click();
  await expect(page.getByTestId("queue-count")).toContainText(`${queueBefore} caso(s)`);
  const suggested = page.locator('[data-testid="review-case"][data-status="SUGGESTED"]').first();
  await suggested.getByRole("button", { name: "Aprobar" }).click();
  await expect(page.getByTestId("queue-count")).toContainText(`${queueBefore - 1} caso(s)`);

  // Dashboard: matched went up by one
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByTestId("count-bank-MATCHED")).toHaveText("41");

  // 8. Audit shows the approval and an intact chain
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Auditoría" }).click();
  await expect(page.getByTestId("chain-ok")).toBeVisible();
  await expect(page.getByRole("cell", { name: "candidate_approved" }).first()).toBeVisible();
});

test("ambiguous cases need a note; rejection works", async ({ page }) => {
  await setReviewer(page);
  await page.getByRole("navigation", { name: "Principal" }).getByRole("link", { name: "Revisión" }).click();
  const amb = page.locator('[data-testid="review-case"][data-status="AMBIGUOUS"]').first();
  await expect(amb).toBeVisible();
  await expect(amb.getByRole("button", { name: "Aprobar" })).toBeDisabled();
  await amb.getByRole("textbox").fill("Verificado contra el extracto original");
  await expect(amb.getByRole("button", { name: "Aprobar" })).toBeEnabled();

  const before = Number((await page.getByTestId("queue-count").innerText()).match(/\d+/)![0]);
  await amb.getByRole("button", { name: "Rechazar" }).click();
  await expect(page.getByTestId("queue-count")).toContainText(`${before - 1} caso(s)`);
});

test("decisions without a reviewer name are refused with a visible error", async ({ page }) => {
  await page.goto("/review");
  await page.evaluate(() => localStorage.removeItem("reconcileai.actor"));
  await page.reload();
  await page.locator('[data-testid="review-case"]').first().getByRole("button", { name: "Rechazar" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "X-Actor" })).toBeVisible();
});

test("invalid CSV is rejected with line-level errors and nothing is imported", async ({ page }) => {
  await setReviewer(page);
  await page.goto("/import");
  await page.locator("#file-bank").setInputFiles({
    name: "bad.csv", mimeType: "text/csv",
    buffer: Buffer.from("id,date,amount,description\nX1,2025-13-45,10.00,bad date\nX2,2025-01-01,abc,bad amount\n"),
  });
  await page.getByRole("button", { name: "Validar e importar" }).first().click();
  const alert = page.getByRole("alert").filter({ hasText: "nothing was imported" });
  await expect(alert).toContainText("nothing was imported");
  await expect(alert).toContainText("Línea 2");
  await expect(alert).toContainText("Línea 3");
});

test("transaction table filters by status and detail shows evidence", async ({ page }) => {
  await page.goto("/transactions");
  await page.getByRole("button", { name: "AMBIGUOUS" }).click();
  const rows = page.getByTestId("tx-table").locator("tbody tr");
  await expect(rows.first()).toContainText("AMBIGUOUS");
  await rows.first().getByRole("link").click();
  await expect(page.getByRole("heading", { name: /Movimiento B\d+/ })).toBeVisible();
  await expect(page.getByText("Ambiguo: hay más de una combinación")).toBeVisible();

  await page.goto("/transactions");
  await page.getByRole("button", { name: "UNMATCHED" }).click();
  const unmatched = page.getByTestId("tx-table").locator("tbody tr");
  await expect(unmatched.first()).toBeVisible();
});

test("AMD Inference Monitor never presents mock data as real inference", async ({ page }) => {
  await page.goto("/inference");
  await expect(page.getByText("MODO MOCK")).toBeVisible();
  await expect(page.getByText("Sin llamadas reales registradas")).toBeVisible();
  await expect(page.getByTestId("real-metrics")).toHaveCount(0);
});
