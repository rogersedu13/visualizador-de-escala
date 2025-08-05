# Importando as bibliotecas necessárias
import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta, date
from supabase import create_client, Client
import time

# --- Constantes da Aplicação ---
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# --- Configuração da Página do Streamlit ---
st.set_page_config(
    page_title="Gestor de Escalas Pro",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Conexão com o Banco de Dados Supabase ---
# Nota: As credenciais são carregadas dos "Secrets" do Streamlit para segurança.
try:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("🚨 **Erro de Conexão:** Não foi possível conectar ao banco de dados. Verifique se as credenciais `supabase_url` e `supabase_key` estão configuradas nos Secrets do Streamlit.")
    st.stop()

# --- Gerenciamento de Estado da Sessão ---
if "logado" not in st.session_state:
    st.session_state.logado = False
if "nome_logado" not in st.session_state:
    st.session_state.nome_logado = ""

# --- Funções de Acesso a Dados (com Cache) ---
@st.cache_data(ttl=300)  # Cache de 5 minutos
def carregar_colaboradores() -> pd.DataFrame:
    """Busca a lista de colaboradores do banco de dados."""
    try:
        response = supabase.rpc('get_colaboradores').execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Erro ao carregar colaboradores: {e}")
        return pd.DataFrame(columns=['id', 'nome'])

@st.cache_data(ttl=60)  # Cache de 1 minuto para dados que mudam com frequência
def carregar_escalas() -> pd.DataFrame:
    """Busca todos os registros de escala do banco de dados."""
    try:
        response = supabase.rpc('get_escalas').execute()
        df = pd.DataFrame(response.data)
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escalas: {e}")
        return pd.DataFrame()

def salvar_dia_individual(nome: str, data: date, horario: str) -> bool:
    """Salva ou atualiza a escala de um colaborador para um dia específico."""
    try:
        supabase.rpc('save_escala_dia_final', {
            'p_nome': nome,
            'p_data': data.strftime('%Y-%m-%d'),
            'p_horario': horario
        }).execute()
        return True
    except Exception as e:
        st.error(f"Erro detalhado ao salvar: {e}")
        return False

def adicionar_colaborador(nome: str) -> bool:
    """Adiciona um novo colaborador ao banco de dados."""
    try:
        supabase.rpc('add_colaborador', {'p_nome': nome}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar colaborador: {e}")
        return False

def remover_colaboradores(lista_nomes: list) -> bool:
    """Remove um ou mais colaboradores do banco de dados."""
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': lista_nomes}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao remover colaboradores: {e}")
        return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    """Carrega os dados dos fiscais.
    
    ATENÇÃO: Em um ambiente de produção real, as senhas NUNCA devem ser
    armazenadas diretamente no código. Use um sistema de hash seguro e
    busque os dados de um local seguro, como os secrets do Streamlit.
    """
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"}
    ])

# --- Funções de Formatação e UI ---

