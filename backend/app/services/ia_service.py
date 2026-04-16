from __future__ import annotations

import json
import re
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
        raise OpenRouterResponseError("OpenRouter retornou JSON invalido.") from exc


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

    if isinstance(content, str):
        parsed_content = _extract_json_content(content)
    elif isinstance(content, dict):
        parsed_content = content
    else:
        raise OpenRouterResponseError("Formato de content inesperado retornado pelo OpenRouter.")

    try:
        return DocumentExtractionResult.model_validate(parsed_content)
    except Exception as exc:
        raise OpenRouterResponseError("JSON retornado pelo OpenRouter falhou na validacao.") from exc


def extract_document_data(document_text: str) -> DocumentExtractionResult:
    if not settings.openrouter_api_key:
        raise OpenRouterConfigurationError("OPENROUTER_API_KEY nao configurada.")

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
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

    raise OpenRouterTimeoutError("Timeout ao chamar OpenRouter.")
