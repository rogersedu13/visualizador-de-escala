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
    "", "Folga", "5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]
# NOVO: Constantes para o Dashboard
FUNCOES_VALIDAS = ["N/D", "Operador(a) de Caixa", "Empacotador(a)"]
# REGRAS DE CONTAGEM PARA O DASHBOARD
OP_MANHA_SEMANA = {"6:50 HRS", "8:00 HRS", "10:00 HRS"}
OP_TARDE_SEMANA = {"10:00 HRS", "12:00 HRS"}
EMP_MANHA_SEMANA = {"6:50 HRS", "7:30 HRS", "9:00 HRS"}
EMP_TARDE_SEMANA = {"13:30 HRS"}
EMP_MANHA_SABADO = {"6:50 HRS", "7:30 HRS", "9:00 HRS", "10:00 HRS"}
EMP_TARDE_SABADO = {"9:00 HRS", "10:00 HRS", "10:30 HRS", "12:00 HRS"}


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

# MODIFICADO: Função agora lê diretamente da tabela e lida com a nova coluna 'funcao'
@st.cache_data(ttl=300)
def carregar_colaboradores() -> pd.DataFrame:
    try:
        response = supabase.table('colaboradores').select('id, nome, funcao').order('nome').execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['nome'] = df['nome'].str.strip()
            if 'funcao' not in df.columns:
                df['funcao'] = 'N/D'
            df['funcao'] = df['funcao'].fillna('N/D')
        return df
    except Exception as e: st.error(f"Erro ao carregar colaboradores: {e}"); return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_indice_semanas(apenas_ativas: bool = False) -> pd.DataFrame:
    try:
        query = supabase.table('semanas').select('id, nome_semana, data_inicio, ativa').order('data_inicio', desc=True)
        if apenas_ativas:
            query = query.eq('ativa', True)
        response = query.execute()
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
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute(); return True
    except Exception as e: st.error(f"Erro ao inicializar semana: {e}"); return False

def salvar_escala_semanal(nome: str, horarios: list, semana_info: dict) -> bool:
    try:
        data_inicio = semana_info['data_inicio']
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            supabase.rpc('save_escala_dia_final', {'p_nome': nome.strip(), 'p_data': data_dia.strftime('%Y-%m-%d'), 'p_horario': horario}).execute()
        return True
    except Exception as e: st.error(f"Erro detalhado ao salvar semana: {e}"); return False

def arquivar_reativar_semana(id_semana: int, novo_status: bool):
    try:
        supabase.table('semanas').update({'ativa': novo_status}).eq('id', id_semana).execute(); return True
    except Exception as e: st.error(f"Erro ao alterar status da semana: {e}"); return False

# MODIFICADO: Funções de Adicionar/Atualizar agora lidam com o campo 'funcao'
def adicionar_colaborador(nome: str, funcao: str) -> bool:
    try:
        supabase.table('colaboradores').insert({'nome': nome.strip(), 'funcao': funcao}).execute(); return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def atualizar_colaborador(colab_id: int, nome: str, funcao: str) -> bool:
    try:
        supabase.table('colaboradores').update({'nome': nome.strip(), 'funcao': funcao}).eq('id', colab_id).execute(); return True
    except Exception as e: st.error(f"Erro ao atualizar: {e}"); return False

def remover_colaboradores(lista_ids: list) -> bool:
    try:
        supabase.table('colaboradores').delete().in_('id', lista_ids).execute(); return True
    except Exception as e: st.error(f"Erro ao remover: {e}"); return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([{"codigo": 1017, "nome": "Rogério", "senha": "1"}, {"codigo": 1002, "nome": "Andrews", "senha": "2"}])

def gerar_html_escala(df_escala: pd.DataFrame, nome_colaborador: str, semana_str: str) -> str:
    # (Código original mantido, sem alterações)
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

# MODIFICADO: Dashboard agora separa por função
def aba_dashboard_horarios(df_semanas_ativas: pd.DataFrame, df_colaboradores: pd.DataFrame):
    st.subheader("📊 Dashboard de Cobertura de Turnos")
    st.markdown("Veja quantos colaboradores de cada função estão escalados para a semana selecionada.")

    if df_semanas_ativas.empty:
        st.warning("Nenhuma semana ativa para analisar."); return

    opcoes_semana = {row['nome_semana']: {'id': row['id']} for index, row in df_semanas_ativas.iterrows()}
    semana_selecionada_str = st.selectbox("Selecione a semana para analisar:", options=opcoes_semana.keys())

    if semana_selecionada_str:
        semana_id = opcoes_semana[semana_selecionada_str]['id']
        with st.spinner("Carregando e processando escala..."):
            df_escala = carregar_escala_semana_por_id(semana_id)

        if df_escala.empty:
            st.info("Não há horários lançados para esta semana."); return

        horarios_de_nao_trabalho = ["", "Folga", "Ferias", "Afastado(a)", "Atestado"]
        df_trabalho = df_escala[~df_escala['horario'].isin(horarios_de_nao_trabalho)]

        if df_trabalho.empty:
            st.info("Nenhum horário de trabalho efetivo definido para esta semana."); return

        # Junta a escala com os dados dos colaboradores para obter a função
        df_merged = pd.merge(df_trabalho, df_colaboradores[['nome', 'funcao']], on='nome', how='left')
        df_merged['dia_semana_idx'] = df_merged['data'].dt.weekday

        contagens = {"op_manha": [0]*7, "op_tarde": [0]*7, "emp_manha": [0]*7, "emp_tarde": [0]*7}

        for _, row in df_merged.iterrows():
            idx = row['dia_semana_idx']
            funcao = row['funcao']
            horario = row['horario']
            is_sabado = (idx == 5)
            
            regras_emp_manha = EMP_MANHA_SABADO if is_sabado else EMP_MANHA_SEMANA
            regras_emp_tarde = EMP_TARDE_SABADO if is_sabado else EMP_TARDE_SEMANA

            if funcao == 'Operador(a) de Caixa':
                if horario in OP_MANHA_SEMANA: contagens['op_manha'][idx] += 1
                if horario in OP_TARDE_SEMANA: contagens['op_tarde'][idx] += 1
            elif funcao == 'Empacotador(a)':
                if horario in regras_emp_manha: contagens['emp_manha'][idx] += 1
                if horario in regras_emp_tarde: contagens['emp_tarde'][idx] += 1
        
        df_resultado = pd.DataFrame(contagens, index=DIAS_SEMANA_PT).T
        st.markdown("#### Operadores(as) de Caixa")
        st.dataframe(df_resultado.loc[['op_manha', 'op_tarde']].rename(index={'op_manha': 'Manhã', 'op_tarde': 'Tarde'}), use_container_width=True)
        st.markdown("#### Empacotadores(as)")
        st.dataframe(df_resultado.loc[['emp_manha', 'emp_tarde']].rename(index={'emp_manha': 'Manhã', 'emp_tarde': 'Tarde'}), use_container_width=True)

