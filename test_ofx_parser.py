"""Testes do parser OFX.

Execucao::

    python -m unittest -v
"""

from __future__ import annotations

import unittest

from ofx_parser import OFXParserBR, nome_banco

# --------------------------------------------------------------------------
# Amostras
# --------------------------------------------------------------------------

# OFX 1.x (SGML) - tags de valor sem fechamento, como Bradesco/Itau enviam
OFX_SGML = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252

<OFX>
<SIGNONMSGSRSV1>
<SONRS>
<FI><ORG>Banco Exemplo S.A.<FID>237</FI>
</SONRS>
</SIGNONMSGSRSV1>
<BANKMSGSRSV1>
<STMTTRNRS>
<STMTRS>
<CURDEF>BRL
<BANKACCTFROM>
<BANKID>237
<BRANCHID>1234
<ACCTID>56789-0
<ACCTTYPE>CHECKING
</BANKACCTFROM>
<BANKTRANLIST>
<DTSTART>20240101000000[-3:BRT]
<DTEND>20240131235959[-3:BRT]
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20240105120000[-3:BRT]
<TRNAMT>1500.00
<FITID>001
<MEMO>TED RECEBIDA JOAO &amp; MARIA LTDA
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20240110
<TRNAMT>-250.50
<FITID>002
<MEMO>PAGAMENTO FORNECEDOR
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20240120
<TRNAMT>-99.50
<FITID>003
<MEMO>TARIFA MENSAL
</BANKTRANLIST>
<LEDGERBAL>
<BALAMT>1150.00
<DTASOF>20240131235959[-3:BRT]
</LEDGERBAL>
<AVAILBAL>
<BALAMT>1100.00
<DTASOF>20240131235959[-3:BRT]
</AVAILBAL>
</STMTRS>
</STMTTRNRS>
</BANKMSGSRSV1>
</OFX>
"""

# OFX 2.x (XML) - todas as tags fechadas
OFX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<?OFX OFXHEADER="200" VERSION="211" SECURITY="NONE"?>
<OFX>
  <BANKMSGSRSV1>
    <STMTTRNRS>
      <STMTRS>
        <CURDEF>BRL</CURDEF>
        <BANKACCTFROM>
          <BANKID>341</BANKID>
          <ACCTID>9999</ACCTID>
          <ACCTTYPE>CHECKING</ACCTTYPE>
        </BANKACCTFROM>
        <BANKTRANLIST>
          <DTSTART>20240301</DTSTART>
          <DTEND>20240331</DTEND>
          <STMTTRN>
            <TRNTYPE>DEBIT</TRNTYPE>
            <DTPOSTED>20240302</DTPOSTED>
            <TRNAMT>-10.00</TRNAMT>
            <FITID>X1</FITID>
            <NAME>PIX ENVIADO</NAME>
            <MEMO>PIX ENVIADO PARA FULANO</MEMO>
          </STMTTRN>
        </BANKTRANLIST>
        <LEDGERBAL>
          <BALAMT>90.00</BALAMT>
          <DTASOF>20240331</DTASOF>
        </LEDGERBAL>
      </STMTRS>
    </STMTTRNRS>
  </BANKMSGSRSV1>
</OFX>
"""

# Conta corrente + cartao de credito no mesmo arquivo
OFX_MULTI = """<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<CURDEF>BRL
<BANKACCTFROM><BANKID>001<ACCTID>111<ACCTTYPE>CHECKING</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20240105<TRNAMT>10.00<FITID>A</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>10.00<DTASOF>20240131</LEDGERBAL>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
<CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS>
<CURDEF>BRL
<CCACCTFROM><ACCTID>4444****1111</CCACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20240107<TRNAMT>-30.00<FITID>B</STMTTRN>
</BANKTRANLIST>
<LEDGERBAL><BALAMT>-30.00<DTASOF>20240131</LEDGERBAL>
</CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1>
</OFX>
"""


