(function (root) {
  function setFeedback(node, message, tone) {
    node.textContent = message;
    node.className = "feedback feedback--" + tone;
  }

  function createUploadController(options) {
    var dropzone = options.dropzone;
    var fileInput = options.fileInput;
    var browseButton = options.browseButton;
    var feedbackNode = options.feedbackNode;
    var onUploadsCreated = options.onUploadsCreated;
    var maxSizeBytes = options.maxSizeBytes || (5 * 1024 * 1024);

    async function handleFiles(fileList) {
      var files = Array.from(fileList || []);
      if (!files.length) {
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
        var mappedDocuments = root.DocAuditUiLogic.mapUploadItemsToDocuments(payload.items);
        onUploadsCreated(mappedDocuments);
        setFeedback(feedbackNode, "Upload concluido. Processamento em andamento.", "success");
        fileInput.value = "";
      } catch (error) {
        setFeedback(feedbackNode, error.message, "error");
      }
    }

    browseButton.addEventListener("click", function (event) {
      event.stopPropagation();
      fileInput.click();
    });

    fileInput.addEventListener("change", function () {
      handleFiles(fileInput.files);
    });

    dropzone.addEventListener("click", function () {
      fileInput.click();
    });

    dropzone.addEventListener("keydown", function (event) {
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
  }

  root.DocAuditUpload = {
    createUploadController: createUploadController
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
