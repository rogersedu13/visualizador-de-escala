# Importando as bibliotecas necessárias
import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta, date
from supabase import create_client, Client
import time
import base64
import io
import random
from itertools import zip_longest 

# --- Constantes da Aplicação ---
DIAS_SEMANA_PT = ["Segunda-Feira", "Terça-Feira", "Quarta-Feira", "Quinta-Feira", "Sexta-Feira", "Sábado", "Domingo"]
FUNCOES_LOJA = ["Operador(a) de Caixa", "Empacotador(a)", "Fiscal de Caixa", "Recepção"]

HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# Lista de Caixas
LISTA_CAIXAS = ["", "---", "Self"] + [str(i) for i in range(1, 18)]

# --- LÓGICA DE CORTE MANHÃ / TARDE (AUXILIARES) ---
def calcular_minutos(horario_str):
    if not isinstance(horario_str, str) or "HRS" not in horario_str: return 9999
    try:
        time_part = horario_str.split(' ')[0]
        h, m = map(int, time_part.split(':'))
        return h * 60 + m
    except:
        return 9999

# Regras de Negócio
HORARIOS_RESTRITOS = ["9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS"]
CAIXAS_ESPECIAIS_LISTA = ["17", "16", "15", "01", "Self"] 
CAIXAS_RESTRITOS_LISTA = [str(i) for i in range(2, 11)]

HORARIOS_LIVRES_MANHA = ["5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS"]
HORARIOS_LIVRES_TARDE = ["11:00 HRS", "11:30 HRS", "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS", "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS"]
HORARIOS_LIVRES_TOTAL = HORARIOS_LIVRES_MANHA + HORARIOS_LIVRES_TARDE

# --- Configuração da Página ---
st.set_page_config(page_title="Frente de Caixa", page_icon="📅", layout="wide", initial_sidebar_state="expanded")

# --- Conexão Supabase ---
try:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("🚨 **Erro de Conexão:** Verifique os Secrets `supabase_url` e `supabase_key`.")
    st.stop()

# --- Estado da Sessão ---
if "logado" not in st.session_state: st.session_state.logado = False
if "nome_logado" not in st.session_state: st.session_state.nome_logado = ""

# --- Funções Auxiliares de Dados ---

def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

@st.cache_data(ttl=1) 
def carregar_colaboradores() -> pd.DataFrame:
    try:
        response = supabase.table('colaboradores').select('*').execute()
        df = pd.DataFrame(response.data)
        if not df.empty: 
            df['nome'] = df['nome'].str.strip()
            if 'funcao' not in df.columns: df['funcao'] = 'Operador(a) de Caixa'
            df['funcao'] = df['funcao'].fillna('Operador(a) de Caixa')
        return df
    except Exception as e: 
        return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_indice_semanas(apenas_ativas: bool = False) -> pd.DataFrame:
    try:
        query = supabase.table('semanas').select('id, nome_semana, data_inicio, ativa').order('data_inicio', desc=True)
        if apenas_ativas:
            query = query.eq('ativa', True)
        response = query.execute()
        return pd.DataFrame(response.data)
    except Exception as e: st.error(f"Erro ao carregar índice de semanas: {e}"); return pd.DataFrame()

@st.cache_data(ttl=10)
def carregar_escala_semana_por_id(id_semana: int) -> pd.DataFrame:
    try:
        params = {'p_semana_id': id_semana}
        response = supabase.rpc('get_escala_semana', params).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
            df['nome'] = df['nome'].str.strip()
            if 'numero_caixa' not in df.columns: df['numero_caixa'] = ""
            df['numero_caixa'] = df['numero_caixa'].fillna("")
            
            df_colabs = carregar_colaboradores()
            if not df_colabs.empty and 'funcao' in df_colabs.columns:
                df_colabs_unique = df_colabs.drop_duplicates(subset=['nome'])
                df = df.merge(df_colabs_unique[['nome', 'funcao']], on='nome', how='left')
                df['funcao'] = df['funcao'].fillna('Operador(a) de Caixa')
        return df
    except Exception as e: st.error(f"Erro ao carregar escala: {e}"); return pd.DataFrame()

def salvar_escala_individual(nome: str, horarios: list, caixas: list, data_inicio: date, id_semana: int) -> bool:
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            cx = caixas[i] if caixas and i < len(caixas) else None
            
            supabase.rpc('save_escala_dia_final', {
                'p_nome': nome.strip(), 
                'p_data': data_dia.strftime('%Y-%m-%d'), 
                'p_horario': horario, 
                'p_caixa': cx,
                'p_semana_id': id_semana
            }).execute()
        return True
    except Exception as e: st.error(f"Erro ao salvar: {e}"); return False

