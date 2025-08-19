# Importando as bibliotecas necessárias
import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta, date
from supabase import create_client, Client
import time
import base64

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
st.set_page_config(page_title="Escala Frente de Caixa", page_icon="📅", layout="wide", initial_sidebar_state="expanded")

# --- Conexão com o Banco de Dados Supabase ---
try:
    url = st.secrets["supabase_url"]; key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("🚨 **Erro de Conexão:** Verifique os Secrets `supabase_url` e `supabase_key`."); st.stop()

# --- Gerenciamento de Estado da Sessão ---
if "logado" not in st.session_state: st.session_state.logado = False
if "nome_logado" not in st.session_state: st.session_state.nome_logado = ""

# --- Funções de Formatação e Acesso a Dados ---
def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

@st.cache_data(ttl=300)
def carregar_colaboradores() -> pd.DataFrame:
    try:
        df = pd.DataFrame(supabase.rpc('get_colaboradores').execute().data)
        if not df.empty: df['nome'] = df['nome'].str.strip()
        return df
    except Exception as e: st.error(f"Erro ao carregar colaboradores: {e}"); return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_indice_semanas() -> pd.DataFrame:
    try:
        response = supabase.table('semanas').select('id, nome_semana, data_inicio').order('data_inicio', desc=True).execute()
        return pd.DataFrame(response.data)
    except Exception as e: st.error(f"Erro ao carregar índice de semanas: {e}"); return pd.DataFrame()

@st.cache_data(ttl=10)
def carregar_escala_semana_por_id(id_semana: int) -> pd.DataFrame:
    try:
        params = {'p_semana_id': id_semana}
        response = supabase.rpc('get_escala_semana', params).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
            df['nome'] = df['nome'].str.strip()
        return df
    except Exception as e: st.error(f"Erro ao carregar escala da semana por ID: {e}"); return pd.DataFrame()

def inicializar_semana_no_banco(data_inicio: date) -> bool:
    try:
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        return True
    except Exception as e: st.error(f"Erro ao inicializar semana: {e}"); return False

def salvar_escala_semanal(nome: str, horarios: list, semana_info: dict) -> bool:
    try:
        data_inicio = semana_info['data_inicio']
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            supabase.rpc('save_escala_dia_final', {'p_nome': nome.strip(), 'p_data': data_dia.strftime('%Y-%m-%d'), 'p_horario': horario}).execute()
        return True
    except Exception as e: st.error(f"Erro detalhado ao salvar semana: {e}"); return False

# <<<<===== NOVA FUNÇÃO =====>>>>
def apagar_semana(id_semana: int) -> bool:
    try:
        supabase.rpc('apagar_semana', {'p_semana_id': id_semana}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao apagar semana: {e}"); return False

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

def gerar_html_escala(df_escala: pd.DataFrame, nome_colaborador: str, semana_str: str) -> str:
    tabela_html = df_escala.to_html(index=False, border=1, justify="center")
    html_template = f"""
    <html><head><title>Escala de {nome_colaborador}</title><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }} h1, h2 {{ text-align: center; color: #333; }}
        table {{ width: 80%; margin: 20px auto; border-collapse: collapse; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1); }}
        th, td {{ padding: 12px 15px; text-align: center; border: 1px solid #ddd; }}
        thead {{ background-color: #f2f2f2; font-weight: bold; }} tbody tr:nth-child(even) {{ background-color: #f9f9f9; }}
        p {{ text-align: center; color: #777; }}
    </style></head><body>
        <h1>Escala de Trabalho</h1><h2>{nome_colaborador}</h2><h2>{semana_str}</h2>
        {tabela_html}
        <p>Documento gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
    </body></html>
    """
    return html_template

# --- Abas da Interface ---
def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_semanas: pd.DataFrame):
    st.header("🔎 Consultar Minha Escala")
    st.markdown("Selecione seu nome e a semana que deseja visualizar.")
    if df_colaboradores.empty: st.warning("Nenhum colaborador cadastrado."); return

    nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
    nome_selecionado = st.selectbox("1. Selecione seu nome:", options=nomes_disponiveis, index=0)

    if nome_selecionado:
        if df_semanas.empty:
            st.info(f"**{nome_selecionado}**, ainda não há nenhuma semana de escala registrada no sistema."); return
        
        opcoes_semana = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for index, row in df_semanas.iterrows()}
        semana_selecionada_str = st.selectbox("2. Selecione a semana que deseja visualizar:", options=opcoes_semana.keys())

        if semana_selecionada_str:
            semana_info = opcoes_semana[semana_selecionada_str]
            with st.container(border=True):
                id_semana = semana_info['id']
                df_escala_semana_atual = carregar_escala_semana_por_id(id_semana)
                
                escala_final = df_escala_semana_atual[df_escala_semana_atual['nome'] == nome_selecionado].sort_values("data")
                
                if not escala_final.empty:
                    resultados_display = escala_final.copy(); resultados_display["Data"] = resultados_display["data"].apply(formatar_data_completa); resultados_display.rename(columns={"horario": "Horário"}, inplace=True)
                    st.dataframe(resultados_display[["Data", "Horário"]], use_container_width=True, hide_index=True)
                    st.markdown("---"); st.subheader("📄 Opções de Impressão")
                    html_string = gerar_html_escala(resultados_display[["Data", "Horário"]], nome_selecionado, semana_selecionada_str)
                    b64 = base64.b64encode(html_string.encode('utf-8')).decode()
                    nome_arquivo = "".join(c for c in nome_selecionado if c.isalnum() or c in (' ', '_')).rstrip().replace(' ', '_').lower()
                    href = f'<a href="data:text/html;charset=utf-8;base64,{b64}" download="escala_{nome_arquivo}_{semana_info["data_inicio"].strftime("%Y%m%d")}.html" style="display: inline-block; padding: 0.5em 1em; background-color: #0068c9; color: white; text-align: center; text-decoration: none; border-radius: 0.25rem;">🖨️ Gerar Versão para Impressão/PDF</a>'
                    st.markdown(href, unsafe_allow_html=True); st.caption("Dica: após abrir o arquivo, use Ctrl+P para imprimir ou salvar como PDF.")
                else:
                    st.warning(f"**{nome_selecionado}**, você não possui horários definidos para esta semana específica.")

