"use client";

import { useState } from "react";
import { FileDown, Loader2 } from "lucide-react";
import type { Report } from "@/lib/types";

interface ExportPDFProps {
  report: Report;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: decimals });
}

// Wraps text and returns new y position
function wrapText(
  doc: InstanceType<typeof import("jspdf").jsPDF>,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number
): number {
  const lines = doc.splitTextToSize(text, maxWidth) as string[];
  doc.text(lines, x, y);
  return y + lines.length * lineHeight;
}

// ---------------------------------------------------------------------------
// PDF builder
// ---------------------------------------------------------------------------

async function buildPDF(report: Report): Promise<void> {
  const { jsPDF } = await import("jspdf");

  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });

  const PAGE_W = 210;
  const PAGE_H = 297;
  const MARGIN = 18;
  const CONTENT_W = PAGE_W - MARGIN * 2;
  const LINE = 6;
  const SMALL_LINE = 5;

  // Brand colours
  const ACCENT: [number, number, number] = [79, 70, 229];   // indigo-600
  const MUTED: [number, number, number]  = [100, 116, 139]; // slate-500
  const TEXT: [number, number, number]   = [30, 41, 59];    // slate-800

  let y = 0;

  // ── Guard / new-page helper ──────────────────────────────────────────────
  function checkPage(needed = 12): void {
    if (y + needed > PAGE_H - MARGIN) {
      doc.addPage();
      y = MARGIN;
    }
  }

  // ── Coloured section header ───────────────────────────────────────────────
  function sectionHeader(title: string): void {
    checkPage(14);
    doc.setFillColor(...ACCENT);
    doc.roundedRect(MARGIN, y, CONTENT_W, 8, 2, 2, "F");
    doc.setTextColor(255, 255, 255);
    doc.setFontSize(10);
    doc.setFont("helvetica", "bold");
    doc.text(title.toUpperCase(), MARGIN + 4, y + 5.5);
    y += 12;
    doc.setTextColor(...TEXT);
  }

  // ── Horizontal divider ────────────────────────────────────────────────────
  function divider(): void {
    doc.setDrawColor(226, 232, 240); // slate-200
    doc.line(MARGIN, y, MARGIN + CONTENT_W, y);
    y += 4;
  }

  // ── Bullet list of strings ───────────────────────────────────────────────
  function bulletList(
    items: string[],
    dotColor: [number, number, number],
    bgColor: [number, number, number] | null = null
  ): void {
    items.forEach((item) => {
      checkPage(12);
      if (bgColor) {
        doc.setFillColor(...bgColor);
        const preview = doc.splitTextToSize(item, CONTENT_W - 12) as string[];
        const h = preview.length * SMALL_LINE + 4;
        doc.roundedRect(MARGIN, y - 1, CONTENT_W, h, 2, 2, "F");
      }
      doc.setFillColor(...dotColor);
      doc.circle(MARGIN + 3, y + 1.5, 1.5, "F");
      doc.setFontSize(8.5);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(...TEXT);
      y = wrapText(doc, item, MARGIN + 7, y, CONTENT_W - 9, SMALL_LINE);
      y += 2;
    });
  }

  // ─────────────────────────────────────────────────────────────────────────
  // COVER PAGE
  // ─────────────────────────────────────────────────────────────────────────

  doc.setFillColor(...ACCENT);
  doc.rect(0, 0, PAGE_W, 60, "F");

  doc.setTextColor(255, 255, 255);
  doc.setFontSize(22);
  doc.setFont("helvetica", "bold");
  doc.text("Insight Flow AI", MARGIN, 28);
  doc.setFontSize(11);
  doc.setFont("helvetica", "normal");
  doc.text("Autonomous Data Analysis Report", MARGIN, 37);

  // White card
  doc.setFillColor(255, 255, 255);
  doc.roundedRect(MARGIN, 68, CONTENT_W, 82, 4, 4, "F");
  doc.setDrawColor(...ACCENT);
  doc.setLineWidth(0.4);
  doc.roundedRect(MARGIN, 68, CONTENT_W, 82, 4, 4, "S");
  doc.setLineWidth(0.2);

  doc.setTextColor(...TEXT);
  doc.setFontSize(15);
  doc.setFont("helvetica", "bold");
  const filenameLines = doc.splitTextToSize(report.dataset.filename, CONTENT_W - 16) as string[];
  doc.text(filenameLines, MARGIN + 8, 82);

  const cardBodyY = 82 + filenameLines.length * 7 + 3;
  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(...MUTED);
  [
    `Rows: ${report.dataset.row_count.toLocaleString()}`,
    `Columns: ${report.dataset.column_count}`,
    `Size: ${report.dataset.size_mb.toFixed(1)} MB`,
    `Format: ${report.dataset.format.toUpperCase()}`,
    `Scan strategy: ${report.dataset.strategy}`,
    `Generated: ${new Date().toLocaleString()}`,
  ].forEach((line, i) => doc.text(line, MARGIN + 8, cardBodyY + i * SMALL_LINE));

  // Big stat numbers
  const statsY = 164;
  const colW = CONTENT_W / 3;
  const statItems = [
    { label: "Charts",          value: String(report.charts.length) },
    { label: "Insights",        value: String(report.insights.length) },
    { label: "Recommendations", value: String(report.recommendations?.length ?? 0) },
  ];
  statItems.forEach(({ label, value }, i) => {
    const cx = MARGIN + i * colW + colW / 2;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(22);
    doc.setTextColor(...ACCENT);
    doc.text(value, cx, statsY, { align: "center" });
    doc.setFontSize(8);
    doc.setFont("helvetica", "normal");
    doc.setTextColor(...MUTED);
    doc.text(label, cx, statsY + 6, { align: "center" });
  });

  doc.setFontSize(7.5);
  doc.setTextColor(...MUTED);
  doc.text(
    "This report was generated automatically by an AI multi-agent system. Verify key findings before acting.",
    PAGE_W / 2,
    PAGE_H - 12,
    { align: "center" },
  );

  // ─────────────────────────────────────────────────────────────────────────
  // PAGE 2+  — CONTENT
  // ─────────────────────────────────────────────────────────────────────────

  doc.addPage();
  y = MARGIN;

  // ── 1. Dataset Overview ──────────────────────────────────────────────────
  sectionHeader("1. Dataset Overview");

  doc.setFontSize(9);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(...TEXT);

  const overviewRows: [string, string][] = [
    ["File",          report.dataset.filename],
    ["Format",        report.dataset.format.toUpperCase()],
    ["Rows",          report.dataset.row_count.toLocaleString()],
    ["Columns",       String(report.dataset.column_count)],
    ["Size",          `${report.dataset.size_mb.toFixed(2)} MB`],
    ["Scan strategy", report.dataset.strategy],
    ...(report.dataset.sample_size
      ? [["Sample size", report.dataset.sample_size.toLocaleString()] as [string, string]]
      : []),
  ];

  overviewRows.forEach(([key, val]) => {
    checkPage(LINE);
    doc.setFont("helvetica", "bold");
    doc.text(key, MARGIN, y);
    doc.setFont("helvetica", "normal");
    doc.text(val, MARGIN + 50, y);
    y += LINE;
  });

  y += 4;
  divider();

  // ── 2. Column Schema ─────────────────────────────────────────────────────
  sectionHeader("2. Column Schema");

  // Column widths and x-offsets
  const colWidths = [38, 28, 22, 22, 22, CONTENT_W - 132];
  const colX = [0, 38, 66, 88, 110, 132].map((v) => MARGIN + v);
  const headers = ["Column", "Type", "dtype", "Missing %", "Unique", "Sample / Stats"];

  // Header row
  doc.setFillColor(241, 245, 249);
  doc.rect(MARGIN, y, CONTENT_W, 6, "F");
  doc.setFontSize(7.5);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...MUTED);
  headers.forEach((h, i) => doc.text(h, colX[i], y + 4.5));
  y += 7;

  doc.setFont("helvetica", "normal");
  doc.setTextColor(...TEXT);

  report.schema.columns.forEach((col, idx) => {
    checkPage(6);
    if (idx % 2 === 0) {
      doc.setFillColor(248, 250, 252);
      doc.rect(MARGIN, y - 0.5, CONTENT_W, 5.5, "F");
    }

    const sample =
      col.category === "numeric"
        ? `μ=${fmt(col.mean_val)} σ=${fmt(col.std_val)}`
        : (Array.isArray(col.sample_values) ? col.sample_values.slice(0, 3).join(", ") : "—");

    const cells = [
      col.name,
      col.category,
      col.dtype,
      `${col.missing_pct.toFixed(1)}%`,
      col.unique_count.toLocaleString(),
      sample,
    ];

    doc.setFontSize(7.5);
    cells.forEach((cell, i) => {
      const maxW = colWidths[i] - 1;
      const lines = doc.splitTextToSize(String(cell), maxW) as string[];
      doc.text(lines[0] + (lines.length > 1 ? "…" : ""), colX[i], y + 4);
    });
    y += 5.5;
  });

  y += 4;
  divider();

  let sectionNum = 3;

  // ── 3. Key Insights ───────────────────────────────────────────────────────
  if (report.insights.length > 0) {
    sectionHeader(`${sectionNum++}. Key Insights`);
    bulletList(report.insights, [251, 191, 36]); // amber-400
    y += 2;
    divider();
  }

  // ── 4. Anomalies ─────────────────────────────────────────────────────────
  if (report.anomalies && report.anomalies.length > 0) {
    sectionHeader(`${sectionNum++}. Anomalies Detected`);
    bulletList(report.anomalies, [248, 113, 113], [254, 242, 242]); // rose tones
    y += 2;
    divider();
  }

  // ── 5. Recommendations ───────────────────────────────────────────────────
  if (report.recommendations && report.recommendations.length > 0) {
    sectionHeader(`${sectionNum++}. Recommendations`);
    bulletList(report.recommendations, [34, 197, 94], [240, 253, 244]); // green tones
  }

  // ── Footer on every page ─────────────────────────────────────────────────
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const totalPages = (doc as any).internal.getNumberOfPages() as number;
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p);
    doc.setFontSize(7.5);
    doc.setTextColor(...MUTED);
    doc.text(`Insight Flow AI  •  ${report.dataset.filename}`, MARGIN, PAGE_H - 8);
    doc.text(`Page ${p} / ${totalPages}`, PAGE_W - MARGIN, PAGE_H - 8, { align: "right" });
  }

  // ── Download ─────────────────────────────────────────────────────────────
  const safeName = report.dataset.filename.replace(/[^a-z0-9._-]/gi, "_");
  doc.save(`insight_report_${safeName}.pdf`);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ExportPDF({ report }: ExportPDFProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      await buildPDF(report);
    } catch (err) {
      console.error("PDF export failed:", err);
      alert("PDF export failed. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  return (
    <button
      onClick={handleExport}
      disabled={exporting}
      className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-500 px-4 py-2 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {exporting
        ? <Loader2 className="w-4 h-4 animate-spin" />
        : <FileDown className="w-4 h-4" />
      }
      {exporting ? "Exporting…" : "Export PDF"}
    </button>
  );
}
