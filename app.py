import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from supabase import create_client, Client
import random
import time
from fpdf import FPDF
import base64
from io import BytesIO

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
    st.stop()

# --- Gerenciamento de Estado e Cache ---
if "logado" not in st.session_state: st.session_state.logado = False
if "nome_logado" not in st.session_state: st.session_state.nome_logado = ""
if "cache_key" not in st.session_state: st.session_state.cache_key = str(random.randint(1, 1000000))

def invalidate_cache():
    st.session_state.cache_key = str(random.randint(1, 1000000))

# --- Funções de Dados ---
@st.cache_data(ttl=600)
def carregar_colaboradores(cache_key):
    try:
        # Usando a função SQL para maior segurança e consistência
        response = supabase.rpc('get_colaboradores').execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Erro ao carregar colaboradores: {e}")
        return pd.DataFrame(columns=['nome'])

@st.cache_data(ttl=600)
def carregar_escalas(cache_key):
    try:
        # Usando a função SQL
        response = supabase.rpc('get_escalas').execute()
        df = pd.DataFrame(response.data)
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escalas: {e}")
        return pd.DataFrame(columns=['nome', 'data', 'horario'])

def salvar_dia_individual(nome, data, horario):
    try:
        # Usando a função SQL segura
        supabase.rpc('save_escala_dia_final', {'p_nome': nome, 'p_data': data.strftime('%Y-%m-%d'), 'p_horario': horario}).execute()
        return True
    except Exception as e:
        st.error(f"ERRO DETALHADO AO SALVAR: {e}")
        return False

