from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


DEFAULT_SEVERITY_BY_CODE = {
    "DUP_NF": "CRITICA",
    "CNPJ_DIV": "ALTA",
    "DATA_INV": "CRITICA",
    "APROV_NR": "ALTA",
    "VALOR_ZERO": "ALTA",
    "NF_FUTURA": "MEDIA",
    "CNPJ_INVALIDO": "ALTA",
    "CAMPO_VAZIO": "CRITICA",
}

REQUIRED_FIELDS = ("numero_nf", "cnpj_emitente", "valor_total", "data_emissao")


@dataclass(frozen=True, slots=True)
class DetectedAnomaly:
    codigo: str
    descricao: str
    severidade: str


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return str(value).strip() or None


def _normalize_cnpj(value: Any) -> str | None:
    raw_value = _normalize_text(value)
    if raw_value is None:
        return None
    digits = "".join(char for char in raw_value if char.isdigit())
    return digits or None


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _is_valid_cnpj(value: str | None) -> bool:
    if value is None:
        return False
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) != 14:
        return False
    if digits == digits[0] * 14:
        return False

    def calculate_digit(base: str) -> str:
        weights = list(range(len(base) - 7, 1, -1)) + list(range(9, 1, -1))
        total = sum(int(digit) * weight for digit, weight in zip(base, weights))
        remainder = total % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first_digit = calculate_digit(digits[:12])
    second_digit = calculate_digit(digits[:12] + first_digit)
    return digits[-2:] == first_digit + second_digit


def detectar_anomalias(
    documento: Mapping[str, Any],
    *,
    existing_invoice_keys: set[tuple[str, str]] | None = None,
    fornecedores_cnpj: set[str] | None = None,
    aprovadores_autorizados: set[str] | None = None,
    today: date | None = None,
) -> list[DetectedAnomaly]:
    """Aplica as regras de negocio do PRD aos dados extraidos."""
    current_day = today or date.today()

    numero_nf = _normalize_text(documento.get("numero_nf"))
    cnpj_emitente_raw = _normalize_text(documento.get("cnpj_emitente"))
    cnpj_emitente = _normalize_cnpj(documento.get("cnpj_emitente"))
    cnpj_destinatario_raw = _normalize_text(documento.get("cnpj_destinatario"))
    cnpj_destinatario = _normalize_cnpj(documento.get("cnpj_destinatario"))
    data_emissao = _parse_date(documento.get("data_emissao"))
    data_pagamento = _parse_date(documento.get("data_pagamento"))
    valor_total = _parse_decimal(documento.get("valor_total"))
    aprovador = _normalize_text(documento.get("aprovador"))

    anomalies: list[DetectedAnomaly] = []
    seen_codes: set[str] = set()

    def add_anomaly(codigo: str, descricao: str) -> None:
        if codigo in seen_codes:
            return
        anomalies.append(
            DetectedAnomaly(
                codigo=codigo,
                descricao=descricao,
                severidade=DEFAULT_SEVERITY_BY_CODE[codigo],
            )
        )
        seen_codes.add(codigo)

    missing_fields: list[str] = []
    if not numero_nf:
        missing_fields.append("numero_nf")
    if not cnpj_emitente_raw:
        missing_fields.append("cnpj_emitente")
    if valor_total is None:
        missing_fields.append("valor_total")
    if data_emissao is None:
        missing_fields.append("data_emissao")
    if missing_fields:
        add_anomaly(
            "CAMPO_VAZIO",
            f"Campos obrigatorios ausentes ou invalidos: {', '.join(missing_fields)}.",
        )

    if valor_total is not None and valor_total <= 0:
        add_anomaly(
            "VALOR_ZERO",
            "Valor total da NF e zero ou negativo.",
        )

    if data_emissao and data_pagamento and data_emissao > data_pagamento:
        add_anomaly(
            "DATA_INV",
            "Data de emissao da NF e posterior a data de pagamento.",
        )

    if data_emissao and data_emissao > current_day:
        add_anomaly(
            "NF_FUTURA",
            "Data de emissao da NF esta no futuro.",
        )

    invalid_cnpj_fields: list[str] = []
    if cnpj_emitente_raw and not _is_valid_cnpj(cnpj_emitente):
        invalid_cnpj_fields.append("cnpj_emitente")
    if cnpj_destinatario_raw and not _is_valid_cnpj(cnpj_destinatario):
        invalid_cnpj_fields.append("cnpj_destinatario")
    if invalid_cnpj_fields:
        add_anomaly(
            "CNPJ_INVALIDO",
            f"CNPJ invalido nos campos: {', '.join(invalid_cnpj_fields)}.",
        )

    if existing_invoice_keys and numero_nf and cnpj_emitente:
        normalized_keys = {(nf, _normalize_cnpj(cnpj) or "") for nf, cnpj in existing_invoice_keys}
        if (numero_nf, cnpj_emitente) in normalized_keys:
            add_anomaly(
                "DUP_NF",
                "Ja existe uma NF com o mesmo numero para o mesmo CNPJ emitente.",
            )

    if fornecedores_cnpj is not None and cnpj_emitente:
        normalized_fornecedores = {_normalize_cnpj(cnpj) or "" for cnpj in fornecedores_cnpj}
        if cnpj_emitente not in normalized_fornecedores:
            add_anomaly(
                "CNPJ_DIV",
                "CNPJ do emitente nao corresponde ao cadastro interno do fornecedor.",
            )

    if aprovadores_autorizados is not None and aprovador:
        normalized_aprovadores = {name.strip().casefold() for name in aprovadores_autorizados}
        if aprovador.casefold() not in normalized_aprovadores:
            add_anomaly(
                "APROV_NR",
                "Aprovador nao reconhecido na lista de aprovadores autorizados.",
            )

    return anomalies
