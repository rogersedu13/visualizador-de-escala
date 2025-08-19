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
    page_title="WEscala Frente de Caixa",
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

# --- Funções de Acesso a Dados (com Cache e Limpeza) ---
@st.cache_data(ttl=300)
def carregar_colaboradores() -> pd.DataFrame:
    try:
        df = pd.DataFrame(supabase.rpc('get_colaboradores').execute().data)
        if not df.empty:
            df['nome'] = df['nome'].str.strip()
        return df
    except Exception as e:
        st.error(f"Erro ao carregar colaboradores: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_escalas() -> pd.DataFrame:
    try:
        response = supabase.rpc('get_escalas').execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
            df['nome'] = df['nome'].str.strip()
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escalas: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=10)
def carregar_escala_semana(data_inicio: date) -> pd.DataFrame:
    try:
        params = {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}
        response = supabase.rpc('get_escala_semana', params).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
            df['nome'] = df['nome'].str.strip()
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escala da semana: {e}")
        return pd.DataFrame()

def get_semanas_iniciadas(df_escalas: pd.DataFrame) -> list[date]:
    if df_escalas.empty or 'data' not in df_escalas.columns:
        return []
    df_escalas = df_escalas.dropna(subset=['data'])
    if df_escalas.empty:
        return []
    datas_unicas = df_escalas['data'].dt.date.unique()
    segundas = {d - timedelta(days=d.weekday()) for d in datas_unicas}
    return sorted(list(segundas), reverse=True)

def inicializar_semana_no_banco(data_inicio: date, df_colaboradores: pd.DataFrame) -> bool:
    try:
        nomes_colaboradores = df_colaboradores['nome'].tolist()
        total_operacoes = len(nomes_colaboradores)
        progresso = st.progress(0, text=f"Inicializando semana para {total_operacoes} colaboradores...")
        for i, nome in enumerate(nomes_colaboradores):
            for j in range(7):
                data_dia = data_inicio + timedelta(days=j)
                supabase.rpc('save_escala_dia_final', {
                    'p_nome': nome.strip(), 
                    'p_data': data_dia.strftime('%Y-%m-%d'), 
                    'p_horario': ''
                }).execute()
            percentual_completo = int(((i + 1) / total_operacoes) * 100)
            progresso.progress(percentual_completo, text=f"Inicializando: {i+1}/{total_operacoes} concluídos...")
        progresso.empty()
        return True
    except Exception as e:
        st.error(f"Erro ao inicializar semana no Python: {e}")
        return False

def salvar_escala_semanal(nome: str, data_inicio: date, horarios: list) -> bool:
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            supabase.rpc('save_escala_dia_final', {'p_nome': nome.strip(), 'p_data': data_dia.strftime('%Y-%m-%d'), 'p_horario': horario}).execute()
        return True
    except Exception as e: st.error(f"Erro detalhado ao salvar semana: {e}"); return False

def apagar_semana_no_banco(data_inicio: date) -> bool:
    try:
        supabase.rpc('apagar_escala_semana', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao apagar semana: {e}")
        return False

def adicionar_colaborador(nome: str) -> bool:
    try:
        supabase.rpc('add_colaborador', {'p_nome': nome.strip()}).execute(); return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def remover_colaboradores(lista_nomes: list) -> bool:
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': [n.strip() for n in lista_nomes]}).execute(); return True
    except Exception as e: st.error(f"Erro: {e}"); return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([{"codigo": 1017, "nome": "Rogério", "senha": "1"}, {"codigo": 1002, "nome": "Andrews", "senha": "2"}])

def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

# --- Abas da Interface ---
def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_escalas: pd.DataFrame):
    st.header("🔎 Consultar Minha Escala")
    st.markdown("Selecione seu nome para visualizar sua escala para os próximos 30 dias.")
    if df_colaboradores.empty: st.warning("Nenhum colaborador cadastrado."); return

    nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
    nome_selecionado = st.selectbox("Selecione seu nome:", options=nomes_disponiveis, index=0)

    if nome_selecionado:
        with st.container(border=True):
            hoje = pd.Timestamp.today().normalize()
            data_fim = hoje + timedelta(days=30)
            st.info(f"Mostrando a escala de **{nome_selecionado}** de hoje até {data_fim.strftime('%d/%m/%Y')}.")
            
            resultados = df_escalas[
                (df_escalas['nome'].str.strip().str.lower() == nome_selecionado.strip().lower()) &
                (df_escalas['data'] >= hoje) &
                (df_escalas['data'] <= data_fim)
            ].sort_values("data")
            if not resultados.empty:
                resultados_display = resultados.copy()
                resultados_display["Data"] = resultados_display["data"].apply(formatar_data_completa)
                resultados_display.rename(columns={"horario": "Horário"}, inplace=True)
                st.dataframe(resultados_display[["Data", "Horário"]], use_container_width=True, hide_index=True)
            else:
                st.success(f"✅ **{nome_selecionado}**, você não possui escalas agendadas para este período.")

