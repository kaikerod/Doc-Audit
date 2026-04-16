(function (root) {
  async function parseJsonSafely(response) {
    try {
      return await response.json();
    } catch (_error) {
      return null;
    }
  }

  async function fetchApiHealth() {
    const response = await fetch("/api/v1/health");
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

    const response = await fetch("/api/v1/uploads", {
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
    const response = await fetch("/api/v1/documentos");
    if (!response.ok) {
      throw new Error("Nao foi possivel carregar os documentos do dashboard.");
    }

    return response.json();
  }

  root.DocAuditApi = {
    fetchDocuments: fetchDocuments,
    fetchApiHealth: fetchApiHealth,
    uploadTxtFiles: uploadTxtFiles
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
