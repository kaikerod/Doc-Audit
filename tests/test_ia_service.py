from __future__ import annotations

import json
from unittest.mock import Mock, patch

import httpx
import pytest

from backend.app.config import settings
from backend.app.schemas.documento import DocumentExtractionResult
from backend.app.services.ia_service import (
    OpenRouterTimeoutError,
    build_extraction_prompt,
    extract_document_data,
)


def test_build_extraction_prompt_contains_expected_fields() -> None:
    prompt = build_extraction_prompt("NF 123 emitida para teste")

    assert "numero_nf" in prompt
    assert "cnpj_emitente" in prompt
    assert "confiancas" in prompt
    assert "extraction_failed_fields" in prompt


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_success(mock_post: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "numero_nf": "NF-123",
                            "cnpj_emitente": "12.345.678/0001-99",
                            "cnpj_destinatario": "98.765.432/0001-11",
                            "data_emissao": "2026-04-15",
                            "data_pagamento": "2026-04-16",
                            "valor_total": 199.9,
                            "aprovador": "Maria Silva",
                            "descricao": "Licenca de software",
                            "confiancas": {
                                "numero_nf": 0.99,
                                "cnpj_emitente": 0.98,
                                "cnpj_destinatario": 0.97,
                                "data_emissao": 0.95,
                                "data_pagamento": 0.94,
                                "valor_total": 0.96,
                                "aprovador": 0.91,
                                "descricao": 0.89,
                            },
                            "extraction_failed_fields": [],
                        }
                    )
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    result = extract_document_data("Conteudo do documento fiscal")

    assert isinstance(result, DocumentExtractionResult)
    assert result.numero_nf == "NF-123"
    assert result.cnpj_emitente == "12.345.678/0001-99"
    assert result.aprovador == "Maria Silva"
    assert result.confiancas["numero_nf"] == 0.99
    assert result.extraction_failed_fields == []
    mock_post.assert_called_once()
    assert "Conteudo do documento fiscal" in mock_post.call_args.kwargs["json"]["messages"][1]["content"]


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_timeout(mock_post: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_timeout_retries", 2)
    mock_post.side_effect = httpx.TimeoutException("timed out")

    with pytest.raises(OpenRouterTimeoutError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert "apos 3 tentativas" in str(exc_info.value)
    assert mock_post.call_count == 3
