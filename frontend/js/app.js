(function (root) {
  async function updateApiHealth(indicator) {
    try {
      await root.DocAuditApi.fetchApiHealth();
      indicator.textContent = "Dispon\u00edvel";
      indicator.className = "hero__status-pill hero__status-pill--success";
    } catch (_error) {
      indicator.textContent = "Offline";
      indicator.className = "hero__status-pill hero__status-pill--error";
    }
  }

  async function loadDocuments(tableController) {
    var payload = await root.DocAuditApi.fetchDocuments();
    tableController.setDocuments(root.DocAuditUiLogic.mapApiDocumentsToViewModels(payload.items));
  }

  function init() {
    var tableController = root.DocAuditTable.createTableController({
      initialDocuments: [],
      dashboardGrid: document.getElementById("results-layout"),
      tableBody: document.getElementById("results-table-body"),
      emptyState: document.getElementById("results-empty-state"),
      searchInput: document.getElementById("document-search-input"),
      statusFilter: document.getElementById("document-status-filter"),
      severityFilter: document.getElementById("document-severity-filter"),
      detailPanel: document.getElementById("detail-panel"),
      detailTitle: document.getElementById("detail-title"),
      detailDeleteButton: document.getElementById("detail-delete-button"),
      detailMetadata: document.getElementById("detail-metadata"),
      detailFlags: document.getElementById("detail-flags"),
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

    root.DocAuditUpload.createUploadController({
      dropzone: document.getElementById("upload-dropzone"),
      fileInput: document.getElementById("upload-file-input"),
      browseButton: document.getElementById("upload-browse-button"),
      feedbackNode: document.getElementById("upload-feedback"),
      maxSizeBytes: 5 * 1024 * 1024,
      onUploadSuccess: async function () {
        await loadDocuments(tableController);
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

    updateApiHealth(document.getElementById("api-health-indicator"));
    loadDocuments(tableController).catch(function (error) {
      console.error(error);
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})(typeof globalThis !== "undefined" ? globalThis : this);
