"""Parser de arquivos OFX (Open Financial Exchange) com foco em bancos brasileiros.

Suporta as duas sintaxes do formato:

* OFX 1.x (SGML) - tags de valor sem fechamento, cabecalho `CHAVE:VALOR`;
* OFX 2.x (XML)  - tags fechadas, declaracao `<?xml ...?>` / `<?OFX ...?>`.

O documento inteiro e lido em uma unica passagem (um `finditer` sobre o texto),
montando uma arvore de tags. Isso e bem mais rapido do que varrer o arquivo com
uma expressao regular por campo, e evita falhas em historicos que contenham
caracteres especiais.

Uso basico::

    from ofx_parser import OFXParserBR

    extrato = OFXParserBR().parse_file("extrato.ofx")
    for t in extrato.transacoes:
        print(t.dt_posted_iso, t.valor, t.descricao)
"""

from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "BANCOS_BR",
    "ContaOFX",
    "TransacaoOFX",
    "ExtratoOFX",
    "OFXParserBR",
    "nome_banco",
]


# ---------------------------------------------------------------------------
# Tabela de bancos (codigo COMPE). As chaves ficam sem zeros a esquerda; a
# consulta e feita por `nome_banco()`, que normaliza o codigo recebido.
# ---------------------------------------------------------------------------
BANCOS_BR: dict[str, str] = {
    "1": "Banco do Brasil",
    "3": "Banco da Amazônia",
    "4": "Banco do Nordeste",
    "21": "Banestes",
    "25": "Banco Alfa",
    "33": "Santander",
    "36": "Banco Bradesco BBI",
    "37": "Banpará",
    "41": "Banrisul",
    "47": "Banese",
    "62": "Hipercard",
    "70": "BRB",
    "74": "Safra",
    "77": "Banco Inter",
    "84": "Uniprime Norte do Paraná",
    "85": "Ailos / Cecred",
    "89": "Credisan",
    "91": "Unicred Central RS",
    "94": "Banco Finaxis",
    "97": "Credisis",
    "99": "Uniprime Central",
    "104": "Caixa Econômica Federal",
    "107": "Banco Bocom BBM",
    "121": "Agibank",
    "133": "Cresol",
    "136": "Unicred",
    "197": "Stone",
    "208": "BTG Pactual",
    "212": "Banco Original",
    "213": "Banco Arbi",
    "218": "BS2",
    "222": "Banco Credit Agricole",
    "224": "Banco Fibra",
    "233": "Banco Cifra",
    "237": "Bradesco",
    "246": "Banco ABC Brasil",
    "254": "Paraná Banco",
    "260": "Nubank",
    "265": "Banco Fator",
    "274": "Money Plus",
    "290": "PagBank / PagSeguro",
    "301": "BPP / Dock",
    "318": "Banco BMG",
    "320": "China Construction Bank",
    "323": "Mercado Pago",
    "329": "QI Sociedade de Crédito",
    "332": "Acesso Soluções de Pagamento",
    "335": "Banco Digio",
    "336": "C6 Bank",
    "341": "Itaú Unibanco",
    "348": "Banco XP",
    "364": "Gerencianet / Efi",
    "376": "J.P. Morgan",
    "380": "PicPay",
    "383": "Banco Ebanx",
    "389": "Banco Mercantil do Brasil",
    "394": "Banco Bradesco Financiamentos",
    "399": "Kirton Bank",
    "403": "Cora",
    "412": "Banco Capital",
    "422": "Banco Safra",
    "450": "Fitbank",
    "461": "Asaas",
    "479": "Banco ItaúBank",
    "487": "Deutsche Bank",
    "505": "Banco Credit Suisse",
    "600": "Banco Luso Brasileiro",
    "604": "Banco Industrial do Brasil",
    "610": "Banco VR",
    "611": "Banco Paulista",
    "612": "Banco Guanabara",
    "613": "Omni Banco",
    "623": "Banco Pan",
    "626": "Banco C6 Consignado",
    "630": "Banco Smartbank",
    "633": "Banco Rendimento",
    "634": "Banco Triângulo",
    "637": "Banco Sofisa",
    "643": "Banco Pine",
    "652": "Itaú Unibanco Holding",
    "653": "Banco Voiter",
    "654": "Banco Digimais",
    "655": "Neon / Votorantim",
    "707": "Banco Daycoval",
    "712": "Banco Ourinvest",
    "739": "Banco Cetelem",
    "741": "Banco Ribeirão Preto",
    "745": "Citibank",
    "746": "Banco Modal",
    "747": "Rabobank",
    "748": "Sicredi",
    "751": "Scotiabank Brasil",
    "752": "BNP Paribas Brasil",
    "755": "Bank of America Merrill Lynch",
    "756": "Sicoob",
    "757": "Banco KEB Hana",
}


