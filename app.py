# Importando as bibliotecas necessárias
import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta, date
from supabase import create_client, Client
import time
from fpdf import FPDF # Importado para gerar PDF
from io import BytesIO # Importado para gerar PDF
import unicodedata # Importado para remover acentos

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
    page_title="Escalas Frente de Caixa",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Conexão com o Banco de Dados Supabase ---
try:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("🚨 **Erro de Conexão:** Verifique os Secrets `supabase_url` e `supabase_key`.")
    st.stop()

# --- Gerenciamento de Estado da Sessão ---
if "logado" not in st.session_state: st.session_state.logado = False
if "nome_logado" not in st.session_state: st.session_state.nome_logado = ""

# --- Funções de Acesso a Dados (com Cache) ---
@st.cache_data(ttl=300)
def carregar_colaboradores() -> pd.DataFrame:
    try:
        return pd.DataFrame(supabase.rpc('get_colaboradores').execute().data)
    except Exception as e:
        st.error(f"Erro ao carregar colaboradores: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_escalas() -> pd.DataFrame:
    try:
        response = supabase.rpc('get_escalas').execute()
        df = pd.DataFrame(response.data)
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escalas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def get_semanas_iniciadas(df_escalas: pd.DataFrame) -> list[date]:
    if df_escalas.empty:
        return []
    datas_unicas = df_escalas['data'].dt.date.unique()
    segundas = {d - timedelta(days=d.weekday()) for d in datas_unicas}
    return sorted(list(segundas), reverse=True)

def inicializar_semana_no_banco(data_inicio: date) -> bool:
    try:
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao inicializar semana: {e}")
        return False

def salvar_escala_semanal(nome: str, data_inicio: date, horarios: list) -> bool:
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            supabase.rpc('save_escala_dia_final', {
                'p_nome': nome,
                'p_data': data_dia.strftime('%Y-%m-%d'),
                'p_horario': horario
            }).execute()
        return True
    except Exception as e:
        st.error(f"Erro detalhado ao salvar semana: {e}")
        return False

def adicionar_colaborador(nome: str) -> bool:
    try:
        supabase.rpc('add_colaborador', {'p_nome': nome}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def remover_colaboradores(lista_nomes: list) -> bool:
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': lista_nomes}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"}
    ])

# --- Funções de Formatação e Geração de PDF ---

def remover_acentos(texto: str) -> str:
    """
    Remove acentos de uma string, trocando por seus equivalentes sem acento.
    Ex: 'Rogério' -> 'Rogerio'
    """
    texto_normalizado = unicodedata.normalize('NFD', texto)
    return texto_normalizado.encode('ascii', 'ignore').decode('utf-8')

def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

def gerar_pdf_escala_individual(df_escala: pd.DataFrame, nome_colaborador: str) -> bytes:
    """Gera um PDF simples com a escala de um único colaborador, removendo acentos."""
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)

    # Título
    titulo_pdf = f"Escala de Trabalho - {remover_acentos(nome_colaborador)}"
    pdf.cell(0, 10, titulo_pdf, 0, 1, 'C')
    pdf.ln(5)

    # Subtítulo com data da emissão
    pdf.set_font('Arial', '', 10)
    data_emissao = f"Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    pdf.cell(0, 10, data_emissao, 0, 1, 'C')
    pdf.ln(10)

    # Cabeçalho da Tabela
    pdf.set_font('Arial', 'B', 12)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(95, 10, 'Data', 1, 0, 'C', fill=True)
    pdf.cell(95, 10, 'Horario', 1, 1, 'C', fill=True)

    # Corpo da Tabela
    pdf.set_font('Arial', '', 11)
    for _, row in df_escala.iterrows():
        data_cell = str(row['Data'])
        horario_cell = remover_acentos(str(row['Horário']))
        pdf.cell(95, 10, data_cell, 1, 0, 'C')
        pdf.cell(95, 10, horario_cell, 1, 1, 'C')

    # Retorna o PDF como bytes
    return pdf.output()

# --- Funções de Interface (Abas) ---

