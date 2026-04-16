(function (root) {
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

  async function loadDocuments(tableController) {
    var payload = await root.DocAuditApi.fetchDocuments();
    tableController.setDocuments(root.DocAuditUiLogic.mapApiDocumentsToViewModels(payload.items));
  }

  function init() {
    var tableController = root.DocAuditTable.createTableController({
      initialDocuments: [],
      dashboardGrid: document.getElementById("dashboard-grid"),
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
      document.getElementById("detail-panel").classList.add("is-hidden");
    });

    updateApiHealth(document.getElementById("api-health-indicator"));
    loadDocuments(tableController).catch(function (error) {
      console.error(error);
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})(typeof globalThis !== "undefined" ? globalThis : this);
