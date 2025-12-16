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

# --- Configuração da Página do Streamlit ---
st.set_page_config(page_title="Frente de Caixa", page_icon="📅", layout="wide", initial_sidebar_state="expanded")

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

# --- Funções Auxiliares e de Banco de Dados ---

def formatar_data_completa(data_timestamp: pd.Timestamp) -> str:
    if pd.isna(data_timestamp): return ""
    return data_timestamp.strftime(f'%d/%m/%Y ({DIAS_SEMANA_PT[data_timestamp.weekday()]})')

@st.cache_data(ttl=300)
def carregar_colaboradores() -> pd.DataFrame:
    try:
        data = supabase.rpc('get_colaboradores').execute().data
        df = pd.DataFrame(data)
        if not df.empty: df['nome'] = df['nome'].str.strip()
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
    except Exception as e: st.error(f"Erro ao carregar escala: {e}"); return pd.DataFrame()

def salvar_escala_individual(nome: str, horarios: list, data_inicio: date) -> bool:
    """
    Salva a escala.
    """
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            supabase.rpc('save_escala_dia_final', {
                'p_nome': nome.strip(), 
                'p_data': data_dia.strftime('%Y-%m-%d'), 
                'p_horario': horario
            }).execute()
        return True
    except Exception as e: st.error(f"Erro ao salvar: {e}"); return False

def inicializar_semana_simples(data_inicio: date) -> bool:
    try:
        supabase.rpc('inicializar_escala_semanal', {'p_data_inicio': data_inicio.strftime('%Y-%m-%d')}).execute()
        
        df_colabs = carregar_colaboradores()
        if not df_colabs.empty:
            for nome in df_colabs['nome']:
                for i in range(7):
                    d = data_inicio + timedelta(days=i)
                    supabase.rpc('save_escala_dia_final', {'p_nome': nome, 'p_data': d.strftime('%Y-%m-%d'), 'p_horario': ''}).execute()
        
        return True
    except Exception as e:
        st.error(f"Erro na inicialização: {e}")
        return False

