import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from streamlit_gsheets import GSheetsConnection
import time
import gspread_dataframe as gd
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
    st.session_state.cache_key = str(random.randint(1, 1000000))

# --- Funções de Dados (usando Google Sheets) ---
@st.cache_data(ttl=600)
def carregar_dados(worksheet_name, columns, _cache_key):
    try:
        df = conn.read(worksheet=worksheet_name, usecols=list(range(len(columns))))
        df = df.dropna(how="all")
        if not df.empty and 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        return pd.DataFrame(columns=columns)

# --- NOVA FUNÇÃO DE SALVAMENTO DE ACESSO DIRETO ---
def salvar_dados_direto(worksheet_name, df_atualizado):
    try:
        spreadsheet = conn.instance.open(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = spreadsheet.worksheet(worksheet_name)
        
        # Converte a coluna de data para string no formato correto
        if 'data' in df_atualizado.columns:
            df_atualizado['data'] = pd.to_datetime(df_atualizado['data']).dt.strftime('%Y-%m-%d')

        worksheet.clear()
        gd.set_with_dataframe(worksheet, df_atualizado, resize=True)
        return True
    except Exception as e:
        st.error(f"ERRO DETALHADO AO SALVAR DIRETAMENTE: {e}")
        st.exception(e)
        return False

def carregar_fiscais():
    return pd.DataFrame([{"codigo": 1017, "nome": "Rogério", "senha": "1"}, {"codigo": 1002, "nome": "Andrews", "senha": "2"}])

def formatar_data_manual(data_timestamp):
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

# --- Funções de Interface (Componentes das Abas) ---
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
        
        index_horario = HORARIOS_PADRAO.index(str(horario_atual)) if str(horario_atual) in HORARIOS_PADRAO else 0

        novo_horario = st.selectbox(f"**3. Defina o horário para {colaborador_selecionado} em {data_selecionada.strftime('%d/%m/%Y')}:**", options=HORARIOS_PADRAO, index=index_horario)

        if st.button("Salvar Dia", type="primary", use_container_width=True):
            with st.spinner("Salvando..."):
                df_escalas_fresco = carregar_dados("escalas", ["nome", "data", "horario"], str(time.time()))
                
                df_escalas_sem_o_dia = df_escalas_fresco[~((df_escalas_fresco['nome'] == colaborador_selecionado) & (df_escalas_fresco['data'].dt.date == data_selecionada))]
                
                df_escalas_atualizado = df_escalas_sem_o_dia
                if novo_horario not in ["", None]:
                    novo_registro = pd.DataFrame([{"nome": colaborador_selecionado, "data": pd.to_datetime(data_selecionada), "horario": novo_horario}])
                    df_escalas_atualizado = pd.concat([df_escalas_sem_o_dia, novo_registro], ignore_index=True)

                if salvar_dados_direto("escalas", df_escalas_atualizado):
                    invalidate_cache()
                    st.success("Escala salva com sucesso!")
                    time.sleep(1)
                    st.rerun()

def aba_gerenciar_colaboradores(df_colaboradores, df_escalas):
    st.subheader("👥 Gerenciar Colaboradores")
    
    # --- FERRAMENTA DE DIAGNÓSTICO DE PERMISSÃO ---
    st.markdown("---")
    with st.expander("🔬 Clique aqui para verificar as permissões da Planilha"):
        if st.button("Verificar Permissão de Escrita"):
            try:
                client_email = st.secrets["connections"]["gsheets"]["client_email"]
                spreadsheet = conn.instance.open(st.secrets["connections"]["gsheets"]["spreadsheet"])
                permissions = spreadsheet.list_permissions()
                
                permissao_encontrada = False
                for p in permissions:
                    if p.get('emailAddress') == client_email:
                        st.info(f"Email do Robô: {p.get('emailAddress')}")
                        st.info(f"Permissão Encontrada: **{p.get('role').upper()}**")
                        permissao_encontrada = True
                        if p.get('role') == 'writer':
                            st.success("✅ A permissão 'writer' (Editor) está CORRETA!")
                        else:
                            st.error(f"❌ A permissão está como '{p.get('role')}', mas deveria ser 'writer' (Editor).")
                
                if not permissao_encontrada:
                    st.error("ERRO: O email do robô não foi encontrado na lista de compartilhamento da planilha.")

            except Exception as e:
                st.error("Ocorreu um erro ao verificar as permissões.")
                st.exception(e)
    st.markdown("---")


    col1, col2 = st.columns([0.6, 0.4])
    with col1:
        st.write("**Colaboradores Atuais:**")
        st.dataframe(df_colaboradores, use_container_width=True, hide_index=True)
    with col2:
        st.write("**Adicionar novo(a) colaborador(a):**")
        novo_nome = st.text_input("Nome").strip()
        if st.button("Adicionar Colaborador(a)"):
            if novo_nome and (df_colaboradores.empty or novo_nome not in df_colaboradores["nome"].values):
                novo_df = pd.DataFrame([{"nome": novo_nome}])
                df_atualizado = pd.concat([df_colaboradores, novo_df], ignore_index=True)
                if salvar_dados_direto("colaboradores", df_atualizado):
                    invalidate_cache()
                    st.success(f"'{novo_nome}' adicionado(a) com sucesso!")
                    st.rerun()
            else: st.error("Nome inválido ou já existente.")
        
        st.write("**Remover colaborador(a):**")
        if not df_colaboradores.empty:
            nomes_para_remover = st.multiselect("Selecione para remover", options=df_colaboradores["nome"].tolist())
            if st.button("Remover Selecionados", type="secondary"):
                if nomes_para_remover:
                    df_colaboradores_final = df_colaboradores[~df_colaboradores['nome'].isin(nomes_para_remover)]
                    df_escalas_final = df_escalas[~df_escalas['nome'].isin(nomes_para_remover)]
                    if salvar_dados_direto("colaboradores", df_colaboradores_final) and salvar_dados_direto("escalas", df_escalas_final):
                        invalidate_cache()
                        st.success("Colaboradores removidos com sucesso!")
                        st.rerun()
# --- Estrutura Principal da Aplicação ---
def main():
    st.title("📅 Visualizador de Escala")
    st.markdown("<p style='text-align: center; font-size: 12px;'>Versão 1.2</p>", unsafe_allow_html=True)
    
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_dados("colaboradores", ["nome"], st.session_state.cache_key)
    df_escalas = carregar_dados("escalas", ["nome", "data", "horario"], st.session_state.cache_key)

    st.sidebar.title("Modo de Acesso")
    if not st.session_state.logado:
        # TELA DE LOGIN
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
        # ABA CONSULTAR ESCALA PARA NÃO LOGADOS
        aba_consultar_escala(df_colaboradores, df_escalas)
    
    else:
        st.sidebar.success(f"Logado como: {st.session_state.nome_logado}")
        if st.sidebar.button("Logout", use_container_width=True):
            st.session_state.logado = False
            invalidate_cache()
            st.rerun()
        
        opcoes_abas = ["Visão Geral da Escala", "Editar Escala", "Gerenciar Colaboradores", "Consultar Escala"]
        aba_selecionada = st.radio("Navegação", opcoes_abas, horizontal=True, label_visibility="collapsed")
        
        if aba_selecionada == "Visão Geral da Escala": aba_visao_geral(df_escalas)
        elif aba_selecionada == "Editar Escala": aba_editar_escala(df_colaboradores, df_escalas)
        elif aba_selecionada == "Gerenciar Colaboradores": aba_gerenciar_colaboradores(df_colaboradores, df_escalas)
        elif aba_selecionada == "Consultar Escala": aba_consultar_escala(df_colaboradores, df_escalas)

    st.markdown("---")
    st.markdown("""<p style='text-align: center; color: grey;'>Desenvolvido por @Rogério Souza</p>""", unsafe_allow_html=True)

if __name__ == "__main__":
    main()