import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from streamlit_gsheets import GSheetsConnection
import time
import random

# --- Constantes ---
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

# --- Configuração da Página ---
st.set_page_config(page_title="Visualizador de Escala", layout="wide", initial_sidebar_state="expanded")

# --- Conexão com o Google Sheets ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error("Falha na conexão com a Planilha Google. Verifique a configuração dos 'Secrets'.")
    st.exception(e)
    st.stop()

# --- Gerenciamento de Estado e Cache ---
if "logado" not in st.session_state: st.session_state.logado = False
if "nome_logado" not in st.session_state: st.session_state.nome_logado = ""
if "cache_key" not in st.session_state: st.session_state.cache_key = str(random.randint(1, 1000000))

def invalidate_cache():
    """Força a invalidação do cache gerando uma nova chave."""
    st.session_state.cache_key = str(random.randint(1, 1000000))

# --- Funções de Dados (Apenas Leitura) ---
@st.cache_data(ttl=60) # Cache de 1 minuto
def carregar_dados(worksheet_name, columns, _cache_key):
    try:
        df = conn.read(worksheet=worksheet_name, usecols=list(range(len(columns))))
        df = df.dropna(how="all")
        if not df.empty and 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        return pd.DataFrame(columns=columns)

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

def aba_gerenciar_colaboradores(df_colaboradores):
    st.subheader("👥 Colaboradores Cadastrados")
    st.info("Para adicionar ou remover colaboradores, por favor, edite diretamente a aba 'colaboradores' da sua Planilha Google.")
    st.dataframe(df_colaboradores, use_container_width=True, hide_index=True)


# --- Estrutura Principal da Aplicação ---
def main():
    st.title("📅 Visualizador de Escala")
    st.markdown("<p style='text-align: center; font-size: 12px;'>1.2</p>", unsafe_allow_html=True)
    
    # Carrega os dados usando a chave de cache da sessão
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_dados("colaboradores", ["nome"], st.session_state.cache_key)
    df_escalas = carregar_dados("escalas", ["nome", "data", "horario"], st.session_state.cache_key)

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
                    invalidate_cache()
                    st.rerun()
                else: st.sidebar.error("Código ou senha incorretos.")
        
        st.sidebar.markdown("---")
        aba_consultar_escala(df_colaboradores, df_escalas)
    
    else: # Se estiver logado
        st.sidebar.success(f"Logado como: {st.session_state.nome_logado}")
        
        # Botão para o fiscal forçar a atualização dos dados após editar a planilha
        if st.sidebar.button("🔄 Atualizar Dados da Planilha", use_container_width=True):
            invalidate_cache()
            st.toast("Dados atualizados!")
            time.sleep(1)
            st.rerun()

        if st.sidebar.button("Logout", use_container_width=True):
            st.session_state.logado = False
            invalidate_cache()
            st.rerun()
        
        opcoes_abas = ["Visão Geral da Escala", "Gerenciar Colaboradores", "Consultar Escala"]
        aba_selecionada = st.radio("Navegação", opcoes_abas, horizontal=True, label_visibility="collapsed")
        
        if aba_selecionada == "Visão Geral da Escala":
            aba_visao_geral(df_escalas)
        elif aba_selecionada == "Gerenciar Colaboradores":
            aba_gerenciar_colaboradores(df_colaboradores)
        elif aba_selecionada == "Consultar Escala":
            aba_consultar_escala(df_colaboradores, df_escalas)

    st.markdown("---")
    st.markdown("""<p style='text-align: center; color: grey;'>Desenvolvido por @Rogério Souza</p>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()