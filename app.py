import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from supabase import create_client, Client

# --- Configurações Iniciais ---
st.set_page_config(page_title="Gestor de Escalas", layout="centered", initial_sidebar_state="collapsed")
st.title("📆 Gestor de Escalas")

# --- Conexão com Supabase ---
@st.cache_resource
def conectar_supabase():
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    return create_client(url, key)

supabase: Client = conectar_supabase()

# --- Dados Estáticos dos Fiscais ---
FISCAIS = {
    "1017": {"nome": "Rogério", "senha": "1"},
    "1002": {"nome": "Andrews", "senha": "2"},
}

HORARIOS_OPCOES = ["", "Folga", "5:50", "6:50", "7:30", "8:00", "8:30", "9:00", "9:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "Férias", "Afastado(a)", "Atestado"]

# --- Funções de Dados ---
@st.cache_data(ttl=300)
def get_colaboradores():
    res = supabase.table("colaboradores").select("nome").execute()
    return [r["nome"] for r in res.data] if res.data else []

@st.cache_data(ttl=300)
def get_escala():
    res = supabase.table("escala").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
    return df

def salvar_escala(nome, data, horario):
    data_str = data.strftime("%Y-%m-%d")
    existe = supabase.table("escala").select("*").eq("nome", nome).eq("data", data_str).execute()
    if existe.data:
        supabase.table("escala").update({"horario": horario}).eq("nome", nome).eq("data", data_str).execute()
    else:
        supabase.table("escala").insert({"nome": nome, "data": data_str, "horario": horario}).execute()

def adicionar_colaborador(nome):
    supabase.table("colaboradores").insert({"nome": nome}).execute()

def remover_colaborador(nome):
    supabase.table("colaboradores").delete().eq("nome", nome).execute()

# --- Sessão de Login ---
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_fiscal = ""

if not st.session_state.logado:
    st.subheader("🔐 Login de Fiscal")
    col1, col2 = st.columns(2)
    with col1:
        codigo = st.text_input("Código")
    with col2:
        senha = st.text_input("Senha", type="password")

    if st.button("Entrar"):
        if codigo in FISCAIS and FISCAIS[codigo]["senha"] == senha:
            st.session_state.logado = True
            st.session_state.nome_fiscal = FISCAIS[codigo]["nome"]
            st.success("Acesso concedido.")
            st.experimental_rerun()
        else:
            st.error("Código ou senha incorretos.")

# --- Página Principal ---
if st.session_state.logado:
    st.success(f"Logado como {st.session_state.nome_fiscal}")
    aba = st.radio("Menu", ["📋 Ver Escala", "🛠️ Editar Escala", "👤 Gerenciar Colaboradores"], horizontal=True)

    colaboradores = get_colaboradores()
    escalas = get_escala()

    if aba == "📋 Ver Escala":
        nome = st.selectbox("Selecione seu nome", colaboradores)
        hoje = datetime.today()
        data_limite = hoje + timedelta(days=30)
        df_pessoa = escalas[(escalas["nome"] == nome) & (escalas["data"] >= hoje) & (escalas["data"] <= data_limite)]
        df_pessoa = df_pessoa.sort_values("data")

        if not df_pessoa.empty:
            df_pessoa["data"] = df_pessoa["data"].dt.strftime("%d/%m/%Y")
            st.dataframe(df_pessoa[["data", "horario"]], use_container_width=True)
        else:
            st.info("Nenhuma escala registrada nos próximos 30 dias.")

    elif aba == "🛠️ Editar Escala":
        col1, col2 = st.columns(2)
        with col1:
            nome_colab = st.selectbox("Colaborador", colaboradores)
        with col2:
            data_alvo = st.date_input("Data")

        atual = escalas[(escalas["nome"] == nome_colab) & (escalas["data"].dt.date == data_alvo)]
        horario_atual = atual["horario"].values[0] if not atual.empty else ""
        novo_horario = st.selectbox("Horário", HORARIOS_OPCOES, index=HORARIOS_OPCOES.index(horario_atual) if horario_atual in HORARIOS_OPCOES else 0)

        if st.button("Salvar Horário"):
            salvar_escala(nome_colab, data_alvo, novo_horario)
            st.success("Horário salvo!")
            st.cache_data.clear()
            st.experimental_rerun()

    elif aba == "👤 Gerenciar Colaboradores":
        st.write("### Adicionar Novo Colaborador")
        novo_nome = st.text_input("Nome completo")
        if st.button("Adicionar") and novo_nome:
            adicionar_colaborador(novo_nome)
            st.success(f"'{novo_nome}' adicionado com sucesso.")
            st.cache_data.clear()
            st.experimental_rerun()

        st.write("### Remover Colaborador")
        nome_remover = st.selectbox("Escolha para remover", colaboradores)
        if st.button("Remover"):
            remover_colaborador(nome_remover)
            st.warning(f"'{nome_remover}' removido.")
            st.cache_data.clear()
            st.experimental_rerun()

    if st.button("Sair", type="primary"):
        st.session_state.logado = False
        st.session_state.nome_fiscal = ""
        st.experimental_rerun()
