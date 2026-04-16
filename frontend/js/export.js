(function (root) {
  function setFeedback(node, message, tone) {
    node.textContent = message;
    node.className = "feedback feedback--" + tone + " table-panel__feedback";
  }

  function downloadFile(blob, filename) {
    var objectUrl = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.hidden = true;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () {
      URL.revokeObjectURL(objectUrl);
    }, 0);
  }

  function createExportController(options) {
    var button = options.button;
    var formatSelect = options.formatSelect;
    var anomaliesOnly = options.anomaliesOnly;
    var feedbackNode = options.feedbackNode;
    var defaultLabel = (button.textContent || "Exportar").trim();

    async function handleExport() {
      var format = root.DocAuditUiLogic.normalizeKeyword(formatSelect.value) === "excel" ? "excel" : "csv";
      var formatLabel = format === "excel" ? "Excel" : "CSV";

      button.disabled = true;
      formatSelect.disabled = true;
      anomaliesOnly.disabled = true;
      button.textContent = "Exportando...";
      setFeedback(feedbackNode, "Preparando arquivo " + formatLabel + "...", "busy");

      try {
        var exportFile = await root.DocAuditApi.fetchDocumentExport({
          format: format,
          onlyAnomalies: anomaliesOnly.checked
        });
        downloadFile(exportFile.blob, exportFile.filename);
        setFeedback(feedbackNode, "Download " + formatLabel + " iniciado.", "success");
      } catch (error) {
        setFeedback(feedbackNode, error.message, "error");
      } finally {
        button.disabled = false;
        formatSelect.disabled = false;
        anomaliesOnly.disabled = false;
        button.textContent = defaultLabel;
      }
    }

    button.addEventListener("click", handleExport);
  }

  root.DocAuditExport = {
    createExportController: createExportController
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
