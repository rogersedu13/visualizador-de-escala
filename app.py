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
LISTA_OPCOES_CAIXA = ["", "---", "Self", "Recepção", "Delivery", "Magazine", "Salinha"] + [str(i) for i in range(1, 18)]

# Para Empacotadores (Tarefas)
LISTA_TAREFAS_EMPACOTADOR = [
    "", "---", 
    "Varrer Estacionamento", 
    "Vasilhame", 
    "Devolução", 
    "Carrinho", 
    "Varrer Baias", 
    "Recolher Cestas",
    "Lavar carrinhos"
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

# Regras de Negócio para Totais do Excel (Padrao Geral)
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
            if 'nome_social' not in df.columns: df['nome_social'] = None
            if 'folga_fixa' not in df.columns: df['folga_fixa'] = None
            df['funcao'] = df['funcao'].fillna('Operador(a) de Caixa')
            df['nome_social'] = df['nome_social'].fillna('')
            df['folga_fixa'] = df['folga_fixa'].fillna('')
        return df
    except Exception as e: 
        return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_indice_semanas(apenas_ativas: bool = False) -> pd.DataFrame:
    try:
        query = supabase.table('semanas').select('id, nome_semana, data_inicio, ativa').order('data_inicio', desc=True)
        if apenas_ativas: query = query.eq('ativa', True)
        response = query.execute()
        return pd.DataFrame(response.data)
    except Exception as e: st.error(f"Erro ao carregar índice de semanas: {e}"); return pd.DataFrame()

@st.cache_data(ttl=10)
def carregar_escala_semana_por_id(id_semana: int) -> pd.DataFrame:
    try:
        params = {'p_semana_id': int(id_semana)}
        response = supabase.rpc('get_escala_semana', params).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
            df['nome'] = df['nome'].str.strip()
            if 'numero_caixa' not in df.columns: df['numero_caixa'] = ""
            df['numero_caixa'] = df['numero_caixa'].fillna("")
            
            df_colabs = carregar_colaboradores()
            if not df_colabs.empty and 'funcao' in df_colabs.columns:
                cols_to_merge = ['nome', 'funcao']
                if 'nome_social' in df_colabs.columns: cols_to_merge.append('nome_social')
                df_colabs_unique = df_colabs.drop_duplicates(subset=['nome'])
                df = df.merge(df_colabs_unique[cols_to_merge], on='nome', how='left')
                df['funcao'] = df['funcao'].fillna('Operador(a) de Caixa')
                if 'nome_social' in df.columns: df['nome_social'] = df['nome_social'].fillna('')
        return df
    except Exception as e: st.error(f"Erro ao carregar escala: {e}"); return pd.DataFrame()

def salvar_escala_individual(nome: str, horarios: list, caixas: list, data_inicio: date, id_semana: int) -> bool:
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            cx = caixas[i] if caixas and i < len(caixas) else None
            supabase.rpc('save_escala_dia_final', {'p_nome': nome.strip(), 'p_data': data_dia.strftime('%Y-%m-%d'), 'p_horario': horario, 'p_caixa': cx, 'p_semana_id': int(id_semana)}).execute()
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
                except: pass
            for i in range(7):
                data_str_header = datas_reais[i]
                horario = ""
                if data_str_header in df_excel.columns: horario = row[data_str_header]
                if pd.isna(horario): horario = ""
                horario = str(horario).strip()
                caixa = None
                try:
                    col_idx = df_excel.columns.get_loc(data_str_header)
                    if col_idx + 1 < len(df_excel.columns):
                        prox_col_nome = str(df_excel.columns[col_idx + 1]).upper()
                        if "CX" in prox_col_nome or "TAREFA" in prox_col_nome:
                            val_caixa = row.iloc[col_idx + 1]
                            if not pd.isna(val_caixa): caixa = str(val_caixa).strip().replace(".0", "")
                except: caixa = None
                data_banco = (data_inicio_semana + timedelta(days=i)).strftime('%Y-%m-%d')
                supabase.rpc('save_escala_dia_final', {'p_nome': nome_limpo, 'p_data': data_banco, 'p_horario': horario, 'p_caixa': caixa, 'p_semana_id': int(id_semana)}).execute()
            if index % 5 == 0: barra.progress((index + 1) / total_linhas)
        barra.empty()
        return True
    except Exception as e: st.error(f"Erro ao processar Excel: {e}"); return False

def inicializar_semana_simples(data_inicio: date) -> bool:
    try:
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        res = supabase.table('semanas').select('id').eq('data_inicio', data_inicio.strftime('%Y-%m-%d')).execute()
        if not res.data: return False
        new_id = int(res.data[0]['id'])
        df_colabs = carregar_colaboradores()
        if not df_colabs.empty:
            for index, row in df_colabs.iterrows():
                nome = row['nome']
                folga_fixa = row.get('folga_fixa', '')
                for i in range(7):
                    d = data_inicio + timedelta(days=i)
                    dia_semana_nome = DIAS_SEMANA_PT[d.weekday()]
                    horario_padrao = "Folga" if folga_fixa == dia_semana_nome else ""
                    supabase.rpc('save_escala_dia_final', {'p_nome': nome, 'p_data': d.strftime('%Y-%m-%d'), 'p_horario': horario_padrao, 'p_caixa': None, 'p_semana_id': new_id}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def arquivar_reativar_semana(id_semana: int, novo_status: bool):
    try:
        func = 'reativar_semana' if novo_status else 'arquivar_semana'
        supabase.rpc(func, {'p_semana_id': int(id_semana)}).execute()
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

def atualizar_dados_colaborador(nome: str, nova_funcao: str, novo_nome_social: str, nova_folga: str):
    try:
        supabase.table('colaboradores').update({'funcao': nova_funcao, 'nome_social': novo_nome_social, 'folga_fixa': nova_folga}).eq('nome', nome).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def salvar_pedido(nome, texto):
    try:
        supabase.table('pedidos').insert({'nome': nome, 'descricao': texto}).execute()
        return True
    except Exception as e: st.error(f"Erro ao salvar pedido: {e}"); return False

def carregar_pedidos():
    try:
        response = supabase.table('pedidos').select('*').order('created_at', desc=True).execute()
        return pd.DataFrame(response.data)
    except Exception as e: return pd.DataFrame()

def atualizar_status_pedido(id_pedido, novo_status):
    try:
        supabase.table('pedidos').update({'status': novo_status}).eq('id', int(id_pedido)).execute()
        return True
    except Exception as e: st.error(f"Erro ao atualizar: {e}"); return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"},
        {"codigo": 1015, "nome": "Gisele", "senha": "3"},
        {"codigo": 1005, "nome": "Fabiana", "senha": "4"},
        {"codigo": 1016, "nome": "Amanda", "senha": "5"}
    ])

# --- FUNÇÃO DE ALOCAÇÃO AUTOMÁTICA DE HORÁRIOS (RODÍZIO) ---
def gerar_alocacao_semanal(df_colabs_op, data_ini_atual, df_semanas_todas):
    n_total = len(df_colabs_op)
    if n_total == 0: return {}
    vagas_650 = int(n_total * 0.35)
    vagas_1200 = int(n_total * 0.45)
    vagas_1000 = n_total - vagas_650 - vagas_1200 
    vagas_disponiveis = {"6:50 HRS": vagas_650, "10:00 HRS": vagas_1000, "12:00 HRS": vagas_1200}
    data_menos_7 = (data_ini_atual - timedelta(days=7)).strftime('%Y-%m-%d')
    data_menos_14 = (data_ini_atual - timedelta(days=14)).strftime('%Y-%m-%d')
    semanas_passadas = df_semanas_todas[df_semanas_todas['data_inicio'].isin([data_menos_7, data_menos_14])]
    historico_colabs = {row['nome']: {"6:50 HRS": 0, "10:00 HRS": 0, "12:00 HRS": 0} for _, row in df_colabs_op.iterrows()}
    for _, row_sem in semanas_passadas.iterrows():
        id_sem = int(row_sem['id'])
        data_ini_sem = row_sem['data_inicio']
        peso = 10 if data_ini_sem == data_menos_7 else 1
        df_escala = carregar_escala_semana_por_id(id_sem)
        if not df_escala.empty:
            for _, row in df_escala.iterrows():
                nome = row['nome']; h = row['horario']
                if h == "9:30 HRS": h = "10:00 HRS"
                if nome in historico_colabs and h in historico_colabs[nome]:
                    historico_colabs[nome][h] += peso
    alocacao = {}
    nomes_embaralhados = list(historico_colabs.keys())
    random.shuffle(nomes_embaralhados) 
    prefs = {}
    for nome in nomes_embaralhados:
        prefs[nome] = sorted(["6:50 HRS", "10:00 HRS", "12:00 HRS"], key=lambda t: historico_colabs[nome][t])
    nomes_embaralhados.sort(key=lambda n: historico_colabs[n][prefs[n][1]] - historico_colabs[n][prefs[n][0]], reverse=True)
    for nome in nomes_embaralhados:
        alocado = False
        for t in prefs[nome]:
            if vagas_disponiveis[t] > 0:
                alocacao[nome] = t; vagas_disponiveis[t] -= 1; alocado = True; break
        if not alocado:
            for t in vagas_disponiveis.keys():
                if vagas_disponiveis[t] > 0:
                    alocacao[nome] = t; vagas_disponiveis[t] -= 1; break
    return alocacao

