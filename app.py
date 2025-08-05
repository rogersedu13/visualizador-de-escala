import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
from supabase import create_client, Client

# Conexão com o Supabase
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

# Dados de fiscais autorizados
FISCAIS = {
    "1017": {"nome": "Rogério", "senha": "1"},
    "1002": {"nome": "Andrews", "senha": "2"},
}

# Inicializa estados da sessão
if "logado" not in st.session_state:
    st.session_state.logado = False
    st.session_state.nome_fiscal = ""

# Funções auxiliares

def get_colaboradores():
    response = supabase.table("colaboradores").select("nome").execute()
    nomes = [item["nome"] for item in response.data]
    return sorted(nomes)

def get_escala():
    response = supabase.table("escala").select("*").execute()
    df = pd.DataFrame(response.data)
    if not df.empty:
        df["data"] = pd.to_datetime(df["data"])
    return df

def carregar_escala_por_data(data):
    response = supabase.table("escala").select("*").eq("data", data).execute()
    df = pd.DataFrame(response.data)
    return df

def salvar_escala(df):
    for _, row in df.iterrows():
        existente = supabase.table("escala").select("id").eq("nome", row["nome"]).eq("data", row["data"]).execute()
        if existente.data:
            supabase.table("escala").update({"horario": row["horario"]}).eq("id", existente.data[0]["id"]).execute()
        else:
            supabase.table("escala").insert({"nome": row["nome"], "horario": row["horario"], "data": row["data"]}).execute()

# --- INTERFACE PRINCIPAL ---
st.title("📅 Visualizador de Escala - Antonelli Supermercados")

# VISUALIZAÇÃO PÚBLICA PARA COLABORADOR
df_escalas = get_escala()
st.markdown("### 🔍 Consultar Escala (Colaborador)")
nome_colaborador = st.selectbox("Selecione seu nome", get_colaboradores())

hoje = datetime.today()
limite = hoje + timedelta(days=30)
df_colab = df_escalas[(df_escalas["nome"] == nome_colaborador) & (df_escalas["data"] >= hoje) & (df_escalas["data"] <= limite)]

if not df_colab.empty:
    df_colab = df_colab.sort_values("data")
    df_colab["data"] = df_colab["data"].dt.strftime("%d/%m/%Y")
    st.dataframe(df_colab[["data", "horario"]], use_container_width=True)
else:
    st.info("Nenhuma escala encontrada nos próximos 30 dias para este colaborador.")

st.divider()

# ÁREA DE LOGIN DOS FISCAIS
if not st.session_state.logado:
    st.markdown("### 🔐 Acesso Restrito (Fiscais)")
    codigo = st.text_input("Código de Fiscal")
    senha = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if codigo in FISCAIS and FISCAIS[codigo]["senha"] == senha:
            st.session_state.logado = True
            st.session_state.nome_fiscal = FISCAIS[codigo]["nome"]
            st.success(f"Bem-vindo, {st.session_state.nome_fiscal}!")
        else:
            st.error("Código ou senha incorretos.")
else:
    st.markdown(f"### 💼 Editor de Escala - Fiscal {st.session_state.nome_fiscal}")

    data_ref = st.date_input("Selecione o dia da escala")
    nomes = get_colaboradores()
    df_atual = carregar_escala_por_data(data_ref.strftime("%Y-%m-%d"))

    if df_atual.empty:
        df_edit = pd.DataFrame({"nome": nomes, "horario": [""] * len(nomes), "data": [data_ref.strftime("%Y-%m-%d")] * len(nomes)})
    else:
        df_edit = pd.DataFrame({"nome": nomes})
        df_merge = df_edit.merge(df_atual[["nome", "horario"]], on="nome", how="left")
        df_merge["horario"] = df_merge["horario"].fillna("")
        df_merge["data"] = data_ref.strftime("%Y-%m-%d")
        df_edit = df_merge

    df_editado = st.data_editor(df_edit, num_rows="dynamic", use_container_width=True, key="escala_editor")

    if st.button("Salvar Escala"):
        salvar_escala(df_editado)
        st.success("Escala salva com sucesso!")

    if st.button("Sair"):
        st.session_state.logado = False
        st.session_state.nome_fiscal = ""
        st.experimental_rerun()
