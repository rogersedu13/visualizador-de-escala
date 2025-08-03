import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from supabase import create_client, Client
import base64
from io import BytesIO
from fpdf import FPDF
import time
import random

# --- Constantes ---
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# --- Configuração da Página ---
st.set_page_config(page_title="Visualizador de Escala", layout="wide", initial_sidebar_state="expanded")

# --- Conexão com o Supabase ---
try:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Falha na conexão com o banco de dados. Verifique a configuração dos 'Secrets'.")
    st.info("Certifique-se de que os nomes nos Secrets são 'supabase_url' e 'supabase_key'.")
    st.stop()

# --- Funções de Dados (usando Supabase) ---
@st.cache_data(ttl=30)
def carregar_colaboradores():
    try:
        response = supabase.table('colaboradores').select('nome').order('nome').execute()
        df = pd.DataFrame(response.data)
        return df if not df.empty else pd.DataFrame(columns=['nome'])
    except Exception as e:
        st.error(f"Erro ao carregar colaboradores: {e}")
        return pd.DataFrame(columns=['nome'])

@st.cache_data(ttl=30)
def carregar_escalas():
    try:
        response = supabase.table('escalas').select('nome, data, horario').execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            return pd.DataFrame(columns=['nome', 'data', 'horario'])
        
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escalas: {e}")
        return pd.DataFrame(columns=['nome', 'data', 'horario'])

def salvar_escala_individual(registros_para_salvar):
    try:
        for registro in registros_para_salvar:
            nome = registro['nome']
            data = registro['data']
            horario = registro['horario']

            if horario in ["", None]:
                supabase.table('escalas').delete().match({'nome': nome, 'data': data}).execute()
            else:
                supabase.table('escalas').upsert({
                    'nome': nome,
                    'data': data,
                    'horario': horario
                }, on_conflict='nome, data').execute()
        return True
    except Exception as e:
        st.error(f"ERRO DETALHADO AO SALVAR: {e}")
        return False

def adicionar_colaborador(nome):
    try:
        supabase.table('colaboradores').insert({"nome": nome}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar colaborador: {e}")
        return False

def remover_colaboradores(lista_nomes):
    try:
        supabase.table('colaboradores').delete().in_('nome', lista_nomes).execute()
        supabase.table('escalas').delete().in_('nome', lista_nomes).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao remover colaboradores: {e}")
        return False

def carregar_fiscais():
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"}
    ])

def formatar_data_manual(data_timestamp):
    if pd.isna(data_timestamp):
        return ""
    dia_semana_str = DIAS_SEMANA_PT[data_timestamp.weekday()]
    return data_timestamp.strftime(f'%d/%m/%Y ({dia_semana_str})')

# --- Carregamento inicial dos dados ---
df_colaboradores = carregar_colaboradores()
df_escalas = carregar_escalas()

# --- Interface Principal ---
st.title("📅 Visualizador de Escala")
st.markdown("<p style='text-align: center; font-size: 12px;'>Versão 12.2 - Diagnóstico</p>", unsafe_allow_html=True)

st.sidebar.title("Modo de Acesso")
aba_principal = st.sidebar.radio("", ["Consultar minha escala", "Área do Fiscal"])

if "logado" not in st.session_state:
    st.session_state.logado = False

if st.session_state.logado:
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.logado = False
        st.rerun()

# --- Aba: Consultar Minha Escala ---
if aba_principal == "Consultar minha escala":
    # ... (código desta aba permanece o mesmo) ...
    pass
