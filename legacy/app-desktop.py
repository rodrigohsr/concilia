import sys
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
from ofx_parser import OFXParserBR
from fpdf import FPDF
from PIL import Image, ImageTk

# Função para o PyInstaller encontrar arquivos injetados
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class LeitorOFXApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Leitor de Extratos OFX - Esquema Assessoria Contábil")
        self.root.geometry("1200x630")
        
        # Ícone do cifrão na janela do programa
        try:
            self.root.iconbitmap(resource_path("cifrao.ico"))
        except:
            pass
        
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # 1. CABEÇALHO
        self.header_frame = tk.Frame(root, bg="white")
        self.header_frame.pack(fill="x", side="top")
        
        try:
            img_path = resource_path("logo.png")
            img = Image.open(img_path)
            altura_maxima = 65
            proporcao = altura_maxima / float(img.size[1])
            largura_nova = int(float(img.size[0]) * float(proporcao))
            img = img.resize((largura_nova, altura_maxima), Image.LANCZOS)
            
            self.logo_img = ImageTk.PhotoImage(img)
            self.title_label = tk.Label(self.header_frame, image=self.logo_img, bg="white")
        except Exception:
            self.title_label = tk.Label(self.header_frame, text="🧾 Extrato Bancário Corporativo", font=("Arial", 14, "bold"), fg="#333333", bg="white")
            
        self.title_label.pack(anchor="center", pady=(15, 5))
        
        self.info_label = tk.Label(self.header_frame, text="Aguardando abertura de arquivo OFX...", font=("Arial", 10), fg="#333333", bg="white", justify="center")
        self.info_label.pack(anchor="center", pady=(0, 15))

        self.separator = tk.Frame(root, bg="#00a8e8", height=3) 
        self.separator.pack(fill="x")

        # 2. BARRA DE FERRAMENTAS
        self.toolbar = tk.Frame(root, height=40, bg="#f4f6f9", bd=1, relief="groove")
        self.toolbar.pack(fill="x")
        
        self.btn_open = ttk.Button(self.toolbar, text="📂 Abrir Arquivo OFX", command=self.select_file)
        self.btn_open.pack(side="left", padx=10, pady=5)
        
        self.btn_export = ttk.Button(self.toolbar, text="📥 Exportar para PDF", command=self.export_pdf, state="disabled")
        self.btn_export.pack(side="left", padx=5, pady=5)
        
        # 3. PAINEL DA TABELA
        self.table_frame = tk.Frame(root)
        self.table_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        columns = ("data", "tipo", "descricao", "valor", "saldo")
        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings", selectmode="extended")
        
        self.tree.heading("data", text="Data Mov.")
        self.tree.heading("tipo", text="Tipo")
        self.tree.heading("descricao", text="Histórico")
        self.tree.heading("valor", text="Valor")
        self.tree.heading("saldo", text="Saldo")
        
        self.tree.column("data", width=100, anchor="center")
        self.tree.column("tipo", width=90, anchor="center")
        self.tree.column("descricao", width=550, anchor="w")
        self.tree.column("valor", width=140, anchor="e")
        self.tree.column("saldo", width=140, anchor="e")
        
        self.tree.tag_configure("debit", foreground="#cc0000")
        
        vsb = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        
        self.tree.bind("<Control-c>", self.copy_to_clipboard)
        
        self.df_data = None
        
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path):
                self.root.after(100, lambda: self.load_ofx(file_path))

    def copy_to_clipboard(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        clipboard_text = ""
        for item in selected_items:
            row_values = self.tree.item(item)['values']
            historico = str(row_values[2])
            clipboard_text += historico + "\n"
            
        self.root.clipboard_clear()
        self.root.clipboard_append(clipboard_text.strip("\n"))
        self.root.update()

    def format_currency(self, val):
        if val is None: return "0,00"
        p = f"{val:,.2f}"
        return p.replace(",", "X").replace(".", ",").replace("X", ".")

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Arquivos Bancários", "*.ofx")])
        if file_path:
            self.load_ofx(file_path)

    def load_ofx(self, file_path):
        try:
            parser = OFXParserBR()
            extrato = parser.parse_file(file_path)
            
            bancos_br = {
                "0237": "Bradesco", "237": "Bradesco", "0341": "Itaú", "341": "Itaú",
                "0001": "Banco do Brasil", "001": "Banco do Brasil", "1": "Banco do Brasil",
                "0104": "Caixa Econômica", "104": "Caixa Econômica", "0033": "Santander", "033": "Santander", "33": "Santander",
                "0748": "Sicredi", "748": "Sicredi", "0756": "Sicoob", "756": "Sicoob",
                "0197": "Stone", "197": "Stone", "0260": "Nubank", "260": "Nubank",
                "0077": "Banco Inter", "077": "Banco Inter", "77": "Banco Inter", "0336": "C6 Bank", "336": "C6 Bank"
            }
            
            banco_id = extrato.conta.bank_id or "Desconhecido"
            nome_banco = bancos_br.get(banco_id, "Banco")
            banco_display = f"{nome_banco} ({banco_id})" if banco_id != "Desconhecido" else "Desconhecido"
            conta = extrato.conta.acct_id or "Não informada"
            
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            transactions = [vars(t) for t in extrato.transacoes]
            self.df_data = pd.DataFrame(transactions)
            
            if 'dt_posted_iso' in self.df_data.columns:
                self.df_data = self.df_data.sort_values(by='dt_posted_iso', ascending=True).reset_index(drop=True)
            
            total_movido = self.df_data['valor'].fillna(0).sum()
            saldo_final_arquivo = getattr(extrato, 'saldo_final', None)
            
            if saldo_final_arquivo is not None:
                saldo_inicial = saldo_final_arquivo - total_movido
                self.df_data['saldo_real'] = saldo_inicial + self.df_data['valor'].fillna(0).cumsum()
                
                txt_saldo_ant = "R$ " + self.format_currency(saldo_inicial)
                txt_saldo_fin = "R$ " + self.format_currency(saldo_final_arquivo)
                
                self.info_label.config(text=f"Instituição: {banco_display}   |   Conta Corrente: {conta}   |   Lançamentos: {len(extrato.transacoes)}\nSaldo Anterior: {txt_saldo_ant}   |   Saldo Final do Período: {txt_saldo_fin}")
            else:
                self.df_data['saldo_real'] = None
                self.info_label.config(text=f"Instituição: {banco_display}   |   Conta Corrente: {conta}   |   Lançamentos: {len(extrato.transacoes)}\n(Saldos não informados no arquivo)")
            
            self.df_data['Data_Formatada'] = pd.to_datetime(self.df_data['dt_posted_iso']).dt.strftime('%d/%m/%Y')
            
            for _, row in self.df_data.iterrows():
                val_float = float(row['valor']) if row['valor'] is not None else 0.0
                val_str = self.format_currency(val_float)
                
                if val_float >= 0:
                    val_str += " C"
                    tag = () 
                else:
                    val_str = val_str.replace("-", "") + " D"
                    tag = ("debit",)
                    
                saldo_val = row.get('saldo_real')
                if pd.isna(saldo_val) or saldo_val is None:
                    saldo_str = "-"
                else:
                    saldo_float = float(saldo_val)
                    saldo_str = self.format_currency(saldo_float)
                    if saldo_float >= 0:
                        saldo_str += " C"
                    else:
                        saldo_str = saldo_str.replace("-", "") + " D"

                self.tree.insert("", "end", values=(row['Data_Formatada'], row['tipo'], row['memo'], val_str, saldo_str), tags=tag)
            
            self.btn_export.config(state="normal")
            
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler este arquivo OFX:\n{str(e)}")

    def export_pdf(self):
        if self.df_data is not None:
            save_path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("Documento PDF", "*.pdf")])
            if save_path:
                try:
                    pdf = FPDF(orientation='P', unit='mm', format='A4')
                    pdf.set_auto_page_break(auto=True, margin=15)
                    pdf.set_margins(10, 15, 10)
                    pdf.add_page()

                    pdf.set_font("Arial", 'B', 16)
                    pdf.cell(0, 10, "Extrato Bancário".encode('latin-1', 'replace').decode('latin-1'), 0, 1, 'C')
                    pdf.ln(2)

                    pdf.set_font("Arial", '', 9) 
                    info_text = self.info_label.cget("text").replace("\n", "  |  ")
                    info_text = info_text.encode('latin-1', 'replace').decode('latin-1')
                    pdf.cell(0, 8, info_text, 0, 1, 'C')
                    pdf.ln(5)

                    col_widths = [22, 18, 90, 30, 30]
                    headers = ['Data', 'Tipo', 'Histórico', 'Valor', 'Saldo']

                    pdf.set_font("Arial", 'B', 9)
                    for i in range(len(headers)):
                        txt = headers[i].encode('latin-1', 'replace').decode('latin-1')
                        pdf.cell(col_widths[i], 8, txt, border=1, align='C')
                    pdf.ln()

                    pdf.set_font("Arial", '', 8) 
                    for item in self.tree.get_children():
                        row = self.tree.item(item)['values']
                        
                        data = str(row[0]).encode('latin-1', 'replace').decode('latin-1')
                        tipo = str(row[1]).encode('latin-1', 'replace').decode('latin-1')
                        hist = str(row[2])[:55].encode('latin-1', 'replace').decode('latin-1') 
                        valor = str(row[3]).encode('latin-1', 'replace').decode('latin-1')
                        saldo = str(row[4]).encode('latin-1', 'replace').decode('latin-1')

                        pdf.cell(col_widths[0], 6, data, border=1, align='C')
                        pdf.cell(col_widths[1], 6, tipo, border=1, align='C')
                        pdf.cell(col_widths[2], 6, hist, border=1, align='L')
                        pdf.cell(col_widths[3], 6, valor, border=1, align='R')
                        pdf.cell(col_widths[4], 6, saldo, border=1, align='R')
                        pdf.ln()

                    pdf.ln(5)
                    pdf.set_font("Arial", 'I', 8)
                    aviso = "Extrato gerado para conferencia, não substitui o original e pode apresentar divergencias."
                    pdf.cell(0, 5, aviso.encode('latin-1', 'replace').decode('latin-1'), 0, 1, 'C')

                    pdf.output(save_path)
                    messagebox.showinfo("Sucesso", "O extrato foi exportado para PDF com sucesso!")
                except Exception as e:
                    messagebox.showerror("Erro ao Salvar", f"Não foi possível gerar o arquivo PDF:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = LeitorOFXApp(root)
    root.mainloop()