class TestValores(unittest.TestCase):
    def parse(self, valor):
        return OFXParserBR._parse_amount(valor)

    def test_formato_americano(self):
        self.assertEqual(self.parse("1234.56"), 1234.56)
        self.assertEqual(self.parse("-250.50"), -250.50)
        self.assertEqual(self.parse("+10.00"), 10.00)

    def test_formato_brasileiro(self):
        self.assertEqual(self.parse("1.234,56"), 1234.56)
        self.assertEqual(self.parse("-1.234,56"), -1234.56)
        self.assertEqual(self.parse("0,99"), 0.99)

    def test_milhar_sem_decimal(self):
        self.assertEqual(self.parse("1,234"), 1234.0)
        self.assertEqual(self.parse("1.234.567"), 1234567.0)

    def test_sinal_a_direita(self):
        self.assertEqual(self.parse("50.00-"), -50.00)

    def test_invalidos(self):
        self.assertIsNone(self.parse(None))
        self.assertIsNone(self.parse(""))
        self.assertIsNone(self.parse("   "))
        self.assertIsNone(self.parse("abc"))


class TestDatas(unittest.TestCase):
    def parse(self, valor):
        return OFXParserBR._parse_date(valor)

    def test_com_fuso_brasileiro(self):
        self.assertEqual(self.parse("20240105120000[-3:BRT]"), "2024-01-05T12:00:00")

    def test_somente_data(self):
        self.assertEqual(self.parse("20240105"), "2024-01-05T00:00:00")

    def test_com_milissegundos(self):
        self.assertEqual(self.parse("20240105120000.000[-03:EST]"), "2024-01-05T12:00:00")

    def test_invalidos(self):
        self.assertIsNone(self.parse(None))
        self.assertIsNone(self.parse("nao e data"))
        self.assertIsNone(self.parse("20241332"))  # mes 13, dia 32


class TestSGML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extrato = OFXParserBR().parse_string(OFX_SGML)

    def test_conta(self):
        conta = self.extrato.conta
        self.assertEqual(conta.bank_id, "237")
        self.assertEqual(conta.branch_id, "1234")
        self.assertEqual(conta.acct_id, "56789-0")
        self.assertEqual(conta.acct_type, "CHECKING")
        self.assertEqual(conta.banco_nome, "Bradesco")

    def test_periodo_e_moeda(self):
        self.assertEqual(self.extrato.moeda, "BRL")
        self.assertEqual(self.extrato.dt_inicio_iso, "2024-01-01T00:00:00")
        self.assertEqual(self.extrato.dt_fim_iso, "2024-01-31T23:59:59")

    def test_todas_as_transacoes(self):
        self.assertEqual(len(self.extrato.transacoes), 3)

    def test_entidade_html_no_memo(self):
        self.assertEqual(self.extrato.transacoes[0].memo, "TED RECEBIDA JOAO & MARIA LTDA")

    def test_rotulos_em_portugues(self):
        self.assertEqual(self.extrato.transacoes[0].tipo, "Credito")
        self.assertEqual(self.extrato.transacoes[1].tipo, "Debito")

    def test_saldos(self):
        self.assertEqual(self.extrato.saldo_final, 1150.00)
        self.assertEqual(self.extrato.saldo_disponivel, 1100.00)
        # 1150 - (1500 - 250,50 - 99,50) = 0
        self.assertEqual(self.extrato.saldo_inicial, 0.00)

    def test_saldo_corrente_por_lancamento(self):
        saldos = [t.saldo for t in self.extrato.transacoes]
        self.assertEqual(saldos, [1500.00, 1249.50, 1150.00])
        self.assertEqual(saldos[-1], self.extrato.saldo_final)

    def test_totais(self):
        self.assertEqual(self.extrato.total_creditos, 1500.00)
        self.assertEqual(self.extrato.total_debitos, -350.00)

    def test_instituicao_do_cabecalho(self):
        self.assertEqual(self.extrato.instituicao, "Banco Exemplo S.A.")