def nome_banco(bank_id: str | None) -> str | None:
    """Retorna o nome da instituicao a partir do codigo COMPE (com ou sem zeros)."""
    if not bank_id:
        return None
    codigo = re.sub(r"\D", "", str(bank_id))
    if not codigo:
        return None
    return BANCOS_BR.get(codigo.lstrip("0") or "0")


# ---------------------------------------------------------------------------
# Modelos
# ---------------------------------------------------------------------------
@dataclass
class ContaOFX:
    bank_id: str | None = None
    branch_id: str | None = None
    acct_id: str | None = None
    acct_type: str | None = None
    banco_nome: str | None = None

    @property
    def descricao(self) -> str:
        if self.banco_nome and self.bank_id:
            return f"{self.banco_nome} ({self.bank_id})"
        if self.banco_nome or self.bank_id:
            return self.banco_nome or self.bank_id  # type: ignore[return-value]
        # cartoes costumam vir sem BANKID; ao menos identifica o produto
        return self.tipo_descricao or "Não informado"

    @property
    def tipo_descricao(self) -> str | None:
        return {
            "CHECKING": "Conta corrente",
            "SAVINGS": "Poupança",
            "MONEYMRKT": "Conta investimento",
            "CREDITLINE": "Crédito rotativo",
            "CREDITCARD": "Cartão de crédito",
        }.get((self.acct_type or "").upper())


@dataclass
class TransacaoOFX:
    dt_posted: str | None = None
    dt_posted_iso: str | None = None
    valor: float | None = None
    tipo: str | None = None           # rotulo em portugues: "Crédito", "Débito"...
    trn_type: str | None = None       # codigo original: CREDIT, DEBIT, ...
    fit_id: str | None = None
    memo: str | None = None
    name: str | None = None           # alguns bancos usam <NAME> no lugar de <MEMO>
    check_num: str | None = None
    ref_num: str | None = None
    saldo: float | None = None        # saldo corrente (preenchido por calcular_saldos)

    @property
    def descricao(self) -> str:
        """Historico do lancamento: junta MEMO e NAME sem repetir informacao."""
        memo = (self.memo or "").strip()
        name = (self.name or "").strip()
        if memo and name and name.upper() not in memo.upper():
            return f"{name} - {memo}"
        return memo or name or ""

    @property
    def credito(self) -> bool:
        return (self.valor or 0.0) >= 0


@dataclass
class ExtratoOFX:
    conta: ContaOFX = field(default_factory=ContaOFX)
    transacoes: list[TransacaoOFX] = field(default_factory=list)
    moeda: str | None = None
    dt_inicio: str | None = None
    dt_fim: str | None = None
    dt_inicio_iso: str | None = None
    dt_fim_iso: str | None = None
    saldo_final: float | None = None       # LEDGERBAL/BALAMT (saldo consolidado)
    saldo_final_data: str | None = None    # LEDGERBAL/DTASOF
    saldo_disponivel: float | None = None  # AVAILBAL/BALAMT
    instituicao: str | None = None         # <ORG> do cabecalho, quando presente

    # -- agregados ---------------------------------------------------------
    @property
    def total_creditos(self) -> float:
        return sum(t.valor for t in self.transacoes if t.valor and t.valor > 0)

    @property
    def total_debitos(self) -> float:
        return sum(t.valor for t in self.transacoes if t.valor and t.valor < 0)

    @property
    def total_movimentado(self) -> float:
        return sum(t.valor or 0.0 for t in self.transacoes)

    @property
    def saldo_inicial(self) -> float | None:
        """Saldo anterior, deduzido do saldo final informado pelo banco."""
        if self.saldo_final is None:
            return None
        return round(self.saldo_final - self.total_movimentado, 2)

    def ordenar(self) -> None:
        """Ordena as transacoes por data (as sem data vao para o fim)."""
        self.transacoes.sort(key=lambda t: (t.dt_posted_iso is None, t.dt_posted_iso or ""))

    def calcular_saldos(self) -> None:
        """Preenche `TransacaoOFX.saldo` com o saldo corrente apos cada lancamento.

        Depende do saldo final informado no arquivo (LEDGERBAL). Sem ele nao ha
        como reconstruir a serie, e os saldos ficam `None`.
        """
        inicial = self.saldo_inicial
        if inicial is None:
            for t in self.transacoes:
                t.saldo = None
            return
        acumulado = inicial
        for t in self.transacoes:
            acumulado += t.valor or 0.0
            t.saldo = round(acumulado, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "instituicao": self.instituicao,
            "conta": asdict(self.conta),
            "moeda": self.moeda,
            "periodo": {"inicio": self.dt_inicio_iso, "fim": self.dt_fim_iso},
            "transacoes": [asdict(t) for t in self.transacoes],
            "total_transacoes": len(self.transacoes),
            "total_creditos": round(self.total_creditos, 2),
            "total_debitos": round(self.total_debitos, 2),
            "saldo_inicial": self.saldo_inicial,
            "saldo_final": self.saldo_final,
            "saldo_disponivel": self.saldo_disponivel,
        }