def aba_gerenciar_semanas(df_colaboradores: pd.DataFrame, df_escalas_todas: pd.DataFrame):
    semanas_iniciadas = get_semanas_iniciadas(df_escalas_todas)
    with st.container(border=True):
        st.subheader("➕ Inicializar Nova Semana de Escala")
        hoje = date.today(); data_padrao = hoje - timedelta(days=hoje.weekday())
        data_selecionada = st.date_input("Selecione o dia de início da semana:", value=data_padrao)
        if st.button("🗓️ Inicializar Semana", type="primary", use_container_width=True):
            if df_colaboradores.empty:
                st.error("Não há colaboradores cadastrados para inicializar a semana."); return
            data_inicio_semana = data_selecionada - timedelta(days=data_selecionada.weekday())
            if inicializar_semana_no_banco(data_inicio_semana, df_colaboradores):
                st.cache_data.clear(); st.success("Semana inicializada com sucesso!"); time.sleep(1); st.rerun()

    with st.container(border=True):
        st.subheader("📋 Semanas Já Inicializadas")
        if not semanas_iniciadas:
            st.info("Nenhuma semana foi inicializada ainda.")
        else:
            for semana in semanas_iniciadas:
                col1, col2 = st.columns([3, 1])
                semana_fim = semana + timedelta(days=6)
                col1.write(f"Semana de {semana.strftime('%d/%m/%Y')} a {semana_fim.strftime('%d/%m/%Y')}")
                if col2.button("Apagar", key=f"del_{semana}", type="secondary"):
                    st.session_state[f"confirm_delete_{semana}"] = True
                if st.session_state.get(f"confirm_delete_{semana}"):
                    st.warning(f"**Atenção!** Você tem certeza que deseja apagar todos os registros da semana de {semana.strftime('%d/%m')}?")
                    confirm_col1, confirm_col2 = st.columns(2)
                    if confirm_col1.button("Sim, apagar esta semana", key=f"confirm_ok_{semana}", type="primary"):
                        with st.spinner("Apagando..."):
                            if apagar_semana_no_banco(semana):
                                st.success("Semana apagada com sucesso!")
                                del st.session_state[f"confirm_delete_{semana}"]
                                st.cache_data.clear()
                                time.sleep(1); st.rerun()
                            else:
                                del st.session_state[f"confirm_delete_{semana}"]
                    if confirm_col2.button("Cancelar", key=f"confirm_cancel_{semana}"):
                        del st.session_state[f"confirm_delete_{semana}"]
                        st.rerun()

