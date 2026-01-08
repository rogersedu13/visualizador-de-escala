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
    horarios_ordenados = sorted(list(todos_horarios), key=