# ---------------------------------------------------------------------------
# Arvore de tags
# ---------------------------------------------------------------------------
class _No:
    """No da arvore SGML/XML: ou tem `valor` (folha) ou `filhos` (agregado)."""

    __slots__ = ("tag", "valor", "filhos")

    def __init__(self, tag: str, valor: str | None = None) -> None:
        self.tag = tag
        self.valor = valor
        self.filhos: list[_No] = []

    def encontrar(self, tag: str) -> "_No | None":
        """Busca em largura: o no mais raso vence.

        A busca em largura importa por desempenho. <LEDGERBAL> e <BANKACCTFROM>
        sao filhos diretos de <STMTRS>, mas ficam depois de <BANKTRANLIST> no
        documento; em profundidade, cada consulta desceria por todos os
        lancamentos do extrato antes de encontra-los.
        """
        nivel = self.filhos
        while nivel:
            proximo: list[_No] = []
            for no in nivel:
                if no.tag == tag:
                    return no
                if no.filhos:
                    proximo.extend(no.filhos)
            nivel = proximo
        return None

    def encontrar_todos(self, *tags: str) -> list["_No"]:
        alvo = set(tags)
        achados: list[_No] = []
        pilha = list(reversed(self.filhos))
        while pilha:
            no = pilha.pop()
            if no.tag in alvo:
                achados.append(no)
            pilha.extend(reversed(no.filhos))
        return achados

    def texto(self, tag: str) -> str | None:
        no = self.encontrar(tag)
        if no is None or not no.valor:
            return None
        return no.valor

    def mapa(self) -> dict[str, str]:
        """Valores dos filhos diretos, por tag (o primeiro de cada tag vence).

        Ler um bloco pequeno e conhecido - como <STMTTRN> - de uma vez so e bem
        mais barato do que fazer uma busca em profundidade por campo.
        """
        campos: dict[str, str] = {}
        for filho in self.filhos:
            if filho.valor and filho.tag not in campos:
                campos[filho.tag] = filho.valor
        return campos

    def __repr__(self) -> str:  # pragma: no cover - apoio a depuracao
        return f"<{self.tag} valor={self.valor!r} filhos={len(self.filhos)}>"


# Pares tipicos de mojibake: texto UTF-8 lido como latin-1/cp1252.
_MOJIBAKE = ("\u00c3\u00a1", "\u00c3\u00a9", "\u00c3\u00ad", "\u00c3\u00b3", "\u00c3\u00ba",
             "\u00c3\u00a7", "\u00c3\u00a3", "\u00c3\u00b5", "\u00c3\u00aa", "\u00c3\u00b4",
             "\u00c3\u00a0", "\u00c3\u00a2", "\u00c2\u00a0", "\u00c3\u0083", "\u00c3\u0087")

_RE_TAG = re.compile(r"<(/?)([A-Za-z0-9._:-]+)([^>]*)>([^<]*)")
_RE_ESPACOS = re.compile(r"[ \t\xa0]+")
# Um unico teste decide se o valor precisa de tratamento: entidade, espaco
# especial, quebra de linha ou espacos repetidos.
_RE_PRECISA_LIMPEZA = re.compile(r"[&\xa0\r\n\t]|  ")


