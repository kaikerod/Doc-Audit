(function (root) {
  var API_PREFIX = "/api/v1";

  async function parseJsonSafely(response) {
    try {
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  function parseAttachmentFilename(contentDisposition, fallbackFilename) {
    if (!contentDisposition) {
      return fallbackFilename;
    }

    var utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match && utf8Match[1]) {
      return decodeURIComponent(utf8Match[1]);
    }

    var quotedMatch = contentDisposition.match(/filename="([^"]+)"/i);
    if (quotedMatch && quotedMatch[1]) {
      return quotedMatch[1];
    }

    var plainMatch = contentDisposition.match(/filename=([^;]+)/i);
    if (plainMatch && plainMatch[1]) {
      return plainMatch[1].trim();
    }

    return fallbackFilename;
  }

  function normalizeBaseUrl(baseUrl) {
    return String(baseUrl || "").replace(/\/+$/, "");
  }

  function getConfiguredApiBaseUrl() {
    var metaTag = document.querySelector('meta[name="docaudit-api-base-url"]');
    if (metaTag && metaTag.content) {
      return normalizeBaseUrl(metaTag.content);
    }

    if (typeof root.DOC_AUDIT_API_BASE_URL === "string" && root.DOC_AUDIT_API_BASE_URL.trim()) {
      return normalizeBaseUrl(root.DOC_AUDIT_API_BASE_URL);
    }

    return "";
  }

  function resolveApiBaseUrl() {
    var configuredBaseUrl = getConfiguredApiBaseUrl();
    if (configuredBaseUrl) {
      return configuredBaseUrl;
    }

    if (root.location.protocol === "file:") {
      return "http://127.0.0.1:8000";
    }

    if (
      ["localhost", "127.0.0.1"].includes(root.location.hostname) &&
      root.location.port &&
      root.location.port !== "8000"
    ) {
      return root.location.protocol + "//" + root.location.hostname + ":8000";
    }

    return root.location.origin;
  }

  function buildApiUrl(path) {
    return resolveApiBaseUrl() + path;
  }

  async function fetchApiHealth() {
    const response = await fetch(buildApiUrl(API_PREFIX + "/health"));
    if (!response.ok) {
      throw new Error("Nao foi possivel consultar o health check da API.");
    }

    return response.json();
  }

  async function uploadTxtFiles(files) {
    const formData = new FormData();
    files.forEach(function (file) {
      formData.append("files", file);
    });

    const response = await fetch(buildApiUrl(API_PREFIX + "/uploads"), {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      const payload = await parseJsonSafely(response);
      throw new Error(payload && payload.detail ? payload.detail : "Falha ao enviar os arquivos.");
    }

    return response.json();
  }

  async function fetchDocuments() {
    const response = await fetch(buildApiUrl(API_PREFIX + "/documentos"));
    if (!response.ok) {
      throw new Error("Nao foi possivel carregar os documentos do dashboard.");
    }

    return response.json();
  }

  async function fetchDocumentExport(options) {
    var safeOptions = options || {};
    var format = root.DocAuditUiLogic.normalizeKeyword(safeOptions.format) === "excel" ? "excel" : "csv";
    var response = await fetch(
      buildApiUrl(root.DocAuditUiLogic.buildExportPath({
        format: format,
        onlyAnomalies: safeOptions.onlyAnomalies
      }))
    );

    if (!response.ok) {
      const payload = await parseJsonSafely(response);
      throw new Error(payload && payload.detail ? payload.detail : "Nao foi possivel exportar os documentos.");
    }

    return {
      blob: await response.blob(),
      filename: parseAttachmentFilename(
        response.headers.get("content-disposition"),
        format === "excel" ? "docaudit_exportacao.xlsx" : "docaudit_exportacao.csv"
      )
    };
  }

  root.DocAuditApi = {
    fetchDocumentExport: fetchDocumentExport,
    fetchDocuments: fetchDocuments,
    fetchApiHealth: fetchApiHealth,
    resolveApiBaseUrl: resolveApiBaseUrl,
    uploadTxtFiles: uploadTxtFiles
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
