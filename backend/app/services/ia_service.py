from __future__ import annotations

import json
import logging
import re
import socket
import time
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..observability import elapsed_ms, log_observability_event, utcnow_iso
from ..schemas.documento import DOCUMENT_EXTRACTION_FIELDS, DocumentExtractionResult
from .openrouter_rate_limit_service import (
    build_openrouter_rate_limit_scope,
    get_openrouter_rate_limit_cooldown,
    record_openrouter_rate_limit_cooldown,
)

logger = logging.getLogger(__name__)

TIMEOUT_PHASE_DETAILS = {
    "connect": "dns_tcp_tls_connect",
    "write": "request_body_write",
    "read": "response_headers_or_body_read",
    "pool": "connection_pool_wait",
    "request": "request_execution",
}


class IAServiceError(Exception):
    """Erro base do servico de integracao com IA."""


class OpenRouterConfigurationError(IAServiceError):
    """Configuracao obrigatoria do OpenRouter nao encontrada."""


class OpenRouterResponseError(IAServiceError):
    """Resposta invalida ou malformada da API do OpenRouter."""


class OpenRouterTimeoutError(IAServiceError):
    """Timeout ocorrido durante uma unica tentativa ao OpenRouter."""

    def __init__(
        self,
        message: str,
        *,
        retry_delay_seconds: float | None = None,
        timeout_phase: str | None = None,
        phase_timeout_seconds: float | None = None,
        timeout_budget_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_delay_seconds = retry_delay_seconds
        self.timeout_phase = timeout_phase
        self.phase_timeout_seconds = phase_timeout_seconds
        self.timeout_budget_seconds = timeout_budget_seconds


class OpenRouterUpstreamError(IAServiceError):
    """Erro de comunicacao ou status invalido retornado pelo OpenRouter."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        rate_limit_scope: str | None = None,
        rate_limit_source: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.rate_limit_scope = rate_limit_scope
        self.rate_limit_source = rate_limit_source


def build_ai_health_check() -> tuple[str, bool, str | None]:
    if not settings.openrouter_api_key.strip():
        return (
            "not_configured",
            False,
            "OPENROUTER_API_KEY nao configurada. Configure a integracao de IA para habilitar uploads.",
        )

    parsed_url = urlparse(settings.openrouter_api_url)
    if not parsed_url.hostname:
        return (
            "misconfigured",
            False,
            "OPENROUTER_API_URL invalida. Revise a configuracao da integracao de IA.",
        )

    port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)
    timeout_seconds = max(1.0, min(settings.openrouter_connect_timeout_seconds, 3.0))

    try:
        with socket.create_connection((parsed_url.hostname, port), timeout=timeout_seconds):
            return ("ok", True, None)
    except OSError:
        return (
            "unreachable",
            False,
            "Falha ao conectar ao OpenRouter. Verifique rede, DNS e firewall do backend.",
        )


def _build_openrouter_headers() -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    if settings.openrouter_referer:
        headers["HTTP-Referer"] = settings.openrouter_referer
    if settings.openrouter_title:
        headers["X-OpenRouter-Title"] = settings.openrouter_title
    return headers


def _build_openrouter_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.openrouter_connect_timeout_seconds,
        write=settings.openrouter_write_timeout_seconds,
        read=settings.openrouter_read_timeout_seconds,
        pool=settings.openrouter_pool_timeout_seconds,
    )


def _build_openrouter_timeout_context() -> dict[str, float]:
    connect_timeout = settings.openrouter_connect_timeout_seconds
    write_timeout = settings.openrouter_write_timeout_seconds
    read_timeout = settings.openrouter_read_timeout_seconds
    pool_timeout = settings.openrouter_pool_timeout_seconds
    return {
        "connect_timeout_seconds": connect_timeout,
        "write_timeout_seconds": write_timeout,
        "read_timeout_seconds": read_timeout,
        "pool_timeout_seconds": pool_timeout,
        "request_timeout_budget_seconds": round(
            connect_timeout + write_timeout + read_timeout + pool_timeout,
            3,
        ),
    }


def _resolve_timeout_phase(exc: httpx.TimeoutException) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect"
    if isinstance(exc, httpx.WriteTimeout):
        return "write"
    if isinstance(exc, httpx.ReadTimeout):
        return "read"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool"
    return "request"


def _resolve_phase_timeout_seconds(timeout_phase: str) -> float | None:
    phase_budgets = {
        "connect": settings.openrouter_connect_timeout_seconds,
        "write": settings.openrouter_write_timeout_seconds,
        "read": settings.openrouter_read_timeout_seconds,
        "pool": settings.openrouter_pool_timeout_seconds,
    }
    return phase_budgets.get(timeout_phase)


def build_extraction_prompt(document_text: str) -> str:
    fields_text = "\n".join(
        [
            "- numero_nf: numero da nota fiscal",
            "- cnpj_emitente: CNPJ de quem emitiu (formato: XX.XXX.XXX/XXXX-XX)",
            "- cnpj_destinatario: CNPJ do destinatario",
            "- data_emissao: data de emissao da NF (formato: YYYY-MM-DD)",
            "- data_pagamento: data de pagamento (formato: YYYY-MM-DD)",
            "- valor_total: valor total em reais (numero decimal)",
            "- aprovador: nome completo do aprovador",
            "- descricao: descricao resumida do produto ou servico",
        ]
    )
    confidence_template = ",\n    ".join(
        f'"{field_name}": 0.0' for field_name in DOCUMENT_EXTRACTION_FIELDS
    )
    failed_fields_template = ", ".join(f'"{field_name}"' for field_name in DOCUMENT_EXTRACTION_FIELDS[:2])
    label_mapping_text = "\n".join(
        [
            "- numero_nf: procure primeiro por NUMERO_DOCUMENTO, NUMERO_NF, NF, NOTA_FISCAL",
            "- cnpj_emitente: procure primeiro por CNPJ_FORNECEDOR, CNPJ_EMITENTE, CNPJ_PRESTADOR",
            "- cnpj_destinatario: procure por CNPJ_DESTINATARIO, CNPJ_CLIENTE, CNPJ_TOMADOR, CNPJ_PAGADOR; se nao existir no TXT, retorne null",
            "- data_emissao: prefira DATA_EMISSAO_NF; se nao existir, use DATA_EMISSAO",
            "- data_pagamento: procure por DATA_PAGAMENTO, PAGO_EM, DATA_QUITACAO",
            "- valor_total: procure por VALOR_TOTAL, VALOR_BRUTO, VALOR_LIQUIDO, nessa ordem; retorne apenas o numero decimal",
            "- aprovador: procure por APROVADO_POR, APROVADOR, AUTORIZADO_POR",
            "- descricao: procure por DESCRICAO_SERVICO, DESCRICAO_PRODUTO, DESCRICAO, HISTORICO, OBJETO",
        ]
    )

    return f"""
Voce e um extrator deterministico de dados de documentos fiscais e financeiros brasileiros.
Sua unica tarefa e localizar campos literais no texto e devolve-los em JSON estruturado.
Nao escreva resumo, analise, classificacao, comentarios, markdown, introducao ou texto fora do JSON.
Se um campo nao for encontrado com seguranca, retorne null para ele.
Nao invente, nao complete com suposicoes e nao use conhecimento externo ao arquivo.
Quando o arquivo estiver em formato CHAVE: VALOR, trate os rotulos explicitos como fonte primaria da extracao.
Inclua tambem:
- confiancas: objeto com nivel de confianca entre 0 e 1 para cada campo
- extraction_failed_fields: lista com os nomes dos campos que nao puderam ser extraidos

Campos a extrair:
{fields_text}

Regras de extracao para o formato de arquivo recebido:
- Os TXTs normalmente usam uma linha por campo, no padrao CHAVE: VALOR.
- Preserve o valor textual de numero_nf como aparece no arquivo, inclusive prefixos como NF-.
- Converta datas para YYYY-MM-DD.
- Converta valores monetarios brasileiros para numero decimal sem R$, sem separador de milhar e com ponto decimal.
- Ignore campos administrativos que nao fazem parte do schema, como HASH_VERIFICACAO, STATUS, BANCO_DESTINO e TIPO_DOCUMENTO.
- Use a confianca mais alta quando houver correspondencia direta de rotulo; reduza a confianca quando houver normalizacao, sinonimo ou ambiguidade.

Mapeamento preferencial de rotulos:
{label_mapping_text}

Formato esperado:
{{
  "numero_nf": "string ou null",
  "cnpj_emitente": "string ou null",
  "cnpj_destinatario": "string ou null",
  "data_emissao": "YYYY-MM-DD ou null",
  "data_pagamento": "YYYY-MM-DD ou null",
  "valor_total": 0.0,
  "aprovador": "string ou null",
  "descricao": "string ou null",
  "confiancas": {{
    {confidence_template}
  }},
  "extraction_failed_fields": [{failed_fields_template}]
}}

Texto do documento:
---
{document_text}
---
""".strip()


def _extract_json_content(content: str) -> dict[str, Any]:
    normalized_content = content.strip()
    if normalized_content.startswith("```"):
        normalized_content = re.sub(r"^```(?:json)?\s*", "", normalized_content)
        normalized_content = re.sub(r"\s*```$", "", normalized_content)

    try:
        return json.loads(normalized_content)
    except json.JSONDecodeError as exc:
        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", normalized_content, flags=re.DOTALL)
        if fenced_match:
            try:
                return json.loads(fenced_match.group(1))
            except json.JSONDecodeError:
                pass

        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", normalized_content):
            try:
                parsed_content, _end = decoder.raw_decode(normalized_content[match.start() :])
            except json.JSONDecodeError:
                continue

            if isinstance(parsed_content, dict):
                return parsed_content

        raise OpenRouterResponseError("OpenRouter retornou JSON invalido.") from exc


def _normalize_confidence_value(raw_value: Any) -> float | None:
    if raw_value is None:
        return None

    if isinstance(raw_value, str):
        normalized_value = raw_value.strip().replace("%", "").replace(",", ".")
        if not normalized_value:
            return None
        try:
            numeric_value = float(normalized_value)
        except ValueError:
            return None
    elif isinstance(raw_value, (int, float)):
        numeric_value = float(raw_value)
    else:
        return None

    if 0 <= numeric_value <= 1:
        return numeric_value
    if 1 < numeric_value <= 100:
        return numeric_value / 100
    return None


def _normalize_decimal_value(raw_value: Any) -> Any:
    if raw_value is None or isinstance(raw_value, (int, float, Decimal)):
        return raw_value
    if not isinstance(raw_value, str):
        return raw_value

    normalized_value = raw_value.strip()
    if not normalized_value:
        return None

    normalized_value = re.sub(r"[^\d,.\-]", "", normalized_value)
    if not normalized_value:
        return None

    if "," in normalized_value and "." in normalized_value:
        if normalized_value.rfind(",") > normalized_value.rfind("."):
            normalized_value = normalized_value.replace(".", "").replace(",", ".")
        else:
            normalized_value = normalized_value.replace(",", "")
    elif "," in normalized_value:
        normalized_value = normalized_value.replace(".", "").replace(",", ".")

    try:
        return str(Decimal(normalized_value))
    except InvalidOperation:
        return raw_value


def _normalize_date_value(raw_value: Any) -> Any:
    if raw_value is None or not isinstance(raw_value, str):
        return raw_value

    normalized_value = raw_value.strip()
    if not normalized_value:
        return None

    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(normalized_value, pattern).date().isoformat()
        except ValueError:
            continue

    return raw_value


def _normalize_failed_fields(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    if isinstance(raw_value, str):
        return [item.strip() for item in re.split(r"[,;]", raw_value) if item.strip()]
    return []


def _normalize_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload)
    normalized_payload["data_emissao"] = _normalize_date_value(payload.get("data_emissao"))
    normalized_payload["data_pagamento"] = _normalize_date_value(payload.get("data_pagamento"))
    normalized_payload["valor_total"] = _normalize_decimal_value(payload.get("valor_total"))
    normalized_payload["extraction_failed_fields"] = _normalize_failed_fields(
        payload.get("extraction_failed_fields")
    )

    raw_confidences = payload.get("confiancas")
    if isinstance(raw_confidences, dict):
        normalized_payload["confiancas"] = {
            field_name: _normalize_confidence_value(raw_confidences.get(field_name))
            for field_name in DOCUMENT_EXTRACTION_FIELDS
        }

    return normalized_payload


def _looks_like_extraction_payload(value: dict[str, Any]) -> bool:
    expected_keys = set(DOCUMENT_EXTRACTION_FIELDS) | {"confiancas", "extraction_failed_fields"}
    return bool(expected_keys.intersection(value))


def _collect_text_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped_value = value.strip()
        return [stripped_value] if stripped_value else []

    if isinstance(value, list):
        text_parts: list[str] = []
        for item in value:
            text_parts.extend(_collect_text_parts(item))
        return text_parts

    if isinstance(value, dict):
        priority_keys = (
            "text",
            "content",
            "value",
            "output_text",
            "output",
            "message",
            "parts",
            "items",
        )
        text_parts: list[str] = []
        for key in priority_keys:
            if key in value:
                text_parts.extend(_collect_text_parts(value[key]))
        return text_parts

    return []


def _extract_message_content(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        return _extract_json_content(content)

    if isinstance(content, dict):
        if _looks_like_extraction_payload(content):
            return content

        text_parts = _collect_text_parts(content)
        if text_parts:
            return _extract_json_content("\n".join(text_parts))

    if isinstance(content, list):
        text_parts = _collect_text_parts(content)
        if text_parts:
            return _extract_json_content("\n".join(text_parts))

    raise OpenRouterResponseError("Formato de content inesperado retornado pelo OpenRouter.")


def _build_request_payload(document_text: str) -> dict[str, Any]:
    return {
        "model": settings.openrouter_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "provider": {
            "require_parameters": True,
        },
        "plugins": [
            {"id": "response-healing"},
        ],
        "messages": [
            {
                "role": "system",
                "content": (
                    "Voce extrai dados estruturados de documentos fiscais brasileiros. "
                    "Responda somente com um objeto JSON valido contendo exatamente as chaves solicitadas. "
                    "Nao gere resumo, analise, explicacao ou markdown."
                ),
            },
            {
                "role": "user",
                "content": build_extraction_prompt(document_text),
            },
        ],
    }


def _parse_openrouter_response(response_json: dict[str, Any]) -> DocumentExtractionResult:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterResponseError("Resposta do OpenRouter nao contem choices validos.") from exc

    parsed_content = _normalize_extraction_payload(_extract_message_content(content))

    try:
        return DocumentExtractionResult.model_validate(parsed_content)
    except Exception as exc:
        raise OpenRouterResponseError("JSON retornado pelo OpenRouter falhou na validacao.") from exc


def _extract_openrouter_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            message = error_payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        if isinstance(error_payload, str) and error_payload.strip():
            return error_payload.strip()

    detail = response.text.strip()
    if detail:
        return re.sub(r"\s+", " ", detail)[:300]

    return f"OpenRouter retornou status {response.status_code}."


def _extract_retry_after_seconds(response: httpx.Response) -> float | None:
    retry_after = response.headers.get("retry-after", "").strip()
    if retry_after:
        try:
            return max(0.0, min(float(retry_after), 5.0))
        except ValueError:
            pass

    return None


def _is_non_retryable_rate_limit_message(message: str) -> bool:
    normalized_message = re.sub(r"\s+", " ", (message or "")).strip().lower()
    if not normalized_message:
        return False

    non_retryable_markers = (
        "free-models-per-day",
        "free models per day",
        "insufficient credits",
        "add 10 credits",
        "add credits",
        "quota exceeded",
        "quota reached",
        "quota exhausted",
        "daily quota",
        "daily limit",
        "monthly quota",
        "monthly limit",
        "billing",
        "payment required",
    )
    return any(marker in normalized_message for marker in non_retryable_markers)


def _build_upstream_user_message(status_code: int, message: str) -> str:
    normalized_message = (message or "").strip()

    if status_code == 429:
        if _is_non_retryable_rate_limit_message(normalized_message):
            return (
                "A cota do modelo configurado na OpenRouter foi esgotada. "
                "Altere OPENROUTER_MODEL para outro modelo ou adicione creditos na conta."
            )
        return (
            "O provedor de IA atingiu o limite de requisicoes no momento. "
            "Aguarde alguns segundos e tente novamente."
        )

    if normalized_message.lower() == "provider returned error":
        return "O provedor de IA retornou um erro temporario. Tente novamente em instantes."

    return normalized_message or f"OpenRouter retornou status {status_code}."


def extract_document_data(
    document_text: str,
    *,
    request_context: dict[str, Any] | None = None,
) -> DocumentExtractionResult:
    if not settings.openrouter_api_key:
        raise OpenRouterConfigurationError("OPENROUTER_API_KEY nao configurada.")

    headers = _build_openrouter_headers()
    payload = _build_request_payload(document_text)
    timeout = _build_openrouter_timeout()
    timeout_context = _build_openrouter_timeout_context()
    current_attempt = int((request_context or {}).get("task_attempt", 1))
    max_attempts = settings.openrouter_timeout_retries + 1
    rate_limit_scope = build_openrouter_rate_limit_scope()
    request_started_at = utcnow_iso()
    request_started = time.perf_counter()
    log_context = {
        **(request_context or {}),
        "model": settings.openrouter_model,
        "document_length": len(document_text),
        "max_attempts": max_attempts,
        "rate_limit_scope": rate_limit_scope,
        **timeout_context,
    }

    log_observability_event(
        logger,
        "openrouter_request_started",
        request_started_at=request_started_at,
        **log_context,
    )

    attempt_started_at = utcnow_iso()
    attempt_started = time.perf_counter()
    log_observability_event(
        logger,
        "openrouter_request_attempt_started",
        attempt=current_attempt,
        attempt_started_at=attempt_started_at,
        **log_context,
    )
    try:
        local_cooldown = get_openrouter_rate_limit_cooldown(rate_limit_scope)
        if local_cooldown is not None:
            deferred_at = utcnow_iso()
            user_message = _build_upstream_user_message(429, "rate limit")
            log_observability_event(
                logger,
                "openrouter_request_deferred_by_rate_limit",
                level=logging.WARNING,
                attempt=current_attempt,
                attempt_started_at=attempt_started_at,
                attempt_completed_at=deferred_at,
                latency_ms=elapsed_ms(attempt_started),
                status_code=429,
                retryable=True,
                retry_after_seconds=local_cooldown.wait_seconds,
                rate_limit_source="local_cooldown",
                rate_limit_backend=local_cooldown.backend,
                **log_context,
            )
            log_observability_event(
                logger,
                "openrouter_request_failed",
                level=logging.ERROR,
                request_started_at=request_started_at,
                request_completed_at=deferred_at,
                total_latency_ms=elapsed_ms(request_started),
                final_attempt=current_attempt,
                status_code=429,
                retry_after_seconds=local_cooldown.wait_seconds,
                rate_limit_source="local_cooldown",
                error_message=user_message,
                **log_context,
            )
            raise OpenRouterUpstreamError(
                user_message,
                status_code=429,
                retryable=True,
                retry_after_seconds=local_cooldown.wait_seconds,
                rate_limit_scope=rate_limit_scope,
                rate_limit_source="local_cooldown",
            )

        response = httpx.post(
            settings.openrouter_api_url,
            headers=headers,
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        completed_at = utcnow_iso()
        log_observability_event(
            logger,
            "openrouter_request_attempt_succeeded",
            attempt=current_attempt,
            attempt_started_at=attempt_started_at,
            attempt_completed_at=completed_at,
            latency_ms=elapsed_ms(attempt_started),
            status_code=getattr(response, "status_code", None),
            **log_context,
        )
        log_observability_event(
            logger,
            "openrouter_request_completed",
            request_started_at=request_started_at,
            request_completed_at=completed_at,
            total_latency_ms=elapsed_ms(request_started),
            final_attempt=current_attempt,
            status_code=getattr(response, "status_code", None),
            **log_context,
        )
        return _parse_openrouter_response(response.json())
    except httpx.TimeoutException as exc:
        timed_out_at = utcnow_iso()
        timeout_phase = _resolve_timeout_phase(exc)
        phase_timeout_seconds = _resolve_phase_timeout_seconds(timeout_phase)
        log_observability_event(
            logger,
            "openrouter_request_attempt_timed_out",
            level=logging.WARNING,
            attempt=current_attempt,
            attempt_started_at=attempt_started_at,
            attempt_completed_at=timed_out_at,
            latency_ms=elapsed_ms(attempt_started),
            timeout_phase=timeout_phase,
            timeout_scope=TIMEOUT_PHASE_DETAILS[timeout_phase],
            phase_timeout_seconds=phase_timeout_seconds,
            exception_class=exc.__class__.__name__,
            error_message=str(exc),
            **log_context,
        )
        log_observability_event(
            logger,
            "openrouter_request_failed",
            level=logging.ERROR,
            request_started_at=request_started_at,
            request_completed_at=timed_out_at,
            total_latency_ms=elapsed_ms(request_started),
            final_attempt=current_attempt,
            timeout_phase=timeout_phase,
            timeout_scope=TIMEOUT_PHASE_DETAILS[timeout_phase],
            phase_timeout_seconds=phase_timeout_seconds,
            exception_class=exc.__class__.__name__,
            error_message=str(exc),
            **log_context,
        )
        raise OpenRouterTimeoutError(
            "Timeout ao chamar OpenRouter.",
            timeout_phase=timeout_phase,
            phase_timeout_seconds=phase_timeout_seconds,
            timeout_budget_seconds=timeout_context["request_timeout_budget_seconds"],
        ) from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        error_message = _extract_openrouter_error_message(exc.response)
        completed_at = utcnow_iso()
        retryable = status_code in {429, 502, 503, 504}
        if status_code == 429 and _is_non_retryable_rate_limit_message(error_message):
            retryable = False
        retry_after_seconds = _extract_retry_after_seconds(exc.response)
        rate_limit_source = None
        rate_limit_backend = None
        if status_code == 429 and retryable:
            cooldown = record_openrouter_rate_limit_cooldown(
                rate_limit_scope,
                retry_after_seconds=retry_after_seconds,
            )
            retry_after_seconds = cooldown.wait_seconds
            rate_limit_source = "upstream_429"
            rate_limit_backend = cooldown.backend
            log_observability_event(
                logger,
                "openrouter_rate_limit_cooldown_recorded",
                level=logging.WARNING,
                attempt=current_attempt,
                attempt_started_at=attempt_started_at,
                attempt_completed_at=completed_at,
                status_code=status_code,
                retry_after_seconds=retry_after_seconds,
                rate_limit_source=rate_limit_source,
                rate_limit_backend=rate_limit_backend,
                **log_context,
            )
        log_observability_event(
            logger,
            "openrouter_request_attempt_failed",
            level=logging.WARNING if retryable else logging.ERROR,
            attempt=current_attempt,
            attempt_started_at=attempt_started_at,
            attempt_completed_at=completed_at,
            latency_ms=elapsed_ms(attempt_started),
            status_code=status_code,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            rate_limit_source=rate_limit_source,
            rate_limit_backend=rate_limit_backend,
            error_message=error_message,
            **log_context,
        )
        message = error_message
        log_observability_event(
            logger,
            "openrouter_request_failed",
            level=logging.ERROR,
            request_started_at=request_started_at,
            request_completed_at=completed_at,
            total_latency_ms=elapsed_ms(request_started),
            final_attempt=current_attempt,
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
            rate_limit_source=rate_limit_source,
            error_message=message,
            **log_context,
        )
        raise OpenRouterUpstreamError(
            _build_upstream_user_message(status_code, message),
            status_code=status_code,
            retryable=retryable,
            retry_after_seconds=retry_after_seconds,
            rate_limit_scope=rate_limit_scope if status_code == 429 else None,
            rate_limit_source=rate_limit_source,
        ) from exc
    except httpx.RequestError as exc:
        completed_at = utcnow_iso()
        log_observability_event(
            logger,
            "openrouter_request_attempt_request_error",
            level=logging.WARNING,
            attempt=current_attempt,
            attempt_started_at=attempt_started_at,
            attempt_completed_at=completed_at,
            latency_ms=elapsed_ms(attempt_started),
            retryable=True,
            exception_class=exc.__class__.__name__,
            error_message=str(exc),
            **log_context,
        )
        log_observability_event(
            logger,
            "openrouter_request_failed",
            level=logging.ERROR,
            request_started_at=request_started_at,
            request_completed_at=completed_at,
            total_latency_ms=elapsed_ms(request_started),
            final_attempt=current_attempt,
            exception_class=exc.__class__.__name__,
            error_message=str(exc),
            **log_context,
        )
        raise OpenRouterUpstreamError(
            "Falha ao conectar ao OpenRouter.",
            status_code=503,
            retryable=True,
        ) from exc