def _limpar(valor: str) -> str:
    """Resolve entidades (&amp;, &#233;) e normaliza espacos do valor de uma tag.

    A grande maioria dos valores ja vem limpa; o teste unico acima evita pagar
    quatro substituicoes por campo em extratos com milhares de lancamentos.
    """
    if not _RE_PRECISA_LIMPEZA.search(valor):
        return valor
    if "&" in valor:
        valor = html.unescape(valor)
    valor = valor.replace("\xa0", " ").replace("\r", " ").replace("\n", " ")
    return _RE_ESPACOS.sub(" ", valor).strip()


def _montar_arvore(texto: str) -> _No:
    """Le o documento inteiro em uma passagem e devolve a raiz da arvore."""
    raiz = _No("__RAIZ__")
    pilha: list[_No] = [raiz]

    criar_no = _No  # atalhos locais: evitam busca de nome no laco principal
    limpar = _limpar

    for m in _RE_TAG.finditer(texto):
        fechamento, tag, atributos, cauda = m.groups()
        if not tag.isupper():
            tag = tag.upper()

        if fechamento:
            # fecha o agregado correspondente (ignora fechamento de folha)
            for i in range(len(pilha) - 1, 0, -1):
                if pilha[i].tag == tag:
                    del pilha[i:]
                    break
            continue

        if atributos.rstrip().endswith("/"):  # <TAG/> - sem conteudo
            continue

        valor = cauda.strip()
        if valor:
            pilha[-1].filhos.append(criar_no(tag, limpar(valor)))
            continue

        # agregado: se a mesma tag ja estiver aberta, o arquivo omitiu o
        # fechamento (comum em OFX 1.x com varios <STMTTRN>) - fecha o anterior
        for i in range(len(pilha) - 1, 0, -1):
            if pilha[i].tag == tag:
                del pilha[i:]
                break

        no = _No(tag)
        pilha[-1].filhos.append(no)
        pilha.append(no)

    return raiz


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
class OFXParserBR:
    """Le arquivos OFX e devolve `ExtratoOFX`.

    `parse_*` retorna o primeiro extrato do arquivo; `parse_*_todos` retorna a
    lista completa (arquivos com mais de uma conta, ou conta corrente + cartao).
    """

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
        "HOLD": "Bloqueio",
        "OTHER": "Outro",
    }

    _TAGS_EXTRATO = ("STMTRS", "CCSTMTRS")

    def __init__(self) -> None:
        self._header: dict[str, str] = {}

    # -- entradas publicas -------------------------------------------------
    def parse_file(self, path: str | Path) -> ExtratoOFX:
        return self._primeiro(self.parse_file_todos(path))

    def parse_bytes(self, raw: bytes) -> ExtratoOFX:
        return self._primeiro(self.parse_bytes_todos(raw))

    def parse_string(self, text: str) -> ExtratoOFX:
        return self._primeiro(self.parse_string_todos(text))

    def parse_file_todos(self, path: str | Path) -> list[ExtratoOFX]:
        return self.parse_bytes_todos(Path(path).read_bytes())

    def parse_bytes_todos(self, raw: bytes) -> list[ExtratoOFX]:
        self._header = self._parse_header(raw)
        return self._parse_body(self._decode_content(raw))

    def parse_string_todos(self, text: str) -> list[ExtratoOFX]:
        self._header = {}
        return self._parse_body(text)

    @staticmethod
    def _primeiro(extratos: list[ExtratoOFX]) -> ExtratoOFX:
        return extratos[0] if extratos else ExtratoOFX()

    # -- cabecalho e codificacao ------------------------------------------
    def _parse_header(self, raw: bytes) -> dict[str, str]:
        header: dict[str, str] = {}
        preview = raw[:2048].decode("ascii", errors="replace")
        for linha in preview.splitlines():
            limpa = linha.strip()
            if limpa.upper().startswith("<OFX"):
                break
            if ":" in limpa and not limpa.startswith("<"):
                chave, _, valor = limpa.partition(":")
                header[chave.strip().upper()] = valor.strip()
        return header

    def _decode_content(self, raw: bytes) -> str:
        for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
            if raw.startswith(bom):
                return raw[len(bom):].decode(enc, errors="replace")

        charset = self._header.get("CHARSET", "").upper()
        encoding = self._header.get("ENCODING", "").upper()

        candidatos: list[str] = []
        if charset in ("1252", "WIN1252", "WINDOWS-1252"):
            candidatos.append("cp1252")
        elif charset in ("8859-1", "8859_1", "ISO-8859-1", "LATIN-1", "LATIN1"):
            candidatos.append("iso-8859-1")
        elif charset in ("65001", "UTF-8", "UTF8"):
            candidatos.append("utf-8")
        if encoding in ("UTF-8", "UTF8"):
            candidatos.append("utf-8")
        candidatos += ["utf-8", "cp1252", "iso-8859-1"]

        vistos: set[str] = set()
        melhor_texto: str | None = None
        melhor_nota = -1.0

        for enc in candidatos:
            if enc in vistos:
                continue
            vistos.add(enc)
            try:
                texto = raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            nota = self._nota_codificacao(texto)
            if nota > melhor_nota:
                melhor_nota, melhor_texto = nota, texto

        return melhor_texto if melhor_texto is not None else raw.decode("latin-1")

    @staticmethod
    def _nota_codificacao(texto: str) -> float:
        """Nota heuristica: penaliza mojibake, premia acentuacao valida."""
        nota = 0.0
        nota -= texto.count("�") * 50
        # "Ã©", "Ã§"... indicam UTF-8 lido como latin-1
        nota -= sum(texto.count(p) for p in _MOJIBAKE) * 30
        nota += len(re.findall(r"[áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ]", texto)) * 5
        return nota

    # -- corpo -------------------------------------------------------------
    def _parse_body(self, texto: str) -> list[ExtratoOFX]:
        inicio = texto.upper().find("<OFX")
        if inicio > 0:
            texto = texto[inicio:]

        raiz = _montar_arvore(texto)
        instituicao = raiz.texto("ORG")

        blocos = raiz.encontrar_todos(*self._TAGS_EXTRATO)
        if not blocos:
            # arquivo fora do padrao: trata o documento inteiro como um extrato
            blocos = [raiz] if raiz.encontrar("STMTTRN") or raiz.encontrar("BANKTRANLIST") else []

        return [self._parse_extrato(bloco, instituicao) for bloco in blocos]

    def _parse_extrato(self, no: _No, instituicao: str | None) -> ExtratoOFX:
        extrato = ExtratoOFX(moeda=no.texto("CURDEF"), instituicao=instituicao)

        acct = no.encontrar("BANKACCTFROM") or no.encontrar("CCACCTFROM")
        if acct is not None:
            bank_id = acct.texto("BANKID")
            extrato.conta = ContaOFX(
                bank_id=bank_id,
                branch_id=acct.texto("BRANCHID"),
                acct_id=acct.texto("ACCTID"),
                acct_type=acct.texto("ACCTTYPE") or ("CREDITCARD" if acct.tag == "CCACCTFROM" else None),
                banco_nome=nome_banco(bank_id) or instituicao,
            )

        tranlist = no.encontrar("BANKTRANLIST") or no.encontrar("CCTRANLIST") or no
        extrato.dt_inicio = tranlist.texto("DTSTART")
        extrato.dt_fim = tranlist.texto("DTEND")
        extrato.dt_inicio_iso = self._parse_date(extrato.dt_inicio)
        extrato.dt_fim_iso = self._parse_date(extrato.dt_fim)

        ledger = no.encontrar("LEDGERBAL")
        if ledger is not None:
            extrato.saldo_final = self._parse_amount(ledger.texto("BALAMT"))
            extrato.saldo_final_data = self._parse_date(ledger.texto("DTASOF"))
        avail = no.encontrar("AVAILBAL")
        if avail is not None:
            extrato.saldo_disponivel = self._parse_amount(avail.texto("BALAMT"))

        for bloco in no.encontrar_todos("STMTTRN"):
            transacao = self._parse_transacao(bloco)
            if transacao is not None:
                extrato.transacoes.append(transacao)

        extrato.ordenar()
        extrato.calcular_saldos()
        return extrato

    def _parse_transacao(self, no: _No) -> TransacaoOFX | None:
        campos = no.mapa()
        obter = campos.get

        trn_type = obter("TRNTYPE")
        dt_raw = obter("DTPOSTED") or obter("DTUSER") or obter("DTAVAIL")
        valor = self._parse_amount(obter("TRNAMT"))

        # lancamento so e valido se tiver ao menos valor ou data
        if valor is None and dt_raw is None:
            return None

        if trn_type:
            codigo = trn_type.upper()
            rotulo = self._TIPO_LABEL.get(codigo, trn_type)
        else:  # banco omitiu TRNTYPE - deduz pelo sinal do valor
            codigo = "CREDIT" if (valor or 0.0) >= 0 else "DEBIT"
            rotulo = self._TIPO_LABEL[codigo]

        return TransacaoOFX(
            dt_posted=dt_raw,
            dt_posted_iso=self._parse_date(dt_raw),
            valor=valor,
            tipo=rotulo,
            trn_type=codigo,
            fit_id=obter("FITID"),
            memo=obter("MEMO"),
            name=obter("NAME") or obter("PAYEE"),
            check_num=obter("CHECKNUM"),
            ref_num=obter("REFNUM"),
        )

    # -- conversores -------------------------------------------------------
    @staticmethod
    def _parse_amount(raw: str | None) -> float | None:
        """Converte valores em formato americano (1234.56) ou brasileiro (1.234,56)."""
        if raw is None:
            return None

        try:  # caminho rapido: "-250.50", "1234", "+10.00" - o formato normal
            valor = float(raw)
        except ValueError:
            pass
        else:
            return valor if -1e15 < valor < 1e15 else None  # descarta nan/inf

        limpo = re.sub(r"\[.*?\]", "", raw).strip()
        limpo = re.sub(r"[^\d,.\-+]", "", limpo)
        if not limpo:
            return None

        negativo = limpo.startswith("-") or limpo.endswith("-")
        limpo = limpo.strip("+-")
        if not limpo:
            return None

        tem_virgula, tem_ponto = "," in limpo, "." in limpo
        if tem_virgula and tem_ponto:
            # o separador mais a direita e o decimal
            if limpo.rfind(",") > limpo.rfind("."):
                limpo = limpo.replace(".", "").replace(",", ".")
            else:
                limpo = limpo.replace(",", "")
        elif tem_virgula:
            inteiro, _, decimal = limpo.rpartition(",")
            # "1,234" e milhar; "1,23" / "1,2345" e decimal
            limpo = inteiro + decimal if len(decimal) == 3 and inteiro else f"{inteiro}.{decimal}"
        elif limpo.count(".") > 1:  # 1.234.567 - todos sao separadores de milhar
            limpo = limpo.replace(".", "")

        try:
            valor = float(limpo)
        except ValueError:
            return None
        return -valor if negativo and valor > 0 else valor

    @staticmethod
    def _parse_date(raw: str | None) -> str | None:
        """Converte DTPOSTED (YYYYMMDD[HHMMSS][.mmm][-3:BRT]) para ISO 8601."""
        if raw is None:
            return None

        # Caminho rapido, que cobre praticamente todo arquivo real: a data ja
        # comeca em YYYYMMDD. Fatiar e validar com o construtor de datetime
        # custa uma fracao do que custaria strptime()+strftime() por lancamento.
        if len(raw) >= 8 and raw[:8].isdigit():
            hora = raw[8:14] if len(raw) >= 14 and raw[8:14].isdigit() else "000000"
            iso = OFXParserBR._montar_iso(raw[:8], hora)
            if iso is not None:
                return iso

        limpo = re.sub(r"\[.*?\]", "", raw).split(".")[0]
        digitos = re.sub(r"\D", "", limpo)
        for tamanho in (14, 12, 8):
            if len(digitos) < tamanho:
                continue
            hora = digitos[8:tamanho].ljust(6, "0")
            iso = OFXParserBR._montar_iso(digitos[:8], hora)
            if iso is not None:
                return iso
        return None

    @staticmethod
    def _montar_iso(data: str, hora: str) -> str | None:
        """Valida YYYYMMDD + HHMMSS e devolve a data em ISO 8601, ou None."""
        try:
            datetime(
                int(data[0:4]), int(data[4:6]), int(data[6:8]),
                int(hora[0:2]), int(hora[2:4]), int(hora[4:6]),
            )
        except ValueError:
            return None
        return f"{data[0:4]}-{data[4:6]}-{data[6:8]}T{hora[0:2]}:{hora[2:4]}:{hora[4:6]}"


# ---------------------------------------------------------------------------
# Execucao direta: `python ofx_parser.py extrato.ofx` imprime o JSON do extrato
# ---------------------------------------------------------------------------
def _cli(argv: Iterable[str]) -> int:  # pragma: no cover - utilitario
    import json
    import sys

    args = list(argv)
    if not args:
        print("uso: python ofx_parser.py <arquivo.ofx> [...]", file=sys.stderr)
        return 2

    saida = []
    for caminho in args:
        saida.extend(e.to_dict() for e in OFXParserBR().parse_file_todos(caminho))
    print(json.dumps(saida, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_cli(sys.argv[1:]))