# --- FUNÇÕES DE LÓGICA DA ESCALA MÁGICA (ETAPA 2) ---
def trabalhou_na_data(nome, data_alvo, df_semanas_todas):
    for _, w in df_semanas_todas.iterrows():
        try:
            d_ini = pd.to_datetime(w['data_inicio']).date()
            d_fim = d_ini + timedelta(days=6)
            if d_ini <= data_alvo <= d_fim:
                df_esc = carregar_escala_semana_por_id(int(w['id']))
                if not df_esc.empty:
                    df_esc['data_date'] = pd.to_datetime(df_esc['data']).dt.date
                    row = df_esc[(df_esc['nome'] == nome) & (df_esc['data_date'] == data_alvo)]
                    if not row.empty:
                        h = str(row.iloc[0]['horario'])
                        if h and "HRS" in h: return True
        except: pass
    return False

def atribuir_caixas_dia(dia_items):
    alocacao = {}
    abertura = []
    fechamento = []
    intermediario = []
    
    for nome, h in dia_items:
        if not isinstance(h, str) or "Folga" in h or "Feria" in h or "Afast" in h or "Atest" in h or h.strip() == "" or h.strip() == "nan":
            alocacao[nome] = "---"
            continue
            
        if h in ["9:30 HRS", "10:00 HRS", "10:30 HRS"]:
            intermediario.append(nome)
        elif calcular_minutos(h) <= 540: # <= 9:00 -> Abertura
            abertura.append(nome)
        else: # > 9:00 -> Fechamento
            fechamento.append(nome)
            
    caixas_prioridade = ['Self', '17', '16', '15', '5', '1']
    caixas_pares = ['14', '12', '10', '8', '6', '4', '2']
    caixas_impares = ['13', '11', '9', '7', '3']
    
    random.shuffle(intermediario)
    disp_pares = list(caixas_pares)
    for nome in intermediario:
        if disp_pares: alocacao[nome] = disp_pares.pop(0)
        else: alocacao[nome] = ""
        
    random.shuffle(abertura)
    disp_pri_m = list(caixas_prioridade)
    disp_imp_m = list(caixas_impares)
    for nome in abertura:
        if disp_pri_m: alocacao[nome] = disp_pri_m.pop(0)
        elif disp_imp_m: alocacao[nome] = disp_imp_m.pop(0)
        else: alocacao[nome] = ""
        
    random.shuffle(fechamento)
    disp_pri_t = list(caixas_prioridade) 
    disp_imp_t = list(caixas_impares)
    for nome in fechamento:
        if disp_pri_t: alocacao[nome] = disp_pri_t.pop(0)
        elif disp_imp_t: alocacao[nome] = disp_imp_t.pop(0)
        else: alocacao[nome] = ""
        
    return alocacao