def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    """Formata a data para 'dd/mm/aaaa (Dia da Semana)'."""
    if pd.isna(data_timestamp):
        return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_escalas: pd.DataFrame):
    """Interface para o colaborador consultar sua própria escala."""
    st.header("🔎 Consultar Minha Escala")
    st.markdown("Selecione seu nome para visualizar sua escala para os próximos 30 dias.")

    if df_colaboradores.empty:
        st.warning("Nenhum colaborador cadastrado no momento.")
        return

    nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
    nome_selecionado = st.selectbox(
        "Selecione seu nome:",
        options=nomes_disponiveis,
        index=0,
        help="Comece a digitar para buscar seu nome na lista."
    )

    if nome_selecionado:
        with st.container(border=True):
            hoje = pd.Timestamp.today().normalize()
            data_fim = hoje + timedelta(days=30)

            st.info(f"Mostrando a escala de **{nome_selecionado}** de hoje até {data_fim.strftime('%d/%m/%Y')}.")

            resultados = pd.DataFrame()
            if not df_escalas.empty:
                resultados = df_escalas[
                    (df_escalas["nome"].str.lower() == nome_selecionado.lower()) &
                    (df_escalas["data"] >= hoje) &
                    (df_escalas["data"] <= data_fim)
                ].sort_values("data")

            if not resultados.empty:
                resultados_display = resultados.copy()
                resultados_display["Data"] = resultados_display["data"].apply(formatar_data_completa)
                resultados_display.rename(columns={"horario": "Horário"}, inplace=True)
                st.dataframe(
                    resultados_display[["Data", "Horário"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success(f"✅ **{nome_selecionado}**, você não possui escalas agendadas para este período.")

def aba_visao_geral(df_escalas: pd.DataFrame):
    """Aba para visualização geral da escala da semana."""
    with st.container(border=True):
        st.subheader("🗓️ Visão Geral da Escala Semanal")
        data_inicio_visao = st.date_input("Ver escala a partir de:", datetime.date.today())

        if data_inicio_visao:
            data_fim_visao = data_inicio_visao + timedelta(days=6)
            st.info(f"Mostrando escalas de **{data_inicio_visao.strftime('%d/%m')}** a **{data_fim_visao.strftime('%d/%m')}**")

            df_view = pd.DataFrame()
            if not df_escalas.empty:
                df_view = df_escalas[
                    (df_escalas['data'].dt.date >= data_inicio_visao) &
                    (df_escalas['data'].dt.date <= data_fim_visao)
                ].copy()

            if df_view.empty:
                st.info("Nenhuma escala encontrada para este período.")
            else:
                # Pivotando a tabela para melhor visualização
                df_view['Dia'] = df_view['data'].dt.strftime('%d/%m (%a)')
                tabela_pivot = df_view.pivot_table(
                    index='nome',
                    columns='Dia',
                    values='horario',
                    aggfunc='first'
                ).fillna('') # Preenche dias sem escala com string vazia
                
                # Garante a ordem correta das colunas de data
                dias_ordenados = sorted(df_view['Dia'].unique())
                st.dataframe(tabela_pivot[dias_ordenados], use_container_width=True)


def aba_editar_escala(df_colaboradores: pd.DataFrame, df_escalas: pd.DataFrame):
    """Aba para editar a escala de um colaborador em um dia específico."""
    with st.container(border=True):
        st.subheader("✏️ Editar Escala por Dia")
        if df_colaboradores.empty:
            st.warning("Adicione colaboradores na aba 'Gerenciar' para poder editar escalas.")
            return

        col1, col2 = st.columns(2)
        with col1:
            nomes_lista = sorted(df_colaboradores["nome"].tolist())
            colaborador = st.selectbox("1. Selecione o colaborador:", nomes_lista, key="edit_colab")
        with col2:
            data_edicao = st.date_input("2. Selecione a data para editar:", key="edit_data")

        if colaborador and data_edicao:
            st.markdown("---")
            horario_atual = ""
            if not df_escalas.empty:
                escala_existente = df_escalas[
                    (df_escalas['nome'] == colaborador) &
                    (df_escalas['data'].dt.date == data_edicao)
                ]
                if not escala_existente.empty:
                    horario_atual = escala_existente['horario'].iloc[0]

            index_horario = HORARIOS_PADRAO.index(horario_atual) if horario_atual in HORARIOS_PADRAO else 0

            novo_horario = st.selectbox(
                f"**3. Defina o horário para {colaborador} em {data_edicao.strftime('%d/%m/%Y')}:**",
                options=HORARIOS_PADRAO,
                index=index_horario
            )

            if st.button("Salvar Alteração", type="primary", use_container_width=True):
                with st.spinner("Salvando..."):
                    if salvar_dia_individual(colaborador, data_edicao, novo_horario):
                        st.cache_data.clear()  # Limpa o cache para recarregar os dados
                        st.success("Escala salva com sucesso!")
                        time.sleep(1)
                        st.rerun()

def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    """Aba para adicionar e remover colaboradores."""
    st.subheader("👥 Gerenciar Colaboradores")
    col1, col2 = st.columns(2)

    with col1:
        with st.container(border=True):
            st.markdown("##### ➕ Adicionar Novo Colaborador")
            novo_nome = st.text_input("Nome do colaborador:", key="novo_nome").strip()
            if st.button("Adicionar", use_container_width=True):
                if novo_nome and (df_colaboradores.empty or novo_nome not in df_colaboradores["nome"].values):
                    if adicionar_colaborador(novo_nome):
                        st.cache_data.clear()
                        st.success(f"'{novo_nome}' adicionado com sucesso!")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("Nome inválido ou já existente.")

    with col2:
        with st.container(border=True):
            st.markdown("##### ➖ Remover Colaboradores")
            if not df_colaboradores.empty:
                nomes_para_remover = st.multiselect(
                    "Selecione um ou mais nomes:",
                    options=sorted(df_colaboradores["nome"].tolist())
                )
                if st.button("Remover Selecionados", type="secondary", use_container_width=True):
                    if nomes_para_remover:
                        if remover_colaboradores(nomes_para_remover):
                            st.cache_data.clear()
                            st.success("Colaboradores removidos com sucesso!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.warning("Nenhum colaborador selecionado.")
            else:
                st.info("Não há colaboradores para remover.")
    
    st.markdown("---")
    st.markdown("##### 📋 Lista de Colaboradores Atuais")
    st.dataframe(df_colaboradores[['nome']].sort_values('nome'), use_container_width=True, hide_index=True)


# --- Estrutura Principal da Aplicação ---
def main():
    """Função principal que renderiza a aplicação Streamlit."""
    st.title("📅 Gestor de Escalas Pro")

    # Carrega todos os dados necessários no início
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_escalas = carregar_escalas()

    # --- Lógica da Barra Lateral (Login/Logout) ---
    with st.sidebar:
        st.header("Modo de Acesso")

        if not st.session_state.logado:
            with st.form("login_form"):
                st.markdown("##### 🔐 Acesso Restrito")
                codigo = st.text_input("Código do Fiscal")
                senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    fiscal_auth = pd.DataFrame()
                    if codigo.isdigit():
                        fiscal_auth = df_fiscais[
                            (df_fiscais["codigo"] == int(codigo)) &
                            (df_fiscais["senha"] == str(senha))
                        ]
                    if not fiscal_auth.empty:
                        st.session_state.logado = True
                        st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]
                        st.rerun()
                    else:
                        st.error("Código ou senha incorretos.")
        else:
            st.success(f"Bem-vindo, **{st.session_state.nome_logado}**!")
            if st.button("Logout", use_container_width=True):
                st.session_state.logado = False
                st.session_state.nome_logado = ""
                st.cache_data.clear()
                st.rerun()

        st.markdown("---")
        st.info("Desenvolvido por Rogério Souza")
        st.write("Versão 2.0")


    # --- Renderização do Conteúdo Principal ---
    if st.session_state.logado:
        # Interface do Fiscal (Logado)
        tab1, tab2, tab3, tab4 = st.tabs([
            "Visão Geral 🗓️",
            "Editar Escala ✏️",
            "Gerenciar Colaboradores 👥",
            "Consultar Individualmente 🔎"
        ])

        with tab1:
            aba_visao_geral(df_escalas)
        with tab2:
            aba_editar_escala(df_colaboradores, df_escalas)
        with tab3:
            aba_gerenciar_colaboradores(df_colaboradores)
        with tab4:
            # Reutiliza a mesma função da visão pública
            aba_consultar_escala_publica(df_colaboradores, df_escalas)
    else:
        # Interface Pública (Não Logado)
        aba_consultar_escala_publica(df_colaboradores, df_escalas)


if __name__ == "__main__":
    main()