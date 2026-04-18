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

  test("uploadTxtFiles nao dispara POST quando o health bloqueia uploads", async () => {
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
      global.DocAuditApi.uploadTxtFiles([{ name: "nota-fiscal.txt", size: 10 }])
    ).rejects.toThrow("Falha ao conectar ao OpenRouter.");

    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/api/v1/health");
  });

  test("uploadTxtFiles envia o FormData apos health bem-sucedido", async () => {
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
      global.DocAuditApi.uploadTxtFiles([{ name: "nota-fiscal.txt", size: 10 }])
    ).resolves.toEqual({
      items: []
    });

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch.mock.calls[1][0]).toBe("http://127.0.0.1:8000/api/v1/uploads");
    expect(global.fetch.mock.calls[1][1].method).toBe("POST");
  });
});