# --- FUNÇÕES DE IMPRESSÃO E LAYOUT ---
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
            table.tabela-escala {{ width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: auto; }}
            table.tabela-escala th {{ background-color: #34495e; color: white; padding: 12px; text-transform: uppercase; font-size: 12px; letter-spacing: 1px; border-top-left-radius: 4px; border-top-right-radius: 4px; }}
            table.tabela-escala td {{ padding: 12px; border-bottom: 1px solid #eee; color: #333; font-size: 14px; white-space: nowrap; }}
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

def gerar_html_layout_exato(df_ops_dia, df_emp_dia, data_str, dia_semana, cor_tema):
    lista_op_folga = []
    lista_emp_folga = []
    status_invisivel = ["Ferias", "Afastado(a)", "Atestado", "", None]
    c_op_manha = 0; c_self_manha = 0; c_op_tarde = 0; c_self_tarde = 0; c_emp_manha = 0; c_emp_tarde = 0
    flat_ops_data = []; flat_emp_data = []

    def sort_key_caixa(row):
        cx = str(row.get('numero_caixa', '')).strip().upper()
        cx = cx.replace('.0', '')
        if not cx or cx == 'NAN': return -999 
        if cx == 'SELF': return 1000
        if cx.isdigit(): return int(cx)
        return -50 
    
    if not df_ops_dia.empty:
        df_ops_dia['rank_cx'] = df_ops_dia.apply(sort_key_caixa, axis=1)
    else:
        df_ops_dia['rank_cx'] = []
        
    df_ops_sorted = df_ops_dia.sort_values(by='rank_cx', ascending=False) if not df_ops_dia.empty else df_ops_dia

    for _, row in df_ops_sorted.iterrows():
        horario = str(row['horario'])
        if 'nome_impressao' in row and pd.notna(row['nome_impressao']) and str(row['nome_impressao']).strip() != "": nome = str(row['nome_impressao']).upper()
        elif 'nome_social' in row and pd.notna(row['nome_social']) and str(row['nome_social']).strip() != "": nome = str(row['nome_social']).upper()
        else: nome = str(row['nome']).upper()
            
        cx = str(row.get('numero_caixa', '')).replace('.0', '')
        if horario in status_invisivel or horario == "nan": continue
        if "Folga" in horario:
            lista_op_folga.append(nome); continue
            
        mins = calcular_minutos(horario)
        is_self = (cx == "Self")
        cx_upper = cx.upper()
        is_excluded_count = (cx_upper in ["RECEPÇÃO", "DELIVERY", "MAGAZINE", "SALINHA"])

        if mins == 450: 
            if is_self: c_self_manha += 1
            elif not is_excluded_count: c_op_manha += 1
            if is_self: c_self_tarde += 1
            elif not is_excluded_count: c_op_tarde += 1
        else:
            if mins <= 630: 
                if is_self: c_self_manha += 1
                elif not is_excluded_count: c_op_manha += 1
            if mins >= 570: 
                if is_self: c_self_tarde += 1
                elif not is_excluded_count: c_op_tarde += 1

        h_clean = horario.replace(" HRS", "H").replace(":", ":")
        flat_ops_data.append({ 'cx': cx, 'nome': nome, 'h_clean': h_clean, 'mins': mins, 'rank': row.get('rank_cx', -999), 'has_separator': False })

    df_emp_sorted = df_emp_dia.sort_values(by='nome')
    for _, row in df_emp_sorted.iterrows():
        horario = str(row['horario'])
        if 'nome_impressao' in row and pd.notna(row['nome_impressao']) and str(row['nome_impressao']).strip() != "": nome = str(row['nome_impressao']).upper()
        elif 'nome_social' in row and pd.notna(row['nome_social']) and str(row['nome_social']).strip() != "": nome = str(row['nome_social']).upper()
        else: nome = str(row['nome']).upper()

        tarefa = str(row.get('numero_caixa', '')).replace('.0', '').strip()
        if tarefa == 'nan': tarefa = ""

        if horario in status_invisivel or horario == "nan": continue
        if "Folga" in horario:
            lista_emp_folga.append(nome); continue
            
        mins = calcular_minutos(horario)
        if mins <= 630: c_emp_manha += 1
        if mins >= 570: c_emp_tarde += 1
        
        h_clean = horario.replace(" HRS", "H").replace(":", ":")
        nome_display = nome
        if tarefa and tarefa != "nan" and tarefa != "": nome_display = f"{nome} <span style='font-size:0.85em'>({tarefa})</span>"
            
        flat_emp_data.append({ 'nome': nome_display, 'h_clean': h_clean, 'mins': mins, 'has_separator': False })

    flat_ops_data.sort(key=lambda x: (x['mins'], -x['rank']))
    flat_emp_data.sort(key=lambda x: (x['mins'], x['nome']))

    for i in range(len(flat_ops_data) - 1):
        if flat_ops_data[i]['h_clean'] != flat_ops_data[i+1]['h_clean']: flat_ops_data[i]['has_separator'] = True
    for i in range(len(flat_emp_data) - 1):
        if flat_emp_data[i]['h_clean'] != flat_emp_data[i+1]['h_clean']: flat_emp_data[i]['has_separator'] = True

    final_emp_list = []
    for emp in flat_emp_data:
        final_emp_list.append(emp)
        if emp.get('has_separator'): final_emp_list.append(None) 
            
    rows_html = ""
    for op, emp in zip_longest(flat_ops_data, final_emp_list, fillvalue=None):
        op_html = ""
        op_class_extra = " separator-bottom" if (op and op['has_separator']) else ""
        if op: op_html = f"<td class='cx-col{op_class_extra}'>{op['cx']}</td><td class='nome-col{op_class_extra}'>{op['nome']}</td><td class='horario-col{op_class_extra}'>{op['h_clean']}</td>"
        else: op_html = "<td class='cx-col'></td><td class='nome-col'></td><td class='horario-col'></td>"
        
        emp_html = ""
        emp_class_extra = " separator-bottom" if (emp and emp.get('has_separator')) else ""
        if emp: emp_html = f"<td class='col-emp-nome border-left{emp_class_extra}'>{emp['nome']}</td><td class='horario-col{emp_class_extra}'>{emp['h_clean']}</td>"
        else: emp_html = "<td class='col-emp-nome border-left'></td><td class='horario-col'></td>"
            
        rows_html += f"<tr>{op_html}<td class='divider-col'></td>{emp_html}</tr>"

    str_folga_op = formatar_lista_folgas_multilinha(lista_op_folga, step=2)
    str_folga_emp = formatar_lista_folgas_multilinha(lista_emp_folga, step=2)

    tot_op_m = c_op_manha + c_self_manha; tot_op_t = c_op_tarde + c_self_tarde
    resumo_op = f"MANHÃ: {c_op_manha:02d} OP + {c_self_manha} SELF = {tot_op_m:02d} OPERADORES<br>TARDE: {c_op_tarde:02d} OP + {c_self_tarde} SELF = {tot_op_t:02d} OPERADORES"
    resumo_emp = f"MANHÃ: {c_emp_manha:02d} EMPACOTADORES<br>TARDE: {c_emp_tarde:02d} EMPACOTADORES"

    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Escala {dia_semana}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Roboto+Condensed:wght@700&display=swap');
            @page {{ size: portrait; margin: 5mm; }}
            body {{ font-family: 'Roboto Condensed', 'Arial Narrow', Arial, sans-serif; color: #000; margin: 0; padding: 10px; background: white; font-size: 16px; width: 90%; margin-left: auto; margin-right: auto; zoom: 90%; }}
            .print-frame {{ border: 4px solid {cor_tema}; padding: 15px; width: 100%; box-sizing: border-box; }}
            .header-main {{ text-align: center; border-bottom: 3px solid {cor_tema}; padding-bottom: 5px; margin-bottom: 3px; }}
            .header-dia {{ font-size: 42px; font-weight: 900; text-transform: uppercase; line-height: 0.9; margin-bottom: 2px; }}
            .header-data {{ font-size: 28px; font-weight: bold; line-height: 1; color: #000; }}
            table {{ width: 100%; border-collapse: collapse; border: 2px solid {cor_tema}; margin-bottom: 2px; table-layout: fixed; }}
            thead th {{ background-color: {cor_tema} !important; color: #fff !important; padding: 6px; text-transform: uppercase; border: 1px solid {cor_tema}; font-size: 19px; text-align: center; -webkit-print-color-adjust: exact; }}
            td {{ padding: 4px; border: 1px solid {cor_tema}; height: 28px; vertical-align: middle; white-space: nowrap; overflow: hidden; text-align: center; }}
            .separator-bottom {{ border-bottom: 4px solid #000 !important; }}
            .cx-col {{ width: 8%; font-weight: bold; font-size: 20px; }} 
            .col-op-nome {{ width: 31.5%; font-weight: bold; font-size: 18px; }} 
            .horario-col {{ width: 10%; font-weight: bold; font-size: 18px; }} 
            .divider-col {{ width: 1%; background-color: {cor_tema} !important; padding: 0; border: none; -webkit-print-color-adjust: exact; }}
            .col-emp-nome {{ width: 39.5%; font-weight: bold; font-size: 18px; }} 
            .nome-col {{ font-weight: bold; text-transform: uppercase; letter-spacing: -0.5px; }}
            .border-left {{ border-left: 3px solid {cor_tema}; }}
            tr:nth-child(even) {{ background-color: #d9d9d9 !important; -webkit-print-color-adjust: exact; }}
            .footer-container {{ display: flex; border: 2px solid {cor_tema}; border-top: none; }}
            .footer-box {{ width: 50%; }}
            .footer-header {{ background: {cor_tema} !important; color: #fff !important; text-align: center; font-weight: bold; font-size: 14px; padding: 4px; -webkit-print-color-adjust: exact; }}
            .footer-content {{ background: #eee !important; font-size: 14px; padding: 6px; text-align: center; min-height: 40px; text-transform: uppercase; -webkit-print-color-adjust: exact; line-height: 1.2; white-space: normal; }}
            .totals-container {{ display: flex; border: 2px solid {cor_tema}; border-top: none; background: {cor_tema} !important; color: #fff !important; -webkit-print-color-adjust: exact; }}
            .totals-box {{ width: 50%; font-size: 12px; font-weight: bold; padding: 6px; text-align: center; line-height: 1.3; }}
            @media print {{
                body {{ padding: 0; margin: 0 auto; width: 90%; zoom: 90%; }}
                thead th, .footer-header, .totals-container {{ background-color: {cor_tema} !important; color: #fff !important; }}
                tr:nth-child(even), .footer-content {{ background-color: #ccc !important; }}
                .separator-bottom {{ border-bottom: 4px solid #000 !important; }}
            }}
        </style>
    </head>
    <body>
        <div class="print-frame">
            <div class="header-main">
                <div class="header-dia">{dia_semana}</div>
                <div class="header-data">DATA: <span style="color: {cor_tema}">{data_str}</span></div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th class="cx-col">CX</th>
                        <th class="col-op-nome">OPERADOR(A)</th>
                        <th class="horario-col">HORÁRIO</th>
                        <th class="divider-col"></th>
                        <th class="col-emp-nome border-left">EMPACOTADOR(A)</th>
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
        </div>
    </body>
    </html>
    """

# --- FUNÇÕES DE CONTROLE DE HORAS E AVISOS ---

def obter_intervalo_minutos(h, m):
    mins = h * 60 + m
    if mins == 570 or mins == 600: return 105 
    elif mins == 660 or mins == 720: return 75 
    elif mins >= 870: return 15
    else: return 60

def calcular_saida_prevista(entrada_str, is_domingo_feriado=False):
    if not entrada_str or "HRS" not in str(entrada_str): return "", ""
    try:
        time_part = str(entrada_str).replace(" HRS", "").strip()
        h, m = map(int, time_part.split(':'))
        if is_domingo_feriado: intervalo_mins = 10
        else: intervalo_mins = obter_intervalo_minutos(h, m)
        td_entrada = timedelta(hours=h, minutes=m)
        td_saida = td_entrada + timedelta(minutes=(440 + intervalo_mins))
        total_minutes = int(td_saida.total_seconds() // 60)
        out_h = (total_minutes // 60) % 24
        out_m = total_minutes % 60
        if is_domingo_feriado: str_int = "10 min (Só Café)"
        elif intervalo_mins == 15: str_int = "15 min (Só Café)"
        elif intervalo_mins == 75: str_int = "1h 15m (Almoço+Café)"
        elif intervalo_mins == 90: str_int = "1h 30m"
        elif intervalo_mins == 105: str_int = "1h 45m (Almoço+Café)"
        else: str_int = "1 hora"
        return str_int, f"{out_h:02d}:{out_m:02d}"
    except: return "", ""

def calcular_saida_estimada(entrada_str, prevista_str, is_domingo_feriado):
    if not entrada_str or "HRS" not in str(entrada_str): return ""
    try:
        time_part = str(entrada_str).replace(" HRS", "").strip()
        h, m = map(int, time_part.split(':'))
        mins = h * 60 + m
        if is_domingo_feriado:
            if mins == 410: return "12:50" 
            if mins == 450: return "13:10" 
            if mins == 480: return "13:30" 
            return prevista_str
        else:
            if mins == 570 or mins == 600: return "19:05"
            elif mins >= 660: return "20:45"
            else: return prevista_str
    except: return prevista_str

def calcular_diferenca(prevista_str, estimada_str):
    if not prevista_str or not estimada_str: return 0
    try:
        ph, pm = map(int, str(prevista_str).split(':'))
        eh, em = map(int, str(estimada_str).replace("h", ":").replace("H", ":").split(':'))
        mins_prev = ph * 60 + pm
        mins_est = eh * 60 + em
        if mins_est < mins_prev and mins_prev > 1200 and mins_est < 480: mins_est += 24 * 60
        return mins_est - mins_prev
    except: return 0

def formatar_minutos(total_mins):
    if total_mins == 0: return "00h 00m"
    sign = "+" if total_mins > 0 else "-"
    total_mins = abs(total_mins)
    h = total_mins // 60; m = total_mins % 60
    return f"{sign} {h:02d}h {m:02d}m"

def gerar_alertas_trabalhistas(nome, horarios, data_inicio):
    alertas = []
    if len(horarios) < 7: return alertas
    dias_trabalho = sum(1 for h in horarios if h and "HRS" in h)
    if dias_trabalho == 7: alertas.append("⚠️ **Sem Folga Semanal:** Escalado(a) os 7 dias seguidos.")
    for i in range(6):
        h1 = horarios[i]; h2 = horarios[i+1]
        if h1 and "HRS" in h1 and h2 and "HRS" in h2:
            data1 = data_inicio + timedelta(days=i)
            data2 = data_inicio + timedelta(days=i+1)
            is_domingo1 = (data1.weekday() == 6)
            _, prev1 = calcular_saida_prevista(h1, is_domingo1)
            saida1 = calcular_saida_estimada(h1, prev1, is_domingo1)
            ent2 = h2.replace(" HRS", "").strip()
            if saida1 and ent2:
                try:
                    s_h, s_m = map(int, saida1.replace("h",":").replace("H",":").split(':'))
                    e_h, e_m = map(int, ent2.split(':'))
                    dt1 = datetime.datetime.combine(data1, datetime.time(s_h, s_m))
                    h1_int = int(h1.replace(" HRS","").split(":")[0])
                    if s_h < 12 and h1_int >= 12: dt1 += timedelta(days=1)
                    dt2 = datetime.datetime.combine(data2, datetime.time(e_h, e_m))
                    diff_hours = (dt2 - dt1).total_seconds() / 3600.0
                    if diff_hours < 11:
                        dia1_str = f"{DIAS_SEMANA_PT[data1.weekday()][:3]} ({data1.strftime('%d/%m')})"
                        dia2_str = f"{DIAS_SEMANA_PT[data2.weekday()][:3]} ({data2.strftime('%d/%m')})"
                        h_fmt = int(diff_hours); m_fmt = int(round((diff_hours - h_fmt) * 60))
                        alertas.append(f"⚠️ **Interjornada Curta:** Apenas {h_fmt}h {m_fmt}m de descanso entre {dia1_str} e {dia2_str}.")
                except: pass
    return alertas

def exibir_painel_alertas(df_semanas_ativas, df_colaboradores):
    if df_semanas_ativas.empty or df_colaboradores.empty: return
    semana_recente = df_semanas_ativas.iloc[0]
    id_semana = int(semana_recente['id'])
    data_ini = pd.to_datetime(semana_recente['data_inicio']).date()
    nome_semana = semana_recente['nome_semana']
    df_escala = carregar_escala_semana_por_id(id_semana)
    if df_escala.empty: return
    alertas_gerais = []
    for nome in df_colaboradores['nome']:
        escala_colab = df_escala[df_escala['nome'] == nome].sort_values('data')
        if len(escala_colab) == 7:
            horarios = escala_colab['horario'].tolist()
            alertas_colab = gerar_alertas_trabalhistas(nome, horarios, data_ini)
            for alerta in alertas_colab:
                alerta_limpo = alerta.replace('⚠️ ', '')
                alertas_gerais.append(f"**{nome}** ➔ {alerta_limpo}")
    if alertas_gerais: st.error(f"### 🚨 Alertas Trabalhistas Pendentes ({nome_semana})\n" + "\n".join(["* " + a for a in alertas_gerais]))


# --- ABAS ---
@st.fragment
def aba_controle_horas(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.header("⏱️ Controle de Horas e Calculadora")
    st.info("A tabela gera a Saída Estimada automaticamente para te dar uma prévia do Saldo da Semana.")
    
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return

    df_horas = df_colaboradores[df_colaboradores['funcao'] != 'Empacotador(a)']
    c1, c2 = st.columns(2)
    with c1:
        opcoes = {row['nome_semana']: {'id': int(row['id']), 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("1. Selecione a semana:", options=opcoes.keys(), key="sel_sem_horas")
        semana_info = opcoes[semana_str]
    with c2:
        nomes = [""] + sorted(df_horas['nome'].unique())
        colaborador = st.selectbox("2. Selecione o Colaborador:", nomes, key="sel_colab_horas")

    st.markdown("---")
    if semana_info and colaborador:
        id_semana = semana_info['id']
        df_full = carregar_escala_semana_por_id(id_semana)
        escala_colab = df_full[df_full['nome'] == colaborador] if not df_full.empty else pd.DataFrame()
        
        if escala_colab.empty:
            st.info("Nenhum horário cadastrado para este colaborador nesta semana.")
        else:
            escala_colab['data'] = pd.to_datetime(escala_colab['data'])
            escala_colab = escala_colab.sort_values('data')
            dados_tabela = []
            for _, row in escala_colab.iterrows():
                data_dt = pd.to_datetime(row['data'])
                dia_str = data_dt.strftime(f'%d/%m ({DIAS_SEMANA_PT[data_dt.weekday()][:3]})')
                entrada = row['horario']
                is_domingo = (data_dt.weekday() == 6)
                intervalo, prevista = calcular_saida_prevista(entrada, is_domingo) if "HRS" in str(entrada) else ("", "")
                estimada_padrao = calcular_saida_estimada(entrada, prevista, is_domingo)
                dados_tabela.append({
                    "Data": dia_str, "Entrada Escala": entrada, "Tempo Almoço/Café": intervalo,
                    "Saída Prevista (Cravada)": prevista, "Saída Estimada (Aprox)": estimada_padrao, "Dom / Feriado?": is_domingo
                })
            df_display = pd.DataFrame(dados_tabela)
            st.markdown(f"#### 📅 Escala Prevista da Semana: `{colaborador}`")
            edited_df = st.data_editor(
                df_display,
                column_config={
                    "Data": st.column_config.TextColumn("Data", disabled=True),
                    "Entrada Escala": st.column_config.TextColumn("Entrada Programada", disabled=True),
                    "Tempo Almoço/Café": st.column_config.TextColumn("Tempo Almoço/Café", disabled=True),
                    "Saída Prevista (Cravada)": st.column_config.TextColumn("Saída Prevista (Cravada)", disabled=True),
                    "Saída Estimada (Aprox)": st.column_config.TextColumn("Saída Estimada (Editável)"),
                    "Dom / Feriado?": st.column_config.CheckboxColumn("Dom / Feriado?")
                },
                hide_index=True, use_container_width=True
            )
            total_extra_mins = 0; total_atraso_mins = 0
            st.markdown("### 📊 Resumo da Semana")
            for index, row in edited_df.iterrows():
                entrada_str = row['Entrada Escala']; estimada_str = row['Saída Estimada (Aprox)']; is_feriado = row['Dom / Feriado?']
                _, prevista_str = calcular_saida_prevista(entrada_str, is_feriado)
                if prevista_str and estimada_str:
                    diff_mins = calcular_diferenca(prevista_str, estimada_str)
                    if diff_mins > 0: total_extra_mins += diff_mins
                    elif diff_mins < 0: total_atraso_mins += abs(diff_mins)
            c_res1, c_res2 = st.columns(2)
            c_res1.metric("🔴 Atrasos Aprox.", formatar_minutos(-total_atraso_mins))
            saldo_geral = total_extra_mins - total_atraso_mins
            cor_saldo = "🟢" if saldo_geral >= 0 else "🔴"
            c_res2.metric(f"{cor_saldo} Saldo Estimado", formatar_minutos(saldo_geral))

    st.markdown("---"); st.markdown("### 🧮 Calculadora Avulsa de Horas (Base: 7h20m)")
    col_calc1, col_calc2, col_calc3, col_calc4, col_calc5 = st.columns(5)
    with col_calc1: calc_entrada = st.time_input("Entrada (Real)", datetime.time(6, 50))
    with col_calc2: calc_saida = st.time_input("Saída (Real)", datetime.time(15, 10))
    with col_calc3: calc_almoco = st.selectbox("Tempo Almoço", ["1 hora", "1 hora e 30 min", "2 horas", "Sem almoço"])
    with col_calc4: calc_cafe = st.selectbox("Tempo Café", ["Sem café", "10 min", "15 min", "30 min"])
    with col_calc5: st.markdown("<br>", unsafe_allow_html=True); st.info("Cálculo Automático ⬇️")
    mins_entrada = calc_entrada.hour * 60 + calc_entrada.minute
    mins_saida = calc_saida.hour * 60 + calc_saida.minute
    if mins_saida < mins_entrada: mins_saida += 24 * 60
    mapa_almoco = { "Sem almoço": 0, "1 hora": 60, "1 hora e 30 min": 90, "2 horas": 120 }
    mapa_cafe = { "Sem café": 0, "10 min": 10, "15 min": 15, "30 min": 30 }
    trabalhado_liquido = (mins_saida - mins_entrada) - mapa_almoco[calc_almoco] - mapa_cafe[calc_cafe]
    if trabalhado_liquido < 0: trabalhado_liquido = 0
    diferenca = trabalhado_liquido - 440 
    res1, res2 = st.columns(2)
    res1.metric("Total Trabalhado (Líquido)", f"{trabalhado_liquido // 60:02d}h {trabalhado_liquido % 60:02d}m")
    if diferenca > 0: res2.metric("Saldo do Dia", f"+ {diferenca // 60:02d}h {diferenca % 60:02d}m", "Hora Extra (Lançar Positivo)")
    elif diferenca < 0: res2.metric("Saldo do Dia", f"- {abs(diferenca) // 60:02d}h {abs(diferenca) % 60:02d}m", "Atraso / Faltou Tempo", delta_color="inverse")
    else: res2.metric("Saldo do Dia", "00h 00m", "Cravado (Sem extra/atraso)")


@st.fragment
def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.header("🔎 Visão Geral")
    if df_colaboradores.empty: st.warning("Nenhum colaborador cadastrado."); return
    nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
    nome_selecionado = st.selectbox("1. Selecione seu nome para ver a escala:", options=nomes_disponiveis)

    if nome_selecionado:
        is_operador = False
        if 'funcao' in df_colaboradores.columns:
            f = df_colaboradores[df_colaboradores['nome'] == nome_selecionado]['funcao']
            if not f.empty and f.iloc[0] == "Operador(a) de Caixa": is_operador = True

        if df_semanas_ativas.empty: st.info("Nenhuma semana disponível."); return
        opcoes_semana = {row['nome_semana']: {'id': int(row['id']), 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for index, row in df_semanas_ativas.iterrows()}
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

    st.markdown("---")
    with st.expander("📬 Fazer um Pedido / Solicitação (Folgas, Trocas, etc)", expanded=False):
        with st.form("form_novo_pedido", clear_on_submit=True):
            nomes_para_pedido = sorted(df_colaboradores["nome"].dropna().unique())
            c_p1, c_p2 = st.columns([1, 2])
            with c_p1: nome_pedido = st.selectbox("Seu Nome:", nomes_para_pedido)
            with c_p2: texto_pedido = st.text_area("O que você precisa?", placeholder="Ex: Preciso de folga dia 15/05 pois tenho médico...")
            btn_enviar = st.form_submit_button("🚀 Enviar Pedido", type="primary")
            
        if btn_enviar:
            if texto_pedido.strip():
                if salvar_pedido(nome_pedido, texto_pedido):
                    st.success("✅ SEU PEDIDO FOI ENVIADO COM SUCESSO! O fiscal irá analisar.")
                    st.balloons(); time.sleep(2.5); st.rerun()
            else: st.warning("Escreva algo no pedido antes de enviar.")

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
                st.cache_data.clear(); st.success("Semana inicializada com as Folgas Fixas!"); time.sleep(1.5); st.rerun()
    
    st.markdown("---"); st.markdown("##### 📂 Histórico de Semanas")
    if not df_semanas_todas.empty:
        mostrar_arquivadas = st.toggle("📂 Mostrar APENAS semanas arquivadas", value=False)
        if mostrar_arquivadas:
            df_view = df_semanas_todas[df_semanas_todas['ativa'] == False]
            if df_view.empty: st.info("Nenhuma semana arquivada.")
        else:
            df_view = df_semanas_todas[df_semanas_todas['ativa'] == True]
            if df_view.empty: st.info("Nenhuma semana ativa no momento.")
                
        for index, row in df_view.iterrows():
            c1, c2, c3 = st.columns([4, 1, 1])
            status_icon = "🟢" if row['ativa'] else "📁"
            c1.markdown(f"**{status_icon} {row['nome_semana']}**")
            key_arch = f"btn_arch_{row['id']}"
            if row['ativa']:
                if c2.button("Arquivar", key=key_arch):
                    arquivar_reativar_semana(int(row['id']), False); st.cache_data.clear(); st.rerun()
            else:
                if c2.button("Reativar", key=key_arch):
                    arquivar_reativar_semana(int(row['id']), True); st.cache_data.clear(); st.rerun()
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
        opcoes = {row['nome_semana']: {'id': int(row['id']), 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
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
        
        is_operador = (funcao_atual in ["Operador(a) de Caixa", "Recepção"])

        st.markdown(f"**Editando:** `{colaborador}` ({funcao_atual})")
        cols = st.columns(7)
        novos_horarios = []; novos_caixas = []
        
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
                    lista_opcoes = LISTA_OPCOES_CAIXA if is_operador else LISTA_TAREFAS_EMPACOTADOR
                    if caixa_atual and caixa_atual not in lista_opcoes: lista_opcoes = [caixa_atual] + lista_opcoes
                    idx_c = lista_opcoes.index(caixa_atual) if caixa_atual in lista_opcoes else 0
                    val_c = st.selectbox("C" if is_operador else "T", lista_opcoes, index=idx_c, key=key_c, label_visibility="collapsed")
                novos_caixas.append(val_c)
        st.markdown("")
        
        alertas_clt = gerar_alertas_trabalhistas(colaborador, novos_horarios, data_ini)
        if alertas_clt: st.error("**🚨 Alertas Trabalhistas (CLT):**\n\n" + "\n\n".join(alertas_clt))
            
        if st.button("💾 Salvar Alterações", type="primary", use_container_width=True):
            if salvar_escala_individual(colaborador, novos_horarios, novos_caixas, data_ini, id_semana):
                st.cache_data.clear(); st.success(f"Salvo!"); time.sleep(1); st.rerun()

# ------------------- NOVA ABA: ESCALA MÁGICA -------------------
@st.fragment
def aba_escala_magica(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame, df_semanas_todas: pd.DataFrame):
    st.header("✨ Escala Mágica")
    st.markdown("**Siga os dois passos abaixo:**")
    
    if df_semanas_ativas.empty: st.warning("Crie ou ative uma semana primeiro na aba 'Gerar Semanas'."); return
    
    # ---------------- ETAPA 1: GERAR HORÁRIOS ----------------
    st.markdown("---")
    st.subheader("1️⃣ Gerar Horários (Rodízio Inteligente)")
    st.info("Baixe a planilha com os horários pré-preenchidos. O sistema vai analisar os últimos 14 dias para rodar a equipe de forma justa.")
    
    col1, col2 = st.columns(2)
    with col1:
        opcoes_m = {row['nome_semana']: {'id': int(row['id']), 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
        semana_str_m = st.selectbox("Qual semana?", options=opcoes_m.keys(), key="sel_sem_magica_down")
        semana_info_m = opcoes_m[semana_str_m]
    
    if semana_info_m:
        data_ini_m = semana_info_m['data_inicio']
        id_semana_m = semana_info_m['id']
        
        df_filtrado_m = df_colaboradores.copy()
        if 'funcao' in df_filtrado_m.columns: df_filtrado_m = df_filtrado_m[df_filtrado_m['funcao'] == "Operador(a) de Caixa"]
            
        mapa_folga_fixa_m = {row['nome']: row.get('folga_fixa', '') for _, row in df_filtrado_m.iterrows()}
        
        if df_filtrado_m.empty: st.error("Não há Operadores de Caixa cadastrados.")
        else:
            colunas_m = ['Nome']
            for i in range(7):
                d_str_m = (data_ini_m + timedelta(days=i)).strftime('%d/%m/%Y')
                colunas_m.append(d_str_m); colunas_m.append(f"CX_REF_{d_str_m}")

            df_template_m = pd.DataFrame(columns=colunas_m)
            df_template_m['Nome'] = sorted(df_filtrado_m['nome'].unique())
            
            buffer_m = io.BytesIO()
            try:
                with pd.ExcelWriter(buffer_m, engine='xlsxwriter') as writer:
                    df_template_m.to_excel(writer, index=False, sheet_name='Escala')
                    workbook = writer.book; worksheet = writer.sheets['Escala']
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
                    fmt_duplicata = workbook.add_format({'bg_color': '#FF0000', 'font_color': '#FFFFFF', 'bold': True, 'align': 'center'})
                    
                    ws_data = workbook.add_worksheet('Dados'); ws_data.hide()
                    ws_data.write_column('A1', HORARIOS_PADRAO)
                    ws_data.write_column('B1', LISTA_OPCOES_CAIXA)
                    
                    fmt_nome = workbook.add_format({'border': 1, 'valign': 'vcenter', 'align': 'left'})
                    worksheet.write(0, 0, "Nome", fmt_bold); worksheet.set_column(0, 0, 35, None)
                    
                    alocacao_auto = gerar_alocacao_semanal(df_filtrado_m, data_ini_m, df_semanas_todas)
                    
                    last_data_row = len(df_template_m)
                    row_total_m = last_data_row + 1
                    row_total_t = last_data_row + 2
                    
                    for r_idx, row_name in enumerate(df_template_m['Nome']):
                        row_excel = r_idx + 1
                        worksheet.write(row_excel, 0, row_name, fmt_nome)
                        
                        current_c = 1
                        for i_day in range(7):
                            d_atual = data_ini_m + timedelta(days=i_day)
                            h_val = alocacao_auto.get(row_name, "")
                            if h_val == "10:00 HRS" and d_atual.weekday() in [2, 3]: h_val = "9:30 HRS"
                            if d_atual.weekday() == 6: h_val = ""
                            
                            dia_semana_atual = DIAS_SEMANA_PT[d_atual.weekday()]
                            if mapa_folga_fixa_m.get(row_name, "") == dia_semana_atual: h_val = "Folga"
                            
                            worksheet.write(row_excel, current_c, h_val, fmt_grid); current_c += 1
                            worksheet.write(row_excel, current_c, "", fmt_grid); current_c += 1

                    col_idx = 1
                    for i in range(7):
                        d_str = (data_ini_m + timedelta(days=i)).strftime('%d/%m/%Y')
                        worksheet.write(0, col_idx, d_str, fmt_date_header); worksheet.set_column(col_idx, col_idx, 12, None)
                        worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$A$1:$A$' + str(len(HORARIOS_PADRAO))})
                        for h in H_VERMELHO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_vermelho})
                        for h in H_VERDE: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_verde})
                        for h in H_ROXO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_roxo})
                        for h in H_CINZA: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_cinza})
                        for h in H_AMARELO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_amarelo})
                        col_idx += 1
                        
                        worksheet.write(0, col_idx, "CX", fmt_cx_header); worksheet.set_column(col_idx, col_idx, 10, None)
                        worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$B$1:$B$' + str(len(LISTA_OPCOES_CAIXA))})
                        col_idx += 1
                        
                    # ADICIONANDO AS FÓRMULAS DE SOMA NO FINAL
                    worksheet.write(row_total_m, 0, "Operadoras Manhã", fmt_manha)
                    worksheet.write(row_total_t, 0, "Operadoras Tarde", fmt_tarde)
                    
                    def num_to_col(n):
                        s = ""
                        while n >= 0:
                            s = chr(n % 26 + 65) + s
                            n = n // 26 - 1
                        return s

                    current_col = 1
                    for i in range(7):
                        letra = num_to_col(current_col)
                        rng = f"{letra}2:{letra}{last_data_row+1}"
                        letra_cx = num_to_col(current_col + 1)
                        rng_cx = f"{letra_cx}2:{letra_cx}{last_data_row+1}"
                        
                        lista_h_tarde_op = HORARIOS_TARDE + ["7:30 HRS"]
                        crit_m = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine", {rng_cx}, "<>Salinha")' for h in HORARIOS_MANHA])
                        crit_t = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine", {rng_cx}, "<>Salinha")' for h in lista_h_tarde_op])
                        
                        rng_abs = f"${letra}$2:${letra}${last_data_row+1}"
                        rng_cx_abs = f"${letra_cx}$2:${letra_cx}${last_data_row+1}"
                        crit_cx = f"{letra_cx}2"
                        crit_h = f"{letra}2"
                        formula_dup = f'=COUNTIFS({rng_cx_abs}, {crit_cx}, {rng_abs}, {crit_h}) > 1'
                        worksheet.conditional_format(rng_cx, {'type': 'formula', 'criteria': formula_dup, 'format': fmt_duplicata})

                        if crit_m: worksheet.write_formula(row_total_m, current_col, f"=SUM({crit_m})", fmt_manha)
                        else: worksheet.write(row_total_m, current_col, 0, fmt_manha)

                        if crit_t: worksheet.write_formula(row_total_t, current_col, f"=SUM({crit_t})", fmt_tarde)
                        else: worksheet.write(row_total_t, current_col, 0, fmt_tarde)
                            
                        current_col += 2

            except Exception as e: st.error(f"Erro ao gerar Excel: {e}"); return

            st.download_button(label="📥 1. Baixar Excel com Horários Inteligentes", data=buffer_m.getvalue(), file_name=f"escala_MAGICA_horarios_{data_ini_m.strftime('%d-%m')}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type="primary")

    # ---------------- ETAPA 2: ATRIBUIR CAIXAS E DOMINGOS ----------------
    st.markdown("---")
    st.subheader("2️⃣ Atribuir Caixas e Domingos Automaticamente")
    st.info("Faça o upload da planilha (após seus ajustes manuais se houver). O sistema vai cobrir os buracos dos Domingos (regra 1x1) e distribuir os caixas respeitando as prioridades!")
    
    arquivo_upload_magica = st.file_uploader("Arraste o Excel **com os horários preenchidos** aqui:", type=["xlsx"], key="magica_upload_cx")
    
    if arquivo_upload_magica is not None:
        if st.button("🪄 Processar Domingos e Distribuir Caixas", type="primary"):
            with st.spinner("Analisando Domingos e Distribuindo Caixas..."):
                df_up = pd.read_excel(arquivo_upload_magica)
                datas_cols = [col for col in df_up.columns if "CX_REF" not in col and "TAREFA" not in col and col != "Nome"]
                
                try: data_ini_up = datetime.datetime.strptime(datas_cols[0], "%d/%m/%Y").date()
                except: st.error("Formato de data inválido na planilha."); st.stop()
                    
                dados_existentes = {}; nomes_validos = []
                for r_idx, row in df_up.iterrows():
                    nome = row.get('Nome', "")
                    if pd.isna(nome) or str(nome).strip() == "" or "TOTAL" in str(nome) or "Manhã" in str(nome) or "Tarde" in str(nome) or "Operadoras" in str(nome): continue
                    nome = str(nome).strip()
                    nomes_validos.append(nome)
                    
                    for col_data in datas_cols:
                        dt = datetime.datetime.strptime(col_data, "%d/%m/%Y").date()
                        h_val = str(row.get(col_data, ""))
                        if h_val == "nan": h_val = ""
                        cx_col = f"CX_REF_{col_data}"
                        c_val = str(row.get(cx_col, ""))
                        if c_val == "nan": c_val = ""
                        
                        if dt.weekday() == 6 and h_val.strip() == "":
                            trab_passado = trabalhou_na_data(nome, dt - timedelta(days=7), df_semanas_todas)
                            if trab_passado: h_val = "Folga"
                            else: h_val = random.choice(["8:00 HRS", "12:00 HRS"]) 
                                
                        dados_existentes[(nome, dt)] = {'horario': h_val, 'caixa': c_val}
                        
                for col_data in datas_cols:
                    dt = datetime.datetime.strptime(col_data, "%d/%m/%Y").date()
                    dia_items = []
                    for nome in nomes_validos:
                        h = dados_existentes.get((nome, dt), {}).get('horario', "")
                        dia_items.append((nome, h))
                        
                    alocacao = atribuir_caixas_dia(dia_items)
                    
                    for nome in nomes_validos:
                        if (nome, dt) in dados_existentes:
                            dados_existentes[(nome, dt)]['caixa'] = alocacao.get(nome, "")
                            
                colunas_f = ['Nome']
                for i in range(7):
                    d_str_f = (data_ini_up + timedelta(days=i)).strftime('%d/%m/%Y')
                    colunas_f.append(d_str_f); colunas_f.append(f"CX_REF_{d_str_f}")

                df_template_f = pd.DataFrame(columns=colunas_f)
                df_template_f['Nome'] = sorted(nomes_validos)
                
                buffer_out = io.BytesIO()
                try:
                    with pd.ExcelWriter(buffer_out, engine='xlsxwriter') as writer:
                        df_template_f.to_excel(writer, index=False, sheet_name='Escala')
                        workbook = writer.book; worksheet = writer.sheets['Escala']
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
                        fmt_duplicata = workbook.add_format({'bg_color': '#FF0000', 'font_color': '#FFFFFF', 'bold': True, 'align': 'center'})
                        
                        ws_data = workbook.add_worksheet('Dados'); ws_data.hide()
                        ws_data.write_column('A1', HORARIOS_PADRAO)
                        ws_data.write_column('B1', LISTA_OPCOES_CAIXA)
                        
                        fmt_nome = workbook.add_format({'border': 1, 'valign': 'vcenter', 'align': 'left'})
                        worksheet.write(0, 0, "Nome", fmt_bold); worksheet.set_column(0, 0, 35, None)
                        
                        last_data_row = len(df_template_f)
                        row_total_m = last_data_row + 1
                        row_total_t = last_data_row + 2
                        
                        for r_idx, row_name in enumerate(df_template_f['Nome']):
                            row_excel = r_idx + 1
                            worksheet.write(row_excel, 0, row_name, fmt_nome)
                            current_c = 1
                            for i_day in range(7):
                                d_atual = data_ini_up + timedelta(days=i_day)
                                info = dados_existentes.get((row_name, d_atual), {})
                                worksheet.write(row_excel, current_c, info.get('horario', ""), fmt_grid); current_c += 1
                                worksheet.write(row_excel, current_c, info.get('caixa', ""), fmt_grid); current_c += 1

                        col_idx = 1
                        for i in range(7):
                            d_str = (data_ini_up + timedelta(days=i)).strftime('%d/%m/%Y')
                            worksheet.write(0, col_idx, d_str, fmt_date_header); worksheet.set_column(col_idx, col_idx, 12, None)
                            worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$A$1:$A$' + str(len(HORARIOS_PADRAO))})
                            for h in H_VERMELHO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_vermelho})
                            for h in H_VERDE: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_verde})
                            for h in H_ROXO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_roxo})
                            for h in H_CINZA: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_cinza})
                            for h in H_AMARELO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_amarelo})
                            col_idx += 1
                            
                            worksheet.write(0, col_idx, "CX", fmt_cx_header); worksheet.set_column(col_idx, col_idx, 10, None)
                            worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$B$1:$B$' + str(len(LISTA_OPCOES_CAIXA))})
                            col_idx += 1
                            
                        # ADICIONANDO AS FÓRMULAS DE SOMA NO FINAL DO ARQUIVO DA ETAPA 2
                        worksheet.write(row_total_m, 0, "Operadoras Manhã", fmt_manha)
                        worksheet.write(row_total_t, 0, "Operadoras Tarde", fmt_tarde)
                        
                        def num_to_col(n):
                            s = ""
                            while n >= 0:
                                s = chr(n % 26 + 65) + s
                                n = n // 26 - 1
                            return s

                        current_col = 1
                        for i in range(7):
                            letra = num_to_col(current_col)
                            rng = f"{letra}2:{letra}{last_data_row+1}"
                            letra_cx = num_to_col(current_col + 1)
                            rng_cx = f"{letra_cx}2:{letra_cx}{last_data_row+1}"
                            
                            lista_h_tarde_op = HORARIOS_TARDE + ["7:30 HRS"]
                            crit_m = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine", {rng_cx}, "<>Salinha")' for h in HORARIOS_MANHA])
                            crit_t = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine", {rng_cx}, "<>Salinha")' for h in lista_h_tarde_op])
                            
                            rng_abs = f"${letra}$2:${letra}${last_data_row+1}"
                            rng_cx_abs = f"${letra_cx}$2:${letra_cx}${last_data_row+1}"
                            crit_cx = f"{letra_cx}2"
                            crit_h = f"{letra}2"
                            formula_dup = f'=COUNTIFS({rng_cx_abs}, {crit_cx}, {rng_abs}, {crit_h}) > 1'
                            worksheet.conditional_format(rng_cx, {'type': 'formula', 'criteria': formula_dup, 'format': fmt_duplicata})

                            if crit_m: worksheet.write_formula(row_total_m, current_col, f"=SUM({crit_m})", fmt_manha)
                            else: worksheet.write(row_total_m, current_col, 0, fmt_manha)

                            if crit_t: worksheet.write_formula(row_total_t, current_col, f"=SUM({crit_t})", fmt_tarde)
                            else: worksheet.write(row_total_t, current_col, 0, fmt_tarde)
                                
                            current_col += 2
                            
                except Exception as e: st.error(f"Erro ao gerar Excel: {e}"); return
                
                st.session_state['magica_buffer'] = buffer_out.getvalue()
                st.session_state['magica_filename'] = f"escala_FINALIZADA_{data_ini_up.strftime('%d-%m')}.xlsx"
                st.success("✅ Caixas e Domingos processados com sucesso!")
                
    if 'magica_buffer' in st.session_state:
        st.download_button(
            label="📥 2. Baixar Escala Final (Com Caixas)", 
            data=st.session_state['magica_buffer'], 
            file_name=st.session_state['magica_filename'], 
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 
            type="primary"
        )
        st.info("⬆️ Faça o download deste arquivo e suba na aba tradicional **'📤 Importar / Baixar'** para salvar tudo no banco de dados!")


# --- ABA DE IMPORTAÇÃO PADRÃO (LIMPA, APENAS TEMPLATE MANUAL) ---
@st.fragment
def aba_importar_excel(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("📤 Importar / Baixar Escala (Excel)")
    st.info("Utilize esta aba para baixar o modelo em branco (ou backup) e subir a escala manual pronta para o banco de dados.")
    
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    
    col1, col2 = st.columns(2)
    with col1:
        funcao_selecionada = st.selectbox("1. Qual função?", FUNCOES_LOJA, key="sel_func_down")
    with col2:
        opcoes = {row['nome_semana']: {'id': int(row['id']), 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("2. Qual semana?", options=opcoes.keys(), key="sel_sem_imp")
        semana_info = opcoes[semana_str]
        
    if semana_info and funcao_selecionada:
        data_ini = semana_info['data_inicio']
        id_semana = semana_info['id']
        
        df_dados_db = carregar_escala_semana_por_id(id_semana)
        
        df_filtrado = df_colaboradores.copy()
        if 'funcao' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['funcao'] == funcao_selecionada]
            
        mapa_folga_fixa = {row['nome']: row.get('folga_fixa', '') for _, row in df_filtrado.iterrows()}
        
        if df_filtrado.empty:
            st.error(f"Não há colaboradores com função '{funcao_selecionada}'.")
        else:
            colunas = ['Nome']
            for i in range(7):
                d_str = (data_ini + timedelta(days=i)).strftime('%d/%m/%Y')
                colunas.append(d_str)
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
                    
                    fmt_duplicata = workbook.add_format({'bg_color': '#FF0000', 'font_color': '#FFFFFF', 'bold': True, 'align': 'center'})

                    ws_data = workbook.add_worksheet('Dados'); ws_data.hide()
                    ws_data.write_column('A1', HORARIOS_PADRAO)
                    ws_data.write_column('B1', LISTA_OPCOES_CAIXA)
                    ws_data.write_column('C1', LISTA_TAREFAS_EMPACOTADOR)
                    
                    fmt_nome = workbook.add_format({'border': 1, 'valign': 'vcenter', 'align': 'left'})
                    worksheet.write(0, 0, "Nome", fmt_bold)
                    
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
                            
                            dia_semana_atual = DIAS_SEMANA_PT[d_atual.weekday()]
                            folga_fixa_colab = mapa_folga_fixa.get(row_name, "")
                            
                            if folga_fixa_colab == dia_semana_atual:
                                h_val = "Folga"
                            
                            worksheet.write(row_excel, current_c, h_val, fmt_grid)
                            current_c += 1
                            
                            is_recep = (funcao_selecionada == "Recepção")
                            
                            if is_op or is_emp or is_recep:
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
                        
                        is_recep = (funcao_selecionada == "Recepção")
                        
                        if is_op or is_emp or is_recep:
                            header_title = "CX" if (is_op or is_recep) else "TAREFAS"
                            valid_list = '=Dados!$B$1:$B$' + str(len(LISTA_OPCOES_CAIXA)) if (is_op or is_recep) else '=Dados!$C$1:$C$' + str(len(LISTA_TAREFAS_EMPACOTADOR))
                            
                            worksheet.write(0, col_idx, header_title, fmt_cx_header)
                            worksheet.set_column(col_idx, col_idx, 10, None)
                            worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': valid_list})
                            col_idx += 1
                    
                    mapa_nomes = {"Operador(a) de Caixa": "Operadoras", "Empacotador(a)": "Empacotadores", "Fiscal de Caixa": "Fiscais", "Recepção": "Recepção"}
                    nome_cargo = mapa_nomes.get(funcao_selecionada, funcao_selecionada)
                    
                    worksheet.write(row_total_m, 0, f"{nome_cargo} Manhã", fmt_manha)
                    worksheet.write(row_total_t, 0, f"{nome_cargo} Tarde", fmt_tarde)
                    
                    step = 2 if (is_op or is_emp or is_recep) else 1
                    
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
                        
                        if is_op:
                            letra_cx = num_to_col(current_col + 1)
                            rng_cx = f"{letra_cx}2:{letra_cx}{last_data_row+1}"
                            
                            lista_h_tarde_op = HORARIOS_TARDE + ["7:30 HRS"]
                            
                            crit_m = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine", {rng_cx}, "<>Salinha")' for h in HORARIOS_MANHA])
                            crit_t = ",".join([f'COUNTIFS({rng}, "{h}", {rng_cx}, "<>Recepção", {rng_cx}, "<>Delivery", {rng_cx}, "<>Magazine", {rng_cx}, "<>Salinha")' for h in lista_h_tarde_op])
                            
                            rng_abs = f"${letra}$2:${letra}${last_data_row+1}"
                            rng_cx_abs = f"${letra_cx}$2:${letra_cx}${last_data_row+1}"
                            crit_cx = f"{letra_cx}2"
                            crit_h = f"{letra}2"
                            formula_dup = f'=COUNTIFS({rng_cx_abs}, {crit_cx}, {rng_abs}, {crit_h}) > 1'
                            worksheet.conditional_format(rng_cx, {'type': 'formula', 'criteria': formula_dup, 'format': fmt_duplicata})

                        else:
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

            st.download_button(label="📥 Baixar Planilha (Modelo Manual)", data=buffer.getvalue(), file_name=f"escala_{funcao_selecionada.split()[0]}_{data_ini.strftime('%d-%m')}.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', type="secondary")
            
            st.markdown("---")
            arquivo_upload = st.file_uploader("Arraste o Excel preenchido para Salvar:", type=["xlsx"], key="upl_excel_uniq")
            if arquivo_upload is not None:
                if st.button("🚀 Processar e Salvar no Banco", type="primary", key="btn_proc_excel"):
                    if salvar_escala_via_excel(pd.read_excel(arquivo_upload), data_ini, id_semana):
                        st.success("Importado com sucesso!"); time.sleep(2); st.cache_data.clear(); st.rerun()

@st.fragment
def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Gerenciar Colaboradores")
    st.markdown("##### ✏️ Classificar / Editar Colaboradores Existentes")
    
    if not df_colaboradores.empty:
        mapa_original = {row['nome']: row['funcao'] for _, row in df_colaboradores.iterrows()}
        mapa_social = {row['nome']: row['nome_social'] for _, row in df_colaboradores.iterrows()}
        mapa_folga = {row['nome']: row.get('folga_fixa', '') for _, row in df_colaboradores.iterrows()}
        
        df_editor = df_colaboradores.copy()
        
        col_config = {
            "nome": st.column_config.TextColumn("Nome", disabled=True),
            "funcao": st.column_config.SelectboxColumn("Função (Cargo)", options=FUNCOES_LOJA, required=True, width="medium"),
            "nome_social": st.column_config.TextColumn("Nome Social (Para Impressão)", width="medium"),
            "folga_fixa": st.column_config.SelectboxColumn("Folga Fixa", options=[""] + DIAS_SEMANA_PT, width="medium")
        }
        
        df_editado = st.data_editor(
            df_editor[['nome', 'funcao', 'nome_social', 'folga_fixa']], 
            column_config=col_config, 
            use_container_width=True,
            key="editor_colabs",
            num_rows="fixed"
        )
        
        if st.button("💾 Salvar Alterações"):
            barra = st.progress(0, text="Atualizando dados...")
            total = len(df_editado)
            contador_updates = 0
            
            for index, row in df_editado.iterrows():
                nome = row['nome']
                nova_funcao = row['funcao']
                novo_social = row['nome_social']
                nova_folga = row['folga_fixa']
                
                if nova_funcao != mapa_original.get(nome, "") or novo_social != mapa_social.get(nome, "") or nova_folga != mapa_folga.get(nome, ""):
                    atualizar_dados_colaborador(nome, nova_funcao, novo_social, nova_folga)
                    contador_updates += 1
                if index % 5 == 0: barra.progress((index+1)/total)
            
            barra.empty()
            if contador_updates > 0: st.success(f"{contador_updates} colaboradores atualizados!")
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

# --- ABA DE PEDIDOS ---
@st.fragment
def aba_gerenciar_pedidos():
    st.subheader("📌 Gerenciar Pedidos e Solicitações")
    st.info("Visualize os pedidos das operadoras e atualize o status. Pedidos 'Concluídos' são arquivados automaticamente.")
    
    df_pedidos = carregar_pedidos()
    
    if not df_pedidos.empty:
        df_pedidos['created_at'] = pd.to_datetime(df_pedidos['created_at']).dt.strftime('%d/%m/%Y %H:%M')
        
        mostrar_arquivados = st.toggle("📂 Mostrar APENAS pedidos arquivados (Concluídos)", value=False)
        
        if mostrar_arquivados:
            df_editor = df_pedidos[df_pedidos['status'] == 'Concluido'].copy()
        else:
            df_editor = df_pedidos[df_pedidos['status'] == 'Pendente'].copy()
            
        if df_editor.empty:
            if mostrar_arquivados:
                st.success("📂 Nenhum pedido arquivado encontrado.")
            else:
                st.success("🎉 Nenhum pedido pendente no momento!")
        else:
            edited_df = st.data_editor(
                df_editor[['id', 'created_at', 'nome', 'descricao', 'status']],
                column_config={
                    "id": None, 
                    "created_at": st.column_config.TextColumn("Data do Pedido", disabled=True),
                    "nome": st.column_config.TextColumn("Nome", disabled=True),
                    "descricao": st.column_config.TextColumn("Pedido/Solicitação", disabled=True, width="large"),
                    "status": st.column_config.SelectboxColumn(
                        "Status",
                        options=["Pendente", "Concluido"],
                        required=True,
                        width="medium"
                    )
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                key="editor_pedidos"
            )
            
            if st.button("💾 Salvar Status dos Pedidos", type="primary"):
                count = 0
                for index, row in edited_df.iterrows():
                    original_status = df_pedidos.loc[df_pedidos['id'] == row['id'], 'status'].values[0]
                    if row['status'] != original_status:
                        if atualizar_status_pedido(row['id'], row['status']):
                            count += 1
                if count > 0:
                    st.success(f"{count} pedidos atualizados!")
                    time.sleep(1.5)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.info("Nenhuma alteração detectada.")
    else:
        st.info("Nenhum pedido encontrado.")

# --- ABA DE ESCALA DIÁRIA (IMPRESSÃO ESTILO FOTO - PRETO E BRANCO) ---
@st.fragment
def aba_escala_diaria_impressao(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("🖨️ Escala Diária (Impressão)")
    st.info("Selecione a semana e o dia específico para editar e imprimir a escala diária.")

    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return

    opcoes = {row['nome_semana']: {'id': int(row['id']), 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
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

    df_ops_base = df_colaboradores[df_colaboradores['funcao'].isin(['Operador(a) de Caixa', 'Recepção'])]
    df_emp_base = df_colaboradores[df_colaboradores['funcao'] == 'Empacotador(a)']

    df_ops_final = df_ops_base.merge(df_dia[['nome', 'horario', 'numero_caixa']], on='nome', how='left').fillna("")
    df_emp_final = df_emp_base.merge(df_dia[['nome', 'horario', 'numero_caixa']], on='nome', how='left').fillna("")

    df_ops_final = df_ops_final.sort_values('nome')
    df_emp_final = df_emp_final.sort_values('nome')

    if 'nome_social' not in df_ops_final.columns: df_ops_final['nome_social'] = ""
    if 'nome_social' not in df_emp_final.columns: df_emp_final['nome_social'] = ""

    df_ops_final['nome_impressao'] = df_ops_final.apply(
        lambda row: row['nome_social'] if pd.notna(row['nome_social']) and str(row['nome_social']).strip() != "" else row['nome'], 
        axis=1
    )
    
    df_emp_final['nome_impressao'] = df_emp_final.apply(
        lambda row: row['nome_social'] if pd.notna(row['nome_social']) and str(row['nome_social']).strip() != "" else row['nome'], 
        axis=1
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🛒 Operadoras")
        df_ops_edited = st.data_editor(
            df_ops_final[['nome', 'nome_impressao', 'horario', 'numero_caixa']],
            column_config={
                "nome": st.column_config.TextColumn("Nome Original", disabled=True),
                "nome_impressao": "Nome na Impressão (Editável)",
                "horario": "Horário", 
                "numero_caixa": "Caixa"
            },
            hide_index=True, use_container_width=True, key=f"editor_ops_{data_selecionada}"
        )
    with c2:
        st.markdown("### 📦 Empacotadores")
        df_emp_edited = st.data_editor(
            df_emp_final[['nome', 'nome_impressao', 'horario', 'numero_caixa']],
            column_config={
                "nome": st.column_config.TextColumn("Nome Original", disabled=True),
                "nome_impressao": "Nome na Impressão (Editável)",
                "horario": "Horário", 
                "numero_caixa": "Tarefa/Obs"
            },
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
        exibir_painel_alertas(df_semanas_ativas, df_colaboradores)
        
        t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs(["🗓️ Semanas", "✏️ Editar", "🖨️ Diária", "📌 Pedidos", "⏱️ Horas", "📤 Importar", "👥 Colaboradores", "👁️ Geral", "✨ Escala Mágica"])
        
        with t1: aba_gerenciar_semanas(df_semanas)
        with t2: aba_editar_escala_individual(df_colaboradores, df_semanas_ativas)
        with t3: aba_escala_diaria_impressao(df_colaboradores, df_semanas_ativas)
        with t4: aba_gerenciar_pedidos() 
        with t5: aba_controle_horas(df_colaboradores, df_semanas_ativas)
        with t6: aba_importar_excel(df_colaboradores, df_semanas_ativas)
        with t7: aba_gerenciar_colaboradores(df_colaboradores)
        with t8: aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)
        with t9: aba_escala_magica(df_colaboradores, df_semanas_ativas, df_semanas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)

if __name__ == "__main__":
    main()