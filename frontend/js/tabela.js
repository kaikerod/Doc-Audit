(function (root) {
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

  function renderDetail(document, elements) {
    if (!document) {
      if (elements.layout) {
        elements.layout.classList.remove("dashboard-grid--detail-open");
      }
      elements.panel.classList.add("is-hidden");
      return;
    }

    if (elements.layout) {
      elements.layout.classList.add("dashboard-grid--detail-open");
    }
    elements.panel.classList.remove("is-hidden");
    elements.title.textContent = document.nomeArquivo;
    elements.metadata.innerHTML = [
      ["Numero NF", document.numeroNF || "--"],
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
      : '<div class="flag-card"><p>Este documento nao possui anomalias detectadas.</p></div>';
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
            "<td>" +
            '<div class="cell-primary">' +
            "<strong>" +
            root.DocAuditUiLogic.escapeHtml(document.nomeArquivo) +
            "</strong>" +
            '<span class="cell-muted">' +
            root.DocAuditUiLogic.escapeHtml(document.resumo || "Documento monitorado no dashboard.") +
            "</span>" +
            "</div>" +
            "</td>" +
            "<td>" + root.DocAuditUiLogic.escapeHtml(document.numeroNF || "--") + "</td>" +
            "<td>" + root.DocAuditUiLogic.escapeHtml(document.cnpjEmitente || "--") + "</td>" +
            "<td>" + root.DocAuditUiLogic.formatDateBR(document.dataNF) + "</td>" +
            "<td>" + root.DocAuditUiLogic.formatDateBR(document.dataPagamento) + "</td>" +
            "<td>" + root.DocAuditUiLogic.formatCurrencyBRL(document.valor) + "</td>" +
            "<td>" + root.DocAuditUiLogic.escapeHtml(document.aprovador || "--") + "</td>" +
            '<td><span class="' + statusMeta.className + '">' + statusMeta.label + "</span></td>" +
            "<td>" + renderFlags(document.flags) + "</td>" +
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

    function bindEvents() {
      [elements.searchInput, elements.statusFilter, elements.severityFilter].forEach(function (element) {
        element.addEventListener("input", render);
        element.addEventListener("change", render);
      });

      elements.body.addEventListener("click", function (event) {
        var row = event.target.closest("tr[data-document-id]");
        if (!row) {
          return;
        }

        state.selectedDocumentId = row.dataset.documentId;
        render();
      });

      elements.body.addEventListener("keydown", function (event) {
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
    }

    bindEvents();
    render();

    return {
      prependDocuments: prependDocuments,
      render: render,
      setDocuments: setDocuments
    };
  }

  root.DocAuditTable = {
    createTableController: createTableController
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
