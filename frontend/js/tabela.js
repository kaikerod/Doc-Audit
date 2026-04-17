(function (root) {
  var DELETE_ICON =
    '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
    '<path d="M9 3h6l1 2h4v2H4V5h4l1-2zm-1 5h8v11a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V8zm2 2v8h2v-8h-2zm4 0v8h2v-8h-2z" fill="currentColor"></path>' +
    "</svg>";

  function renderFlags(flags) {
    if (!flags.length) {
      return '<span class="cell-muted">Sem flags</span>';
    }

    return (
      '<div class="badge-row">' +
      flags
        .map(function (flag) {
          return (
            '<span class="' +
            root.DocAuditUiLogic.getSeverityBadgeClass(flag.severidade) +
            '">' +
            root.DocAuditUiLogic.escapeHtml(flag.codigo) +
            "</span>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function renderDeleteButton(document, className) {
    if (!document.uploadId) {
      return '<span class="cell-muted">--</span>';
    }

    return (
      '<button type="button" class="' +
      className +
      '" data-delete-upload="true" data-upload-id="' +
      root.DocAuditUiLogic.escapeHtml(document.uploadId) +
      '" aria-label="Excluir nota ' +
      root.DocAuditUiLogic.escapeHtml(document.nomeArquivo) +
      '" title="Excluir nota">' +
      DELETE_ICON +
      "</button>"
    );
  }

  function renderCell(label, content, className) {
    var resolvedClassName = className ? ' class="' + className + '"' : "";
    return (
      "<td" +
      resolvedClassName +
      ' data-label="' +
      root.DocAuditUiLogic.escapeHtml(label) +
      '">' +
      content +
      "</td>"
    );
  }

  function renderDetail(document, elements) {
    if (!document) {
      if (elements.layout) {
        elements.layout.classList.remove("results-layout--detail-open");
      }
      elements.panel.classList.add("is-hidden");
      if (elements.deleteButton) {
        elements.deleteButton.hidden = true;
        elements.deleteButton.dataset.uploadId = "";
      }
      return;
    }

    if (elements.layout) {
      elements.layout.classList.add("results-layout--detail-open");
    }
    elements.panel.classList.remove("is-hidden");
    elements.title.textContent = document.nomeArquivo;
    if (elements.deleteButton) {
      elements.deleteButton.hidden = !document.uploadId;
      elements.deleteButton.dataset.uploadId = document.uploadId || "";
      elements.deleteButton.innerHTML = DELETE_ICON + "<span>Excluir nota</span>";
    }
    elements.metadata.innerHTML = [
      ["N\u00famero NF", document.numeroNF || "--"],
      ["CNPJ emitente", document.cnpjEmitente || "--"],
      ["Data NF", root.DocAuditUiLogic.formatDateBR(document.dataNF)],
      ["Pagamento", root.DocAuditUiLogic.formatDateBR(document.dataPagamento)],
      ["Valor", root.DocAuditUiLogic.formatCurrencyBRL(document.valor)],
      ["Aprovador", document.aprovador || "--"],
      ["Status", root.DocAuditUiLogic.getStatusMeta(document.status, document.flags).label]
    ]
      .map(function (entry) {
        return (
          "<div><dt>" +
          root.DocAuditUiLogic.escapeHtml(entry[0]) +
          "</dt><dd>" +
          root.DocAuditUiLogic.escapeHtml(entry[1]) +
          "</dd></div>"
        );
      })
      .join("");

    elements.flags.innerHTML = document.flags.length
      ? document.flags
          .map(function (flag) {
            return (
              '<article class="flag-card">' +
              '<span class="' +
              root.DocAuditUiLogic.getSeverityBadgeClass(flag.severidade) +
              '">' +
              root.DocAuditUiLogic.escapeHtml(flag.codigo + " - " + flag.severidade) +
              "</span>" +
              "<p>" +
              root.DocAuditUiLogic.escapeHtml(flag.descricao) +
              "</p>" +
              "</article>"
            );
          })
          .join("")
      : '<div class="flag-card"><p>Este documento n\u00e3o possui anomalias detectadas.</p></div>';
  }

  function createTableController(options) {
    var state = {
      documents: options.initialDocuments || [],
      selectedDocumentId: null
    };

    var elements = {
      body: options.tableBody,
      emptyState: options.emptyState,
      searchInput: options.searchInput,
      statusFilter: options.statusFilter,
      severityFilter: options.severityFilter,
      layout: options.dashboardGrid,
      stats: options.stats,
      detailPanel: {
        panel: options.detailPanel,
        title: options.detailTitle,
        deleteButton: options.detailDeleteButton,
        metadata: options.detailMetadata,
        flags: options.detailFlags,
        layout: options.dashboardGrid
      }
    };

    function getVisibleDocuments() {
      return root.DocAuditUiLogic.filterDocuments(state.documents, {
        query: elements.searchInput.value,
        status: elements.statusFilter.value,
        severity: elements.severityFilter.value
      });
    }

    function render() {
      var visibleDocuments = getVisibleDocuments();
      var stats = root.DocAuditUiLogic.buildDashboardStats(state.documents);

      elements.stats.total.textContent = stats.total;
      elements.stats.withFlags.textContent = stats.withFlags;
      elements.stats.critical.textContent = stats.critical;
      elements.stats.processing.textContent = stats.processing;

      elements.emptyState.hidden = visibleDocuments.length !== 0;
      elements.body.innerHTML = visibleDocuments
        .map(function (document) {
          var statusMeta = root.DocAuditUiLogic.getStatusMeta(document.status, document.flags);
          var isSelected = document.id === state.selectedDocumentId;
          var rowClassName = isSelected ? ' class="is-selected"' : "";

          return (
            '<tr data-document-id="' +
            root.DocAuditUiLogic.escapeHtml(document.id) +
            '" tabindex="0" aria-selected="' +
            (isSelected ? "true" : "false") +
            '"' +
            rowClassName +
            ">" +
            renderCell(
              "Arquivo",
              '<div class="cell-primary">' +
                "<strong>" +
                root.DocAuditUiLogic.escapeHtml(document.nomeArquivo) +
                "</strong>" +
                '<span class="cell-muted">' +
                root.DocAuditUiLogic.escapeHtml(document.resumo || "Documento monitorado no dashboard.") +
                "</span>" +
              "</div>"
            ) +
            renderCell("NF", root.DocAuditUiLogic.escapeHtml(document.numeroNF || "--")) +
            renderCell("CNPJ emitente", root.DocAuditUiLogic.escapeHtml(document.cnpjEmitente || "--")) +
            renderCell("Data NF", root.DocAuditUiLogic.formatDateBR(document.dataNF)) +
            renderCell("Pagamento", root.DocAuditUiLogic.formatDateBR(document.dataPagamento)) +
            renderCell("Valor", root.DocAuditUiLogic.formatCurrencyBRL(document.valor)) +
            renderCell("Aprovador", root.DocAuditUiLogic.escapeHtml(document.aprovador || "--")) +
            renderCell(
              "Status",
              '<span class="' + statusMeta.className + '">' + statusMeta.label + "</span>"
            ) +
            renderCell("Flags", renderFlags(document.flags)) +
            renderCell(
              "A\u00e7\u00f5es",
              renderDeleteButton(document, "icon-button icon-button--danger"),
              "table-actions-cell"
            ) +
            "</tr>"
          );
        })
        .join("");

      if (!visibleDocuments.length) {
        elements.body.innerHTML = "";
      }

      var selectedDocument = state.documents.find(function (document) {
        return document.id === state.selectedDocumentId;
      });
      renderDetail(selectedDocument, elements.detailPanel);
    }

    function prependDocuments(documents) {
      state.documents = documents.concat(state.documents);
      if (!state.selectedDocumentId && documents.length) {
        state.selectedDocumentId = documents[0].id;
      }
      render();
    }

    function setDocuments(documents) {
      state.documents = Array.isArray(documents) ? documents : [];
      if (
        state.selectedDocumentId &&
        !state.documents.some(function (document) {
          return document.id === state.selectedDocumentId;
        })
      ) {
        state.selectedDocumentId = null;
      }
      render();
    }

    function removeDocumentByUploadId(uploadId) {
      state.documents = state.documents.filter(function (document) {
        return document.uploadId !== uploadId;
      });

      if (
        state.selectedDocumentId &&
        !state.documents.some(function (document) {
          return document.id === state.selectedDocumentId;
        })
      ) {
        state.selectedDocumentId = state.documents.length ? state.documents[0].id : null;
      }

      render();
    }

    function clearSelection() {
      state.selectedDocumentId = null;
      render();
    }

    function triggerDelete(uploadId) {
      if (!uploadId || typeof options.onDeleteUpload !== "function") {
        return;
      }

      var targetDocument = state.documents.find(function (document) {
        return document.uploadId === uploadId;
      });
      if (!targetDocument) {
        return;
      }

      Promise.resolve(options.onDeleteUpload(targetDocument)).catch(function (error) {
        if (root.console && typeof root.console.error === "function") {
          root.console.error(error);
        }

        if (typeof root.alert === "function") {
          root.alert(error && error.message ? error.message : "N\u00e3o foi poss\u00edvel excluir a nota.");
        }
      });
    }

    function bindEvents() {
      [elements.searchInput, elements.statusFilter, elements.severityFilter].forEach(function (element) {
        element.addEventListener("input", render);
        element.addEventListener("change", render);
      });

      elements.body.addEventListener("click", function (event) {
        var deleteButton = event.target.closest("[data-delete-upload]");
        if (deleteButton) {
          event.preventDefault();
          triggerDelete(deleteButton.dataset.uploadId);
          return;
        }

        var row = event.target.closest("tr[data-document-id]");
        if (!row) {
          return;
        }

        state.selectedDocumentId = row.dataset.documentId;
        render();
      });

      elements.body.addEventListener("keydown", function (event) {
        if (event.target.closest("[data-delete-upload]")) {
          return;
        }

        var row = event.target.closest("tr[data-document-id]");
        if (!row) {
          return;
        }

        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          state.selectedDocumentId = row.dataset.documentId;
          render();
        }
      });

      if (elements.detailPanel.deleteButton) {
        elements.detailPanel.deleteButton.addEventListener("click", function () {
          triggerDelete(this.dataset.uploadId);
        });
      }
    }

    bindEvents();
    render();

    return {
      clearSelection: clearSelection,
      prependDocuments: prependDocuments,
      removeDocumentByUploadId: removeDocumentByUploadId,
      render: render,
      setDocuments: setDocuments
    };
  }

  root.DocAuditTable = {
    createTableController: createTableController
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
