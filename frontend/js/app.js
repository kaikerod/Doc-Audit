(function (root) {
  var demoDocuments = [
    {
      id: "doc-001",
      nomeArquivo: "nf_abril_001.txt",
      numeroNF: "NF-2026-001",
      cnpjEmitente: "11.222.333/0001-81",
      dataNF: "2026-04-15",
      dataPagamento: "2026-04-16",
      valor: 12450.88,
      aprovador: "Maria Silva",
      status: "concluido",
      resumo: "Processamento finalizado sem divergencias.",
      flags: []
    },
    {
      id: "doc-002",
      nomeArquivo: "nf_abril_002.txt",
      numeroNF: "NF-2026-002",
      cnpjEmitente: "55.444.333/0001-09",
      dataNF: "2026-04-19",
      dataPagamento: "2026-04-16",
      valor: 9800.4,
      aprovador: "Carlos Nogueira",
      status: "concluido",
      resumo: "Data de emissao posterior ao pagamento.",
      flags: [
        {
          codigo: "DATA_INV",
          severidade: "CRITICA",
          descricao: "Data de emissao da NF e posterior a data de pagamento."
        }
      ]
    },
    {
      id: "doc-003",
      nomeArquivo: "nf_abril_003.txt",
      numeroNF: "NF-2026-003",
      cnpjEmitente: "77.888.999/0001-12",
      dataNF: "2026-04-12",
      dataPagamento: "2026-04-13",
      valor: 0,
      aprovador: "Luciana Prado",
      status: "concluido",
      resumo: "Valor total zerado na extracao da IA.",
      flags: [
        {
          codigo: "VALOR_ZERO",
          severidade: "ALTA",
          descricao: "Valor total da NF e zero ou negativo."
        }
      ]
    },
    {
      id: "doc-004",
      nomeArquivo: "nf_em_fila_004.txt",
      numeroNF: "--",
      cnpjEmitente: "--",
      dataNF: null,
      dataPagamento: null,
      valor: null,
      aprovador: "--",
      status: "processando",
      resumo: "Arquivo recebido e aguardando worker Celery.",
      flags: []
    }
  ];

  async function updateApiHealth(indicator) {
    try {
      await root.DocAuditApi.fetchApiHealth();
      indicator.textContent = "Disponivel";
      indicator.className = "hero__status-pill";
    } catch (_error) {
      indicator.textContent = "Offline";
      indicator.className = "hero__status-pill";
    }
  }

  function init() {
    var tableController = root.DocAuditTable.createTableController({
      initialDocuments: demoDocuments,
      tableBody: document.getElementById("results-table-body"),
      emptyState: document.getElementById("results-empty-state"),
      searchInput: document.getElementById("document-search-input"),
      statusFilter: document.getElementById("document-status-filter"),
      severityFilter: document.getElementById("document-severity-filter"),
      detailPanel: document.getElementById("detail-panel"),
      detailTitle: document.getElementById("detail-title"),
      detailMetadata: document.getElementById("detail-metadata"),
      detailFlags: document.getElementById("detail-flags"),
      stats: {
        total: document.getElementById("stat-total"),
        withFlags: document.getElementById("stat-with-flags"),
        critical: document.getElementById("stat-critical"),
        processing: document.getElementById("stat-processing")
      }
    });

    root.DocAuditUpload.createUploadController({
      dropzone: document.getElementById("upload-dropzone"),
      fileInput: document.getElementById("upload-file-input"),
      browseButton: document.getElementById("upload-browse-button"),
      feedbackNode: document.getElementById("upload-feedback"),
      maxSizeBytes: 5 * 1024 * 1024,
      onUploadsCreated: function (documents) {
        tableController.prependDocuments(documents);
      }
    });

    document.getElementById("detail-close-button").addEventListener("click", function () {
      document.getElementById("detail-panel").classList.add("is-hidden");
    });

    updateApiHealth(document.getElementById("api-health-indicator"));
  }

  document.addEventListener("DOMContentLoaded", init);
})(typeof globalThis !== "undefined" ? globalThis : this);