def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_escalas: pd.DataFrame):
    """Interface para o colaborador consultar e imprimir sua própria escala."""
    st.header("🔎 Consultar Minha Escala")
    st.markdown("Selecione seu nome para visualizar sua escala para os próximos 30 dias.")

    if not df_colaboradores.empty:
        nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
        nome_selecionado = st.selectbox("Selecione seu nome:", options=nomes_disponiveis, index=0)
    else:
        st.warning("Nenhum colaborador cadastrado no momento.")
        return

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
                # Prepara DataFrame para exibição
                resultados_display = resultados.copy()
                resultados_display["Data"] = resultados_display["data"].apply(formatar_data_completa)
                resultados_display.rename(columns={"horario": "Horário"}, inplace=True)
                
                st.dataframe(
                    resultados_display[["Data", "Horário"]],
                    use_container_width=True,
                    hide_index=True
                )
                
                # --- BOTÃO DE DOWNLOAD ---
                st.markdown("---")
                pdf_bytes = gerar_pdf_escala_individual(resultados_display[["Data", "Horário"]], nome_selecionado)
                
                nome_arquivo = remover_acentos("".join(c for c in nome_selecionado if c.isalnum() or c in (' ', '_')).rstrip())
                
                st.download_button(
                    label="🖨️ Baixar minha escala em PDF",
                    data=pdf_bytes,
                    file_name=f"escala_{nome_arquivo.replace(' ', '_').lower()}.pdf",
                    mime="application/pdf"
                )
            else:
                st.success(f"✅ **{nome_selecionado}**, você não possui escalas agendadas para este período.")


def aba_gerenciar_semanas(semanas_iniciadas: list[date]):
    """Aba para criar e visualizar as semanas de escala."""
    with st.container(border=True):
        st.subheader("➕ Inicializar Nova Semana de Escala")
        st.markdown("Selecione uma data para criar os registros de escala para todos os colaboradores nessa semana.")
        hoje = date.today()
        data_padrao = hoje - timedelta(days=hoje.weekday())
        data_selecionada = st.date_input("Selecione o dia de início da semana:", value=data_padrao)

        if st.button("🗓️ Inicializar Semana", type="primary", use_container_width=True):
            data_inicio_semana = data_selecionada - timedelta(days=data_selecionada.weekday())
            with st.spinner(f"Inicializando semana de {data_inicio_semana.strftime('%d/%m')}..."):
                if inicializar_semana_no_banco(data_inicio_semana):
                    st.cache_data.clear()
                    st.success("Semana inicializada com sucesso!")
                    time.sleep(2)
                    st.rerun()

    with st.container(border=True):
        st.subheader("📋 Semanas Já Inicializadas")
        if not semanas_iniciadas:
            st.info("Nenhuma semana foi inicializada ainda.")
        else:
            datas_formatadas = [f"Semana de {d.strftime('%d/%m/%Y')} a {(d + timedelta(days=6)).strftime('%d/%m/%Y')}" for d in semanas_iniciadas]
            st.dataframe({"Semanas Disponíveis para Edição": datas_formatadas}, use_container_width=True, hide_index=True)