class TestXML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extrato = OFXParserBR().parse_string(OFX_XML)

    def test_le_tags_fechadas(self):
        self.assertEqual(len(self.extrato.transacoes), 1)
        self.assertEqual(self.extrato.transacoes[0].valor, -10.00)
        self.assertEqual(self.extrato.conta.acct_id, "9999")
        self.assertEqual(self.extrato.conta.banco_nome, "Itau Unibanco")

    def test_descricao_junta_name_e_memo(self):
        # NAME esta contido no MEMO: nao deve repetir
        self.assertEqual(self.extrato.transacoes[0].descricao, "PIX ENVIADO PARA FULANO")


class TestMultiplasContas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extratos = OFXParserBR().parse_string_todos(OFX_MULTI)

    def test_encontra_conta_e_cartao(self):
        self.assertEqual(len(self.extratos), 2)

    def test_conta_corrente(self):
        conta = self.extratos[0]
        self.assertEqual(conta.conta.acct_id, "111")
        self.assertEqual(conta.conta.banco_nome, "Banco do Brasil")
        self.assertEqual(len(conta.transacoes), 1)

    def test_cartao_de_credito(self):
        cartao = self.extratos[1]
        self.assertEqual(cartao.conta.acct_id, "4444****1111")
        self.assertEqual(cartao.conta.acct_type, "CREDITCARD")
        self.assertEqual(len(cartao.transacoes), 1)

    def test_parse_simples_retorna_o_primeiro(self):
        primeiro = OFXParserBR().parse_string(OFX_MULTI)
        self.assertEqual(primeiro.conta.acct_id, "111")


