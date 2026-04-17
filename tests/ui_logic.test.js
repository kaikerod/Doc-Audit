const {
  buildExportPath,
  buildDashboardStats,
  filterDocuments,
  formatCurrencyBRL,
  getSeverityBadgeClass,
  mapApiDocumentToViewModel,
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

  test("buildExportPath monta a rota de exportacao com filtro opcional", () => {
    expect(
      buildExportPath({
        format: "excel",
        onlyAnomalies: true
      })
    ).toBe("/api/v1/exportar/excel?somente_com_anomalias=true");

    expect(
      buildExportPath({
        format: "csv",
        onlyAnomalies: false
      })
    ).toBe("/api/v1/exportar/csv");
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
      reason: "Apenas arquivos .txt s\u00e3o permitidos."
    });
  });

  test("mapApiDocumentToViewModel converte o payload da API para o formato da tabela", () => {
    const mapped = mapApiDocumentToViewModel({
      id: "doc-1",
      upload_id: "upload-1",
      documento_id: "doc-1",
      nome_arquivo: "nf-real.txt",
      numero_nf: "NF-2026-500",
      cnpj_emitente: "11.222.333/0001-81",
      data_emissao: "2026-04-15",
      data_pagamento: "2026-04-16",
      valor_total: 2500.1,
      aprovador: "Maria Silva",
      descricao: "Servi\u00e7o",
      status: "conclu\u00eddo",
      resumo: "Processamento conclu\u00eddo sem anomalias.",
      flags: []
    });

    expect(mapped).toEqual({
      id: "doc-1",
      uploadId: "upload-1",
      documentoId: "doc-1",
      nomeArquivo: "nf-real.txt",
      numeroNF: "NF-2026-500",
      cnpjEmitente: "11.222.333/0001-81",
      dataNF: "2026-04-15",
      dataPagamento: "2026-04-16",
      valor: 2500.1,
      aprovador: "Maria Silva",
      descricao: "Servi\u00e7o",
      status: "conclu\u00eddo",
      resumo: "Processamento conclu\u00eddo sem anomalias.",
      flags: []
    });
  });
});
