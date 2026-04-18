from __future__ import annotations

import json
from decimal import Decimal
from unittest.mock import Mock, patch

import httpx
import pytest

from backend.app.config import settings
from backend.app.schemas.documento import DocumentExtractionResult
from backend.app.services.ia_service import (
    OpenRouterUpstreamError,
    OpenRouterTimeoutError,
    build_ai_health_check,
    build_extraction_prompt,
    extract_document_data,
)
from backend.app.services.openrouter_rate_limit_service import (
    build_openrouter_rate_limit_scope,
    record_openrouter_rate_limit_cooldown,
)


def test_build_extraction_prompt_contains_expected_fields() -> None:
    prompt = build_extraction_prompt("NF 123 emitida para teste")

    assert "numero_nf" in prompt
    assert "cnpj_emitente" in prompt
    assert "confiancas" in prompt
    assert "extraction_failed_fields" in prompt
    assert "CHAVE: VALOR" in prompt
    assert "NUMERO_DOCUMENTO" in prompt
    assert "DATA_EMISSAO_NF" in prompt
    assert "VALOR_BRUTO" in prompt
    assert "Nao escreva resumo, analise" in prompt


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
def test_extract_document_data_uses_gemma_defaults_and_openrouter_headers(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_model", "mistralai/ministral-3b-2512")
    monkeypatch.setattr(settings, "openrouter_referer", "https://docaudit.local")
    monkeypatch.setattr(settings, "openrouter_title", "DocAudit")
    monkeypatch.setattr(settings, "openrouter_connect_timeout_seconds", 2.5)
    monkeypatch.setattr(settings, "openrouter_write_timeout_seconds", 3.5)
    monkeypatch.setattr(settings, "openrouter_read_timeout_seconds", 18.0)
    monkeypatch.setattr(settings, "openrouter_pool_timeout_seconds", 1.5)

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "numero_nf": "NF-456",
                                    "cnpj_emitente": "12.345.678/0001-99",
                                    "cnpj_destinatario": "98.765.432/0001-11",
                                    "data_emissao": "2026-04-15",
                                    "data_pagamento": "2026-04-16",
                                    "valor_total": 300.5,
                                    "aprovador": "Joao Souza",
                                    "descricao": "Servico de consultoria",
                                    "confiancas": {
                                        "numero_nf": 0.99,
                                        "cnpj_emitente": 0.98,
                                        "cnpj_destinatario": 0.97,
                                        "data_emissao": 0.96,
                                        "data_pagamento": 0.95,
                                        "valor_total": 0.94,
                                        "aprovador": 0.93,
                                        "descricao": 0.92,
                                    },
                                    "extraction_failed_fields": [],
                                }
                            ),
                        }
                    ]
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    result = extract_document_data("Conteudo do documento fiscal")

    assert isinstance(result, DocumentExtractionResult)
    assert result.numero_nf == "NF-456"
    assert result.aprovador == "Joao Souza"
    assert mock_post.call_args.kwargs["json"]["model"] == "mistralai/ministral-3b-2512"
    assert mock_post.call_args.kwargs["json"]["provider"] == {"require_parameters": True}
    assert mock_post.call_args.kwargs["json"]["plugins"] == [{"id": "response-healing"}]
    assert mock_post.call_args.kwargs["headers"]["HTTP-Referer"] == "https://docaudit.local"
    assert mock_post.call_args.kwargs["headers"]["X-OpenRouter-Title"] == "DocAudit"
    timeout = mock_post.call_args.kwargs["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == 2.5
    assert timeout.write == 3.5
    assert timeout.read == 18.0
    assert timeout.pool == 1.5


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_timeout(mock_post: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_timeout_retries", 2)
    monkeypatch.setattr(settings, "openrouter_connect_timeout_seconds", 4.0)
    monkeypatch.setattr(settings, "openrouter_write_timeout_seconds", 5.0)
    monkeypatch.setattr(settings, "openrouter_read_timeout_seconds", 17.0)
    monkeypatch.setattr(settings, "openrouter_pool_timeout_seconds", 3.0)
    mock_post.side_effect = httpx.ReadTimeout("timed out")

    with pytest.raises(OpenRouterTimeoutError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert str(exc_info.value) == "Timeout ao chamar OpenRouter."
    assert exc_info.value.timeout_phase == "read"
    assert exc_info.value.phase_timeout_seconds == 17.0
    assert exc_info.value.timeout_budget_seconds == 29.0
    assert mock_post.call_count == 1


@patch("backend.app.services.ia_service.socket.create_connection")
def test_build_ai_health_check_uses_connect_timeout_budget(
    mock_create_connection: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    mock_create_connection.return_value = connection

    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_api_url", "https://openrouter.ai/api/v1/chat/completions")
    monkeypatch.setattr(settings, "openrouter_connect_timeout_seconds", 1.7)
    monkeypatch.setattr(settings, "openrouter_read_timeout_seconds", 29.0)

    assert build_ai_health_check() == ("ok", True, None)
    assert mock_create_connection.call_args.kwargs["timeout"] == 1.7


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_emits_observability_logs(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    mock_response = Mock()
    mock_response.status_code = 200
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
    caplog.set_level("INFO", logger="backend.app.services.ia_service")

    extract_document_data(
        "Conteudo do documento fiscal",
        request_context={"upload_id": "upload-1", "task_id": "task-1"},
    )

    messages = [record.message for record in caplog.records]
    assert any('"event": "openrouter_request_started"' in message for message in messages)
    assert any('"event": "openrouter_request_completed"' in message for message in messages)
    assert any('"upload_id": "upload-1"' in message for message in messages)
    assert any('"task_id": "task-1"' in message for message in messages)


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_tolerates_text_around_json(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": (
                        "Segue o JSON solicitado:\n```json\n"
                        '{"numero_nf":"NF-789","cnpj_emitente":"12.345.678/0001-99",'
                        '"cnpj_destinatario":"98.765.432/0001-11","data_emissao":"2026-04-15",'
                        '"data_pagamento":"2026-04-16","valor_total":"199.90",'
                        '"aprovador":"Maria Silva","descricao":"Servico recorrente",'
                        '"confiancas":{"numero_nf":0.99,"cnpj_emitente":0.98,"cnpj_destinatario":0.97,'
                        '"data_emissao":0.96,"data_pagamento":0.95,"valor_total":0.94,'
                        '"aprovador":0.93,"descricao":0.92},"extraction_failed_fields":[]}\n```'
                    )
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    result = extract_document_data("Conteudo fiscal com texto misto")

    assert result.numero_nf == "NF-789"
    assert result.valor_total == Decimal("199.90")


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_accepts_output_text_blocks(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": [
                        {
                            "type": "reasoning",
                            "text": "Analisando o documento...",
                        },
                        {
                            "type": "output_text",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "numero_nf": "NF-850",
                                            "cnpj_emitente": "12.345.678/0001-99",
                                            "cnpj_destinatario": "98.765.432/0001-11",
                                            "data_emissao": "2026-04-15",
                                            "data_pagamento": "2026-04-16",
                                            "valor_total": "250.00",
                                            "aprovador": "Maria Silva",
                                            "descricao": "Servico recorrente",
                                            "confiancas": {
                                                "numero_nf": 0.99,
                                                "cnpj_emitente": 0.98,
                                                "cnpj_destinatario": 0.97,
                                                "data_emissao": 0.96,
                                                "data_pagamento": 0.95,
                                                "valor_total": 0.94,
                                                "aprovador": 0.93,
                                                "descricao": 0.92,
                                            },
                                            "extraction_failed_fields": [],
                                        }
                                    ),
                                }
                            ],
                        },
                    ]
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    result = extract_document_data("Conteudo fiscal em blocos output_text")

    assert result.numero_nf == "NF-850"
    assert result.valor_total == Decimal("250.00")


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_normalizes_brazilian_formats(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": {
                        "numero_nf": "NF-900",
                        "cnpj_emitente": "12.345.678/0001-99",
                        "cnpj_destinatario": "98.765.432/0001-11",
                        "data_emissao": "15/04/2026",
                        "data_pagamento": "16/04/2026",
                        "valor_total": "R$ 1.234,56",
                        "aprovador": "Joao Souza",
                        "descricao": "Consultoria",
                        "confiancas": {
                            "numero_nf": "99%",
                            "cnpj_emitente": 98,
                            "cnpj_destinatario": "0.97",
                            "data_emissao": 96,
                            "data_pagamento": 95,
                            "valor_total": "94%",
                            "aprovador": 0.93,
                            "descricao": 92,
                        },
                        "extraction_failed_fields": "descricao, aprovador",
                    }
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    result = extract_document_data("Conteudo fiscal em formato brasileiro")

    assert result.data_emissao.isoformat() == "2026-04-15"
    assert result.data_pagamento.isoformat() == "2026-04-16"
    assert result.valor_total == Decimal("1234.56")
    assert result.confiancas["numero_nf"] == 0.99
    assert result.confiancas["cnpj_emitente"] == 0.98
    assert result.extraction_failed_fields == ["descricao", "aprovador"]


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_wraps_openrouter_http_errors(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_rate_limit_cooldown_seconds", 2.0)

    request = httpx.Request("POST", settings.openrouter_api_url)
    response = httpx.Response(429, request=request, text='{"error":"rate limit"}')

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limit",
        request=request,
        response=response,
    )
    mock_post.return_value = mock_response

    with pytest.raises(OpenRouterUpstreamError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert (
        str(exc_info.value)
        == "O provedor de IA atingiu o limite de requisicoes no momento. Aguarde alguns segundos e tente novamente."
    )
    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds == 2.0
    assert exc_info.value.rate_limit_source == "upstream_429"


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_marks_transient_openrouter_http_errors_as_retryable(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_timeout_retries", 2)

    request = httpx.Request("POST", settings.openrouter_api_url)
    retry_response = httpx.Response(502, request=request, text='{"error":{"message":"bad gateway"}}')

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad gateway",
        request=request,
        response=retry_response,
    )
    mock_post.return_value = mock_response

    with pytest.raises(OpenRouterUpstreamError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert str(exc_info.value) == "bad gateway"
    assert exc_info.value.status_code == 502
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds is None
    assert mock_post.call_count == 1


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_exposes_retry_after_for_rate_limit(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_timeout_retries", 2)

    request = httpx.Request("POST", settings.openrouter_api_url)
    retry_response = httpx.Response(
        429,
        request=request,
        headers={"Retry-After": "1"},
        text='{"error":"Provider returned error"}',
    )

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limit",
        request=request,
        response=retry_response,
    )
    mock_post.return_value = mock_response

    with pytest.raises(OpenRouterUpstreamError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert (
        str(exc_info.value)
        == "O provedor de IA atingiu o limite de requisicoes no momento. Aguarde alguns segundos e tente novamente."
    )
    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds == 1.0
    assert exc_info.value.rate_limit_source == "upstream_429"
    assert mock_post.call_count == 1


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_marks_quota_exhaustion_429_as_non_retryable(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_rate_limit_cooldown_seconds", 2.0)

    request = httpx.Request("POST", settings.openrouter_api_url)
    quota_response = httpx.Response(
        429,
        request=request,
        text='{"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day"}}',
    )

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "quota exhausted",
        request=request,
        response=quota_response,
    )
    mock_post.return_value = mock_response

    with pytest.raises(OpenRouterUpstreamError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert (
        str(exc_info.value)
        == "A cota do modelo configurado na OpenRouter foi esgotada. Altere OPENROUTER_MODEL para outro modelo ou adicione creditos na conta."
    )
    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is False
    assert exc_info.value.retry_after_seconds is None
    assert exc_info.value.rate_limit_source is None
    assert mock_post.call_count == 1


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_short_circuits_while_local_rate_limit_cooldown_is_active(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_rate_limit_cooldown_seconds", 2.0)
    monkeypatch.setattr(
        "backend.app.services.openrouter_rate_limit_service._get_redis_client",
        lambda: None,
    )

    cooldown = record_openrouter_rate_limit_cooldown(
        build_openrouter_rate_limit_scope(),
        retry_after_seconds=2.0,
    )

    with pytest.raises(OpenRouterUpstreamError) as exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert exc_info.value.status_code == 429
    assert exc_info.value.retryable is True
    assert exc_info.value.retry_after_seconds <= cooldown.wait_seconds
    assert exc_info.value.rate_limit_source == "local_cooldown"
    mock_post.assert_not_called()


@patch("backend.app.services.ia_service.httpx.post")
def test_extract_document_data_reuses_shared_cooldown_after_upstream_429(
    mock_post: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "openrouter_rate_limit_cooldown_seconds", 2.0)
    monkeypatch.setattr(
        "backend.app.services.openrouter_rate_limit_service._get_redis_client",
        lambda: None,
    )

    request = httpx.Request("POST", settings.openrouter_api_url)
    retry_response = httpx.Response(429, request=request, text='{"error":"rate limit"}')

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "rate limit",
        request=request,
        response=retry_response,
    )
    mock_post.return_value = mock_response

    with pytest.raises(OpenRouterUpstreamError) as first_exc_info:
        extract_document_data("Conteudo do documento fiscal")

    with pytest.raises(OpenRouterUpstreamError) as second_exc_info:
        extract_document_data("Conteudo do documento fiscal")

    assert first_exc_info.value.rate_limit_source == "upstream_429"
    assert first_exc_info.value.retry_after_seconds == 2.0
    assert second_exc_info.value.rate_limit_source == "local_cooldown"
    assert second_exc_info.value.retry_after_seconds > 0
    assert mock_post.call_count == 1
