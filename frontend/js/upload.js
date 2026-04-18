(function (root) {
  function setFeedback(node, message, tone) {
    node.textContent = message;
    node.className = "feedback feedback--" + tone;
  }

  function buildUploadCompletionFeedback(payload) {
    var items = payload && Array.isArray(payload.items) ? payload.items : [];
    var queuedCount = items.filter(function (item) {
      return ["pendente", "processando"].includes(
        String(item && item.status ? item.status : "").trim().toLowerCase()
      );
    }).length;
    var failedCount = items.filter(function (item) {
      return String(item && item.status ? item.status : "").trim().toLowerCase() === "erro";
    }).length;

    if (!items.length) {
      return {
        message: "Upload recebido.",
        tone: "success"
      };
    }

    if (failedCount === 0 && queuedCount === items.length) {
      return {
        message: "Upload recebido. As notas foram enfileiradas para an\u00e1lise.",
        tone: "success"
      };
    }

    if (failedCount === 0) {
      return {
        message: "Upload recebido e processamento iniciado.",
        tone: "success"
      };
    }

    if (failedCount === items.length && queuedCount === 0) {
      return {
        message: "Upload recebido, mas n\u00e3o foi poss\u00edvel enfileirar a an\u00e1lise. Verifique a mesa de auditoria.",
        tone: "error"
      };
    }

    return {
      message: "Upload recebido com falhas parciais de enfileiramento. Verifique a mesa de auditoria.",
      tone: "error"
    };
  }

  function createUploadController(options) {
    var dropzone = options.dropzone;
    var fileInput = options.fileInput;
    var browseButton = options.browseButton;
    var feedbackNode = options.feedbackNode;
    var idleMessage = options.idleMessage || "Nenhum envio em andamento.";
    var onUploadSuccess = options.onUploadSuccess;
    var maxFiles = options.maxFiles || 250;
    var maxSizeBytes = options.maxSizeBytes || (5 * 1024 * 1024);
    var availability = options.initialAvailability || {
      enabled: true,
      message: ""
    };

    function applyAvailability(nextAvailability) {
      availability = nextAvailability || {
        enabled: true,
        message: ""
      };

      var isEnabled = availability.enabled !== false;
      dropzone.classList.toggle("is-disabled", !isEnabled);
      dropzone.setAttribute("aria-disabled", isEnabled ? "false" : "true");
      browseButton.disabled = !isEnabled;
      fileInput.disabled = !isEnabled;

      if (!isEnabled && availability.message) {
        setFeedback(feedbackNode, availability.message, availability.tone || "error");
        return;
      }

      setFeedback(feedbackNode, idleMessage, "neutral");
    }

    async function handleFiles(fileList) {
      var files = Array.from(fileList || []);
      if (!files.length) {
        return;
      }

      if (availability.enabled === false) {
        setFeedback(
          feedbackNode,
          availability.message || "Uploads indisponiveis no momento.",
          "error"
        );
        fileInput.value = "";
        return;
      }

      var batchValidation = root.DocAuditUiLogic.validateUploadBatch(files, maxFiles);
      if (!batchValidation.valid) {
        setFeedback(feedbackNode, batchValidation.reason, "error");
        fileInput.value = "";
        return;
      }

      var invalidFile = files.find(function (file) {
        return !root.DocAuditUiLogic.validateUploadFile(file, maxSizeBytes).valid;
      });

      if (invalidFile) {
        var validation = root.DocAuditUiLogic.validateUploadFile(invalidFile, maxSizeBytes);
        setFeedback(feedbackNode, validation.reason, "error");
        fileInput.value = "";
        return;
      }

      setFeedback(feedbackNode, "Enviando arquivos para o backend...", "busy");

      try {
        var payload = await root.DocAuditApi.uploadTxtFiles(files);
        if (typeof onUploadSuccess === "function") {
          await onUploadSuccess(payload);
        }
        var completionFeedback = buildUploadCompletionFeedback(payload);
        setFeedback(feedbackNode, completionFeedback.message, completionFeedback.tone);
        fileInput.value = "";
      } catch (error) {
        setFeedback(feedbackNode, error.message, "error");
      }
    }

    browseButton.addEventListener("click", function (event) {
      if (availability.enabled === false) {
        setFeedback(
          feedbackNode,
          availability.message || "Uploads indisponiveis no momento.",
          "error"
        );
        return;
      }
      event.stopPropagation();
      fileInput.click();
    });

    fileInput.addEventListener("change", function () {
      handleFiles(fileInput.files);
    });

    dropzone.addEventListener("click", function () {
      if (availability.enabled === false) {
        setFeedback(
          feedbackNode,
          availability.message || "Uploads indisponiveis no momento.",
          "error"
        );
        return;
      }
      fileInput.click();
    });

    dropzone.addEventListener("keydown", function (event) {
      if (availability.enabled === false) {
        setFeedback(
          feedbackNode,
          availability.message || "Uploads indisponiveis no momento.",
          "error"
        );
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });

    ["dragenter", "dragover"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.add("is-dragging");
      });
    });

    ["dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.classList.remove("is-dragging");
      });
    });

    dropzone.addEventListener("drop", function (event) {
      handleFiles(event.dataTransfer.files);
    });

    applyAvailability(availability);

    return {
      setAvailability: applyAvailability
    };
  }

  root.DocAuditUpload = {
    createUploadController: createUploadController
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