def aba_editar_escala_semanal(df_colaboradores: pd.DataFrame, df_escalas: pd.DataFrame, semanas_iniciadas: list[date]):
    """Aba para editar a escala de uma semana inteira para um colaborador."""
    with st.container(border=True):
        st.subheader("✏️ Editar Escala Semanal")

        if not semanas_iniciadas:
            st.warning("Vá para a aba 'Gerenciar Semanas' para criar uma.")
            return
        if df_colaboradores.empty:
            st.warning("Vá para a aba 'Gerenciar Colaboradores'.")
            return

        col1, col2 = st.columns(2)
        with col1:
            opcoes_semana = {f"Semana de {d.strftime('%d/%m/%Y')}": d for d in semanas_iniciadas}
            semana_selecionada_str = st.selectbox("1. Selecione a semana para editar:", options=opcoes_semana.keys())
            if semana_selecionada_str:
                semana_selecionada = opcoes_semana[semana_selecionada_str]
        with col2:
            nomes_lista = sorted(df_colaboradores["nome"].tolist())
            colaborador = st.selectbox("2. Selecione o colaborador:", nomes_lista)

        st.markdown("---")

        if colaborador and 'semana_selecionada' in locals():
            st.markdown(f"**Editando horários para:** `{colaborador}` | **Semana de:** `{semana_selecionada.strftime('%d/%m/%Y')}`")
            escala_semana_colab = df_escalas[
                (df_escalas['nome'] == colaborador) &
                (df_escalas['data'].dt.date >= semana_selecionada) &
                (df_escalas['data'].dt.date <= semana_selecionada + timedelta(days=6))
            ].sort_values('data')
            horarios_atuais = {row['data'].date(): row['horario'] for _, row in escala_semana_colab.iterrows()}

            cols = st.columns(7)
            horarios_novos = []
            for i in range(7):
                dia_da_semana = semana_selecionada + timedelta(days=i)
                dia_str = f"{DIAS_SEMANA_PT[i]} ({dia_da_semana.strftime('%d/%m')})"
                horario_atual_dia = horarios_atuais.get(dia_da_semana, "")
                index_horario = HORARIOS_PADRAO.index(horario_atual_dia) if horario_atual_dia in HORARIOS_PADRAO else 0
                with cols[i]:
                    horario_selecionado = st.selectbox(
                        dia_str,
                        options=HORARIOS_PADRAO,
                        index=index_horario,
                        key=f"horario_{colaborador}_{semana_selecionada.strftime('%Y%m%d')}_{i}"
                    )
                    horarios_novos.append(horario_selecionado)
            
            if st.button("💾 Salvar Escala da Semana", type="primary", use_container_width=True):
                with st.spinner("Salvando alterações..."):
                    if salvar_escala_semanal(colaborador, semana_selecionada, horarios_novos):
                        st.cache_data.clear()
                        st.success("Escala da semana salva com sucesso!")
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
                        st.cache_data.clear(); st.success(f"'{novo_nome}' adicionado!"); time.sleep(1); st.rerun()
                else: st.error("Nome inválido ou já existente.")
    with col2:
        with st.container(border=True):
            st.markdown("##### ➖ Remover Colaboradores")
            if not df_colaboradores.empty:
                nomes_para_remover = st.multiselect("Selecione para remover:", options=sorted(df_colaboradores["nome"].tolist()))
                if st.button("Remover Selecionados", type="secondary", use_container_width=True):
                    if nomes_para_remover:
                        if remover_colaboradores(nomes_para_remover):
                            st.cache_data.clear(); st.success("Removidos com sucesso!"); time.sleep(1); st.rerun()
                    else: st.warning("Nenhum nome selecionado.")
            else: st.info("Não há colaboradores para remover.")
    st.markdown("---")
    st.markdown("##### 📋 Lista de Colaboradores Atuais")
    if not df_colaboradores.empty:
        st.dataframe(df_colaboradores[['nome']].sort_values('nome'), use_container_width=True, hide_index=True)

# --- Estrutura Principal da Aplicação ---
def main():
    st.title("📅 Escalas Frente de Caixa")

    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_escalas = carregar_escalas()
    semanas_iniciadas = get_semanas_iniciadas(df_escalas)

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
                        fiscal_auth = df_fiscais[(df_fiscais["codigo"] == int(codigo)) & (df_fiscais["senha"] == str(senha))]
                    if not fiscal_auth.empty:
                        st.session_state.logado = True
                        st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]
                        st.rerun()
                    else: st.error("Código ou senha incorretos.")
        else:
            st.success(f"Bem-vindo, **{st.session_state.nome_logado}**!")
            if st.button("Logout", use_container_width=True):
                st.session_state.logado = False; st.session_state.nome_logado = ""; st.cache_data.clear(); st.rerun()
        st.markdown("---")
        st.info("Desenvolvido @Rogério Souza")
        st.write("Versão 2.0")

    if st.session_state.logado:
        # Interface do Fiscal (Logado)
        tab1, tab2, tab3, tab4 = st.tabs([
            "Gerenciar Semanas 🗓️",
            "Editar Escala Semanal ✏️",
            "Gerenciar Colaboradores 👥",
            "Consultar Individualmente 🔎"
        ])
        with tab1:
            aba_gerenciar_semanas(semanas_iniciadas)
        with tab2:
            aba_editar_escala_semanal(df_colaboradores, df_escalas, semanas_iniciadas)
        with tab3:
            aba_gerenciar_colaboradores(df_colaboradores)
        with tab4:
            aba_consultar_escala_publica(df_colaboradores, df_escalas)
    else:
        # Interface Pública (Não Logado)
        aba_consultar_escala_publica(df_colaboradores, df_escalas)


if __name__ == "__main__":
    main()