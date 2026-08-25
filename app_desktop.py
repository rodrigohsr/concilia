"""Concilia - conferencia de extratos bancarios em OFX.

Interface desktop (Tkinter) usada no fluxo da Esquema Assessoria Contabil.

Notas de desempenho: nada pesado e importado na inicializacao. O parser usa
apenas a biblioteca padrao, e reportlab/openpyxl/PIL sao carregados sob demanda,
na primeira exportacao. Isso mantem a abertura do programa praticamente
instantanea, inclusive no executavel gerado pelo PyInstaller.
"""

from __future__ import annotations

import json
import os
import sys
import tkinter as tk
from dataclasses import dataclass
from tkinter import filedialog, messagebox, ttk

from ofx_parser import ExtratoOFX, OFXParserBR

APP_NOME = "Concilia"
VERSAO = "1.0.0"
DESCRICAO = "Conferencia de extratos bancarios em OFX"
EMPRESA = "Esquema Assessoria Contabil"
AVISO_LEGAL = "Extrato gerado para conferencia. Nao substitui o documento oficial do banco."

# Paleta
COR_FUNDO_TOPO = "#ffffff"
COR_DESTAQUE = "#00a8e8"
COR_BARRA = "#f4f6f9"
COR_TEXTO = "#333333"
COR_DEBITO = "#c62828"
COR_CREDITO = "#1b5e20"
COR_ZEBRA = "#f7f9fc"

# Quantidade de linhas inseridas por ciclo ao preencher a tabela. Manter a
# insercao fatiada deixa a janela responsiva em extratos muito grandes.
LOTE_LINHAS = 400


def resource_path(relative_path: str) -> str:
    """Caminho de um recurso, funcionando tambem dentro do bundle do PyInstaller."""
    base = getattr(sys, "_MEIPASS", None) or os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, relative_path)


def caminho_config() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_NOME, "config.json")


def formatar_moeda(valor: float | None, vazio: str = "-") -> str:
    """Formata no padrao brasileiro: 1234.5 -> '1.234,50'."""
    if valor is None:
        return vazio
    return f"{valor:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def formatar_valor_cd(valor: float | None, vazio: str = "-") -> str:
    """Formata com sufixo contabil C (credito) ou D (debito)."""
    if valor is None:
        return vazio
    return f"{formatar_moeda(abs(valor))} {'C' if valor >= 0 else 'D'}"


def escapar_xml(texto: str) -> str:
    """Escapa &, < e > para uso dentro de Paragraph do reportlab.

    Historicos bancarios trazem '&' com frequencia ("JOAO & MARIA LTDA"), o que
    quebraria a geracao do PDF se fosse repassado cru.
    """
    return texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def formatar_data(iso: str | None) -> str:
    if not iso or len(iso) < 10:
        return ""
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


@dataclass(slots=True)
class Linha:
    """Uma linha da tabela, com os campos ja formatados para exibicao."""

    iso: str
    data: str
    tipo: str
    historico: str
    valor: float
    saldo: float | None
    valor_txt: str
    saldo_txt: str
    detalhes: str
    busca: str  # historico + tipo em minusculas, para filtro rapido


class ConciliaApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config = self._carregar_config()

        self.extratos: list[ExtratoOFX] = []
        self.extrato: ExtratoOFX | None = None
        self.linhas: list[Linha] = []
        self.visiveis: list[Linha] = []
        self.caminho_atual: str | None = None
        self.ordenacao: tuple[str, bool] = ("data", False)
        self.geracao = 0  # invalida preenchimentos em andamento
        self._busca_agendada: str | None = None

        self._montar_janela()
        self._montar_cabecalho()
        self._montar_barra()
        self._montar_tabela()
        self._montar_rodape()
        self._montar_atalhos()

        # Tudo que nao e essencial para a janela aparecer fica para depois do
        # primeiro desenho: drag-and-drop, logo e o arquivo passado por linha
        # de comando.
        self.root.after_idle(self._pos_inicializacao)

    # ------------------------------------------------------------------
    # Construcao da interface
    # ------------------------------------------------------------------
    def _montar_janela(self) -> None:
        self.root.title(f"{APP_NOME} - {EMPRESA}")
        self.root.geometry(self.config.get("geometria", "1200x680"))
        self.root.minsize(900, 480)
        for icone in ("concilia.ico", "cifrao.ico"):
            try:
                self.root.iconbitmap(resource_path(icone))
                break
            except tk.TclError:
                continue

        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Treeview", rowheight=22)
        self.style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        self.root.protocol("WM_DELETE_WINDOW", self._ao_fechar)

    def _montar_cabecalho(self) -> None:
        self.header = tk.Frame(self.root, bg=COR_FUNDO_TOPO)
        self.header.pack(fill="x", side="top")

        self.titulo = tk.Label(
            self.header,
            text=APP_NOME,
            font=("Segoe UI", 14, "bold"),
            fg=COR_TEXTO,
            bg=COR_FUNDO_TOPO,
        )
        self.titulo.pack(anchor="center", pady=(12, 4))

        self.info = tk.Label(
            self.header,
            text="Abra um arquivo OFX (ou arraste-o para esta janela).",
            font=("Segoe UI", 9),
            fg=COR_TEXTO,
            bg=COR_FUNDO_TOPO,
            justify="center",
        )
        self.info.pack(anchor="center", pady=(0, 12))

        tk.Frame(self.root, bg=COR_DESTAQUE, height=3).pack(fill="x")

    def _montar_barra(self) -> None:
        barra = tk.Frame(self.root, bg=COR_BARRA, bd=1, relief="groove")
        barra.pack(fill="x")

        self.btn_abrir = ttk.Button(barra, text="Abrir OFX", command=self.selecionar_arquivo)
        self.btn_abrir.pack(side="left", padx=(10, 4), pady=6)

        self.btn_recarregar = ttk.Button(barra, text="Recarregar", command=self.recarregar, state="disabled")
        self.btn_recarregar.pack(side="left", padx=4, pady=6)

        ttk.Separator(barra, orient="vertical").pack(side="left", fill="y", padx=8, pady=6)

        self.btn_pdf = ttk.Button(barra, text="Exportar PDF", command=self.exportar_pdf, state="disabled")
        self.btn_pdf.pack(side="left", padx=4, pady=6)

        self.btn_planilha = ttk.Button(barra, text="Exportar planilha", command=self.exportar_planilha, state="disabled")
        self.btn_planilha.pack(side="left", padx=4, pady=6)

        # Seletor de conta: so aparece em arquivos com mais de um extrato
        self.frame_conta = tk.Frame(barra, bg=COR_BARRA)
        tk.Label(self.frame_conta, text="Conta:", bg=COR_BARRA, fg=COR_TEXTO).pack(side="left", padx=(8, 4))
        self.cb_conta = ttk.Combobox(self.frame_conta, state="readonly", width=34)
        self.cb_conta.pack(side="left")
        self.cb_conta.bind("<<ComboboxSelected>>", self._trocar_conta)

        # Busca e filtro ficam encostados na direita
        self.var_busca = tk.StringVar()
        self.var_filtro = tk.StringVar(value="Todos")

        self.cb_filtro = ttk.Combobox(
            barra, state="readonly", width=12, values=("Todos", "Creditos", "Debitos"), textvariable=self.var_filtro
        )
        self.cb_filtro.pack(side="right", padx=(4, 10), pady=6)
        self.cb_filtro.bind("<<ComboboxSelected>>", lambda _e: self._aplicar_filtros())
        tk.Label(barra, text="Mostrar:", bg=COR_BARRA, fg=COR_TEXTO).pack(side="right")

        self.entry_busca = ttk.Entry(barra, textvariable=self.var_busca, width=30)
        self.entry_busca.pack(side="right", padx=(4, 12), pady=6)
        self.var_busca.trace_add("write", self._busca_alterada)
        tk.Label(barra, text="Localizar:", bg=COR_BARRA, fg=COR_TEXTO).pack(side="right", padx=(8, 0))

    def _montar_tabela(self) -> None:
        moldura = tk.Frame(self.root)
        moldura.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        colunas = ("data", "tipo", "historico", "valor", "saldo")
        self.tree = ttk.Treeview(moldura, columns=colunas, show="headings", selectmode="extended")

        titulos = {
            "data": ("Data", 100, "center", False),
            "tipo": ("Tipo", 110, "center", False),
            "historico": ("Historico", 560, "w", True),
            "valor": ("Valor", 150, "e", False),
            "saldo": ("Saldo", 150, "e", False),
        }
        for coluna, (texto, largura, alinhamento, estica) in titulos.items():
            self.tree.heading(coluna, text=texto, command=lambda c=coluna: self._ordenar_por(c))
            self.tree.column(coluna, width=largura, anchor=alinhamento, stretch=estica)

        self.tree.tag_configure("debito", foreground=COR_DEBITO)
        self.tree.tag_configure("credito", foreground=COR_CREDITO)
        self.tree.tag_configure("zebra", background=COR_ZEBRA)

        vsb = ttk.Scrollbar(moldura, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(moldura, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        moldura.rowconfigure(0, weight=1)
        moldura.columnconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._mostrar_detalhes)

    def _montar_rodape(self) -> None:
        rodape = tk.Frame(self.root, bg=COR_BARRA, bd=1, relief="groove")
        rodape.pack(fill="x", side="bottom")
        self.status = tk.Label(
            rodape,
            text="Pronto.",
            bg=COR_BARRA,
            fg=COR_TEXTO,
            anchor="w",
            font=("Segoe UI", 9),
            padx=10,
            pady=5,
        )
        self.status.pack(fill="x")

    def _montar_atalhos(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self.selecionar_arquivo())
        self.root.bind("<F5>", lambda _e: self.recarregar())
        self.root.bind("<Control-f>", lambda _e: self.entry_busca.focus_set())
        self.root.bind("<Escape>", self._limpar_busca)
        self.root.bind("<Control-p>", lambda _e: self.exportar_pdf())
        self.tree.bind("<Control-c>", self._copiar_historico)
        self.tree.bind("<Control-C>", self._copiar_linhas)  # Ctrl+Shift+C
        self.tree.bind("<Control-a>", self._selecionar_tudo)

    def _pos_inicializacao(self) -> None:
        self._carregar_logo()
        self._ativar_arrastar_soltar()
        if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
            self.carregar(sys.argv[1])

    def _carregar_logo(self) -> None:
        """Usa o PhotoImage nativo do Tk (le PNG sem depender do Pillow)."""
        caminho = resource_path("logo.png")
        if not os.path.exists(caminho):
            return  # sem logo da empresa, o cabecalho mostra o nome do programa
        try:
            imagem = tk.PhotoImage(file=caminho)
            fator = max(1, round(imagem.height() / 65))
            if fator > 1:
                imagem = imagem.subsample(fator, fator)
        except tk.TclError:
            try:  # formato que o Tk nao le (JPEG, PNG exotico): tenta o Pillow
                from PIL import Image, ImageTk

                img = Image.open(caminho)
                largura = int(img.width * (65 / img.height))
                imagem = ImageTk.PhotoImage(img.resize((largura, 65), Image.LANCZOS))
            except Exception:
                return
        self.logo = imagem  # a referencia precisa sobreviver ao metodo
        self.titulo.configure(image=imagem, text="")

    def _ativar_arrastar_soltar(self) -> None:
        try:
            import windnd

            windnd.hook_dropfiles(self.root, func=self._ao_soltar_arquivo)
        except Exception:
            pass  # recurso opcional

    def _ao_soltar_arquivo(self, arquivos) -> None:
        if not arquivos:
            return
        caminho = arquivos[0].decode("mbcs" if os.name == "nt" else "utf-8", errors="replace")
        self.carregar(caminho)

    # ------------------------------------------------------------------
    # Leitura do arquivo
    # ------------------------------------------------------------------
    def selecionar_arquivo(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione o extrato",
            initialdir=self.config.get("ultima_pasta") or os.path.expanduser("~"),
            filetypes=[("Arquivos OFX", "*.ofx *.qfx *.OFX *.QFX"), ("Todos os arquivos", "*.*")],
        )
        if caminho:
            self.carregar(caminho)

    def recarregar(self) -> None:
        if self.caminho_atual:
            self.carregar(self.caminho_atual)

    def carregar(self, caminho: str) -> None:
        self.status.configure(text=f"Lendo {os.path.basename(caminho)}...")
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            extratos = OFXParserBR().parse_file_todos(caminho)
        except FileNotFoundError:
            self._erro("Arquivo nao encontrado", f"O arquivo nao existe mais:\n{caminho}")
            return
        except PermissionError:
            self._erro("Sem permissao", "O arquivo esta aberto em outro programa ou sem permissao de leitura.")
            return
        except Exception as exc:  # arquivo corrompido, formato inesperado...
            self._erro("Erro de leitura", f"Nao foi possivel ler este arquivo OFX:\n\n{exc}")
            return
        finally:
            self.root.configure(cursor="")

        if not extratos:
            self._erro(
                "Formato nao reconhecido",
                "Nenhum extrato foi encontrado no arquivo.\n\n"
                "Confirme se ele e realmente um OFX exportado pelo banco.",
            )
            return

        self.caminho_atual = caminho
        self.extratos = extratos
        self.config["ultima_pasta"] = os.path.dirname(caminho)

        if len(extratos) > 1:
            self.cb_conta.configure(values=[self._rotulo_conta(e) for e in extratos])
            self.cb_conta.current(0)
            self.frame_conta.pack(side="left", padx=4, pady=6)
        else:
            self.frame_conta.pack_forget()

        self.btn_recarregar.configure(state="normal")
        self._selecionar_extrato(0)

    def _rotulo_conta(self, extrato: ExtratoOFX) -> str:
        conta = extrato.conta
        tipo = conta.tipo_descricao or "Conta"
        banco = conta.banco_nome or conta.bank_id
        return f"{tipo} {conta.acct_id or '?'}" + (f" - {banco}" if banco else "")

    def _trocar_conta(self, _evento=None) -> None:
        self._selecionar_extrato(self.cb_conta.current())

    def _selecionar_extrato(self, indice: int) -> None:
        if not (0 <= indice < len(self.extratos)):
            return
        self.extrato = self.extratos[indice]
        self.linhas = [self._montar_linha(t) for t in self.extrato.transacoes]
        self.ordenacao = ("data", False)
        self._atualizar_cabecalho()
        self._aplicar_filtros()

    @staticmethod
    def _montar_linha(transacao) -> Linha:
        valor = transacao.valor or 0.0
        historico = transacao.descricao or "(sem historico)"
        tipo = transacao.tipo or ""
        detalhes = "\n".join(
            f"{rotulo}: {texto}"
            for rotulo, texto in (
                ("Data", formatar_data(transacao.dt_posted_iso)),
                ("Tipo", tipo),
                ("Valor", formatar_valor_cd(valor)),
                ("Saldo apos o lancamento", formatar_valor_cd(transacao.saldo)),
                ("Documento", transacao.check_num),
                ("Referencia", transacao.ref_num),
                ("Identificador (FITID)", transacao.fit_id),
                ("Historico", historico),
            )
            if texto
        )
        return Linha(
            iso=transacao.dt_posted_iso or "",
            data=formatar_data(transacao.dt_posted_iso),
            tipo=tipo,
            historico=historico,
            valor=valor,
            saldo=transacao.saldo,
            valor_txt=formatar_valor_cd(valor),
            saldo_txt=formatar_valor_cd(transacao.saldo),
            detalhes=detalhes,
            busca=f"{historico}\n{tipo}".lower(),
        )

    def _atualizar_cabecalho(self) -> None:
        extrato = self.extrato
        if extrato is None:
            return
        conta = extrato.conta
        partes = []
        if conta.descricao != conta.tipo_descricao:  # evita "Cartao de credito" duas vezes
            partes.append(f"Instituicao: {conta.descricao}")
        if conta.branch_id:
            partes.append(f"Agencia: {conta.branch_id}")
        partes.append(f"{conta.tipo_descricao or 'Conta'}: {conta.acct_id or 'nao informada'}")
        if extrato.dt_inicio_iso and extrato.dt_fim_iso:
            partes.append(f"Periodo: {formatar_data(extrato.dt_inicio_iso)} a {formatar_data(extrato.dt_fim_iso)}")
        partes.append(f"Lancamentos: {len(extrato.transacoes)}")

        if extrato.saldo_final is not None:
            saldos = (
                f"Saldo anterior: R$ {formatar_valor_cd(extrato.saldo_inicial)}"
                f"     Saldo final: R$ {formatar_valor_cd(extrato.saldo_final)}"
            )
        else:
            saldos = "Saldos nao informados no arquivo (o banco nao enviou a tag LEDGERBAL)."

        self.info.configure(text="     ".join(partes) + "\n" + saldos)

    # ------------------------------------------------------------------
    # Filtro, ordenacao e preenchimento da tabela
    # ------------------------------------------------------------------
    def _busca_alterada(self, *_args) -> None:
        # espera o usuario parar de digitar antes de refiltrar
        if self._busca_agendada is not None:
            self.root.after_cancel(self._busca_agendada)
        self._busca_agendada = self.root.after(180, self._aplicar_filtros)

    def _limpar_busca(self, _evento=None) -> None:
        if self.var_busca.get():
            self.var_busca.set("")

    def _aplicar_filtros(self) -> None:
        self._busca_agendada = None
        termo = self.var_busca.get().strip().lower()
        filtro = self.var_filtro.get()

        linhas = self.linhas
        if filtro == "Creditos":
            linhas = [l for l in linhas if l.valor >= 0]
        elif filtro == "Debitos":
            linhas = [l for l in linhas if l.valor < 0]
        if termo:
            termos = termo.split()
            linhas = [l for l in linhas if all(t in l.busca for t in termos)]

        self.visiveis = linhas
        self._ordenar_visiveis()
        self._preencher_tabela()
        self._atualizar_status()

    _CHAVES = {
        "data": lambda l: l.iso,
        "tipo": lambda l: l.tipo.lower(),
        "historico": lambda l: l.historico.lower(),
        "valor": lambda l: l.valor,
        "saldo": lambda l: (l.saldo is None, l.saldo or 0.0),
    }

    def _ordenar_por(self, coluna: str) -> None:
        atual, invertido = self.ordenacao
        self.ordenacao = (coluna, not invertido if coluna == atual else False)
        self._ordenar_visiveis()
        self._preencher_tabela()

    def _ordenar_visiveis(self) -> None:
        coluna, invertido = self.ordenacao
        self.visiveis.sort(key=self._CHAVES[coluna], reverse=invertido)
        for nome in self._CHAVES:
            texto = {"data": "Data", "tipo": "Tipo", "historico": "Historico", "valor": "Valor", "saldo": "Saldo"}[nome]
            if nome == coluna:
                texto += "  v" if invertido else "  ^"
            self.tree.heading(nome, text=texto)

    def _preencher_tabela(self) -> None:
        self.geracao += 1
        self.tree.delete(*self.tree.get_children())
        self._inserir_lote(0, self.geracao)

    def _inserir_lote(self, inicio: int, geracao: int) -> None:
        if geracao != self.geracao:
            return  # outro preenchimento comecou; este ficou obsoleto
        inserir = self.tree.insert
        fim = min(inicio + LOTE_LINHAS, len(self.visiveis))
        for i in range(inicio, fim):
            linha = self.visiveis[i]
            tags = ["debito" if linha.valor < 0 else "credito"]
            if i % 2:
                tags.append("zebra")
            inserir(
                "",
                "end",
                iid=str(i),
                values=(linha.data, linha.tipo, linha.historico, linha.valor_txt, linha.saldo_txt),
                tags=tags,
            )
        if fim < len(self.visiveis):
            self.root.after(1, self._inserir_lote, fim, geracao)

    def _atualizar_status(self) -> None:
        # so faz sentido exportar o que esta visivel
        estado = "normal" if self.visiveis else "disabled"
        self.btn_pdf.configure(state=estado)
        self.btn_planilha.configure(state=estado)

        if not self.linhas:
            self.status.configure(text="Nenhum lancamento neste extrato.")
            return
        if not self.visiveis:
            self.status.configure(
                text=f"Nenhum dos {len(self.linhas)} lancamentos corresponde ao filtro atual."
            )
            return

        creditos = sum(l.valor for l in self.visiveis if l.valor >= 0)
        debitos = sum(l.valor for l in self.visiveis if l.valor < 0)
        contagem = (
            f"{len(self.visiveis)} de {len(self.linhas)} lancamentos"
            if len(self.visiveis) != len(self.linhas)
            else f"{len(self.linhas)} lancamentos"
        )
        self.status.configure(
            text=f"{contagem}     Creditos: R$ {formatar_moeda(creditos)}"
            f"     Debitos: R$ {formatar_moeda(abs(debitos))}"
            f"     Resultado: R$ {formatar_valor_cd(creditos + debitos)}"
        )

    # ------------------------------------------------------------------
    # Interacoes com a tabela
    # ------------------------------------------------------------------
    def _selecionar_tudo(self, _evento=None) -> str:
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def _linhas_selecionadas(self) -> list[Linha]:
        return [self.visiveis[int(iid)] for iid in self.tree.selection() if iid.isdigit()]

    def _copiar_historico(self, _evento=None) -> str:
        """Ctrl+C: copia so o historico (o campo que costuma ir para o lancamento)."""
        linhas = self._linhas_selecionadas()
        if linhas:
            self._para_area_transferencia("\n".join(l.historico for l in linhas))
            self.status.configure(text=f"{len(linhas)} historico(s) copiado(s).")
        return "break"

    def _copiar_linhas(self, _evento=None) -> str:
        """Ctrl+Shift+C: copia a linha inteira, pronta para colar no Excel."""
        linhas = self._linhas_selecionadas()
        if linhas:
            texto = "\n".join(
                "\t".join((l.data, l.tipo, l.historico, formatar_moeda(l.valor), formatar_moeda(l.saldo, "")))
                for l in linhas
            )
            self._para_area_transferencia(texto)
            self.status.configure(text=f"{len(linhas)} linha(s) copiada(s) para colar em planilha.")
        return "break"

    def _para_area_transferencia(self, texto: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        self.root.update_idletasks()

    def _mostrar_detalhes(self, _evento=None) -> None:
        linhas = self._linhas_selecionadas()
        if linhas:
            messagebox.showinfo("Detalhes do lancamento", linhas[0].detalhes, parent=self.root)

    # ------------------------------------------------------------------
    # Exportacoes
    # ------------------------------------------------------------------
    def _nome_sugerido(self, extensao: str) -> str:
        base = os.path.splitext(os.path.basename(self.caminho_atual or "extrato"))[0]
        conta = (self.extrato.conta.acct_id if self.extrato else "") or ""
        conta = "".join(c for c in conta if c.isalnum())
        return f"{base}{'_' + conta if conta else ''}{extensao}"

    def exportar_pdf(self) -> None:
        if not self.visiveis:
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar PDF",
            defaultextension=".pdf",
            initialfile=self._nome_sugerido(".pdf"),
            initialdir=self.config.get("ultima_pasta"),
            filetypes=[("Documento PDF", "*.pdf")],
        )
        if not destino:
            return
        try:
            self._gerar_pdf(destino)
        except ImportError:
            self._erro(
                "Biblioteca ausente",
                "A geracao de PDF depende do pacote reportlab.\n\nInstale com:\n    pip install reportlab",
            )
            return
        except PermissionError:
            self._erro("Arquivo em uso", "Feche o PDF no leitor antes de gravar por cima.")
            return
        except Exception as exc:
            self._erro("Erro ao salvar", f"Nao foi possivel gerar o PDF:\n\n{exc}")
            return
        self._sucesso(destino, "PDF gerado com sucesso.")

    def _gerar_pdf(self, destino: str) -> None:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

        estilo_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=14, alignment=TA_CENTER, leading=18)
        estilo_info = ParagraphStyle("info", fontName="Helvetica", fontSize=8, alignment=TA_CENTER, leading=11)
        estilo_celula = ParagraphStyle("celula", fontName="Helvetica", fontSize=7, leading=8.5)
        estilo_aviso = ParagraphStyle("aviso", fontName="Helvetica-Oblique", fontSize=7, alignment=TA_CENTER)

        doc = SimpleDocTemplate(
            destino,
            pagesize=A4,
            leftMargin=10 * mm,
            rightMargin=10 * mm,
            topMargin=12 * mm,
            bottomMargin=14 * mm,
            title=f"Extrato - {self.extrato.conta.acct_id if self.extrato else ''}",
            author=EMPRESA,
        )

        cabecalho = escapar_xml(self.info.cget("text")).replace("\n", "<br/>")
        elementos = [
            Paragraph("Extrato Bancario", estilo_titulo),
            Spacer(1, 4),
            Paragraph(cabecalho, estilo_info),
            Spacer(1, 8),
        ]
        if len(self.visiveis) != len(self.linhas):
            elementos.append(Paragraph("<b>Atencao:</b> exportacao filtrada - nao contem todos os lancamentos.", estilo_info))
            elementos.append(Spacer(1, 6))

        dados = [["Data", "Tipo", "Historico", "Valor", "Saldo"]]
        for linha in self.visiveis:
            # o historico vai como Paragraph para quebrar em varias linhas em vez
            # de ser cortado; precisa ter &, < e > escapados
            dados.append(
                [
                    linha.data,
                    linha.tipo,
                    Paragraph(escapar_xml(linha.historico), estilo_celula),
                    linha.valor_txt,
                    linha.saldo_txt,
                ]
            )

        creditos = sum(l.valor for l in self.visiveis if l.valor >= 0)
        debitos = sum(l.valor for l in self.visiveis if l.valor < 0)
        dados.append(["", "", "Total de creditos", formatar_moeda(creditos), ""])
        dados.append(["", "", "Total de debitos", formatar_moeda(abs(debitos)), ""])
        dados.append(["", "", "Resultado do periodo", formatar_valor_cd(creditos + debitos), ""])

        tabela = LongTable(
            dados,
            colWidths=[20 * mm, 24 * mm, 82 * mm, 32 * mm, 32 * mm],
            repeatRows=1,
        )
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9aa5b1")),
            ("ALIGN", (0, 0), (1, -1), "CENTER"),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 1), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
            ("FONTNAME", (0, -3), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -3), (-1, -1), colors.HexColor("#e8eef5")),
            ("ALIGN", (2, -3), (2, -1), "RIGHT"),
        ]
        for indice, linha in enumerate(self.visiveis, start=1):
            if linha.valor < 0:
                estilo.append(("TEXTCOLOR", (3, indice), (3, indice), colors.HexColor(COR_DEBITO)))
            if indice % 2 == 0:
                estilo.append(("BACKGROUND", (0, indice), (-1, indice), colors.HexColor(COR_ZEBRA)))
        tabela.setStyle(TableStyle(estilo))

        elementos.append(tabela)
        elementos.append(Spacer(1, 8))
        elementos.append(Paragraph(AVISO_LEGAL, estilo_aviso))

        def rodape(canvas, documento):
            canvas.saveState()
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(colors.HexColor("#666666"))
            canvas.drawString(10 * mm, 8 * mm, f"{EMPRESA} - {os.path.basename(self.caminho_atual or '')}")
            canvas.drawRightString(A4[0] - 10 * mm, 8 * mm, f"Pagina {documento.page}")
            canvas.restoreState()

        doc.build(elementos, onFirstPage=rodape, onLaterPages=rodape)

    def exportar_planilha(self) -> None:
        if not self.visiveis:
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar planilha",
            defaultextension=".xlsx",
            initialfile=self._nome_sugerido(".xlsx"),
            initialdir=self.config.get("ultima_pasta"),
            filetypes=[("Planilha do Excel", "*.xlsx"), ("CSV para Excel", "*.csv")],
        )
        if not destino:
            return
        try:
            if destino.lower().endswith(".csv"):
                self._gerar_csv(destino)
            else:
                self._gerar_xlsx(destino)
        except ImportError:
            self._erro(
                "Biblioteca ausente",
                "O arquivo .xlsx depende do pacote openpyxl.\n\n"
                "Instale com:\n    pip install openpyxl\n\nOu salve como .csv, que nao exige nada.",
            )
            return
        except PermissionError:
            self._erro("Arquivo em uso", "Feche a planilha no Excel antes de gravar por cima.")
            return
        except Exception as exc:
            self._erro("Erro ao salvar", f"Nao foi possivel gerar a planilha:\n\n{exc}")
            return
        self._sucesso(destino, "Planilha gerada com sucesso.")

    def _gerar_csv(self, destino: str) -> None:
        import csv

        # utf-8-sig + ';' fazem o Excel em portugues abrir o arquivo direito
        with open(destino, "w", encoding="utf-8-sig", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(["Data", "Tipo", "Historico", "Valor", "Saldo"])
            for linha in self.visiveis:
                escritor.writerow(
                    [
                        linha.data,
                        linha.tipo,
                        linha.historico,
                        formatar_moeda(linha.valor),
                        formatar_moeda(linha.saldo, ""),
                    ]
                )

    def _gerar_xlsx(self, destino: str) -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        planilha = Workbook()
        aba = planilha.active
        aba.title = "Extrato"

        cabecalhos = ["Data", "Tipo", "Historico", "Valor", "Saldo"]
        aba.append(cabecalhos)
        fundo = PatternFill("solid", fgColor="E8EEF5")
        for coluna in range(1, len(cabecalhos) + 1):
            celula = aba.cell(row=1, column=coluna)
            celula.font = Font(bold=True)
            celula.fill = fundo
            celula.alignment = Alignment(horizontal="center")

        for linha in self.visiveis:
            aba.append([linha.data, linha.tipo, linha.historico, linha.valor, linha.saldo])

        formato = 'R$ #,##0.00;[RED]-R$ #,##0.00'
        for fileira in aba.iter_rows(min_row=2, min_col=4, max_col=5):
            for celula in fileira:
                celula.number_format = formato

        for coluna, largura in zip(range(1, 6), (12, 16, 70, 16, 16)):
            aba.column_dimensions[get_column_letter(coluna)].width = largura

        aba.freeze_panes = "A2"
        aba.auto_filter.ref = f"A1:E{aba.max_row}"
        planilha.save(destino)

    # ------------------------------------------------------------------
    # Utilitarios
    # ------------------------------------------------------------------
    def _erro(self, titulo: str, mensagem: str) -> None:
        self.status.configure(text=titulo)
        messagebox.showerror(titulo, mensagem, parent=self.root)

    def _sucesso(self, destino: str, mensagem: str) -> None:
        self.status.configure(text=f"{mensagem} {destino}")
        if messagebox.askyesno("Concluido", f"{mensagem}\n\n{destino}\n\nDeseja abrir o arquivo agora?", parent=self.root):
            try:
                os.startfile(destino)  # type: ignore[attr-defined]
            except Exception:
                pass

    def _carregar_config(self) -> dict:
        try:
            with open(caminho_config(), encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
                return dados if isinstance(dados, dict) else {}
        except Exception:
            return {}

    def _salvar_config(self) -> None:
        try:
            self.config["geometria"] = self.root.geometry()
            caminho = caminho_config()
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as arquivo:
                json.dump(self.config, arquivo, ensure_ascii=False, indent=2)
        except Exception:
            pass  # preferencias sao um conforto, nunca um impeditivo

    def _ao_fechar(self) -> None:
        self._salvar_config()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    ConciliaApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
