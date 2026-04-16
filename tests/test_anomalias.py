from __future__ import annotations

from datetime import date

from backend.app.services.anomalia_service import detectar_anomalias


def test_detectar_anomalias_nf_valida_retorna_lista_vazia() -> None:
    documento = {
        "numero_nf": "NF-1001",
        "cnpj_emitente": "11.222.333/0001-81",
        "cnpj_destinatario": "45.723.174/0001-10",
        "data_emissao": "2026-04-15",
        "data_pagamento": "2026-04-16",
        "valor_total": "1500.75",
        "aprovador": "Maria Silva",
    }

    anomalies = detectar_anomalias(
        documento,
        today=date(2026, 4, 16),
        fornecedores_cnpj={"11.222.333/0001-81"},
        aprovadores_autorizados={"Maria Silva"},
    )

    assert anomalies == []


def test_detectar_anomalias_identifica_valor_zero() -> None:
    documento = {
        "numero_nf": "NF-1002",
        "cnpj_emitente": "11.222.333/0001-81",
        "data_emissao": "2026-04-15",
        "data_pagamento": "2026-04-16",
        "valor_total": "0",
        "aprovador": "Maria Silva",
    }

    anomalies = detectar_anomalias(documento, today=date(2026, 4, 16))

    assert len(anomalies) == 1
    assert anomalies[0].codigo == "VALOR_ZERO"
    assert anomalies[0].severidade == "ALTA"


def test_detectar_anomalias_identifica_data_invalida() -> None:
    documento = {
        "numero_nf": "NF-1003",
        "cnpj_emitente": "11.222.333/0001-81",
        "data_emissao": "2026-04-20",
        "data_pagamento": "2026-04-16",
        "valor_total": "500.00",
        "aprovador": "Maria Silva",
    }

    anomalies = detectar_anomalias(documento, today=date(2026, 4, 20))

    assert len(anomalies) == 1
    assert anomalies[0].codigo == "DATA_INV"
    assert anomalies[0].severidade == "CRITICA"
