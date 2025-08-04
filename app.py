import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from supabase import create_client, Client
import base64
from io import BytesIO
from fpdf import FPDF
import time

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

# --- FUNÇÃO DE SALVAMENTO FINAL E SIMPLIFICADA ---
def salvar_dia_individual(nome, data, horario):
    """Salva, atualiza ou apaga a escala para um único dia de um único colaborador."""
    try:
        data_str = data.strftime('%Y-%m-%d')
        # Se o horário estiver vazio, apaga o registro daquele dia.
        if horario in ["", None]:
            supabase.table('escalas').delete().match({'nome': nome, 'data': data_str}).execute()
        # Se houver um horário, insere ou atualiza (upsert).
        else:
            supabase.table('escalas').upsert({'nome': nome, 'data': data_str, 'horario': horario}, on_conflict='nome, data').execute()
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
    return pd.DataFrame([{"codigo": 1017, "nome": "Rogério", "senha": "1"}, {"codigo": 1002, "nome": "Andrews", "senha": "2"}])

def formatar_data_manual(data_timestamp):
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

# --- Carregamento inicial dos dados ---
df_colaboradores = carregar_colaboradores()
df_escalas = carregar_escalas()

# --- Interface Principal ---
st.title("📅 Visualizador de Escala")
st.markdown("<p style='text-align: center; font-size: 12px;'>Versão 1.0</p>", unsafe_allow_html=True)
st.sidebar.title("Modo de Acesso")
aba_principal = st.sidebar.radio("", ["Consultar minha escala", "Área do Fiscal"])

if "logado" not in st.session_state: st.session_state.logado = False
if st.session_state.logado:
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.logado = False
        st.rerun()

# --- Aba: Consultar Minha Escala ---
if aba_principal == "Consultar minha escala":
    st.header("🔎 Buscar minha escala")
    # ... (código da aba de consulta)
    pass

