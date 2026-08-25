from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ContaOFX:
    bank_id: str | None = None
    branch_id: str | None = None
    acct_id: str | None = None
    acct_type: str | None = None


@dataclass
class TransacaoOFX:
    dt_posted: str | None = None
    dt_posted_iso: str | None = None
    valor: float | None = None
    tipo: str | None = None          # "Crédito" ou "Débito"
    trn_type: str | None = None      # CREDIT, DEBIT, etc.
    fit_id: str | None = None
    memo: str | None = None


@dataclass
class ExtratoOFX:
    conta: ContaOFX = field(default_factory=ContaOFX)
    transacoes: list[TransacaoOFX] = field(default_factory=list)
    moeda: str | None = None
    dt_inicio: str | None = None
    dt_fim: str | None = None
    saldo_final: float | None = None  # Captura o saldo real consolidado pelo banco

    def to_dict(self) -> dict[str, Any]:
        return {
            "conta": asdict(self.conta),
            "moeda": self.moeda,
            "periodo": {"inicio": self.dt_inicio, "fim": self.dt_fim},
            "transacoes": [asdict(t) for t in self.transacoes],
            "total_transacoes": len(self.transacoes),
            "saldo_final": self.saldo_final,
        }


class OFXParserBR:
    _TAGS_TRANSACAO = ("TRNTYPE", "DTPOSTED", "TRNAMT", "FITID", "MEMO", "CHECKNUM", "REFNUM")

    _TIPO_LABEL = {
        "CREDIT": "Crédito",
        "DEBIT": "Débito",
        "INT": "Juros",
        "DIV": "Dividendo",
        "FEE": "Tarifa",
        "SRVCHG": "Tarifa de serviço",
        "DEP": "Depósito",
        "ATM": "Saque ATM",
        "POS": "Ponto de venda",
        "XFER": "Transferência",
        "CHECK": "Cheque",
        "PAYMENT": "Pagamento",
        "CASH": "Dinheiro",
        "DIRECTDEP": "Depósito direto",
        "DIRECTDEBIT": "Débito direto",
        "REPEATPMT": "Pagamento recorrente",
        "OTHER": "Outro",
    }

    def __init__(self) -> None:
        self._header: dict[str, str] = {}

    def parse_file(self, path: str | Path) -> ExtratoOFX:
        path = Path(path)
        raw = path.read_bytes()
        return self.parse_bytes(raw)

    def parse_bytes(self, raw: bytes) -> ExtratoOFX:
        self._header = self._parse_header(raw)
        text = self._decode_content(raw)
        return self._parse_body(text)

    def parse_string(self, text: str) -> ExtratoOFX:
        return self._parse_body(text)

    def _parse_header(self, raw: bytes) -> dict[str, str]:
        header: dict[str, str] = {}
        try:
            preview = raw[:2048].decode("ascii", errors="replace")
        except Exception:
            preview = raw[:2048].decode("latin-1", errors="replace")

        for line in preview.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("<OFX"):
                break
            if ":" in stripped and not stripped.startswith("<"):
                key, _, value = stripped.partition(":")
                header[key.strip().upper()] = value.strip()
        return header

    def _decode_content(self, raw: bytes) -> str:
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]

        charset_header = self._header.get("CHARSET", "").upper()
        encoding_header = self._header.get("ENCODING", "").upper()

        candidates: list[str] = []
        if charset_header in ("1252", "WIN1252", "WINDOWS-1252"):
            candidates.append("cp1252")
        elif charset_header in ("8859-1", "8859_1", "ISO-8859-1", "LATIN-1", "LATIN1"):
            candidates.append("iso-8859-1")
        elif charset_header in ("65001", "UTF-8", "UTF8"):
            candidates.append("utf-8")

        if encoding_header in ("UTF-8", "UTF8"):
            candidates.append("utf-8")

        candidates.extend(["cp1252", "iso-8859-1", "utf-8", "latin-1"])

        seen: set[str] = set()
        unique_candidates = []
        for enc in candidates:
            if enc not in seen:
                seen.add(enc)
                unique_candidates.append(enc)

        best_text: str | None = None
        best_score = -1

        for enc in unique_candidates:
            try:
                text = raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue

            score = self._encoding_quality_score(text)
            if score > best_score:
                best_score = score
                best_text = text

        if best_text is None:
            best_text = raw.decode("latin-1")

        return best_text

    @staticmethod
    def _encoding_quality_score(text: str) -> int:
        score = len(text)
        score -= text.count("\ufffd") * 50
        score -= len(re.findall(r"Ã[©ªíóúàâêôãõç]", text)) * 30
        score += len(re.findall(r"[áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ]", text)) * 5
        return score

    def _parse_body(self, text: str) -> ExtratoOFX:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        ofx_match = re.search(r"<OFX\b.*?(?:</OFX>|$)", text, re.DOTALL | re.IGNORECASE)
        body = ofx_match.group(0) if ofx_match else text

        extrato = ExtratoOFX()
        extrato.moeda = self._extract_tag(body, "CURDEF")
        extrato.dt_inicio = self._extract_tag(body, "DTSTART")
        extrato.dt_fim = self._extract_tag(body, "DTEND")

        acct_block = self._extract_block(body, "BANKACCTFROM")
        if acct_block:
            extrato.conta = ContaOFX(
                bank_id=self._extract_tag(acct_block, "BANKID"),
                branch_id=self._extract_tag(acct_block, "BRANCHID"),
                acct_id=self._extract_tag(acct_block, "ACCTID"),
                acct_type=self._extract_tag(acct_block, "ACCTTYPE"),
            )

        # Captura do saldo consolidado do arquivo (LEDGERBAL)
        ledger_block = self._extract_block(body, "LEDGERBAL")
        if ledger_block:
            extrato.saldo_final = self._parse_amount(self._extract_tag(ledger_block, "BALAMT"))
        else:
            # Fallback caso a tag venha solta/sem bloco fechado
            balamt_match = re.search(r"<BALAMT\s*>([^<\n\r]*)", body, re.IGNORECASE)
            if balamt_match:
                extrato.saldo_final = self._parse_amount(balamt_match.group(1))

        for trn_block in self._split_blocks(body, "STMTTRN"):
            transacao = self._parse_transacao(trn_block)
            if transacao:
                extrato.transacoes.append(transacao)

        return extrato

    @staticmethod
    def _extract_tag(text: str, tag: str) -> str | None:
        pattern = rf"<{tag}\s*>([^<\n\r]*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        value = match.group(1).strip()
        return value if value else None

    @staticmethod
    def _extract_block(text: str, tag: str) -> str | None:
        pattern_closed = rf"<{tag}\s*>(.*?)</{tag}\s*>"
        match = re.search(pattern_closed, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)

        pattern_open = rf"<{tag}\s*>(.*?)(?=<(?:/{tag}|BANKTRANLIST|LEDGERBAL|AVAILBAL|STMTRS|STMTTRNRS)\b)"
        match = re.search(pattern_open, text, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else None

    @staticmethod
    def _split_blocks(text: str, tag: str) -> list[str]:
        blocks: list[str] = []
        openings = list(re.finditer(rf"<{tag}\s*>", text, re.IGNORECASE))
        for i, opening in enumerate(openings):
            start = opening.end()
            if i + 1 < len(openings):
                end = openings[i + 1].start()
            else:
                rest = text[start:]
                end_match = re.search(
                    r"</STMTTRN\s*>|</BANKTRANLIST\s*>|</BANKMSGSRSV1\s*>|</OFX\s*>",
                    rest,
                    re.IGNORECASE,
                )
                end = start + (end_match.start() if end_match else len(rest))
            blocks.append(text[start:end])
        return blocks

    def _parse_transacao(self, block: str) -> TransacaoOFX | None:
        trn_type_raw = self._extract_tag(block, "TRNTYPE")
        if not trn_type_raw:
            return None

        dt_raw = self._extract_tag(block, "DTPOSTED")
        valor_raw = self._extract_tag(block, "TRNAMT")
        fit_id = self._extract_tag(block, "FITID")
        memo = self._extract_tag(block, "MEMO")

        valor = self._parse_amount(valor_raw)
        tipo_label = self._TIPO_LABEL.get(trn_type_raw.upper(), trn_type_raw)

        return TransacaoOFX(
            dt_posted=dt_raw,
            dt_posted_iso=self._parse_date(dt_raw),
            valor=valor,
            tipo=tipo_label,
            trn_type=trn_type_raw.upper(),
            fit_id=fit_id,
            memo=memo,
        )

    @staticmethod
    def _parse_amount(raw: str | None) -> float | None:
        if raw is None:
            return None
        cleaned = raw.strip()
        cleaned = re.sub(r"\[.*?\]", "", cleaned).strip()
        if "," in cleaned:
            if re.search(r"\.\d{3},", cleaned):
                cleaned = cleaned.replace(".", "")
            cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(raw: str | None) -> str | None:
        if raw is None:
            return None
        cleaned = re.sub(r"\[.*?\]", "", raw.strip())
        digits = re.sub(r"\D", "", cleaned)
        format_slices = (
            ("%Y%m%d%H%M%S", 14),
            ("%Y%m%d%H%M", 12),
            ("%Y%m%d", 8),
        )
        for fmt, size in format_slices:
            if len(digits) < size:
                continue
            try:
                dt = datetime.strptime(digits[:size], fmt)
                return dt.strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                continue
        return None