def adicionar_colaborador(nome):
    try:
        supabase.rpc('add_colaborador', {'p_nome': nome}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar colaborador: {e}")
        return False

def remover_colaboradores(lista_nomes):
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': lista_nomes}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao remover colaboradores: {e}")
        return False

def carregar_fiscais():
    return pd.DataFrame([{"codigo": 1017, "nome": "Rogério", "senha": "1"}, {"codigo": 1002, "nome": "Andrews", "senha": "2"}])

def formatar_data_manual(data_timestamp):
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

# --- Funções de Interface ---
def aba_consultar_escala(df_colaboradores, df_escalas):
    st.header("🔎 Buscar minha escala")
    nomes_disponiveis = sorted(df_colaboradores["nome"].dropna().unique()) if not df_colaboradores.empty else []
    if not nomes_disponiveis:
        st.warning("Nenhum(a) colaborador(a) cadastrado(a).")
        return

    nome_digitado = st.text_input("Digite seu nome para buscar:", placeholder="Comece a digitar...")
    if nome_digitado:
        sugestoes = [n for n in nomes_disponiveis if nome_digitado.lower() in n.lower()]
        if sugestoes:
            nome_confirmado = st.selectbox("Confirme seu nome:", options=sugestoes)
            if nome_confirmado:
                hoje = pd.Timestamp.today().normalize()
                data_fim = hoje + timedelta(days=30)
                st.info(f"Mostrando sua escala para **{nome_confirmado}** de hoje até {data_fim.strftime('%d/%m/%Y')}.")
                
                resultados = pd.DataFrame()
                if not df_escalas.empty:
                    df_escalas['nome'] = df_escalas['nome'].astype(str)
                    resultados = df_escalas[(df_escalas["nome"].str.lower() == nome_confirmado.lower()) & (df_escalas["data"] >= hoje) & (df_escalas["data"] <= data_fim)].sort_values("data")

                if not resultados.empty:
                    resultados_display = resultados.copy()
                    resultados_display["data"] = resultados_display["data"].apply(formatar_data_manual)
                    st.dataframe(resultados_display[["data", "horario"]], use_container_width=True, hide_index=True)
                else:
                    st.success(f"**{nome_confirmado}**, você não possui escalas agendadas.")
        elif len(nome_digitado) > 2:
            st.warning("Nenhum nome correspondente encontrado.")

def aba_visao_geral(df_escalas):
    st.subheader("🗓️ Visão Geral da Escala")
    data_inicio_visao = st.date_input("Ver escala a partir de:", datetime.date.today())
    if data_inicio_visao:
        data_fim_visao = data_inicio_visao + timedelta(days=6)
        st.info(f"Mostrando escalas de {data_inicio_visao.strftime('%d/%m')} a {data_fim_visao.strftime('%d/%m')}")
        
        df_view = pd.DataFrame()
        if not df_escalas.empty:
            df_view = df_escalas[(df_escalas['data'] >= pd.to_datetime(data_inicio_visao)) & (df_escalas['data'] <= pd.to_datetime(data_fim_visao))].copy()

        if df_view.empty:
            st.info("Nenhuma escala encontrada para este período.")
        else:
            df_view['data'] = df_view['data'].apply(formatar_data_manual)
            st.dataframe(df_view.sort_values(["data", "nome"]), use_container_width=True, hide_index=True)

def aba_editar_escala(df_colaboradores, df_escalas):
    st.subheader("✏️ Editar Escala por Dia")
    if df_colaboradores.empty:
        st.warning("Adicione colaboradores na aba 'Gerenciar Colaboradores'.")
        return

    col1, col2 = st.columns(2)
    with col1:
        nomes_lista = df_colaboradores["nome"].tolist()
        colaborador_selecionado = st.selectbox("1. Selecione o colaborador:", nomes_lista)
    with col2:
        data_selecionada = st.date_input("2. Selecione a data para editar:")

    if colaborador_selecionado and data_selecionada:
        st.markdown("---")
        
        horario_atual = ""
        if not df_escalas.empty:
            escala_existente = df_escalas[(df_escalas['nome'] == colaborador_selecionado) & (df_escalas['data'].dt.date == data_selecionada)]
            if not escala_existente.empty:
                horario_atual = escala_existente['horario'].iloc[0]
        
        index_horario = HORARIOS_PADRAO.index(horario_atual) if horario_atual in HORARIOS_PADRAO else 0

        novo_horario = st.selectbox(f"**3. Defina o horário para {colaborador_selecionado} em {data_selecionada.strftime('%d/%m/%Y')}:**", options=HORARIOS_PADRAO, index=index_horario)

        if st.button("Salvar Dia", type="primary", use_container_width=True):
            with st.spinner("Salvando..."):
                if salvar_dia_individual(colaborador_selecionado, data_selecionada, novo_horario):
                    invalidate_cache()
                    st.success("Escala salva com sucesso!")
                    time.sleep(1)
                    st.rerun()

def aba_gerenciar_colaboradores(df_colaboradores):
    st.subheader("👥 Gerenciar Colaboradores")
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
                    invalidate_cache()
                    st.success(f"'{novo_nome}' adicionado(a) com sucesso!")
                    st.rerun()
            else: st.error("Nome inválido ou já existente.")
        
        st.write("**Remover colaborador(a):**")
        if not df_colaboradores.empty:
            nomes_para_remover = st.multiselect("Selecione para remover", options=df_colaboradores["nome"].tolist())
            if st.button("Remover Selecionados", type="secondary"):
                if nomes_para_remover:
                    if remover_colaboradores(nomes_para_remover):
                        invalidate_cache()
                        st.success("Colaboradores removidos com sucesso!")
                        st.rerun()

# --- Estrutura Principal ---
def main():
    st.title("📅 Visualizador de Escala")
    st.markdown("<p style='text-align: center; font-size: 12px;'>Versão 1.2</p>", unsafe_allow_html=True)
    
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores(st.session_state.cache_key)
    df_escalas = carregar_escalas(st.session_state.cache_key)

    st.sidebar.title("Modo de Acesso")
    if not st.session_state.logado:
        with st.sidebar.form("login_form"):
            st.header("🔐 Acesso Fiscal")
            codigo = st.text_input("Código do fiscal")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                fiscal_auth = pd.DataFrame()
                if codigo.isdigit():
                    fiscal_auth = df_fiscais[(df_fiscais["codigo"] == int(codigo)) & (df_fiscais["senha"] == str(senha))]
                if not fiscal_auth.empty:
                    st.session_state.logado = True
                    st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]
                    st.rerun()
                else: st.sidebar.error("Código ou senha incorretos.")
        
        st.sidebar.markdown("---")
        aba_consultar_escala(df_colaboradores, df_escalas)
    
    else:
        st.sidebar.success(f"Logado como: {st.session_state.nome_logado}")
        if st.sidebar.button("🔄 Forçar Atualização", use_container_width=True, help="Clique se os dados parecerem desatualizados."):
            invalidate_cache()
            st.toast("Dados atualizados!")
            st.rerun()
        if st.sidebar.button("Logout", use_container_width=True):
            st.session_state.logado = False
            invalidate_cache()
            st.rerun()
        
        opcoes_abas = ["Visão Geral da Escala", "Editar Escala", "Gerenciar Colaboradores", "Consultar Escala"]
        aba_selecionada = st.radio("Navegação", opcoes_abas, horizontal=True, label_visibility="collapsed")
        
        if aba_selecionada == "Visão Geral da Escala": aba_visao_geral(df_escalas)
        elif aba_selecionada == "Editar Escala": aba_editar_escala(df_colaboradores, df_escalas)
        elif aba_selecionada == "Gerenciar Colaboradores": aba_gerenciar_colaboradores(df_colaboradores)
        elif aba_selecionada == "Consultar Escala": aba_consultar_escala(df_colaboradores, df_escalas)

    st.markdown("---")
    st.markdown("""<p style='text-align: center; color: grey;'>Desenvolvido por @Rogério Souza</p>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()