class TestRobustez(unittest.TestCase):
    def test_arquivo_vazio(self):
        extrato = OFXParserBR().parse_string("")
        self.assertEqual(extrato.transacoes, [])
        self.assertIsNone(extrato.saldo_final)
        self.assertIsNone(extrato.saldo_inicial)

    def test_extrato_sem_lancamentos(self):
        ofx = """<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS>
        <BANKACCTFROM><BANKID>033<ACCTID>1</BANKACCTFROM>
        <BANKTRANLIST><DTSTART>20240101<DTEND>20240131</BANKTRANLIST>
        <LEDGERBAL><BALAMT>0.00<DTASOF>20240131</LEDGERBAL>
        </STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""
        extrato = OFXParserBR().parse_string(ofx)
        self.assertEqual(extrato.transacoes, [])
        self.assertEqual(extrato.saldo_final, 0.0)

    def test_sem_saldo_no_arquivo(self):
        ofx = """<OFX><STMTRS><BANKTRANLIST>
        <STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20240105<TRNAMT>10.00<FITID>A</STMTTRN>
        </BANKTRANLIST></STMTRS></OFX>"""
        extrato = OFXParserBR().parse_string(ofx)
        self.assertEqual(len(extrato.transacoes), 1)
        self.assertIsNone(extrato.saldo_inicial)
        self.assertIsNone(extrato.transacoes[0].saldo)

    def test_transacao_sem_trntype(self):
        ofx = """<OFX><STMTRS><BANKTRANLIST>
        <STMTTRN><DTPOSTED>20240105<TRNAMT>-10.00<FITID>A</STMTTRN>
        </BANKTRANLIST></STMTRS></OFX>"""
        extrato = OFXParserBR().parse_string(ofx)
        self.assertEqual(len(extrato.transacoes), 1)
        self.assertEqual(extrato.transacoes[0].tipo, "Debito")

    def test_ordena_por_data(self):
        ofx = """<OFX><STMTRS><BANKTRANLIST>
        <STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20240310<TRNAMT>3.00<FITID>C</STMTTRN>
        <STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20240101<TRNAMT>1.00<FITID>A</STMTTRN>
        <STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20240205<TRNAMT>2.00<FITID>B</STMTTRN>
        </BANKTRANLIST></STMTRS></OFX>"""
        extrato = OFXParserBR().parse_string(ofx)
        self.assertEqual([t.fit_id for t in extrato.transacoes], ["A", "B", "C"])

    def test_memo_com_sinal_de_maior(self):
        ofx = """<OFX><STMTRS><BANKTRANLIST>
        <STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20240105<TRNAMT>-1.00
        <MEMO>TRANSF CC =&gt; POUPANCA<FITID>A</STMTTRN>
        </BANKTRANLIST></STMTRS></OFX>"""
        extrato = OFXParserBR().parse_string(ofx)
        self.assertEqual(extrato.transacoes[0].memo, "TRANSF CC => POUPANCA")

    def test_codificacao_utf8(self):
        bruto = OFX_SGML.replace("TARIFA MENSAL", "MANUTENCAO DE CONTA - JOSE ANTONIO").encode("utf-8")
        extrato = OFXParserBR().parse_bytes(bruto)
        self.assertEqual(len(extrato.transacoes), 3)

    def test_codificacao_cp1252(self):
        texto = OFX_SGML.replace("TARIFA MENSAL", "TARIFA DE MANUTENCAO ÇÃO")
        extrato = OFXParserBR().parse_bytes(texto.encode("cp1252"))
        self.assertIn("ÇÃO", extrato.transacoes[2].memo)

    def test_acentos_utf8_nao_viram_mojibake(self):
        texto = OFX_SGML.replace("TARIFA MENSAL", "Manutenção de conta corrente")
        extrato = OFXParserBR().parse_bytes(texto.encode("utf-8"))
        self.assertEqual(extrato.transacoes[2].memo, "Manutenção de conta corrente")

    def test_bom_utf8(self):
        bruto = b"\xef\xbb\xbf" + OFX_SGML.encode("utf-8")
        self.assertEqual(len(OFXParserBR().parse_bytes(bruto).transacoes), 3)


class TestBancos(unittest.TestCase):
    def test_normaliza_zeros_a_esquerda(self):
        self.assertEqual(nome_banco("0237"), "Bradesco")
        self.assertEqual(nome_banco("237"), "Bradesco")
        self.assertEqual(nome_banco("00237"), "Bradesco")

    def test_codigo_curto(self):
        self.assertEqual(nome_banco("1"), "Banco do Brasil")
        self.assertEqual(nome_banco("001"), "Banco do Brasil")

    def test_desconhecido(self):
        self.assertIsNone(nome_banco("99999"))
        self.assertIsNone(nome_banco(None))
        self.assertIsNone(nome_banco(""))


class TestDesempenho(unittest.TestCase):
    def test_extrato_grande(self):
        """5.000 lancamentos devem ser lidos em bem menos de um segundo."""
        import time

        linhas = ["<OFX><STMTRS><CURDEF>BRL<BANKACCTFROM><BANKID>237<ACCTID>1</BANKACCTFROM>",
                  "<BANKTRANLIST><DTSTART>20240101<DTEND>20241231"]
        for i in range(5000):
            linhas.append(
                f"<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>202401{(i % 28) + 1:02d}"
                f"<TRNAMT>-{(i % 900) + 1}.99<FITID>{i}<MEMO>LANCAMENTO DE TESTE {i}</STMTTRN>"
            )
        linhas.append("</BANKTRANLIST><LEDGERBAL><BALAMT>0.00<DTASOF>20241231</LEDGERBAL></STMTRS></OFX>")
        ofx = "\n".join(linhas)

        inicio = time.perf_counter()
        extrato = OFXParserBR().parse_string(ofx)
        decorrido = time.perf_counter() - inicio

        self.assertEqual(len(extrato.transacoes), 5000)
        self.assertLess(decorrido, 1.0, f"parser levou {decorrido:.2f}s para 5.000 lancamentos")


if __name__ == "__main__":
    unittest.main(verbosity=2)
