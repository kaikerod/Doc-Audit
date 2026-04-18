from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any

import httpx

from ..config import settings
from ..schemas.documento import DOCUMENT_EXTRACTION_FIELDS, DocumentExtractionResult


class IAServiceError(Exception):
    """Erro base do servico de integracao com IA."""


class OpenRouterConfigurationError(IAServiceError):
    """Configuracao obrigatoria do OpenRouter nao encontrada."""


class OpenRouterResponseError(IAServiceError):
    """Resposta invalida ou malformada da API do OpenRouter."""


class OpenRouterTimeoutError(IAServiceError):
    """Timeout esgotado apos as retentativas configuradas."""


class OpenRouterUpstreamError(IAServiceError):
    """Erro de comunicacao ou status invalido retornado pelo OpenRouter."""


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

    return f"""
Voce e um extrator de dados de documentos fiscais brasileiros.
Analise o texto abaixo e extraia os campos em formato JSON.
Se um campo nao for encontrado, retorne null para ele.
Retorne APENAS o JSON, sem explicacoes.
Inclua tambem:
- confiancas: objeto com nivel de confianca entre 0 e 1 para cada campo
- extraction_failed_fields: lista com os nomes dos campos que nao puderam ser extraidos

Campos a extrair:
{fields_text}

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


def _extract_message_content(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        return _extract_json_content(content)

    if isinstance(content, dict):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                text_parts.append(text)

        if text_parts:
            return _extract_json_content("\n".join(text_parts))

    raise OpenRouterResponseError("Formato de content inesperado retornado pelo OpenRouter.")


def _build_request_payload(document_text: str) -> dict[str, Any]:
    return {
        "model": settings.openrouter_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "Voce extrai dados estruturados de documentos fiscais brasileiros.",
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


def extract_document_data(document_text: str) -> DocumentExtractionResult:
    if not settings.openrouter_api_key:
        raise OpenRouterConfigurationError("OPENROUTER_API_KEY nao configurada.")

    headers = _build_openrouter_headers()
    payload = _build_request_payload(document_text)
    attempts = settings.openrouter_timeout_retries + 1

    for attempt in range(1, attempts + 1):
        try:
            response = httpx.post(
                settings.openrouter_api_url,
                headers=headers,
                json=payload,
                timeout=settings.openrouter_timeout_seconds,
            )
            response.raise_for_status()
            return _parse_openrouter_response(response.json())
        except httpx.TimeoutException as exc:
            if attempt == attempts:
                raise OpenRouterTimeoutError(
                    f"Timeout ao chamar OpenRouter apos {attempts} tentativas."
                ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            if detail:
                detail = re.sub(r"\s+", " ", detail)
                detail = detail[:300]
                message = (
                    f"OpenRouter retornou status {exc.response.status_code}: {detail}"
                )
            else:
                message = f"OpenRouter retornou status {exc.response.status_code}."
            raise OpenRouterUpstreamError(message) from exc
        except httpx.RequestError as exc:
            raise OpenRouterUpstreamError("Falha ao conectar ao OpenRouter.") from exc

    raise OpenRouterTimeoutError("Timeout ao chamar OpenRouter.")