# --- Aba: Área do Fiscal ---
elif aba_principal == "Área do Fiscal":
    df_fiscais = carregar_fiscais()
    if not st.session_state.logado:
        st.header("🔐 Login do Fiscal")
        with st.form("login_form"):
            # ... (código do formulário de login)
            pass
    else:
        st.header(f"Bem-vindo, {st.session_state.get('nome_logado', '')}!")
        opcoes_abas = ["Visão Geral da Escala", "Editar Escala", "Gerenciar Colaboradores"]
        aba_selecionada = st.radio("Navegação", opcoes_abas, horizontal=True, label_visibility="collapsed")

        if aba_selecionada == "Visão Geral da Escala":
            # ... (código da visão geral)
            pass

        elif aba_selecionada == "Editar Escala":
            st.subheader("✏️ Editar Escala Individual")
            if df_colaboradores.empty:
                st.warning("Adicione colaboradores na aba 'Gerenciar Colaboradores'.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    nomes_lista = [""] + df_colaboradores["nome"].tolist()
                    colaborador_selecionado = st.selectbox("1. Selecione o colaborador:", nomes_lista)
                with col2:
                    data_selecionada = st.date_input("2. Selecione a data para editar:")

                if colaborador_selecionado and data_selecionada:
                    st.markdown("---")
                    
                    # Busca o horário atual para este dia específico
                    horario_atual = ""
                    if not df_escalas.empty:
                        escala_existente = df_escalas[
                            (df_escalas['nome'] == colaborador_selecionado) &
                            (df_escalas['data'].dt.date == data_selecionada)
                        ]
                        if not escala_existente.empty:
                            horario_atual = escala_existente['horario'].iloc[0]
                    
                    index_horario = HORARIOS_PADRAO.index(horario_atual) if horario_atual in HORARIOS_PADRAO else 0

                    novo_horario = st.selectbox(
                        f"**3. Defina o horário para {colaborador_selecionado} em {data_selecionada.strftime('%d/%m/%Y')}:**",
                        options=HORARIOS_PADRAO,
                        index=index_horario
                    )

                    if st.button("Salvar Dia", type="primary"):
                        with st.spinner("Salvando..."):
                            if salvar_dia_individual(colaborador_selecionado, data_selecionada, novo_horario):
                                st.cache_data.clear()
                                st.success(f"Escala de {colaborador_selecionado} para o dia {data_selecionada.strftime('%d/%m/%Y')} salva com sucesso!")
                                time.sleep(1)
                                st.rerun()
        
        elif aba_selecionada == "Gerenciar Colaboradores":
            # ... (código para gerenciar colaboradores)
            pass

# --- CÓDIGO COMPLETO DAS ABAS (PARA EVITAR OMISSÕES) ---
if aba_principal == "Consultar minha escala":
    st.header("🔎 Buscar minha escala")
    nomes_disponiveis = sorted(df_colaboradores["nome"].dropna().unique()) if not df_colaboradores.empty else []
    if not nomes_disponiveis:
        st.warning("Nenhum(a) colaborador(a) cadastrado(a) no sistema. Fale com o fiscal.")
    else:
        nome_digitado = st.text_input("Digite seu nome para buscar:", placeholder="Comece a digitar seu nome aqui...")
        nome_confirmado = None
        if nome_digitado:
            sugestoes = [n for n in nomes_disponiveis if nome_digitado.lower() in n.lower()]
            if sugestoes:
                st.info("Encontramos nomes correspondentes. Por favor, confirme o seu na lista abaixo.")
                nome_confirmado = st.selectbox("Confirme seu nome:", options=sugestoes)
            else:
                st.warning("Nenhum nome correspondente encontrado. Verifique a digitação.")

        if nome_confirmado:
            hoje = pd.Timestamp.today().normalize()
            data_fim = hoje + timedelta(days=30)
            st.info(f"Mostrando sua escala para **{nome_confirmado}** de hoje até {data_fim.strftime('%d/%m/%Y')}.")
            
            if not df_escalas.empty:
                resultados = df_escalas[(df_escalas["nome"].str.lower() == nome_confirmado.lower()) & (df_escalas["data"] >= hoje) & (df_escalas["data"] <= data_fim)].sort_values("data")
            else:
                resultados = pd.DataFrame()

            if not resultados.empty:
                resultados_display = resultados.copy()
                resultados_display["data"] = resultados_display["data"].apply(formatar_data_manual)
                st.dataframe(resultados_display[["data", "horario"]], use_container_width=True, hide_index=True)
                
                if st.button("📥 Baixar em PDF"):
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font('Arial', 'B', 16)
                    pdf.cell(200, 10, txt=f"Escala de Trabalho: {nome_confirmado}", ln=1, align="C")
                    # ... código para preencher o PDF
                    st.markdown("Download do PDF aqui.") # Placeholder
            else:
                st.success(f"**{nome_confirmado}**, você não possui escalas agendadas para os próximos 30 dias.")

if aba_principal == "Área do Fiscal":
    if not st.session_state.logado:
        with st.form("login_form"):
            st.header("🔐 Login do Fiscal")
            codigo = st.text_input("Código do fiscal")
            senha = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
            if submitted:
                if not codigo or not senha: st.error("Por favor, preencha o código e a senha.")
                elif not codigo.isdigit(): st.error("Código inválido. Digite apenas números.")
                else:
                    fiscal_auth = carregar_fiscais()
                    fiscal_auth = fiscal_auth[(fiscal_auth["codigo"] == int(codigo)) & (fiscal_auth["senha"] == str(senha))]
                    if not fiscal_auth.empty:
                        st.session_state.logado = True
                        st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]
                        st.rerun()
                    else: st.error("Código ou senha incorretos.")
    else:
        if aba_selecionada == "Visão Geral da Escala":
            st.subheader("🗓️ Visão Geral da Escala")
            data_inicio_visao = st.date_input("Ver escala a partir de:", datetime.date.today())
            if data_inicio_visao:
                data_fim_visao = data_inicio_visao + timedelta(days=6)
                st.info(f"Mostrando escalas de {data_inicio_visao.strftime('%d/%m')} a {data_fim_visao.strftime('%d/%m')}")
                if not df_escalas.empty:
                    df_view = df_escalas[(df_escalas['data'] >= pd.to_datetime(data_inicio_visao)) & (df_escalas['data'] <= pd.to_datetime(data_fim_visao))].copy()
                else: df_view = pd.DataFrame()

                if df_view.empty:
                    st.info("Nenhuma escala encontrada para este período.")
                else:
                    df_view['data'] = df_view['data'].apply(formatar_data_manual)
                    st.dataframe(df_view.sort_values(["data", "nome"]), use_container_width=True, hide_index=True)

        elif aba_selecionada == "Gerenciar Colaboradores":
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
                            st.cache_data.clear()
                            st.success(f"'{novo_nome}' adicionado(a) com sucesso!")
                            st.rerun()
                    else: st.error("Nome inválido ou já existente.")
                
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
st.markdown("---")
st.markdown(
    """
    <p style='text-align: center; color: grey;'>
        Desenvolvido por @Rogério Souza
    </p>
    """,
    unsafe_allow_html=True
)