describe("DocAudit API", () => {
  beforeEach(() => {
    jest.resetModules();

    global.fetch = jest.fn();
    global.document = {
      querySelector: jest.fn(() => null)
    };
    global.location = {
      protocol: "http:",
      hostname: "127.0.0.1",
      port: "8000",
      origin: "http://127.0.0.1:8000"
    };
    global.FormData = class FormData {
      constructor() {
        this.entries = [];
      }

      append(key, value) {
        this.entries.push([key, value]);
      }
    };

    delete global.DocAuditApi;
    require("../frontend/js/api.js");
  });

  afterEach(() => {
    delete global.fetch;
    delete global.document;
    delete global.location;
    delete global.FormData;
    delete global.DocAuditApi;
  });

  test("uploadFiles nao dispara POST quando o health bloqueia uploads", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        features: {
          uploads_enabled: false
        },
        detail: "Falha ao conectar ao OpenRouter."
      })
    });

    await expect(
      global.DocAuditApi.uploadFiles([{ name: "nota-fiscal.txt", size: 10 }])
    ).rejects.toThrow("Falha ao conectar ao OpenRouter.");

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/api/v1/health");
  });

  test("uploadFiles envia o FormData apos health bem-sucedido", async () => {
    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          features: {
            uploads_enabled: true
          }
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: []
        })
      });

    await expect(
      global.DocAuditApi.uploadFiles([{ name: "nota-fiscal.txt", size: 10 }])
    ).resolves.toEqual({
      items: []
    });

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch.mock.calls[1][0]).toBe("http://127.0.0.1:8000/api/v1/uploads");
    expect(global.fetch.mock.calls[1][1].method).toBe("POST");
  });

  test("fetchDocuments envia limit, offset e filtros na query string", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        total: 3,
        limit: 50,
        offset: 50,
        has_more: true,
        items: []
      })
    });

    await expect(
      global.DocAuditApi.fetchDocuments({
        limit: 50,
        offset: 50,
        query: "NF-2026",
        status: "com_anomalia",
        severity: "CRITICA"
      })
    ).resolves.toEqual({
      total: 3,
      limit: 50,
      offset: 50,
      has_more: true,
      items: []
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls[0][0]).toBe(
      "http://127.0.0.1:8000/api/v1/documentos?limit=50&offset=50&query=NF-2026&status=com_anomalia&severity=CRITICA"
    );
  });

  test("uploadFiles divide a selecao em multiplos POSTs quando o health informa limite menor", async () => {
    const files = [
      { name: "nota-1.txt", size: 10 },
      { name: "nota-2.txt", size: 10 },
      { name: "nota-3.txt", size: 10 },
      { name: "nota-4.txt", size: 10 },
      { name: "nota-5.txt", size: 10 }
    ];

    global.fetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          features: {
            uploads_enabled: true,
            upload_max_files: 2
          }
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [{ id: "upload-1" }, { id: "upload-2" }]
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [{ id: "upload-3" }, { id: "upload-4" }]
        })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [{ id: "upload-5" }]
        })
      });

    await expect(global.DocAuditApi.uploadFiles(files)).resolves.toEqual({
      items: [
        { id: "upload-1" },
        { id: "upload-2" },
        { id: "upload-3" },
        { id: "upload-4" },
        { id: "upload-5" }
      ]
    });

    expect(global.fetch).toHaveBeenCalledTimes(4);
    expect(global.fetch.mock.calls[1][1].body.entries.map((entry) => entry[1].name)).toEqual([
      "nota-1.txt",
      "nota-2.txt"
    ]);
    expect(global.fetch.mock.calls[2][1].body.entries.map((entry) => entry[1].name)).toEqual([
      "nota-3.txt",
      "nota-4.txt"
    ]);
    expect(global.fetch.mock.calls[3][1].body.entries.map((entry) => entry[1].name)).toEqual([
      "nota-5.txt"
    ]);
  });
});