def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    # (Código original mantido, sem alterações)
    st.header("🔎 Consultar Minha Escala") # ...

def aba_gerenciar_semanas(df_semanas_todas: pd.DataFrame):
    # (Código original mantido, sem alterações)
    with st.container(border=True): # ...

def aba_editar_escala_semanal(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    # (Código original mantido, sem alterações)
    with st.container(border=True): # ...

# MODIFICADO: Gerenciar Colaboradores agora tem o campo Função
def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Gerenciar Colaboradores")
    
    if 'editando_id' not in st.session_state: st.session_state.editando_id = None

    colab_selecionado = df_colaboradores[df_colaboradores['id'] == st.session_state.editando_id] if st.session_state.editando_id else pd.DataFrame()

    with st.expander("➕ Adicionar ou ✏️ Editar Colaborador", expanded=True if st.session_state.editando_id else False):
        with st.form("form_colaborador", clear_on_submit=False):
            dados_default = colab_selecionado.iloc[0] if not colab_selecionado.empty else {}
            
            nome = st.text_input("Nome do Colaborador", value=dados_default.get('nome', ''))
            funcao_default = dados_default.get('funcao', 'N/D')
            funcao = st.selectbox("Função", options=FUNCOES_VALIDAS, index=FUNCOES_VALIDAS.index(funcao_default) if funcao_default in FUNCOES_VALIDAS else 0)

            submitted = st.form_submit_button("💾 Salvar", type="primary", use_container_width=True)
            if submitted:
                if nome.strip():
                    if st.session_state.editando_id:
                        if atualizar_colaborador(st.session_state.editando_id, nome, funcao):
                            st.success("Colaborador atualizado!"); st.session_state.editando_id = None; st.cache_data.clear(); time.sleep(1); st.rerun()
                    else:
                        if adicionar_colaborador(nome, funcao):
                            st.success("Colaborador adicionado!"); st.cache_data.clear(); time.sleep(1); st.rerun()
                else:
                    st.error("O nome é obrigatório.")

    st.markdown("---"); st.markdown("##### 📋 Lista de Colaboradores Atuais")
    if not df_colaboradores.empty:
        for _, row in df_colaboradores.sort_values('nome').iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([4, 3, 1, 1])
                c1.write(f"**{row['nome']}**")
                c2.write(f"*{row['funcao']}*")
                if c3.button("✏️", key=f"edit_{row['id']}", help="Editar"):
                    st.session_state.editando_id = row['id']; st.rerun()
                if c4.button("❌", key=f"del_{row['id']}", help="Remover"):
                    if remover_colaboradores([row['id']]):
                        st.cache_data.clear(); st.success(f"{row['nome']} removido!"); time.sleep(1); st.rerun()

# --- Estrutura Principal da Aplicação ---
def main():
    st.title("📅 Escala Frente de Caixa")
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_semanas_todas = carregar_indice_semanas()
    
    with st.sidebar:
        # (Código do sidebar original mantido)
        st.header("Modo de Acesso") # ...
        st.write("Versão 2.2 - Dashboard por Função")

    df_semanas_ativas = df_semanas_todas[df_semanas_todas['ativa']] if 'ativa' in df_semanas_todas.columns else pd.DataFrame()

    if st.session_state.logado:
        # MODIFICADO: Nome da aba do dashboard e passagem de df_colaboradores
        tabs = ["📊 Dashboard", "🗓️ Gerenciar Semanas", "✏️ Editar Escala", "👥 Gerenciar Colaboradores", "🔎 Consultar"]
        tab1, tab2, tab3, tab4, tab5 = st.tabs(tabs)
        with tab1:
            aba_dashboard_horarios(df_semanas_ativas, df_colaboradores)
        with tab2:
            aba_gerenciar_semanas(df_semanas_todas)
        with tab3:
            aba_editar_escala_semanal(df_colaboradores, df_semanas_ativas)
        with tab4:
            aba_gerenciar_colaboradores(df_colaboradores)
        with tab5:
            aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)

# Para simplificar a visualização, o código de algumas abas não modificadas foi omitido com '...'
# Cole o corpo das funções `aba_consultar_escala_publica`, `aba_gerenciar_semanas`, `aba_editar_escala_semanal`
# e o do `st.sidebar` da sua versão anterior para ter o app 100% funcional.
if __name__ == "__main__":
    main()