def aba_editar_escala_semanal(df_colaboradores: pd.DataFrame, df_escalas_todas: pd.DataFrame):
    semanas_iniciadas = get_semanas_iniciadas(df_escalas_todas)
    with st.container(border=True):
        st.subheader("✏️ Editar Escala Semanal")
        if not semanas_iniciadas or df_colaboradores.empty:
            st.warning("Adicione colaboradores e inicialize uma semana para começar."); return

        col1, col2 = st.columns(2)
        with col1:
            opcoes_semana = {f"Semana de {d.strftime('%d/%m/%Y')}": d for d in semanas_iniciadas}
            semana_selecionada_str = st.selectbox("1. Selecione a semana para editar:", options=opcoes_semana.keys())
            semana_selecionada = opcoes_semana.get(semana_selecionada_str)
        with col2:
            nomes_lista = sorted(df_colaboradores["nome"].tolist())
            colaborador = st.selectbox("2. Selecione o colaborador:", nomes_lista)
        
        st.markdown("---")
        if colaborador and semana_selecionada:
            # <<<<===== LÓGICA CORRIGIDA E ROBUSTA =====>>>>
            # 1. Busca os dados apenas da semana selecionada de forma otimizada
            df_escala_semana_atual = carregar_escala_semana(semana_selecionada)
            # 2. Filtra para o colaborador específico
            escala_semana_colab = df_escala_semana_atual[df_escala_semana_atual['nome'] == colaborador]
            
            st.markdown(f"**Editando horários para:** `{colaborador}` | **Semana de:** `{semana_selecionada.strftime('%d/%m/%Y')}`")
            horarios_atuais = {row['data'].date(): row['horario'] for _, row in escala_semana_colab.iterrows()}
            
            cols = st.columns(7); horarios_novos = []
            for i in range(7):
                dia_da_semana = semana_selecionada + timedelta(days=i)
                dia_str = f"{DIAS_SEMANA_PT[i]} ({dia_da_semana.strftime('%d/%m')})"
                horario_atual_dia = horarios_atuais.get(dia_da_semana, "")
                index_horario = HORARIOS_PADRAO.index(horario_atual_dia) if horario_atual_dia in HORARIOS_PADRAO else 0
                with cols[i]:
                    key_colaborador = colaborador.strip().replace(' ', '_')
                    horario_selecionado = st.selectbox(dia_str, options=HORARIOS_PADRAO, index=index_horario, key=f"horario_{key_colaborador}_{semana_selecionada.strftime('%Y%m%d')}_{i}")
                    horarios_novos.append(horario_selecionado)
            
            if st.button("💾 Salvar Escala da Semana", type="primary", use_container_width=True):
                with st.spinner("Salvando alterações..."):
                    if salvar_escala_semanal(colaborador, semana_selecionada, horarios_novos):
                        st.cache_data.clear(); st.success("Escala da semana salva com sucesso!"); time.sleep(1); st.rerun()

def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Gerenciar Colaboradores"); col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("##### ➕ Adicionar Novo Colaborador"); novo_nome = st.text_input("Nome do colaborador:", key="novo_nome").strip()
            if st.button("Adicionar", use_container_width=True):
                if novo_nome and (df_colaboradores.empty or novo_nome not in df_colaboradores["nome"].values):
                    if adicionar_colaborador(novo_nome): st.cache_data.clear(); st.success(f"'{novo_nome}' adicionado!"); time.sleep(1); st.rerun()
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
    st.markdown("---"); st.markdown("##### 📋 Lista de Colaboradores Atuais")
    if not df_colaboradores.empty:
        st.dataframe(df_colaboradores[['nome']].sort_values('nome'), use_container_width=True, hide_index=True)

# --- Estrutura Principal da Aplicação ---
def main():
    st.title("📅 Escala Frente de Caixa")
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_escalas_todas = carregar_escalas()
    
    with st.sidebar:
        st.header("Modo de Acesso")
        if not st.session_state.logado:
            with st.form("login_form"):
                st.markdown("##### 🔐 Acesso Restrito"); codigo = st.text_input("Código do Fiscal"); senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    fiscal_auth = pd.DataFrame();
                    if codigo.isdigit(): fiscal_auth = df_fiscais[(df_fiscais["codigo"] == int(codigo)) & (df_fiscais["senha"] == str(senha))]
                    if not fiscal_auth.empty:
                        st.session_state.logado = True; st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]; st.rerun()
                    else:
                        st.error("Código ou senha incorretos.")
        else:
            st.success(f"Bem-vindo, **{st.session_state.nome_logado}**!")
            if st.button("Logout", use_container_width=True):
                st.session_state.logado = False; st.session_state.nome_logado = ""; st.cache_data.clear(); st.rerun()
        st.markdown("---"); st.info("Desenvolvido por @Rogerio Souza")

    if st.session_state.logado:
        tabs = ["Gerenciar Semanas 🗓️", "Editar Escala Semanal ✏️", "Gerenciar Colaboradores 👥", "Consultar Individualmente 🔎"]
        tab1, tab2, tab3, tab4 = st.tabs(tabs)
        with tab1: aba_gerenciar_semanas(df_colaboradores, df_escalas_todas)
        with tab2: aba_editar_escala_semanal(df_colaboradores, df_escalas_todas)
        with tab3: aba_gerenciar_colaboradores(df_colaboradores)
        with tab4: aba_consultar_escala_publica(df_colaboradores, df_escalas_todas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_escalas_todas)

if __name__ == "__main__":
    main()