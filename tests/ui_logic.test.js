const {
  buildDashboardStats,
  filterDocuments,
  formatCurrencyBRL,
  getSeverityBadgeClass,
  validateUploadFile
} = require("../frontend/js/ui-logic.js");

describe("DocAudit UI logic", () => {
  test("formatCurrencyBRL formata valores em real", () => {
    expect(formatCurrencyBRL(1234.5)).toBe("R$ 1.234,50");
  });

  test("getSeverityBadgeClass retorna o badge correto para severidade critica", () => {
    expect(getSeverityBadgeClass("CRITICA")).toBe("badge badge--critical");
  });

  test("buildDashboardStats consolida totais do dashboard", () => {
    const stats = buildDashboardStats([
      { status: "concluido", flags: [] },
      { status: "processando", flags: [{ severidade: "ALTA" }] },
      { status: "concluido", flags: [{ severidade: "CRITICA" }] }
    ]);

    expect(stats).toEqual({
      total: 3,
      withFlags: 2,
      critical: 1,
      processing: 1
    });
  });

  test("filterDocuments aplica busca, status e severidade", () => {
    const documents = [
      {
        nomeArquivo: "nf_abril_001.txt",
        numeroNF: "NF-1001",
        status: "concluido",
        flags: []
      },
      {
        nomeArquivo: "nf_abril_002.txt",
        numeroNF: "NF-1002",
        status: "concluido",
        flags: [{ codigo: "DATA_INV", severidade: "CRITICA" }]
      }
    ];

    const filtered = filterDocuments(documents, {
      query: "1002",
      status: "com_anomalia",
      severity: "CRITICA"
    });

    expect(filtered).toHaveLength(1);
    expect(filtered[0].numeroNF).toBe("NF-1002");
  });

  test("validateUploadFile rejeita extensao invalida", () => {
    const result = validateUploadFile(
      { name: "nota-fiscal.pdf", size: 1024 },
      5 * 1024 * 1024
    );

    expect(result).toEqual({
      valid: false,
      reason: "Apenas arquivos .txt sao permitidos."
    });
  });
});
