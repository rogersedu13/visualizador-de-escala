# Importando as bibliotecas necessárias
import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta, date
from supabase import create_client, Client
import time
import base64
import io

# --- Constantes da Aplicação ---
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIAS_SEMANA_FULL = ["SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO"]

FUNCOES_LOJA = ["Operador(a) de Caixa", "Empacotador(a)", "Fiscal de Caixa", "Recepção"]

HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# Grupos de Cores para o Excel
H_VERMELHO = ["5:50 HRS", "6:30 HRS", "6:50 HRS"]
H_VERDE    = ["7:30 HRS", "8:00 HRS", "8:30 HRS", "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS"]
H_ROXO     = ["11:00 HRS", "11:30 HRS", "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS", "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS"]
H_CINZA    = ["Folga"]
H_AMARELO  = ["Ferias", "Afastado(a)", "Atestado"]

# Lista de Caixas
LISTA_CAIXAS = ["", "---", "Self"] + [str(i) for i in range(1, 18)]

# --- LÓGICA DE CORTE MANHÃ / TARDE (AJUSTADA) ---
def calcular_minutos(horario_str):
    """Converte '9:30 HRS' em minutos (ex: 570) para comparação precisa."""
    if "HRS" not in horario_str: return -1
    try:
        # Pega a parte da hora "9:30"
        time_part = horario_str.split(' ')[0]
        h, m = map(int, time_part.split(':'))
        return h * 60 + m
    except:
        return -1

# Definindo o ponto de corte: 9:30 (9*60 + 30 = 570 minutos)
# Quem for menor que 570 minutos é MANHÃ. Quem for >= 570 é TARDE.
HORARIOS_MANHA = [h for h in HORARIOS_PADRAO if "HRS" in h and calcular_minutos(h) > 0 and calcular_minutos(h) < 570]
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

def salvar_escala_individual(nome: str, horarios: list, caixas: list, data_inicio: date) -> bool:
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            cx = caixas[i] if caixas and i < len(caixas) else None
            
            supabase.rpc('save_escala_dia_final', {
                'p_nome': nome.strip(), 
                'p_data': data_dia.strftime('%Y-%m-%d'), 
                'p_horario': horario,
                'p_caixa': cx
            }).execute()
        return True
    except Exception as e: st.error(f"Erro ao salvar: {e}"); return False

def salvar_escala_via_excel(df_excel: pd.DataFrame, data_inicio_semana: date) -> bool:
    try:
        datas_reais = [(data_inicio_semana + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(7)]
        
        barra = st.progress(0, text="Processando arquivo...")
        total_linhas = len(df_excel)
        
        for index, row in df_excel.iterrows():
            nome = row.get('Nome')
            if pd.isna(nome) or str(nome).strip() == "" or "TOTAL" in str(nome) or "Manhã" in str(nome) or "Tarde" in str(nome): continue
            
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
                except:
                    caixa = None
                
                data_banco = (data_inicio_semana + timedelta(days=i)).strftime('%Y-%m-%d')
                
                supabase.rpc('save_escala_dia_final', {
                    'p_nome': str(nome).strip(), 
                    'p_data': data_banco, 
                    'p_horario': horario,
                    'p_caixa': caixa
                }).execute()
            
            if index % 5 == 0: barra.progress((index + 1) / total_linhas, text=f"Importando linha {index+1}...")
        barra.empty()
        return True
    except Exception as e: st.error(f"Erro ao processar Excel: {e}"); return False

def inicializar_semana_simples(data_inicio: date) -> bool:
    try:
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        df_colabs = carregar_colaboradores()
        if not df_colabs.empty:
            for nome in df_colabs['nome']:
                for i in range(7):
                    d = data_inicio + timedelta(days=i)
                    supabase.rpc('save_escala_dia_final', {'p_nome': nome, 'p_data': d.strftime('%Y-%m-%d'), 'p_horario': '', 'p_caixa': None}).execute()
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
    except Exception as e: 
        st.error(f"Erro ao adicionar (Verifique se o nome já existe): {e}")
        return False

def remover_colaboradores(lista_nomes: list) -> bool:
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': [n.strip() for n in lista_nomes]}).execute(); return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def atualizar_funcao_colaborador(nome: str, nova_funcao: str):
    try:
        supabase.table('colaboradores').update({'funcao': nova_funcao}).eq('nome', nome).execute()
        return True
    except Exception as e: 
        st.error(f"Erro ao atualizar função de {nome}: {e}")
        return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"},
        {"codigo": 1015, "nome": "Gisele", "senha": "3"},
        {"codigo": 1005, "nome": "Fabiana", "senha": "4"},
        {"codigo": 1016, "nome": "Amanda", "senha": "5"}
    ])