def salvar_escala_via_excel(df_excel: pd.DataFrame, data_inicio_semana: date, id_semana: int) -> bool:
    try:
        datas_reais = [(data_inicio_semana + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(7)]
        res_nomes = supabase.table('colaboradores').select('nome').execute()
        nomes_banco = {item['nome'] for item in res_nomes.data}
        barra = st.progress(0, text="Processando arquivo...")
        total_linhas = len(df_excel)
        for index, row in df_excel.iterrows():
            nome = row.get('Nome')
            if pd.isna(nome) or str(nome).strip() == "" or "TOTAL" in str(nome) or "Manhã" in str(nome) or "Tarde" in str(nome): continue
            nome_limpo = str(nome).strip()
            if nome_limpo not in nomes_banco:
                try:
                    supabase.table('colaboradores').insert({'nome': nome_limpo, 'funcao': 'Operador(a) de Caixa'}).execute()
                    nomes_banco.add(nome_limpo)
                except Exception as e: print(f"Erro auto-cadastro: {e}")
            for i in range(7):
                data_str_header = datas_reais[i]
                horario = ""
                if data_str_header in df_excel.columns:
                    horario = row[data_str_header]
                if pd.isna(horario): horario = ""
                horario = str(horario).strip()
                caixa = None
                try:
                    col_idx = df_excel.columns.get_loc(data_str_header)
                    if col_idx + 1 < len(df_excel.columns):
                        val_caixa = row.iloc[col_idx + 1]
                        if not pd.isna(val_caixa):
                            caixa = str(val_caixa).strip().replace(".0", "")
                except: caixa = None
                data_banco = (data_inicio_semana + timedelta(days=i)).strftime('%Y-%m-%d')
                supabase.rpc('save_escala_dia_final', {'p_nome': nome_limpo, 'p_data': data_banco, 'p_horario': horario, 'p_caixa': caixa, 'p_semana_id': id_semana}).execute()
            if index % 5 == 0: barra.progress((index + 1) / total_linhas, text=f"Importando linha {index+1}...")
        barra.empty()
        return True
    except Exception as e: st.error(f"Erro ao processar Excel: {e}"); return False

def inicializar_semana_simples(data_inicio: date) -> bool:
    try:
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        res = supabase.table('semanas').select('id').eq('data_inicio', data_inicio.strftime('%Y-%m-%d')).execute()
        if not res.data: return False
        new_id = res.data[0]['id']
        df_colabs = carregar_colaboradores()
        if not df_colabs.empty:
            for nome in df_colabs['nome']:
                for i in range(7):
                    d = data_inicio + timedelta(days=i)
                    supabase.rpc('save_escala_dia_final', {'p_nome': nome, 'p_data': d.strftime('%Y-%m-%d'), 'p_horario': '', 'p_caixa': None, 'p_semana_id': new_id}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def arquivar_reativar_semana(id_semana: int, novo_status: bool):
    try:
        func = 'reativar_semana' if novo_status else 'arquivar_semana'
        supabase.rpc(func, {'p_semana_id': id_semana}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def adicionar_colaborador(nome: str, funcao: str) -> bool:
    try:
        supabase.table('colaboradores').insert({'nome': nome.strip(), 'funcao': funcao}).execute()
        return True
    except Exception as e: st.error(f"Erro ao adicionar: {e}"); return False

def remover_colaboradores(lista_nomes: list) -> bool:
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': [n.strip() for n in lista_nomes]}).execute(); return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def atualizar_funcao_colaborador(nome: str, nova_funcao: str):
    try:
        supabase.table('colaboradores').update({'funcao': nova_funcao}).eq('nome', nome).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"},
        {"codigo": 1015, "nome": "Gisele", "senha": "3"},
        {"codigo": 1005, "nome": "Fabiana", "senha": "4"},
        {"codigo": 1016, "nome": "Amanda", "senha": "5"}
    ])

# --- FUNÇÕES DE IMPRESSÃO ---

# Impressão SEMANAL
def gerar_html_escala_semanal(df_escala: pd.DataFrame, nome_colaborador: str, semana_str: str) -> str:
    tabela_html = df_escala.to_html(index=False, border=0, justify="center", classes="tabela-escala")
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Escala {nome_colaborador}</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px; display: flex; justify-content: center; align-items: flex-start; min-height: 100vh; }}
            .container {{ background-color: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 100%; max-width: 700px; text-align: center; }}
            h1 {{ color: #2c3e50; font-size: 24px; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px; }}
            h2 {{ color: #7f8c8d; font-size: 16px; margin-top: 0; margin-bottom: 25px; font-weight: normal; }}
            table.tabela-escala {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            table.tabela-escala th {{ background-color: #34495e; color: white; padding: 12px; text-transform: uppercase; font-size: 12px; letter-spacing: 1px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
            table.tabela-escala td {{ padding: 12px; border-bottom: 1px solid #eee; color: #333; font-size: 14px; }}
            table.tabela-escala tr:last-child td {{ border-bottom: none; }}
            table.tabela-escala tr:nth-child(even) {{ background-color: #f9f9f9; }}
            @media print {{ body {{ background-color: white; }} .container {{ box-shadow: none; border: 1px solid #ddd; max-width: 100%; width: 100%; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Escala Semanal</h1>
            <h2>{nome_colaborador} <br> {semana_str}</h2>
            {tabela_html}
        </div>
    </body>
    </html>
    """

# --- NOVA FUNÇÃO: VISUAL EXATO DAS FOTOS COM CÁLCULO E ORDENAÇÃO ---
def gerar_html_layout_exato(df_ops_dia, df_emp_dia, data_str, dia_semana):
    
    lista_op_trabalha = []
    lista_op_folga = []
    
    lista_emp_trabalha = []
    lista_emp_folga = []

    # Contadores
    count_op_manha = 0
    count_op_tarde = 0
    count_self_manha = 0
    count_self_tarde = 0
    count_emp_manha = 0
    count_emp_tarde = 0

    status_invisivel = ["Ferias", "Afastado(a)", "Atestado", "", None]

    # --- PROCESSA OPERADORAS ---
    # Chave de Ordenação: 
    # 1. Horário (Cedo -> Tarde)
    # 2. Caixa (Self -> 17 -> 16... -> 1)
    def sort_key_op(row):
        h_str = str(row['horario'])
        mins = calcular_minutos(h_str)
        
        cx = str(row.get('numero_caixa', ''))
        cx = cx.replace('.0', '')
        
        cx_rank = 0
        if cx == 'Self': cx_rank = 100
        elif cx.isdigit(): cx_rank = int(cx)
        
        # Retorna tupla: (Minutos ASC, Rank Caixa DESC)
        # Como queremos Self primeiro e 17 antes de 16, usamos negativo ou invertemos a logica
        # Vamos usar: Minutos (crescente), Rank (decrescente)
        return (mins, -cx_rank)
    
    df_ops_dia['sort_temp'] = df_ops_dia.apply(sort_key_op, axis=1)
    df_ops_sorted = df_ops_dia.sort_values(by='sort_temp')

    for _, row in df_ops_sorted.iterrows():
        nome = str(row['nome']).upper()
        horario = str(row['horario'])
        caixa = str(row.get('numero_caixa', '')).replace('.0', '')
        mins = calcular_minutos(horario)
        
        if horario in status_invisivel or horario == "nan": continue 
        
        if "Folga" in horario:
            lista_op_folga.append(nome)
        else:
            h_clean = horario.replace(" HRS", "H").replace(":", ":")
            lista_op_trabalha.append({'cx': caixa, 'nome': nome, 'horario': h_clean})
            
            # Contagem Lógica Excel
            is_self = (caixa == "Self")
            if mins <= 600: # Manhã (<= 10:00)
                if is_self: count_self_manha += 1
                else: count_op_manha += 1
            else: # Tarde
                if is_self: count_self_tarde += 1
                else: count_op_tarde += 1

    # --- PROCESSA EMPACOTADORES ---
    # Ordenação: Horário -> Nome
    def sort_key_emp(row):
        return (calcular_minutos(str(row['horario'])), str(row['nome']))
    
    df_emp_dia['sort_temp'] = df_emp_dia.apply(sort_key_emp, axis=1)
    df_emp_sorted = df_emp_dia.sort_values(by='sort_temp')

    for _, row in df_emp_sorted.iterrows():
        nome = str(row['nome']).upper()
        horario = str(row['horario'])
        mins = calcular_minutos(horario)
        
        if horario in status_invisivel or horario == "nan": continue
        
        if "Folga" in horario:
            lista_emp_folga.append(nome)
        else:
            h_clean = horario.replace(" HRS", "H")
            lista_emp_trabalha.append({'nome': nome, 'horario': h_clean})
            
            if mins <= 600: count_emp_manha += 1
            else: count_emp_tarde += 1

    # --- MONTA AS LINHAS DA TABELA ---
    rows_html = ""
    zipped = list(zip_longest(lista_op_trabalha, lista_emp_trabalha, fillvalue=None))
    
    for idx, (op, emp) in enumerate(zipped):
        bg_class = "even" if idx % 2 == 0 else "odd"
        
        # Coluna Esq
        if op:
            cx_display = op['cx'] if op['cx'] else ""
            op_html = f"<td class='cx-col'>{cx_display}</td><td class='nome-col'>{op['nome']}</td><td class='horario-col'>{op['horario']}</td>"
        else:
            op_html = "<td class='cx-col'></td><td class='nome-col'></td><td class='horario-col'></td>"
            
        # Coluna Dir
        if emp:
            emp_html = f"<td class='nome-col' style='border-left: 2px solid #000;'>{emp['nome']}</td><td class='horario-col'>{emp['horario']}</td>"
        else:
            emp_html = "<td class='nome-col' style='border-left: 2px solid #000;'></td><td class='horario-col'></td>"
            
        rows_html += f"<tr class='{bg_class}'>{op_html}{emp_html}</tr>"

    # Strings Finais
    str_folga_op = ", ".join(sorted(lista_op_folga))
    str_folga_emp = ", ".join(sorted(lista_emp_folga))

    # Totais Calculados
    total_op_manha = count_op_manha + count_self_manha
    total_op_tarde = count_op_tarde + count_self_tarde
    
    str_resumo_manha = f"MANHÃ: {count_op_manha:02d} OP + {count_self_manha} SELF = {total_op_manha:02d} OPERADORES"
    str_resumo_tarde = f"TARDE: {count_op_tarde:02d} OP + {count_self_tarde} SELF = {total_op_tarde:02d} OPERADORES"
    
    str_resumo_emp = f"MANHÃ: {count_emp_manha:02d} EMPACOTADORES | TARDE: {count_emp_tarde:02d} EMPACOTADORES"

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Escala {dia_semana}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@400;700&display=swap');
            
            body {{ 
                font-family: 'Roboto Condensed', 'Arial Narrow', Arial, sans-serif; 
                color: #000; 
                margin: 0; 
                padding: 10px; 
                background: white; 
                font-size: 13px; /* Fonte levemente menor pra caber nomes grandes */
            }}
            
            .header-main {{ 
                text-align: center;
                border-bottom: 3px solid #000; 
                padding-bottom: 5px; 
                margin-bottom: 5px;
            }}
            .header-dia {{ font-size: 34px; font-weight: 900; text-transform: uppercase; line-height: 1; }}
            .header-data {{ font-size: 24px; font-weight: bold; line-height: 1; margin-top: 5px; }}

            table {{ width: 100%; border-collapse: collapse; border: 2px solid #000; }}
            
            thead th {{ 
                background-color: #222 !important; 
                color: #fff !important; 
                padding: 4px; 
                text-transform: uppercase; 
                border: 1px solid #000; 
                font-size: 13px;
                -webkit-print-color-adjust: exact; 
            }}
            
            td {{ padding: 2px 4px; border: 1px solid #000; vertical-align: middle; height: 18px; }}
            
            .cx-col {{ width: 35px; text-align: center; font-weight: bold; font-size: 14px; }}
            .nome-col {{ text-align: center; font-weight: bold; text-transform: uppercase; white-space: nowrap; overflow: hidden; }}
            .horario-col {{ width: 80px; text-align: center; font-size: 12px; }}
            
            tr.odd {{ background-color: #fff !important; }}
            tr.even {{ background-color: #d9d9d9 !important; -webkit-print-color-adjust: exact; }}

            .footer-row {{ display: flex; border: 2px solid #000; border-top: none; }}
            .footer-col {{ width: 50%; }}
            .footer-header {{ 
                background-color: #222 !important; color: #fff !important; 
                text-align: center; font-weight: bold; padding: 4px; font-size: 13px; 
                border-bottom: 1px solid #000; -webkit-print-color-adjust: exact; 
            }}
            .footer-content {{ 
                padding: 5px; font-size: 11px; text-align: center; 
                min-height: 40px; background-color: #eee !important; 
                line-height: 1.3; text-transform: uppercase; -webkit-print-color-adjust: exact; 
            }}
            
            /* Tarja Preta Final com Totais */
            .total-bar {{
                background-color: #000 !important;
                color: #fff !important;
                text-align: center;
                padding: 6px;
                font-weight: bold;
                font-size: 13px;
                margin-top: 3px;
                -webkit-print-color-adjust: exact;
                line-height: 1.4;
            }}

            @media print {{
                body {{ padding: 0; margin: 0; }}
                thead th {{ background-color: #000 !important; color: #fff !important; }}
                tr.even {{ background-color: #ccc !important; }}
                .footer-header {{ background-color: #000 !important; color: #fff !important; }}
                .total-bar {{ background-color: #000 !important; color: #fff !important; }}
            }}
        </style>
    </head>
    <body>
        <div class="header-main">
            <div class="header-dia">{dia_semana.split('-')[0]}</div>
            <div class="header-data">DATA: {data_str}</div>
        </div>

        <table>
            <thead>
                <tr>
                    <th class="cx-col">CX</th>
                    <th>CAIXA</th>
                    <th class="horario-col">HORÁRIO</th>
                    <th>PACOTE</th>
                    <th class="horario-col">HORÁRIO</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div class="footer-row">
            <div class="footer-col" style="border-right: 2px solid #000;">
                <div class="footer-header">FOLGAS OPERADORES</div>
                <div class="footer-content">{str_folga_op}</div>
            </div>
            <div class="footer-col">
                <div class="footer-header">FOLGAS EMPACOTADORES</div>
                <div class="footer-content">{str_folga_emp}</div>
            </div>
        </div>
        
        <div class="total-bar">
            {str_resumo_manha}<br>
            {str_resumo_tarde}<br>
            <span style="font-size: 11px; font-weight: normal;">{str_resumo_emp}</span>
        </div>

    </body>
    </html>
    """

# --- ABAS ---

@st.fragment
def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.header("🔎 Consultar Minha Escala")
    if df_colaboradores.empty: st.warning("Nenhum colaborador cadastrado."); return

    nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
    nome_selecionado = st.selectbox("1. Selecione seu nome:", options=nomes_disponiveis)

    if nome_selecionado:
        is_operador = False
        if 'funcao' in df_colaboradores.columns:
            f = df_colaboradores[df_colaboradores['nome'] == nome_selecionado]['funcao']
            if not f.empty and f.iloc[0] == "Operador(a) de Caixa": is_operador = True

        if df_semanas_ativas.empty: st.info("Nenhuma semana disponível."); return
        opcoes_semana = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for index, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("2. Selecione a semana:", options=opcoes_semana.keys())

        if semana_str:
            semana_info = opcoes_semana[semana_str]
            with st.container(border=True):
                df = carregar_escala_semana_por_id(semana_info['id'])
                final = df[df['nome'] == nome_selecionado].sort_values("data")
                if not final.empty:
                    display = final.copy()
                    display["Data"] = display["data"].apply(formatar_data_completa)
                    
                    cols_to_show = ["Data", "horario"]
                    if is_operador:
                        cols_to_show.append("numero_caixa")
                        display.rename(columns={"horario": "Horário", "numero_caixa": "Caixa"}, inplace=True)
                        cols_renamed = ["Data", "Horário", "Caixa"]
                    else:
                        display.rename(columns={"horario": "Horário"}, inplace=True)
                        cols_renamed = ["Data", "Horário"]

                    st.dataframe(display[cols_renamed], use_container_width=True, hide_index=True)
                    
                    html = gerar_html_escala_semanal(display[cols_renamed], nome_selecionado, semana_str)
                    b64 = base64.b64encode(html.encode('utf-8')).decode()
                    nome_arq = f"escala_{nome_selecionado.strip().replace(' ','_')}.html"
                    st.markdown(f'<a href="data:text/html;charset=utf-8;base64,{b64}" download="{nome_arq}" style="background-color:#0068c9;color:white;padding:0.5em;text-decoration:none;border-radius:5px;">🖨️ Baixar para Impressão</a>', unsafe_allow_html=True)
                else:
                    st.info("Sem horários para esta semana.")

def aba_gerenciar_semanas(df_semanas_todas: pd.DataFrame):
    st.subheader("🗓️ Gerenciar Semanas")
    with st.container(border=True):
        st.markdown("##### ➕ Inicializar Nova Semana")
        hoje = date.today()
        prox_segunda = hoje + timedelta(days=(7 - hoje.weekday()))
        data_sel = st.date_input("Início da Semana (Segunda-feira):", value=prox_segunda)
        if st.button("✨ Inicializar Semana", type="primary", use_container_width=True):
            data_inicio = data_sel - timedelta(days=data_sel.weekday())
            if inicializar_semana_simples(data_inicio):
                st.cache_data.clear(); st.success("Semana inicializada!"); time.sleep(1.5); st.rerun()
    st.markdown("---"); st.markdown("##### 📂 Histórico")
    if not df_semanas_todas.empty:
        for index, row in df_semanas_todas.iterrows():
            c1, c2, c3 = st.columns([4, 1, 1])
            status_icon = "🟢" if row['ativa'] else "📁"
            c1.markdown(f"**{status_icon} {row['nome_semana']}**")
            key_arch = f"btn_arch_{row['id']}"
            if row['ativa']:
                if c2.button("Arquivar", key=key_arch):
                    arquivar_reativar_semana(row['id'], False); st.cache_data.clear(); st.rerun()
            else:
                if c2.button("Reativar", key=key_arch):
                    arquivar_reativar_semana(row['id'], True); st.cache_data.clear(); st.rerun()
    else: st.info("Nenhuma semana criada.")

@st.fragment
def aba_editar_escala_individual(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("✏️ Editar Escala")
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return

    filtro_funcao = st.selectbox("Filtrar por Função:", ["Todos"] + FUNCOES_LOJA)
    colabs_filtrados = df_colaboradores.copy()
    if filtro_funcao != "Todos" and 'funcao' in colabs_filtrados.columns:
        colabs_filtrados = colabs_filtrados[colabs_filtrados['funcao'] == filtro_funcao]

    c1, c2 = st.columns(2)
    with c1:
        opcoes = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("Selecione a semana:", options=opcoes.keys())
        semana_info = opcoes[semana_str]
    with c2:
        nomes = sorted(colabs_filtrados['nome'].unique())
        colaborador = st.selectbox("Selecione o colaborador:", nomes)

    st.markdown("---")
    if semana_info and colaborador:
        id_semana = semana_info['id']; data_ini = semana_info['data_inicio']
        df_full = carregar_escala_semana_por_id(id_semana)
        escala_colab = df_full[df_full['nome'] == colaborador] if not df_full.empty else pd.DataFrame()
        
        horarios_atuais = {pd.to_datetime(row['data']).date(): row['horario'] for _, row in escala_colab.iterrows()}
        caixas_atuais = {pd.to_datetime(row['data']).date(): row['numero_caixa'] for _, row in escala_colab.iterrows()}

        funcao_atual = "Não definido"
        if 'funcao' in df_colaboradores.columns:
            f = df_colaboradores[df_colaboradores['nome'] == colaborador]['funcao']
            if not f.empty: funcao_atual = f.iloc[0]
        
        is_operador = (funcao_atual == "Operador(a) de Caixa")

        st.markdown(f"**Editando:** `{colaborador}` ({funcao_atual})")
        
        cols = st.columns(7)
        novos_horarios = []
        novos_caixas = []
        
        for i in range(7):
            dia_atual = data_ini + timedelta(days=i)
            dia_label = f"{DIAS_SEMANA_PT[i]}\n({dia_atual.strftime('%d/%m')})"
            
            horario_atual = horarios_atuais.get(dia_atual, "")
            caixa_atual = caixas_atuais.get(dia_atual, "")
            if pd.isna(caixa_atual): caixa_atual = ""
            
            idx_h = HORARIOS_PADRAO.index(horario_atual) if horario_atual in HORARIOS_PADRAO else 0
            
            with cols[i]:
                st.caption(dia_label)
                key_h = f"h_{colaborador}_{dia_atual.strftime('%Y%m%d')}"
                val_h = st.selectbox("H", HORARIOS_PADRAO, index=idx_h, key=key_h, label_visibility="collapsed")
                novos_horarios.append(val_h)
                
                val_c = None
                if is_operador:
                    if val_h in ["Folga", "Ferias", "Atestado", "Afastado(a)"]:
                        st.markdown("<div style='color: #aaa; text-align:center; font-size:14px; margin-top:5px;'>---</div>", unsafe_allow_html=True)
                        val_c = "---"
                    else:
                        key_c = f"c_{colaborador}_{dia_atual.strftime('%Y%m%d')}"
                        idx_c = LISTA_CAIXAS.index(caixa_atual) if caixa_atual in LISTA_CAIXAS else 0
                        val_c = st.selectbox("C", LISTA_CAIXAS, index=idx_c, key=key_c, label_visibility="collapsed")
                
                novos_caixas.append(val_c)
        
        st.markdown("")
        if st.button("💾 Salvar Alterações", type="primary", use_container_width=True):
            if salvar_escala_individual(colaborador, novos_horarios, novos_caixas, data_ini, id_semana):
                st.cache_data.clear() 
                st.success(f"Salvo!"); time.sleep(1); st.rerun()

@st.fragment
def aba_importar_excel(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("📤 Importar / Baixar Escala (Excel)")
    st.info("Utilize esta aba para baixar a escala pronta (como backup/impressão) ou para baixar o modelo e preencher offline.")
    
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    
    col1, col2 = st.columns(2)
    with col1:
        funcao_selecionada = st.selectbox("1. Qual função?", FUNCOES_LOJA, key="sel_func_down")
    with col2:
        opcoes = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("2. Qual semana?", options=opcoes.keys(), key="sel_sem_imp")
        semana_info = opcoes[semana_str]
    
    if semana_info and funcao_selecionada:
        data_ini = semana_info['data_inicio']
        id_semana = semana_info['id']
        
        df_dados_db = carregar_escala_semana_por_id(id_semana)
        
        df_filtrado = df_colaboradores.copy()
        if 'funcao' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['funcao'] == funcao_selecionada]
        
        if df_filtrado.empty:
            st.error(f"Não há colaboradores com função '{funcao_selecionada}'.")
        else:
            colunas = ['Nome']
            for i in range(7):
                d_str = (data_ini + timedelta(days=i)).strftime('%d/%m/%Y')
                colunas.append(d_str)
                if funcao_selecionada == "Operador(a) de Caixa":
                    colunas.append(f"CX_REF_{d_str}")

            df_template = pd.DataFrame(columns=colunas)
            df_template['Nome'] = sorted(df_filtrado['nome'].unique())
            
            dados_existentes = {}
            if not df_dados_db.empty:
                df_db_filt = df_dados_db[df_dados_db['nome'].isin(df_filtrado['nome'])]
                for _, row_db in df_db_filt.iterrows():
                    d_db = pd.to_datetime(row_db['data']).date()
                    dados_existentes[(row_db['nome'], d_db)] = {
                        'horario': row_db['horario'],
                        'caixa': row_db['numero_caixa']
                    }
            
            buffer = io.BytesIO()
            try:
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    df_template.to_excel(writer, index=False, sheet_name='Escala')
                    workbook = writer.book
                    worksheet = writer.sheets['Escala']

                    worksheet.hide_gridlines(2)
                    
                    fmt_grid = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
                    fmt_bold = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#D3D3D3', 'border': 1})
                    fmt_date_header = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#DDEBF7', 'border': 1, 'font_color': 'black'}) 
                    fmt_cx_header = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#FFF2CC', 'border': 1, 'font_color': 'black'})
                    
                    fmt_manha = workbook.add_format({'bold': True, 'font_color': 'blue', 'bg_color': '#E0F7FA', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                    fmt_tarde = workbook.add_format({'bold': True, 'font_color': 'orange', 'bg_color': '#FFF3E0', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                    
                    fmt_vermelho = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                    fmt_verde    = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                    fmt_roxo     = workbook.add_format({'bg_color': '#E6E6FA', 'font_color': '#4B0082', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                    fmt_cinza    = workbook.add_format({'bg_color': '#D3D3D3', 'font_color': '#000000', 'align': 'center', 'valign': 'vcenter', 'border': 1})
                    fmt_amarelo  = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700', 'align': 'center', 'valign': 'vcenter', 'border': 1})

                    ws_data = workbook.add_worksheet('Dados'); ws_data.hide()
                    ws_data.write_column('A1', HORARIOS_PADRAO)
                    ws_data.write_column('B1', LISTA_CAIXAS)
                    
                    fmt_nome = workbook.add_format({'border': 1, 'valign': 'vcenter', 'align': 'left'})
                    worksheet.write(0, 0, "Nome", fmt_bold)
                    
                    worksheet.set_column(0, 0, 30, None)
                    
                    col_idx = 1
                    last_data_row = len(df_template) # Ex: 10 nomes
                    row_total_m = last_data_row + 1
                    row_total_t = last_data_row + 2
                    
                    for r_idx, row_name in enumerate(df_template['Nome']):
                        row_excel = r_idx + 1
                        worksheet.write(row_excel, 0, row_name, fmt_nome)
                        
                        current_c = 1
                        for i_day in range(7):
                            d_atual = data_ini + timedelta(days=i_day)
                            info = dados_existentes.get((row_name, d_atual), {})
                            
                            h_val = info.get('horario', "")
                            worksheet.write(row_excel, current_c, h_val, fmt_grid)
                            current_c += 1
                            
                            if funcao_selecionada == "Operador(a) de Caixa":
                                c_val = info.get('caixa', "")
                                worksheet.write(row_excel, current_c, c_val, fmt_grid)
                                current_c += 1

                    col_idx = 1
                    for i in range(7):
                        d_str = (data_ini + timedelta(days=i)).strftime('%d/%m/%Y')
                        
                        worksheet.write(0, col_idx, d_str, fmt_date_header)
                        worksheet.set_column(col_idx, col_idx, 12, None)
                        
                        worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$A$1:$A$' + str(len(HORARIOS_PADRAO))})
                        
                        for h in H_VERMELHO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_vermelho})
                        for h in H_VERDE: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_verde})
                        for h in H_ROXO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_roxo})
                        for h in H_CINZA: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_cinza})
                        for h in H_AMARELO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_amarelo})

                        col_idx += 1
                        
                        if funcao_selecionada == "Operador(a) de Caixa":
                            worksheet.write(0, col_idx, "CX", fmt_cx_header)
                            worksheet.set_column(col_idx, col_idx, 5, None)
                            worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$B$1:$B$' + str(len(LISTA_CAIXAS))})
                            col_idx += 1
                    
                    # --- TOTAIS ---
                    mapa_nomes = {"Operador(a) de Caixa": "Operadoras", "Empacotador(a)": "Empacotadores", "Fiscal de Caixa": "Fiscais", "Recepção": "Recepção"}
                    nome_cargo = mapa_nomes.get(funcao_selecionada, funcao_selecionada)
                    
                    worksheet.write(row_total_m, 0, f"{nome_cargo} Manhã", fmt_manha)
                    worksheet.write(row_total_t, 0, f"{nome_cargo} Tarde", fmt_tarde)
                    
                    step = 2 if funcao_selecionada == "Operador(a) de Caixa" else 1
                    def num_to_col(n):
                        s = ""
                        while n >= 0:
                            s = chr(n % 26 + 65) + s
                            n = n // 26 - 1
                        return s

                    total_data_cols = 7
                    current_col = 1
                    for i in range(total_data_cols):
                        letra = num_to_col(current_col)
                        rng = f"{letra}2:{letra}{last_data_row+1}"
                        
                        crit_m = ",".join([f'COUNTIF({rng}, "{h}")' for h in HORARIOS_MANHA])
                        crit_t = ",".join([f'COUNTIF({rng}, "{h}")' for h in HORARIOS_TARDE])
                        
                        if crit_m:
                            worksheet.write_formula(row_total_m, current_col, f"=SUM({crit_m})", fmt_manha)
                        else:
                            worksheet.write(row_total_m, current_col, 0, fmt_manha)

                        if crit_t:
                            worksheet.write_formula(row_total_t, current_col, f"=SUM({crit_t})", fmt_tarde)
                        else:
                            worksheet.write(row_total_t, current_col, 0, fmt_tarde)
                            
                        current_col += step

            except Exception as e: st.error(f"Erro ao gerar Excel: {e}"); return

            st.download_button(label=f"📥 Baixar Planilha (Preenchida ou Modelo)", data=buffer.getvalue(), file_name=f"escala_{funcao_selecionada.split()[0]}_{data_ini.strftime('%d-%m')}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type="secondary")
            
            st.markdown("---")
            arquivo_upload = st.file_uploader("Arraste o Excel preenchido para Salvar:", type=["xlsx"], key="upl_excel_uniq")
            if arquivo_upload is not None:
                if st.button("🚀 Processar e Salvar", type="primary", key="btn_proc_excel"):
                    if salvar_escala_via_excel(pd.read_excel(arquivo_upload), data_ini, id_semana):
                        st.success("Importado com sucesso!"); time.sleep(2); st.cache_data.clear(); st.rerun()

@st.fragment
def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Gerenciar Colaboradores")
    st.markdown("##### ✏️ Classificar / Editar Colaboradores Existentes")
    
    if not df_colaboradores.empty:
        mapa_original = {row['nome']: row['funcao'] for _, row in df_colaboradores.iterrows()}
        df_editor = df_colaboradores.copy()
        
        col_config = {
            "nome": st.column_config.TextColumn("Nome", disabled=True),
            "funcao": st.column_config.SelectboxColumn("Função (Cargo)", options=FUNCOES_LOJA, required=True, width="medium")
        }
        
        df_editado = st.data_editor(
            df_editor[['nome', 'funcao']], 
            column_config=col_config, 
            use_container_width=True,
            key="editor_colabs",
            num_rows="fixed"
        )
        
        if st.button("💾 Salvar Alterações de Cargo"):
            barra = st.progress(0, text="Atualizando cargos...")
            total = len(df_editado)
            contador_updates = 0
            
            for index, row in df_editado.iterrows():
                nome = row['nome']
                nova_funcao = row['funcao']
                funcao_antiga = mapa_original.get(nome, "")
                if nova_funcao != funcao_antiga:
                    atualizar_funcao_colaborador(nome, nova_funcao)
                    contador_updates += 1
                if index % 5 == 0: barra.progress((index+1)/total)
            
            barra.empty()
            if contador_updates > 0: st.success(f"{contador_updates} cargos atualizados!")
            else: st.info("Nenhuma alteração.")
            time.sleep(1); st.cache_data.clear(); st.rerun()
    else:
        st.info("Sem colaboradores cadastrados.")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("##### ➕ Adicionar Novo")
            nome_novo = st.text_input("Nome:")
            funcao_novo = st.selectbox("Função:", FUNCOES_LOJA, key="add_new_role")
            if st.button("Adicionar", use_container_width=True):
                if nome_novo: 
                    adicionar_colaborador(nome_novo, funcao_novo)
                    st.cache_data.clear()
                    st.success("Adicionado!")
                    time.sleep(1)
                    st.rerun()

    with c2:
        with st.container(border=True):
            st.markdown("##### ➖ Remover")
            if not df_colaboradores.empty:
                rem = st.multiselect("Selecione para remover:", df_colaboradores['nome'])
                if st.button("Remover Selecionados", type="secondary", use_container_width=True):
                    if rem: 
                        remover_colaboradores(rem)
                        st.cache_data.clear()
                        st.success("Removido!")
                        time.sleep(1)
                        st.rerun()

# --- ABA DE ESCALA DIÁRIA (IMPRESSÃO ESTILO FOTO - PRETO E BRANCO) ---
@st.fragment
def aba_escala_diaria_impressao(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("🖨️ Escala Diária (Impressão)")
    st.info("Selecione a semana e o dia específico para editar e imprimir a escala diária.")

    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return

    opcoes = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
    semana_str = st.selectbox("1. Selecione a Semana:", options=opcoes.keys())
    semana_info = opcoes[semana_str]
    id_semana = semana_info['id']
    data_inicio_semana = semana_info['data_inicio']

    dias_opcoes = [f"{DIAS_SEMANA_PT[i]} ({(data_inicio_semana + timedelta(days=i)).strftime('%d/%m')})" for i in range(7)]
    dia_selecionado_str = st.selectbox("2. Selecione o Dia:", dias_opcoes)
    idx_dia = dias_opcoes.index(dia_selecionado_str)
    data_selecionada = data_inicio_semana + timedelta(days=idx_dia)
    dia_semana_nome = DIAS_SEMANA_PT[data_selecionada.weekday()].upper()

    st.markdown("---")

    df_full = carregar_escala_semana_por_id(id_semana)
    df_dia = df_full[pd.to_datetime(df_full['data']).dt.date == data_selecionada].copy()
    if df_dia.empty: df_dia = pd.DataFrame(columns=['nome', 'funcao', 'horario', 'numero_caixa'])

    df_ops_base = df_colaboradores[df_colaboradores['funcao'] == 'Operador(a) de Caixa']
    df_emp_base = df_colaboradores[df_colaboradores['funcao'] == 'Empacotador(a)']

    df_ops_final = df_ops_base.merge(df_dia[['nome', 'horario', 'numero_caixa']], on='nome', how='left').fillna("")
    df_emp_final = df_emp_base.merge(df_dia[['nome', 'horario']], on='nome', how='left').fillna("")

    df_ops_final = df_ops_final.sort_values('nome')
    df_emp_final = df_emp_final.sort_values('nome')

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🛒 Operadoras")
        df_ops_edited = st.data_editor(
            df_ops_final[['nome', 'horario', 'numero_caixa']],
            column_config={"nome": "Nome", "horario": "Horário", "numero_caixa": "Caixa"},
            hide_index=True, use_container_width=True, key=f"editor_ops_{data_selecionada}"
        )
    with c2:
        st.markdown("### 📦 Empacotadores")
        df_emp_edited = st.data_editor(
            df_emp_final[['nome', 'horario']],
            column_config={"nome": "Nome", "horario": "Horário"},
            hide_index=True, use_container_width=True, key=f"editor_emp_{data_selecionada}"
        )

    st.markdown("---")
    
    if st.button("🖨️ Gerar Impressão (Estilo Exato)", type="primary"):
        html_content = gerar_html_layout_exato(df_ops_edited, df_emp_edited, data_selecionada.strftime('%d/%m/%Y'), dia_semana_nome)
        b64 = base64.b64encode(html_content.encode('utf-8')).decode()
        st.markdown(f'<a href="data:text/html;charset=utf-8;base64,{b64}" download="escala_diaria_{data_selecionada.strftime("%d_%m")}.html" style="background-color:#0068c9;color:white;padding:10px 20px;text-decoration:none;border-radius:5px;font-weight:bold;">📥 Baixar Arquivo de Impressão</a>', unsafe_allow_html=True)
        with st.expander("Pré-visualização"): st.components.v1.html(html_content, height=600, scrolling=True)

# --- Main ---
def main():
    st.title("📅 Sistema de Escalas")
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_semanas = carregar_indice_semanas()
    df_semanas_ativas = df_semanas[df_semanas['ativa'] == True] if not df_semanas.empty else pd.DataFrame()

    with st.sidebar:
        st.header("Acesso")
        if not st.session_state.logado:
            with st.form("login"):
                c = st.text_input("Código"); s = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary"):
                    auth = df_fiscais[(df_fiscais['codigo'] == int(c)) & (df_fiscais['senha'] == s)] if c.isdigit() else pd.DataFrame()
                    if not auth.empty: st.session_state.logado = True; st.session_state.nome_logado = auth.iloc[0]['nome']; st.rerun()
                    else: st.error("Inválido")
        else:
            st.success(f"Olá, {st.session_state.nome_logado}")
            if st.button("Sair"): st.session_state.logado = False; st.rerun()
        st.markdown("---"); st.caption("DEV @Rogério Souza")

    if st.session_state.logado:
        t1, t2, t3, t4, t5, t6 = st.tabs(["🗓️ Gerenciar Semanas", "✏️ Editar Manual", "🖨️ Escala Diária", "📤 Importar / Baixar", "👥 Colaboradores", "👁️ Visão Geral"])
        with t1: aba_gerenciar_semanas(df_semanas)
        with t2: aba_editar_escala_individual(df_colaboradores, df_semanas_ativas)
        with t3: aba_escala_diaria_impressao(df_colaboradores, df_semanas_ativas) 
        with t4: aba_importar_excel(df_colaboradores, df_semanas_ativas)
        with t5: aba_gerenciar_colaboradores(df_colaboradores)
        with t6: aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)

if __name__ == "__main__":
    main()