def aba_gerenciar_semanas(df_semanas: pd.DataFrame):
    with st.container(border=True):
        st.subheader("➕ Inicializar Nova Semana de Escala")
        hoje = date.today(); data_padrao = hoje - timedelta(days=hoje.weekday())
        data_selecionada = st.date_input("Selecione o dia de início da semana:", value=data_padrao)
        if st.button("🗓️ Inicializar Semana", type="primary", use_container_width=True):
            data_inicio_semana = data_selecionada - timedelta(days=data_selecionada.weekday())
            with st.spinner(f"Inicializando semana de {data_inicio_semana.strftime('%d/%m')}..."):
                if inicializar_semana_no_banco(data_inicio_semana):
                    st.cache_data.clear(); st.success("Semana inicializada com sucesso!"); time.sleep(1); st.rerun()

    with st.container(border=True):
        st.subheader("📋 Semanas Já Inicializadas")
        if df_semanas.empty: 
            st.info("Nenhuma semana foi inicializada ainda.")
        else:
            # <<<<===== INTERFACE ATUALIZADA COM BOTÃO DE APAGAR =====>>>>
            for _, semana in df_semanas.iterrows():
                col1, col2 = st.columns([4, 1])
                col1.write(semana['nome_semana'])
                
                # Botão de apagar com confirmação
                if col2.button("Apagar", key=f"del_{semana['id']}", type="secondary"):
                    st.session_state[f"confirm_delete_{semana['id']}"] = True

                if st.session_state.get(f"confirm_delete_{semana['id']}"):
                    st.warning(f"**Atenção!** Esta ação é irreversível. Você tem certeza que deseja apagar a **{semana['nome_semana']}** e todos os seus registros?")
                    confirm_col1, confirm_col2 = st.columns(2)
                    if confirm_col1.button("Sim, apagar esta semana", key=f"confirm_ok_{semana['id']}", type="primary"):
                        with st.spinner("Apagando..."):
                            if apagar_semana(semana['id']):
                                st.success("Semana apagada com sucesso!")
                                del st.session_state[f"confirm_delete_{semana['id']}"]
                                st.cache_data.clear()
                                time.sleep(1); st.rerun()
                            else:
                                del st.session_state[f"confirm_delete_{semana['id']}"]
                    
                    if confirm_col2.button("Cancelar", key=f"confirm_cancel_{semana['id']}"):
                        del st.session_state[f"confirm_delete_{semana['id']}"]
                        st.rerun()

