(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.DocAuditUiLogic = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  var currencyFormatter = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL"
  });

  function normalizeKeyword(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim()
      .toLowerCase();
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatCurrencyBRL(value) {
    if (value === null || value === undefined || value === "") {
      return "--";
    }

    var numericValue = Number(value);
    if (Number.isNaN(numericValue)) {
      return "--";
    }

    return currencyFormatter.format(numericValue).replace(/\u00a0/g, " ");
  }

  function formatDateBR(value) {
    if (!value) {
      return "--";
    }

    var normalizedValue = value;
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
      normalizedValue = value + "T00:00:00Z";
    }

    var date = value instanceof Date ? value : new Date(normalizedValue);
    if (Number.isNaN(date.getTime())) {
      return "--";
    }

    return new Intl.DateTimeFormat("pt-BR", {
      timeZone: "UTC"
    }).format(date);
  }

  function getSeverityBadgeClass(severity) {
    switch (normalizeKeyword(severity)) {
      case "critica":
        return "badge badge--critical";
      case "alta":
        return "badge badge--high";
      default:
        return "badge badge--medium";
    }
  }

  function getStatusMeta(status, flags) {
    var normalizedStatus = normalizeKeyword(status);
    var hasFlags = Array.isArray(flags) && flags.length > 0;

    if (normalizedStatus === "pendente") {
      return {
        label: "Pendente",
        className: "badge badge--status badge--status-processing"
      };
    }

    if (normalizedStatus === "processando") {
      return {
        label: "Processando",
        className: "badge badge--status badge--status-processing"
      };
    }

    if (normalizedStatus === "erro") {
      return {
        label: "Erro",
        className: "badge badge--status badge--status-error"
      };
    }

    if (hasFlags) {
      return {
        label: "Conclu\u00eddo com flags",
        className: "badge badge--status badge--status-alert"
      };
    }

    return {
      label: "Conclu\u00eddo",
      className: "badge badge--status badge--status-success"
    };
  }

  function summarizeFlags(flags) {
    if (!Array.isArray(flags) || flags.length === 0) {
      return "Sem flags";
    }

    return flags
      .map(function (flag) {
        return flag.codigo;
      })
      .join(", ");
  }

  function buildDashboardStats(documents) {
    var safeDocuments = Array.isArray(documents) ? documents : [];

    return safeDocuments.reduce(
      function (stats, document) {
        stats.total += 1;

        if (Array.isArray(document.flags) && document.flags.length > 0) {
          stats.withFlags += 1;
        }

        if (
          Array.isArray(document.flags) &&
          document.flags.some(function (flag) {
            return normalizeKeyword(flag.severidade) === "critica";
          })
        ) {
          stats.critical += 1;
        }

        if (["processando", "pendente"].includes(normalizeKeyword(document.status))) {
          stats.processing += 1;
        }

        return stats;
      },
      {
        total: 0,
        withFlags: 0,
        critical: 0,
        processing: 0
      }
    );
  }

  function buildExportPath(options) {
    var safeOptions = options || {};
    var format = normalizeKeyword(safeOptions.format) === "excel" ? "excel" : "csv";
    var basePath = "/api/v1/exportar/" + format;

    if (safeOptions.onlyAnomalies) {
      return basePath + "?somente_com_anomalias=true";
    }

    return basePath;
  }

  function matchesDocumentSearch(document, query) {
    var normalizedQuery = normalizeKeyword(query);
    if (!normalizedQuery) {
      return true;
    }

    return normalizeKeyword(document.nomeArquivo).includes(normalizedQuery) ||
      normalizeKeyword(document.numeroNF).includes(normalizedQuery);
  }

  function filterDocuments(documents, filters) {
    var safeDocuments = Array.isArray(documents) ? documents : [];
    var safeFilters = filters || {};
    var statusFilter = normalizeKeyword(safeFilters.status || "todos");
    var severityFilter = normalizeKeyword(safeFilters.severity || "todas");

    return safeDocuments.filter(function (document) {
      if (!matchesDocumentSearch(document, safeFilters.query || "")) {
        return false;
      }

      var hasFlags = Array.isArray(document.flags) && document.flags.length > 0;
      var normalizedStatus = normalizeKeyword(document.status);

      if (statusFilter === "com_anomalia" && !hasFlags) {
        return false;
      }

      if (statusFilter === "sem_anomalia" && hasFlags) {
        return false;
      }

      if (statusFilter === "processando" && !["processando", "pendente"].includes(normalizedStatus)) {
        return false;
      }

      if (statusFilter === "erro" && normalizedStatus !== "erro") {
        return false;
      }

      if (
        severityFilter !== "todas" &&
        !document.flags.some(function (flag) {
          return normalizeKeyword(flag.severidade) === severityFilter;
        })
      ) {
        return false;
      }

      return true;
    });
  }

  function validateUploadFile(file, maxSizeBytes) {
    var fileName = file && file.name ? file.name : "";
    var normalizedName = normalizeKeyword(fileName);
    var hasTxtExtension = normalizedName.endsWith(".txt");

    if (!hasTxtExtension) {
      return {
        valid: false,
        reason: "Apenas arquivos .txt s\u00e3o permitidos."
      };
    }

    if (!file.size) {
      return {
        valid: false,
        reason: "Arquivos vazios n\u00e3o s\u00e3o permitidos."
      };
    }

    if (file.size > maxSizeBytes) {
      return {
        valid: false,
        reason: "Arquivo excede o limite permitido."
      };
    }

    return {
      valid: true,
      reason: ""
    };
  }

  function validateUploadBatch(files, maxFiles) {
    var safeFiles = Array.isArray(files) ? files : [];

    if (safeFiles.length > maxFiles) {
      return {
        valid: false,
        reason: "Limite maximo de " + maxFiles + " arquivos por envio."
      };
    }

    return {
      valid: true,
      reason: ""
    };
  }

  function buildApiHealthMeta(payload) {
    var safePayload = payload || {};
    var features = safePayload.features || {};
    var uploadsEnabled = features.uploads_enabled !== false;
    var detail = typeof safePayload.detail === "string" && safePayload.detail.trim()
      ? safePayload.detail.trim()
      : "";

    if (!uploadsEnabled) {
      return {
        label: "IA pendente",
        className: "hero__status-pill hero__status-pill--pending",
        description: detail || "Configure a integra\u00e7\u00e3o de IA para habilitar uploads.",
        uploadsEnabled: false,
        uploadMessage: detail || "Uploads indispon\u00edveis at\u00e9 a configura\u00e7\u00e3o da IA."
      };
    }

    return {
      label: "Dispon\u00edvel",
      className: "hero__status-pill hero__status-pill--success",
      description: "API, fila e pipeline de an\u00e1lise prontos para receber arquivos.",
      uploadsEnabled: true,
      uploadMessage: ""
    };
  }

  function mapUploadItemsToDocuments(items) {
    return (items || []).map(function (item) {
      return {
        id: item.id,
        uploadId: item.id,
        documentoId: null,
        nomeArquivo: item.nome_arquivo,
        numeroNF: "--",
        cnpjEmitente: "--",
        dataNF: null,
        dataPagamento: null,
        valor: null,
        aprovador: "--",
        descricao: "",
        status: item.status || "processando",
        flags: [],
        resumo: "Upload recebido e aguardando o pipeline de IA."
      };
    });
  }

  function mapApiDocumentToViewModel(item) {
    return {
      id: item.id,
      uploadId: item.upload_id,
      documentoId: item.documento_id,
      nomeArquivo: item.nome_arquivo,
      numeroNF: item.numero_nf || "--",
      cnpjEmitente: item.cnpj_emitente || "--",
      dataNF: item.data_emissao,
      dataPagamento: item.data_pagamento,
      valor: item.valor_total,
      aprovador: item.aprovador || "--",
      descricao: item.descricao || "",
      status: item.status,
      resumo: item.resumo || "Documento monitorado no dashboard.",
      flags: Array.isArray(item.flags) ? item.flags : []
    };
  }

  function mapApiDocumentsToViewModels(items) {
    return (items || []).map(mapApiDocumentToViewModel);
  }

  return {
    buildExportPath: buildExportPath,
    buildDashboardStats: buildDashboardStats,
    buildApiHealthMeta: buildApiHealthMeta,
    escapeHtml: escapeHtml,
    filterDocuments: filterDocuments,
    formatCurrencyBRL: formatCurrencyBRL,
    formatDateBR: formatDateBR,
    getSeverityBadgeClass: getSeverityBadgeClass,
    getStatusMeta: getStatusMeta,
    mapApiDocumentToViewModel: mapApiDocumentToViewModel,
    mapApiDocumentsToViewModels: mapApiDocumentsToViewModels,
    mapUploadItemsToDocuments: mapUploadItemsToDocuments,
    matchesDocumentSearch: matchesDocumentSearch,
    normalizeKeyword: normalizeKeyword,
    summarizeFlags: summarizeFlags,
    validateUploadBatch: validateUploadBatch,
    validateUploadFile: validateUploadFile
  };
});
