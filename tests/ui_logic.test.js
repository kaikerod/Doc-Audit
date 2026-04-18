const {
  buildApiHealthMeta,
  buildExportPath,
  buildDashboardStats,
  filterDocuments,
  formatCurrencyBRL,
  getSeverityBadgeClass,
  hasUploadSelectionOverlap,
  mapApiDocumentToViewModel,
  mergeUploadSelection,
  validateUploadBatch,
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

  test("buildApiHealthMeta sinaliza uploads bloqueados quando a IA nao esta configurada", () => {
    expect(
      buildApiHealthMeta({
        status: "limited",
        features: {
          uploads_enabled: false
        },
        detail: "OPENROUTER_API_KEY nao configurada."
      })
    ).toEqual({
      label: "IA pendente",
      className: "hero__status-pill hero__status-pill--pending",
      description: "OPENROUTER_API_KEY nao configurada.",
      uploadsEnabled: false,
      uploadMessage: "OPENROUTER_API_KEY nao configurada."
    });
  });

  test("buildApiHealthMeta libera uploads quando a API esta pronta", () => {
    expect(
      buildApiHealthMeta({
        status: "ok",
        features: {
          uploads_enabled: true
        }
      })
    ).toEqual({
      label: "Dispon\u00edvel",
      className: "hero__status-pill hero__status-pill--success",
      description: "API, fila e pipeline de an\u00e1lise prontos para receber arquivos.",
      uploadsEnabled: true,
      uploadMessage: ""
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

  test("validateUploadFile aceita arquivos zip", () => {
    const result = validateUploadFile(
      { name: "lote-notas.zip", size: 1024 },
      5 * 1024 * 1024
    );

    expect(result).toEqual({
      valid: true,
      reason: ""
    });
  });

  test("validateUploadFile rejeita extensao invalida", () => {
    const result = validateUploadFile(
      { name: "nota-fiscal.pdf", size: 1024 },
      5 * 1024 * 1024
    );

    expect(result).toEqual({
      valid: false,
      reason: "Apenas arquivos .txt ou .zip s\u00e3o permitidos."
    });
  });

  test("validateUploadBatch rejeita lotes acima do limite", () => {
    const result = validateUploadBatch(new Array(251).fill({}), 250);

    expect(result).toEqual({
      valid: false,
      reason: "Limite maximo de 250 arquivos por envio."
    });
  });

  test("mergeUploadSelection adiciona ate o limite quando a primeira selecao excede o maximo", () => {
    const files = Array.from({ length: 4 }, (_, index) => ({
      name: "nota-" + index + ".txt",
      size: 1024,
      lastModified: index + 1
    }));

    const result = mergeUploadSelection([], files, {
      maxFiles: 2,
      maxSizeBytes: 5 * 1024 * 1024
    });

    expect(result.addedFiles.map((file) => file.name)).toEqual(["nota-0.txt", "nota-1.txt"]);
    expect(result.files.map((file) => file.name)).toEqual(["nota-0.txt", "nota-1.txt"]);
    expect(result.overflowFiles.map((file) => file.name)).toEqual(["nota-2.txt", "nota-3.txt"]);
    expect(result.limitReached).toBe(true);
    expect(result.remainingSlots).toBe(0);
  });

  test("mergeUploadSelection ignora arquivos ja presentes e preenche vagas restantes ate o limite", () => {
    const currentFiles = [
      { name: "nota-0.txt", size: 1024, lastModified: 1 },
      { name: "nota-1.txt", size: 1024, lastModified: 2 }
    ];
    const nextFiles = [
      { name: "nota-0.txt", size: 1024, lastModified: 1 },
      { name: "nota-1.txt", size: 1024, lastModified: 2 },
      { name: "nota-2.txt", size: 1024, lastModified: 3 },
      { name: "nota-3.txt", size: 1024, lastModified: 4 }
    ];

    const result = mergeUploadSelection(currentFiles, nextFiles, {
      maxFiles: 3,
      maxSizeBytes: 5 * 1024 * 1024
    });

    expect(result.files.map((file) => file.name)).toEqual([
      "nota-0.txt",
      "nota-1.txt",
      "nota-2.txt"
    ]);
    expect(result.addedFiles.map((file) => file.name)).toEqual(["nota-2.txt"]);
    expect(result.duplicateFiles.map((file) => file.name)).toEqual([
      "nota-0.txt",
      "nota-1.txt"
    ]);
    expect(result.overflowFiles.map((file) => file.name)).toEqual(["nota-3.txt"]);
    expect(result.limitReached).toBe(true);
    expect(result.remainingSlots).toBe(0);
  });

  test("mergeUploadSelection ignora invalidos e continua adicionando os validos seguintes", () => {
    const result = mergeUploadSelection(
      [],
      [
        { name: "nota-0.pdf", size: 1024, lastModified: 1 },
        { name: "nota-1.txt", size: 2048, lastModified: 2 },
        { name: "nota-2.txt", size: 0, lastModified: 3 }
      ],
      {
        maxFiles: 5,
        maxSizeBytes: 5 * 1024 * 1024
      }
    );

    expect(result.files.map((file) => file.name)).toEqual(["nota-1.txt"]);
    expect(result.addedFiles.map((file) => file.name)).toEqual(["nota-1.txt"]);
    expect(result.invalidFiles.map((entry) => entry.reason)).toEqual([
      "Apenas arquivos .txt ou .zip s\u00e3o permitidos.",
      "Arquivos vazios n\u00e3o s\u00e3o permitidos."
    ]);
    expect(result.remainingSlots).toBe(4);
  });

  test("hasUploadSelectionOverlap identifica quando a nova selecao reaproveita arquivos ja adicionados", () => {
    const currentFiles = [
      { name: "nota-0.txt", size: 1024, lastModified: 1 },
      { name: "nota-1.txt", size: 1024, lastModified: 2 }
    ];

    expect(
      hasUploadSelectionOverlap(currentFiles, [
        { name: "nota-1.txt", size: 1024, lastModified: 2 },
        { name: "nota-2.txt", size: 1024, lastModified: 3 }
      ])
    ).toBe(true);

    expect(
      hasUploadSelectionOverlap(currentFiles, [
        { name: "nota-3.txt", size: 1024, lastModified: 4 }
      ])
    ).toBe(false);
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