def aba_editar_escala_semanal(df_colaboradores: pd.DataFrame, df_semanas: pd.DataFrame):
    with st.container(border=True):
        st.subheader("✏️ Editar Escala Semanal")
        if df_semanas.empty or df_colaboradores.empty: st.warning("Adicione colaboradores e inicialize uma semana para começar."); return

        col1, col2 = st.columns(2)
        with col1:
            opcoes_semana = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for index, row in df_semanas.iterrows()}
            semana_selecionada_str = st.selectbox("1. Selecione a semana para editar:", options=opcoes_semana.keys())
            semana_info = opcoes_semana.get(semana_selecionada_str)
        with col2:
            nomes_lista = sorted(df_colaboradores["nome"].tolist())
            colaborador = st.selectbox("2. Selecione o colaborador:", nomes_lista)
        
        st.markdown("---")
        if colaborador and semana_info:
            id_semana = semana_info['id']
            data_inicio_semana = semana_info['data_inicio']
            df_escala_semana_atual = carregar_escala_semana_por_id(id_semana)
            escala_semana_colab = df_escala_semana_atual[df_escala_semana_atual['nome'] == colaborador]
            
            st.markdown(f"**Editando horários para:** `{colaborador}` | `{semana_selecionada_str}`")
            horarios_atuais = {pd.to_datetime(row['data']).date(): row['horario'] for _, row in escala_semana_colab.iterrows()}

            cols = st.columns(7); horarios_novos = []
            for i in range(7):
                dia_da_semana = data_inicio_semana + timedelta(days=i)
                dia_str = f"{DIAS_SEMANA_PT[i]} ({dia_da_semana.strftime('%d/%m')})"
                horario_atual_dia = horarios_atuais.get(dia_da_semana, "")
                index_horario = HORARIOS_PADRAO.index(horario_atual_dia) if horario_atual_dia in HORARIOS_PADRAO else 0
                with cols[i]:
                    key_colaborador = colaborador.replace(' ', '_')
                    horario_selecionado = st.selectbox(dia_str, options=HORARIOS_PADRAO, index=index_horario, key=f"horario_{key_colaborador}_{data_inicio_semana.strftime('%Y%m%d')}_{i}")
                    horarios_novos.append(horario_selecionado)
            
            if st.button("💾 Salvar Escala da Semana", type="primary", use_container_width=True):
                with st.spinner("Salvando alterações..."):
                    if salvar_escala_semanal(colaborador, horarios_novos, semana_info):
                        st.cache_data.clear(); st.success("Escala da semana salva com sucesso!"); time.sleep(1); st.rerun()

def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Gerenciar Colaboradores"); col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("##### ➕ Adicionar Novo Colaborador"); novo_nome = st.text_input("Nome do colaborador:", key="novo_nome")
            if st.button("Adicionar", use_container_width=True):
                if novo_nome.strip():
                    if adicionar_colaborador(novo_nome): st.cache_data.clear(); st.success(f"'{novo_nome.strip()}' adicionado!"); time.sleep(1); st.rerun()
                else: st.error("Nome inválido.")
    with col2:
        with st.container(border=True):
            st.markdown("##### ➖ Remover Colaboradores")
            if not df_colaboradores.empty:
                nomes_para_remover = st.multiselect("Selecione para remover:", options=sorted(df_colaboradores["nome"].tolist()))
                if st.button("Remover Selecionados", type="secondary", use_container_width=True):
                    if nomes_para_remover:
                        if remover_colaboradores(nomes_para_remover): st.cache_data.clear(); st.success("Removidos com sucesso!"); time.sleep(1); st.rerun()
                    else: st.warning("Nenhum nome selecionado.")
            else: st.info("Não há colaboradores para remover.")
    st.markdown("---"); st.markdown("##### 📋 Lista de Colaboradores Atuais")
    if not df_colaboradores.empty: st.dataframe(df_colaboradores[['nome']].sort_values('nome'), use_container_width=True, hide_index=True)

# --- Estrutura Principal da Aplicação ---
def main():
    st.title("📅 Escala Frente de Caixa")
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_semanas = carregar_indice_semanas()
    
    with st.sidebar:
        st.header("Modo de Acesso")
        if not st.session_state.logado:
            with st.form("login_form"):
                st.markdown("##### 🔐 Acesso Restrito"); codigo = st.text_input("Código do Fiscal"); senha = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    fiscal_auth = pd.DataFrame();
                    if codigo.isdigit(): fiscal_auth = df_fiscais[(df_fiscais["codigo"] == int(codigo)) & (df_fiscais["senha"] == str(senha))]
                    if not fiscal_auth.empty: st.session_state.logado = True; st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]; st.rerun()
                    else: st.error("Código ou senha incorretos.")
        else:
            st.success(f"Bem-vindo, **{st.session_state.nome_logado}**!")
            if st.button("Logout", use_container_width=True): st.session_state.logado = False; st.session_state.nome_logado = ""; st.cache_data.clear(); st.rerun()
        st.markdown("---"); st.info("Desenvolvido por Rogério Souza"); st.write("Versão 2.0")

    if st.session_state.logado:
        tabs = ["Gerenciar Semanas 🗓️", "Editar Escala Semanal ✏️", "Gerenciar Colaboradores 👥", "Consultar Individualmente 🔎"]
        tab1, tab2, tab3, tab4 = st.tabs(tabs)
        with tab1: aba_gerenciar_semanas(df_semanas)
        with tab2: aba_editar_escala_semanal(df_colaboradores, df_semanas)
        with tab3: aba_gerenciar_colaboradores(df_colaboradores)
        with tab4: aba_consultar_escala_publica(df_colaboradores, df_semanas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas)

if __name__ == "__main__":
    main()