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
DIAS_SEMANA_PT = ["SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO"]
FUNCOES_LOJA = ["Operador(a) de Caixa", "Empacotador(a)", "Fiscal de Caixa", "Recepção"]

HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "14:45 HRS", "15:00 HRS", "15:30 HRS", "15:45 HRS", 
    "16:00 HRS", "16:30 HRS", "16:45 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# --- CONSTANTES DE CORES (PARA O EXCEL) ---
H_VERMELHO = ["5:50 HRS", "6:30 HRS", "6:50 HRS"]
H_VERDE    = ["7:30 HRS", "8:00 HRS", "8:30 HRS", "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS"]
H_ROXO     = ["11:00 HRS", "11:30 HRS", "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS", "14:30 HRS", "14:45 HRS", "15:00 HRS", "15:30 HRS", "15:45 HRS", "16:00 HRS", "16:30 HRS", "16:45 HRS"]
H_CINZA    = ["Folga"]
H_AMARELO  = ["Ferias", "Afastado(a)", "Atestado"]

# --- LISTAS ESPECÍFICAS POR FUNÇÃO ---
LISTA_OPCOES_CAIXA = ["", "---", "Self", "Recepção", "Delivery", "Magazine"] + [str(i) for i in range(1, 18)]

# Para Empacotadores (Tarefas)
LISTA_TAREFAS_EMPACOTADOR = [
    "", "---", 
    "Varrer Estacionamento", 
    "Vasilhame", 
    "Devolução", 
    "Carrinho", 
    "Varrer Baias",
    "Recolher Cestas"
]

# --- LÓGICA DE CORTE MANHÃ / TARDE ---
def calcular_minutos(horario_str):
    if not isinstance(horario_str, str) or "HRS" not in horario_str: return 9999
    try:
        time_part = horario_str.split(' ')[0]
        h, m = map(int, time_part.split(':'))
        return h * 60 + m
    except:
        return 9999

# Regras de Negócio para Totais do Excel
HORARIOS_MANHA = [h for h in HORARIOS_PADRAO if "HRS" in h and calcular_minutos(h) > 0 and calcular_minutos(h) <= 600]
HORARIOS_TARDE = [h for h in HORARIOS_PADRAO if "HRS" in h and calcular_minutos(h) >= 570]

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

# --- Funções Auxiliares ---

def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

def formatar_lista_folgas_multilinha(lista_nomes, step=2):
    """Quebra a lista de nomes em várias linhas a cada 'step' nomes."""
    if not lista_nomes: return ""
    sorted_nomes = sorted([n for n in lista_nomes if n])
    chunks = [sorted_nomes[i:i + step] for i in range(0, len(sorted_nomes), step)]
    return "<br>".join([", ".join(chunk) for chunk in chunks])

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
                        prox_col_nome = str(df_excel.columns[col_idx + 1]).upper()
                        if "CX" in prox_col_nome or "TAREFA" in prox_col_nome:
                            val_caixa = row.iloc[col_idx + 1]
                            if not pd.isna(val_caixa):
                                caixa = str(val_caixa).strip().replace(".0", "")
                except: 
                    caixa = None
                
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