# --- Aba: Área do Fiscal ---
elif aba_principal == "Área do Fiscal":
    df_fiscais = carregar_fiscais()
    if not st.session_state.logado:
        # ... (código de login permanece o mesmo) ...
        pass
    else: 
        st.header(f"Bem-vindo, {st.session_state.get('nome_logado', '')}!")
        
        opcoes_abas = ["Visão Geral da Escala", "Editar Escala Semanal", "Gerenciar Colaboradores"]
        aba_selecionada = st.radio("Navegação do Fiscal", opcoes_abas, horizontal=True, label_visibility="collapsed")
        
        if aba_selecionada == "Visão Geral da Escala":
            # ... (código desta aba permanece o mesmo) ...
            pass

        elif aba_selecionada == "Editar Escala Semanal":
            st.subheader("✏️ Editar Escala Semanal")
            if df_colaboradores.empty:
                st.warning("Adicione colaboradores na aba 'Gerenciar Colaboradores' primeiro.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    dia_selecionado = st.date_input("Selecione uma data para a semana:", datetime.date.today())
                with col2:
                    nomes_lista = [""] + df_colaboradores["nome"].tolist()
                    colaborador_selecionado = st.selectbox("Selecione o colaborador para editar:", nomes_lista, index=0)

                if colaborador_selecionado:
                    dia_inicio_semana = dia_selecionado - timedelta(days=dia_selecionado.weekday())
                    st.info(f"Editando a semana de **{dia_inicio_semana.strftime('%d/%m/%Y')}** para **{colaborador_selecionado}**")
                    
                    datas_da_semana_obj = [dia_inicio_semana + timedelta(days=i) for i in range(7)]
                    datas_da_semana_ts = [pd.to_datetime(d) for d in datas_da_semana_obj]

                    escala_atual_colaborador = df_escalas[
                        (df_escalas['nome'] == colaborador_selecionado) &
                        (df_escalas['data'].isin(datas_da_semana_ts))
                    ]
                    
                    with st.form(key=f"form_{colaborador_selecionado}_{dia_inicio_semana}"):
                        cols = st.columns(7)
                        for i, data_obj in enumerate(datas_da_semana_obj):
                            dia_str = DIAS_SEMANA_PT[i]
                            
                            horario_atual_df = escala_atual_colaborador[escala_atual_colaborador['data'].dt.date == data_obj]
                            horario_atual = horario_atual_df['horario'].iloc[0] if not horario_atual_df.empty else ""
                            
                            index_horario = HORARIOS_PADRAO.index(horario_atual) if horario_atual in HORARIOS_PADRAO else 0
                            
                            with cols[i]:
                                st.selectbox(
                                    f"{dia_str} ({data_obj.strftime('%d/%m')})",
                                    options=HORARIOS_PADRAO,
                                    index=index_horario,
                                    key=f"horario_{i}"
                                )
                        
                        submitted = st.form_submit_button("Salvar Escala de " + colaborador_selecionado)
                        
                        if submitted:
                            registros_para_salvar = []
                            for i, data_obj in enumerate(datas_da_semana_obj):
                                widget_key = f"horario_{i}"
                                novo_horario = st.session_state[widget_key]
                                
                                registro = {
                                    "nome": colaborador_selecionado,
                                    "data": data_obj.strftime('%Y-%m-%d'),
                                    "horario": novo_horario
                                }
                                registros_para_salvar.append(registro)
                            
                            with st.spinner("Salvando..."):
                                if salvar_escala_individual(registros_para_salvar):
                                    st.cache_data.clear()
                                    st.success("Escala salva com sucesso!")
                                    time.sleep(1)
                                    st.rerun()

        elif aba_selecionada == "Gerenciar Colaboradores":
            st.subheader("👥 Gerenciar Colaboradores")
            
            # --- FERRAMENTAS DE DIAGNÓSTICO ---
            st.markdown("---")
            st.subheader("🔬 Ferramentas de Diagnóstico")
            
            col_diag1, col_diag2 = st.columns(2)
            
            with col_diag1:
                if st.button("Teste 1: Forçar Inserção de Teste"):
                    try:
                        # Gera um número aleatório para garantir que o registro seja único
                        rand_num = random.randint(1000, 9999)
                        data_teste = {"nome": f"TESTE_{rand_num}", "data": datetime.date.today().strftime('%Y-%m-%d'), "horario": "12:34"}
                        supabase.table('escalas').insert(data_teste).execute()
                        st.success("SUCESSO: Inserção de teste funcionou!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"FALHA: Inserção de teste falhou.")
                        st.exception(e)

            with col_diag2:
                if st.button("Teste 2: Ver Dados Brutos do Banco"):
                    st.info("Buscando todos os dados da tabela 'escalas'...")
                    try:
                        response = supabase.table('escalas').select('*').order('data', desc=True).execute()
                        df_bruto = pd.DataFrame(response.data)
                        st.success(f"Encontrados {len(df_bruto)} registros.")
                        st.dataframe(df_bruto)
                    except Exception as e:
                        st.error("FALHA: Não foi possível ler os dados brutos.")
                        st.exception(e)
            st.markdown("---")
            
            
            # --- GERENCIAMENTO NORMAL ---
            col1, col2 = st.columns([0.6, 0.4])
            with col1:
                st.write("**Colaboradores Atuais:**")
                st.dataframe(df_colaboradores, use_container_width=True, hide_index=True)
            with col2:
                st.write("**Adicionar novo(a) colaborador(a):**")
                novo_nome = st.text_input("Nome").strip()
                if st.button("Adicionar Colaborador(a)"):
                    if novo_nome and (df_colaboradores.empty or novo_nome not in df_colaboradores["nome"].values):
                        if adicionar_colaborador(novo_nome):
                            st.cache_data.clear()
                            st.success(f"'{novo_nome}' adicionado(a) com sucesso!")
                            st.rerun()
                    else:
                        st.error("Nome inválido ou já existente.")
                
                st.write("**Remover colaborador(a):**")
                if not df_colaboradores.empty:
                    nomes_para_remover = st.multiselect("Selecione para remover", options=df_colaboradores["nome"].tolist())
                    if st.button("Remover Selecionados", type="secondary"):
                        if nomes_para_remover:
                            if remover_colaboradores(nomes_para_remover):
                                st.cache_data.clear()
                                st.success("Colaboradores removidos com sucesso!")
                                st.rerun()

# --- RODAPÉ ---
# ... (código do rodapé)