def gerar_html_escala(df_escala: pd.DataFrame, nome_colaborador: str, semana_str: str) -> str:
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
                    
                    html = gerar_html_escala(display[cols_renamed], nome_selecionado, semana_str)
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
            if salvar_escala_individual(colaborador, novos_horarios, novos_caixas, data_ini):
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
        
        # Carrega dados do banco para pré-preencher (Feature de Download Pronto)
        df_dados_db = carregar_escala_semana_por_id(id_semana)
        
        df_filtrado = df_colaboradores.copy()
        if 'funcao' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['funcao'] == funcao_selecionada]
        
        if df_filtrado.empty:
            st.error(f"Não há colaboradores com função '{funcao_selecionada}'.")
        else:
            # GERA AS COLUNAS DO EXCEL
            colunas = ['Nome']
            for i in range(7):
                d_str = (data_ini + timedelta(days=i)).strftime('%d/%m/%Y')
                colunas.append(d_str)
                if funcao_selecionada == "Operador(a) de Caixa":
                    colunas.append(f"CX_REF_{d_str}")

            df_template = pd.DataFrame(columns=colunas)
            df_template['Nome'] = sorted(df_filtrado['nome'].unique())
            
            # Criar dicionário de dados existentes para preenchimento rápido
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

                    # --- CORREÇÃO DE VISUAL ---
                    # Esconde as linhas de grade (grids) para o Excel ficar limpo
                    worksheet.hide_gridlines(2)
                    
                    # FORMATOS
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
                    worksheet.set_column(0, 0, 30, fmt_nome)
                    
                    col_idx = 1
                    last_data_row = len(df_template) # Ex: 10 nomes
                    row_total_m = last_data_row + 1
                    row_total_t = last_data_row + 2
                    
                    # Preenchendo dados existentes no Excel
                    for r_idx, row_name in enumerate(df_template['Nome']):
                        row_excel = r_idx + 1
                        worksheet.write(row_excel, 0, row_name, fmt_nome) # Reescreve nome com borda
                        
                        current_c = 1
                        for i_day in range(7):
                            d_atual = data_ini + timedelta(days=i_day)
                            info = dados_existentes.get((row_name, d_atual), {})
                            
                            # Horário
                            h_val = info.get('horario', "")
                            worksheet.write(row_excel, current_c, h_val, fmt_grid)
                            current_c += 1
                            
                            # Caixa
                            if funcao_selecionada == "Operador(a) de Caixa":
                                c_val = info.get('caixa', "")
                                worksheet.write(row_excel, current_c, c_val, fmt_grid)
                                current_c += 1

                    # Cabeçalhos e Validações
                    col_idx = 1
                    for i in range(7):
                        d_str = (data_ini + timedelta(days=i)).strftime('%d/%m/%Y')
                        
                        worksheet.write(0, col_idx, d_str, fmt_date_header)
                        worksheet.set_column(col_idx, col_idx, 12, fmt_grid)
                        worksheet.data_validation(1, col_idx, last_data_row, col_idx, {'validate': 'list', 'source': '=Dados!$A$1:$A$' + str(len(HORARIOS_PADRAO))})
                        
                        for h in H_VERMELHO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_vermelho})
                        for h in H_VERDE: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_verde})
                        for h in H_ROXO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_roxo})
                        for h in H_CINZA: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_cinza})
                        for h in H_AMARELO: worksheet.conditional_format(1, col_idx, last_data_row, col_idx, {'type': 'cell', 'criteria': 'equal to', 'value': f'"{h}"', 'format': fmt_amarelo})

                        col_idx += 1
                        
                        if funcao_selecionada == "Operador(a) de Caixa":
                            worksheet.write(0, col_idx, "CX", fmt_cx_header)
                            worksheet.set_column(col_idx, col_idx, 5, fmt_grid)
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
                        
                        # Usando as listas ajustadas (9:30 já é tarde)
                        crit_m = ",".join([f'COUNTIF({rng}, "{h}")' for h in HORARIOS_MANHA])
                        crit_t = ",".join([f'COUNTIF({rng}, "{h}")' for h in HORARIOS_TARDE])
                        
                        # Escreve a fórmula SOMA(CONT.SE(...))
                        # Se as listas estiverem vazias (ex: nenhum horário cadastrado), trata o erro
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
                    if salvar_escala_via_excel(pd.read_excel(arquivo_upload), data_ini):
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
        t1, t2, t3, t4, t5 = st.tabs(["Gerenciar Semanas", "Editar Escala (Manual)", "Importar / Baixar", "Colaboradores", "Visão Geral"])
        with t1: aba_gerenciar_semanas(df_semanas)
        with t2: aba_editar_escala_individual(df_colaboradores, df_semanas_ativas)
        with t3: aba_importar_excel(df_colaboradores, df_semanas_ativas)
        with t4: aba_gerenciar_colaboradores(df_colaboradores)
        with t5: aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)

if __name__ == "__main__":
    main()