(function (root) {
  var DOCUMENT_POLL_INTERVAL_MS = 4000;
  var documentPollTimerId = null;

  function applyOfflineApiHealth(indicator, copyNode) {
    indicator.textContent = "Offline";
    indicator.className = "hero__status-pill hero__status-pill--error";
    copyNode.textContent = "A API ou o banco de dados n\u00e3o responderam ao health check.";
  }

  async function updateApiHealth(indicator, copyNode, uploadController) {
    try {
      var payload = await root.DocAuditApi.fetchApiHealth();
      var meta = root.DocAuditUiLogic.buildApiHealthMeta(payload);
      indicator.textContent = meta.label;
      indicator.className = meta.className;
      copyNode.textContent = meta.description;
      uploadController.setAvailability({
        enabled: meta.uploadsEnabled,
        message: meta.uploadMessage
      });
    } catch (_error) {
      applyOfflineApiHealth(indicator, copyNode);
      uploadController.setAvailability({
        enabled: false,
        message: "Uploads indisponiveis porque a API nao respondeu ao health check."
      });
    }
  }

  async function loadDocuments(tableController) {
    var payload = await root.DocAuditApi.fetchDocuments();
    var documents = root.DocAuditUiLogic.mapApiDocumentsToViewModels(payload.items);
    tableController.setDocuments(documents);
    return documents;
  }

  function stopDocumentPolling() {
    if (documentPollTimerId !== null) {
      root.clearTimeout(documentPollTimerId);
      documentPollTimerId = null;
    }
  }

  function hasPendingDocuments(documents) {
    return (documents || []).some(function (document) {
      var normalizedStatus = root.DocAuditUiLogic.normalizeKeyword(document.status);
      return normalizedStatus === "pendente" || normalizedStatus === "processando";
    });
  }

  function syncDocumentPolling(tableController, documents) {
    stopDocumentPolling();

    if (!hasPendingDocuments(documents)) {
      return;
    }

    documentPollTimerId = root.setTimeout(function () {
      loadDocuments(tableController)
        .then(function (nextDocuments) {
          syncDocumentPolling(tableController, nextDocuments);
        })
        .catch(function (error) {
          console.error(error);
          syncDocumentPolling(tableController, documents);
        });
    }, DOCUMENT_POLL_INTERVAL_MS);
  }

  function init() {
    var apiHealthIndicator = document.getElementById("api-health-indicator");
    var apiHealthCopy = document.getElementById("api-health-copy");
    var clearAllButton = document.getElementById("clear-all-button");
    var tableController = root.DocAuditTable.createTableController({
      initialDocuments: [],
      dashboardGrid: document.getElementById("results-layout"),
      tableBody: document.getElementById("results-table-body"),
      emptyState: document.getElementById("results-empty-state"),
      searchInput: document.getElementById("document-search-input"),
      statusFilter: document.getElementById("document-status-filter"),
      severityFilter: document.getElementById("document-severity-filter"),
      paginationContainer: document.getElementById("pagination-container"),
      detailPanel: document.getElementById("detail-panel"),
      detailTitle: document.getElementById("detail-title"),
      detailDeleteButton: document.getElementById("detail-delete-button"),
      detailMetadata: document.getElementById("detail-metadata"),
      detailFlags: document.getElementById("detail-flags"),
      clearAllCluster: document.getElementById("clear-all-cluster"),
      onDeleteUpload: async function (document) {
        if (!document || !document.uploadId) {
          return;
        }

        if (!root.confirm("Tem certeza que deseja excluir esta nota definitivamente?")) {
          return;
        }

        await root.DocAuditApi.deleteUpload(document.uploadId);
        tableController.removeDocumentByUploadId(document.uploadId);
      },
      stats: {
        total: document.getElementById("stat-total"),
        withFlags: document.getElementById("stat-with-flags"),
        critical: document.getElementById("stat-critical"),
        processing: document.getElementById("stat-processing")
      }
    });

    var uploadController = root.DocAuditUpload.createUploadController({
      dropzone: document.getElementById("upload-dropzone"),
      fileInput: document.getElementById("upload-file-input"),
      browseButton: document.getElementById("upload-browse-button"),
      feedbackNode: document.getElementById("upload-feedback"),
      idleMessage: "Nenhum envio em andamento.",
      initialAvailability: {
        enabled: false,
        message: "Validando a disponibilidade da API antes de liberar uploads.",
        tone: "busy"
      },
      maxFiles: 250,
      maxSizeBytes: 5 * 1024 * 1024,
      onUploadSuccess: async function () {
        var documents = await loadDocuments(tableController);
        syncDocumentPolling(tableController, documents);
      }
    });

    root.DocAuditExport.createExportController({
      button: document.getElementById("export-button"),
      formatSelect: document.getElementById("export-format-select"),
      anomaliesOnly: document.getElementById("export-anomalies-only"),
      feedbackNode: document.getElementById("export-feedback")
    });

    document.getElementById("detail-close-button").addEventListener("click", function () {
      tableController.clearSelection();
    });

    clearAllButton.addEventListener("click", async function () {
      var currentDocuments = tableController.getDocuments();
      if (!currentDocuments.length) {
        return;
      }

      if (!root.confirm("Tem certeza que deseja excluir TODAS as notas da mesa de auditoria? Esta a\u00e7\u00e3o n\u00e3o pode ser desfeita.")) {
        return;
      }

      clearAllButton.disabled = true;
      clearAllButton.textContent = "Limpando...";

      try {
        await root.DocAuditApi.deleteAllUploads();
        stopDocumentPolling();
        tableController.setDocuments([]);
      } catch (error) {
        console.error(error);
        root.alert(error && error.message ? error.message : "N\u00e3o foi poss\u00edvel limpar as notas.");
      } finally {
        clearAllButton.disabled = false;
        clearAllButton.textContent = "Limpar tudo";
      }
    });

    updateApiHealth(apiHealthIndicator, apiHealthCopy, uploadController);
    loadDocuments(tableController)
      .then(function (documents) {
        syncDocumentPolling(tableController, documents);
      })
      .catch(function (error) {
        console.error(error);
      });
  }

  document.addEventListener("DOMContentLoaded", init);
})(typeof globalThis !== "undefined" ? globalThis : this);