def arquivar_reativar_semana(id_semana: int, novo_status: bool):
    try:
        func = 'reativar_semana' if novo_status else 'arquivar_semana'
        supabase.rpc(func, {'p_semana_id': id_semana}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

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
    return f"""
    <html><head><title>Escala {nome_colaborador}</title><meta charset="UTF-8"><style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }} h1, h2 {{ text-align: center; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: center; border: 1px solid #ddd; }}
        thead {{ background-color: #f2f2f2; }} tr:nth-child(even) {{ background-color: #f9f9f9; }}
    </style></head><body>
        <h1>Escala Semanal</h1><h2>{nome_colaborador} - {semana_str}</h2>
        {tabela_html}
    </body></html>
    """

# --- Abas da Aplicação ---

def aba_consultar_escala_publica(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.header("🔎 Consultar Minha Escala")
    if df_colaboradores.empty: st.warning("Nenhum colaborador cadastrado."); return

    nomes_disponiveis = [""] + sorted(df_colaboradores["nome"].dropna().unique())
    nome_selecionado = st.selectbox("1. Selecione seu nome:", options=nomes_disponiveis)

    if nome_selecionado:
        if df_semanas_ativas.empty: st.info("Nenhuma semana disponível."); return
        
        opcoes_semana = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for index, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("2. Selecione a semana:", options=opcoes_semana.keys())

        if semana_str:
            semana_info = opcoes_semana[semana_str]
            with st.container(border=True):
                df = carregar_escala_semana_por_id(semana_info['id'])
                final = df[df['nome'] == nome_selecionado].sort_values("data")
                
                if not final.empty:
                    display = final.copy()
                    display["Data"] = display["data"].apply(formatar_data_completa)
                    display.rename(columns={"horario": "Horário"}, inplace=True)
                    st.dataframe(display[["Data", "Horário"]], use_container_width=True, hide_index=True)
                    
                    html = gerar_html_escala(display[["Data", "Horário"]], nome_selecionado, semana_str)
                    b64 = base64.b64encode(html.encode('utf-8')).decode()
                    nome_arq = f"escala_{nome_selecionado.strip().replace(' ','_')}.html"
                    st.markdown(f'<a href="data:text/html;charset=utf-8;base64,{b64}" download="{nome_arq}" style="background-color:#0068c9;color:white;padding:0.5em;text-decoration:none;border-radius:5px;">🖨️ Baixar para Impressão</a>', unsafe_allow_html=True)
                else:
                    st.info("Sem horários para esta semana.")

def aba_gerenciar_semanas(df_semanas_todas: pd.DataFrame):
    st.subheader("🗓️ Gerenciar Semanas")
    
    with st.container(border=True):
        st.markdown("##### ➕ Inicializar Nova Semana")
        hoje = date.today()
        prox_segunda = hoje + timedelta(days=(7 - hoje.weekday()))
        data_sel = st.date_input("Início da Semana (Segunda-feira):", value=prox_segunda)
        
        if st.button("✨ Inicializar Semana", type="primary", use_container_width=True):
            data_inicio = data_sel - timedelta(days=data_sel.weekday())
            if inicializar_semana_simples(data_inicio):
                st.cache_data.clear(); st.success("Semana inicializada com sucesso!"); time.sleep(1.5); st.rerun()

    st.markdown("---")
    st.markdown("##### 📂 Histórico de Semanas")
    
    if not df_semanas_todas.empty:
        for index, row in df_semanas_todas.iterrows():
            c1, c2, c3 = st.columns([4, 1, 1])
            status_icon = "🟢" if row['ativa'] else "📁"
            c1.markdown(f"**{status_icon} {row['nome_semana']}**")
            
            key_arch = f"btn_arch_{row['id']}"
            if row['ativa']:
                if c2.button("Arquivar", key=key_arch):
                    arquivar_reativar_semana(row['id'], False); st.cache_data.clear(); st.rerun()
            else:
                if c2.button("Reativar", key=key_arch):
                    arquivar_reativar_semana(row['id'], True); st.cache_data.clear(); st.rerun()
    else:
        st.info("Nenhuma semana criada.")

# RETORNANDO A EDIÇÃO INDIVIDUAL (COM ST.FRAGMENT PARA NÃO MEXER A TELA)
@st.fragment
def aba_editar_escala_semanal(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("✏️ Editar Escala")
    
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return

    # Filtros lado a lado
    c1, c2 = st.columns(2)
    with c1:
        opcoes = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
        semana_str = st.selectbox("Selecione a semana:", options=opcoes.keys())
        semana_info = opcoes[semana_str]
    with c2:
        nomes = sorted(df_colaboradores['nome'].unique())
        colaborador = st.selectbox("Selecione o colaborador:", nomes)

    st.markdown("---")

    if semana_info and colaborador:
        # Carregar dados
        id_semana = semana_info['id']
        data_ini = semana_info['data_inicio']
        
        # Busca escala atual
        df_full = carregar_escala_semana_por_id(id_semana)
        
        # Filtra para o colaborador
        escala_colab = pd.DataFrame()
        if not df_full.empty:
            escala_colab = df_full[df_full['nome'] == colaborador]
            
        # Dicionário {data: horario} para preencher os selectboxes
        horarios_atuais = {pd.to_datetime(row['data']).date(): row['horario'] for _, row in escala_colab.iterrows()}

        # Renderiza os 7 dias
        st.markdown(f"**Editando:** `{colaborador}`")
        
        cols = st.columns(7)
        horarios_novos = []
        
        for i in range(7):
            dia_atual = data_ini + timedelta(days=i)
            dia_label = f"{DIAS_SEMANA_PT[i]}\n({dia_atual.strftime('%d/%m')})"
            
            horario_atual = horarios_atuais.get(dia_atual, "")
            
            # Encontra o indice do horario atual na lista padrao
            try:
                idx = HORARIOS_PADRAO.index(horario_atual)
            except ValueError:
                idx = 0 # Se nao achar, padrao é vazio
            
            with cols[i]:
                st.caption(dia_label)
                # Chave unica para o widget não bugar
                key_widget = f"sel_{colaborador}_{dia_atual.strftime('%Y%m%d')}"
                val = st.selectbox("H", HORARIOS_PADRAO, index=idx, key=key_widget, label_visibility="collapsed")
                horarios_novos.append(val)
        
        st.markdown("")
        if st.button("💾 Salvar Alterações", type="primary", use_container_width=True):
            if salvar_escala_individual(colaborador, horarios_novos, data_ini):
                st.success(f"Escala de {colaborador} salva!")
                time.sleep(1)
                st.rerun() # Atualiza apenas este fragmento

def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Gerenciar Colaboradores")
    c1, c2 = st.columns(2)
    
    with c1:
        with st.container(border=True):
            novo = st.text_input("Novo Nome:")
            if st.button("Adicionar Colaborador"):
                if novo: adicionar_colaborador(novo); st.cache_data.clear(); st.success("Adicionado!"); st.rerun()
    
    with c2:
        with st.container(border=True):
            if not df_colaboradores.empty:
                rem = st.multiselect("Remover:", df_colaboradores['nome'])
                if st.button("Remover Selecionados", type="secondary"):
                    if rem: remover_colaboradores(rem); st.cache_data.clear(); st.success("Removido!"); st.rerun()
    
    st.dataframe(df_colaboradores, use_container_width=True)

# --- Main ---
def main():
    st.title("📅 Sistema de Escalas")
    df_fiscais = carregar_fiscais()
    df_colaboradores = carregar_colaboradores()
    df_semanas = carregar_indice_semanas()
    df_semanas_ativas = df_semanas[df_semanas['ativa'] == True] if not df_semanas.empty else pd.DataFrame()

    with st.sidebar:
        st.header("Acesso")
        if not st.session_state.logado:
            with st.form("login"):
                c = st.text_input("Código"); s = st.text_input("Senha", type="password")
                if st.form_submit_button("Entrar", type="primary"):
                    auth = df_fiscais[(df_fiscais['codigo'] == int(c)) & (df_fiscais['senha'] == s)] if c.isdigit() else pd.DataFrame()
                    if not auth.empty: st.session_state.logado = True; st.session_state.nome_logado = auth.iloc[0]['nome']; st.rerun()
                    else: st.error("Inválido")
        else:
            st.success(f"Olá, {st.session_state.nome_logado}")
            if st.button("Sair"): st.session_state.logado = False; st.rerun()
        st.markdown("---"); st.caption("DEV @Rogério Souza")

    if st.session_state.logado:
        t1, t2, t3, t4 = st.tabs(["Gerenciar Semanas", "Editar Escala", "Colaboradores", "Visão Pública"])
        with t1: aba_gerenciar_semanas(df_semanas)
        with t2: aba_editar_escala_semanal(df_colaboradores, df_semanas_ativas)
        with t3: aba_gerenciar_colaboradores(df_colaboradores)
        with t4: aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)

if __name__ == "__main__":
    main()