# --- NOVA FUNÇÃO: LAYOUT IDÊNTICO ÀS FOTOS + LÓGICA DE GRUPOS + COR DINÂMICA ---
def gerar_html_layout_exato(df_ops_dia, df_emp_dia, data_str, dia_semana, cor_tema):
    
    lista_op_folga = []
    lista_emp_folga = []
    status_invisivel = ["Ferias", "Afastado(a)", "Atestado", "", None]

    c_op_manha = 0; c_self_manha = 0
    c_op_tarde = 0; c_self_tarde = 0
    c_emp_manha = 0; c_emp_tarde = 0

    # --- PROCESSA OPERADORAS ---
    ops_agrupado = {} 
    
    # Ordem: Self -> 17 -> 16... -> Recepção/Delivery
    def sort_key_caixa(row):
        cx = str(row.get('numero_caixa', '')).strip().upper()
        cx = cx.replace('.0', '')
        if not cx or cx == 'NAN': return -999 # Sem caixa
        if cx == 'SELF': return 1000
        if cx.isdigit(): return int(cx)
        return -50 # Textos
    
    df_ops_dia['rank_cx'] = df_ops_dia.apply(sort_key_caixa, axis=1)
    df_ops_sorted = df_ops_dia.sort_values(by='rank_cx', ascending=False)

    for _, row in df_ops_sorted.iterrows():
        horario = str(row['horario'])
        nome = str(row['nome']).upper()
        cx = str(row.get('numero_caixa', '')).replace('.0', '')
        
        if horario in status_invisivel or horario == "nan": continue
        if "Folga" in horario:
            lista_op_folga.append(nome)
            continue
            
        mins = calcular_minutos(horario)
        is_self = (cx == "Self")
        
        # Filtro de Contagem: Recepção, Delivery e MAGAZINE NÃO contam
        cx_upper = cx.upper()
        is_excluded_count = (cx_upper in ["RECEPÇÃO", "DELIVERY", "MAGAZINE"])

        if mins <= 630: 
            if is_self: c_self_manha += 1
            elif not is_excluded_count: c_op_manha += 1
        if mins >= 570: 
            if is_self: c_self_tarde += 1
            elif not is_excluded_count: c_op_tarde += 1

        h_clean = horario.replace(" HRS", "H").replace(":", ":")
        if horario not in ops_agrupado: ops_agrupado[horario] = []
        ops_agrupado[horario].append({'cx': cx, 'nome': nome, 'h_clean': h_clean})

    # --- PROCESSA EMPACOTADORES ---
    emp_agrupado = {}
    df_emp_sorted = df_emp_dia.sort_values(by='nome')
    
    for _, row in df_emp_sorted.iterrows():
        horario = str(row['horario'])
        nome = str(row['nome']).upper()
        tarefa = str(row.get('numero_caixa', '')).replace('.0', '').strip()
        if tarefa == 'nan': tarefa = ""

        if horario in status_invisivel or horario == "nan": continue
        if "Folga" in horario:
            lista_emp_folga.append(nome)
            continue
            
        mins = calcular_minutos(horario)
        if mins <= 630: c_emp_manha += 1
        if mins >= 570: c_emp_tarde += 1
        
        h_clean = horario.replace(" HRS", "H").replace(":", ":")
        if horario not in emp_agrupado: emp_agrupado[horario] = []
        
        nome_display = nome
        if tarefa and tarefa != "nan" and tarefa != "":
            nome_display = f"{nome} <span style='font-size:0.85em'>({tarefa})</span>"
            
        emp_agrupado[horario].append({'nome': nome_display, 'h_clean': h_clean})

    # --- CRIA LISTA DE HORÁRIOS ÚNICOS E ORDENADOS ---
    todos_horarios = set(list(ops_agrupado.keys()) + list(emp_agrupado.keys()))
    horarios_ordenados = sorted(list(todos_horarios), key=lambda x: calcular_minutos(x))

    # --- MONTA AS LINHAS DA TABELA (5 COLUNAS) ---
    rows_html = ""
    
    for h_str in horarios_ordenados:
        h_clean = h_str.replace(" HRS", "H")
        
        ops_list = ops_agrupado.get(h_str, [])
        emp_list = emp_agrupado.get(h_str, [])
        
        zipped = list(zip_longest(ops_list, emp_list, fillvalue=None))
        
        if rows_html != "":
            # AQUI ESTÁ O AJUSTE PARA 6 COLUNAS DE ESPAÇO
            rows_html += "<tr class='spacer-row'><td colspan='6'></td></tr>"

        for idx, (op, emp) in enumerate(zipped):
            # Op
            if op:
                cx_display = op['cx']
                op_content = f"{op['nome']}" 
                op_html = f"<td class='cx-col'>{cx_display}</td><td class='nome-col'>{op_content}</td><td class='horario-col'>{op['h_clean']}</td>"
            else:
                op_html = "<td class='cx-col'></td><td class='nome-col'></td><td class='horario-col'></td>"
            
            # Emp
            if emp:
                emp_content = f"{emp['nome']}"
                emp_html = f"<td class='nome-col border-left'>{emp_content}</td><td class='horario-col'>{emp['h_clean']}</td>"
            else:
                emp_html = "<td class='nome-col border-left'></td><td class='horario-col'></td>"
            
            # ADICIONADA A COLUNA DIVISÓRIA NO MEIO
            rows_html += f"<tr>{op_html}<td class='divider-col'></td>{emp_html}</tr>"

    str_folga_op = formatar_lista_folgas_multilinha(lista_op_folga, step=2)
    str_folga_emp = formatar_lista_folgas_multilinha(lista_emp_folga, step=2)

    tot_op_m = c_op_manha + c_self_manha
    tot_op_t = c_op_tarde + c_self_tarde
    
    resumo_op = f"""
    MANHÃ: {c_op_manha:02d} OP + {c_self_manha} SELF = {tot_op_m:02d} OPERADORES<br>
    TARDE: {c_op_tarde:02d} OP + {c_self_tarde} SELF = {tot_op_t:02d} OPERADORES
    """
    
    resumo_emp = f"""
    MANHÃ: {c_emp_manha:02d} EMPACOTADORES<br>
    TARDE: {c_emp_tarde:02d} EMPACOTADORES
    """

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Escala {dia_semana}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@700&display=swap');
            
            @page {{ 
                size: portrait; 
                margin: 5mm; 
            }}

            body {{ 
                font-family: 'Roboto Condensed', 'Arial Narrow', Arial, sans-serif; 
                color: #000; 
                margin: 0; 
                padding: 10px; 
                background: white; 
                font-size: 11px;
                width: 100%;
            }}
            
            .header-main {{ 
                text-align: center;
                border-bottom: 3px solid {cor_tema}; 
                padding-bottom: 5px; 
                margin-bottom: 3px;
            }}
            .header-dia {{ font-size: 42px; font-weight: 900; text-transform: uppercase; line-height: 0.9; margin-bottom: 2px; }}
            .header-data {{ font-size: 28px; font-weight: bold; line-height: 1; color: {cor_tema}; }}

            table {{ width: 100%; border-collapse: collapse; border: 2px solid {cor_tema}; margin-bottom: 2px; }}
            
            thead th {{ 
                background-color: {cor_tema} !important; 
                color: #fff !important; 
                padding: 3px; 
                text-transform: uppercase; 
                border: 1px solid {cor_tema}; 
                font-size: 13px;
                text-align: center;
                -webkit-print-color-adjust: exact; 
            }}
            
            td {{ 
                padding: 1px 4px; 
                border: 1px solid {cor_tema}; 
                height: 16px; 
                vertical-align: middle;
                white-space: nowrap; 
                overflow: hidden;
            }}
            
            /* ESTILO DA COLUNA DIVISÓRIA COM A COR DO TEMA */
            .divider-col {{
                width: 8px;
                background-color: {cor_tema} !important;
                padding: 0;
                border: none;
                -webkit-print-color-adjust: exact;
            }}
            
            .spacer-row td {{ background-color: #999 !important; height: 3px; border: 1px solid {cor_tema}; padding:0; -webkit-print-color-adjust: exact; }}

            .cx-col {{ width: 45px; text-align: center; font-weight: bold; font-size: 13px; }}
            .horario-col {{ width: 55px; text-align: center; font-weight: bold; font-size: 11px; }}
            
            .nome-col {{ font-weight: bold; text-transform: uppercase; text-align: center; letter-spacing: -0.5px; }}
            
            .border-left {{ border-left: 3px solid {cor_tema}; }}

            tr:nth-child(even) {{ background-color: #d9d9d9 !important; -webkit-print-color-adjust: exact; }}

            .footer-container {{ display: flex; border: 2px solid {cor_tema}; border-top: none; }}
            .footer-box {{ width: 50%; }}
            .footer-header {{ background: {cor_tema} !important; color: #fff !important; text-align: center; font-weight: bold; font-size: 12px; padding: 2px; -webkit-print-color-adjust: exact; }}
            .footer-content {{ background: #eee !important; font-size: 10px; padding: 4px; text-align: center; min-height: 30px; text-transform: uppercase; -webkit-print-color-adjust: exact; line-height: 1.2; white-space: normal; }}
            
            .totals-container {{ display: flex; border: 2px solid {cor_tema}; border-top: none; background: {cor_tema} !important; color: #fff !important; -webkit-print-color-adjust: exact; }}
            .totals-box {{ width: 50%; font-size: 11px; font-weight: bold; padding: 4px; text-align: center; line-height: 1.3; }}

            @media print {{
                body {{ padding: 0; margin: 0; width: 100%; }}
                thead th, .footer-header, .totals-container {{ background-color: {cor_tema} !important; color: #fff !important; }}
                tr:nth-child(even), .footer-content {{ background-color: #ccc !important; }}
                .spacer-row td {{ background-color: #999 !important; }}
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
                    <th>OPERADOR(A)</th>
                    <th class="horario-col">HORÁRIO</th>
                    <th class="divider-col"></th>
                    <th class="border-left">EMPACOTADOR(A)</th>
                    <th class="horario-col">HORÁRIO</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div class="footer-container">
            <div class="footer-box" style="border-right: 2px solid {cor_tema};">
                <div class="footer-header">FOLGAS OPERADORES</div>
                <div class="footer-content">{str_folga_op}</div>
            </div>
            <div class="footer-box">
                <div class="footer-header">FOLGAS EMPACOTADORES</div>
                <div class="footer-content">{str_folga_emp}</div>
            </div>
        </div>

        <div class="totals-container">
            <div class="totals-box" style="border-right: 1px solid #fff;">
                {resumo_op}
            </div>
            <div class="totals-box">
                {resumo_emp}
            </div>
        </div>
    </body>
    </html>
    """

# --- ABAS ---

@st.fragment
def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.header("🔎 Visão Geral")
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
                if val_h in ["Folga", "Ferias", "Atestado", "Afastado(a)"]:
                    st.markdown("<div style='color: #aaa; text-align:center; font-size:14px; margin-top:5px;'>---</div>", unsafe_allow_html=True)
                    val_c = "---"
                else:
                    key_c = f"c_{colaborador}_{dia_atual.strftime('%Y%m%d')}"
                    
                    if is_operador:
                        lista_opcoes = LISTA_OPCOES_CAIXA
                    else:
                        lista_opcoes = LISTA_TAREFAS_EMPACOTADOR
                    
                    if caixa_atual and caixa_atual not in lista_opcoes:
                        lista_opcoes = [caixa_atual] + lista_opcoes
                        
                    idx_c = 0
                    if caixa_atual in lista_opcoes:
                        idx_c = lista_opcoes.index(caixa_atual)
                    
                    label_c = "C" if is_operador else "T"
                    val_c = st.selectbox(label_c, lista_opcoes, index=idx_c, key=key_c, label_visibility="collapsed")
                
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
                # Adiciona coluna extra para Operador (CX) E Empacotador (Tarefa)
                if funcao_selecionada == "Operador(a) de Caixa":
                     colunas.append(f"CX_REF_{d_str}")
                elif funcao_selecionada == "Empacotador(a)":
                     colunas.append(f"TAREFA_REF_{d_str}")

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
                    # Escreve as duas listas para validação
                    ws_data.write_column('B1', LISTA_OPCOES_CAIXA)
                    ws_data.write_column('C1', LISTA_TAREFAS_EMPACOTADOR)
                    
                    fmt_nome = workbook.add_format({'border': 1, 'valign': 'vcenter', 'align': 'left'})
                    worksheet.write(0, 0, "Nome", fmt_bold)
                    
                    # AJUSTE DA LARGURA DA COLUNA NOME
                    is_op = (funcao_selecionada == "Operador(a) de Caixa")
                    is_emp = (funcao_selecionada == "Empacotador(a)")
                    
                    width_name = 35 if is_op else 30
                    worksheet.set_column(0, 0, width_name, None)
                    
                    col_idx = 1
                    last_data_row = len(df_template) 
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
                            
                            if is_op or is_emp:
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
                        
                        if is_op or is_emp:
                            header_title = "CX" if is_op else "TAREFAS"
                            valid_list = '=Dados!$B$1:$B$' + str(len(LISTA_OPCOES_CAIXA)) if is_op else '=Dados!$C$1:$C$' + str(len(LISTA_TAREFAS_EMPACOTADOR))
                            
                            worksheet.write(0, col_idx, header_title, fmt_cx_header)
                            worksheet.set_column(col_idx, col_idx, 10, None)
                            worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': valid_list})
                            col_idx += 1
                    
                    # --- TOTAIS ---
                    mapa_nomes = {"Operador(a) de Caixa": "Operadoras", "Empacotador(a)": "Empacotadores", "Fiscal de Caixa": "Fiscais", "Recepção": "Recepção"}
                    nome_cargo = mapa_nomes.get(funcao_selecionada, funcao_selecionada)
                    
                    worksheet.write(row_total_m, 0, f"{nome_cargo} Manhã", fmt_manha)
                    worksheet.write(row_total_t, 0, f"{nome_cargo} Tarde", fmt_tarde)
                    
                    step = 2 if (is_op or is_emp) else 1
                    
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
                        
                        # LOGICA CONDICIONAL DE CONTAGEM PARA EXCEL (EXCLUIR RECEPÇÃO/DELIVERY/MAGAZINE)
                        if is_op:
                            # A coluna CX está em current_col + 1
                            letra_cx = num_to_col(current_col + 1)
                            rng_cx = f"{letra_cx}2:{letra_cx}{last_data_row+1}"
                            
                            # Adicionado MAGAZINE na exclusão
                            crit_m = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine")' for h in HORARIOS_MANHA])
                            crit_t = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine")' for h in HORARIOS_TARDE])
                        else:
                            # Contagem simples para empacotadores (ou outras funções)
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

    col_cor, col_rest = st.columns([1, 5])
    with col_cor:
        cor_tema = st.color_picker("Cor do Tema", "#000000")

    df_full = carregar_escala_semana_por_id(id_semana)
    df_dia = df_full[pd.to_datetime(df_full['data']).dt.date == data_selecionada].copy()
    if df_dia.empty: df_dia = pd.DataFrame(columns=['nome', 'funcao', 'horario', 'numero_caixa'])

    df_ops_base = df_colaboradores[df_colaboradores['funcao'] == 'Operador(a) de Caixa']
    df_emp_base = df_colaboradores[df_colaboradores['funcao'] == 'Empacotador(a)']

    df_ops_final = df_ops_base.merge(df_dia[['nome', 'horario', 'numero_caixa']], on='nome', how='left').fillna("")
    df_emp_final = df_emp_base.merge(df_dia[['nome', 'horario', 'numero_caixa']], on='nome', how='left').fillna("")

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
            df_emp_final[['nome', 'horario', 'numero_caixa']],
            column_config={"nome": "Nome", "horario": "Horário", "numero_caixa": "Tarefa/Obs"},
            hide_index=True, use_container_width=True, key=f"editor_emp_{data_selecionada}"
        )

    st.markdown("---")
    
    if st.button("🖨️ Gerar Impressão", type="primary"):
        html_content = gerar_html_layout_exato(df_ops_edited, df_emp_edited, data_selecionada.strftime('%d/%m/%Y'), dia_semana_nome, cor_tema)
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