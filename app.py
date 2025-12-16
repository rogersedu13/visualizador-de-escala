# Importando as bibliotecas necessárias
import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta, date
from supabase import create_client, Client
import time
import base64
import io

# --- Constantes da Aplicação ---
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# --- Configuração da Página ---
st.set_page_config(page_title="Frente de Caixa", page_icon="📅", layout="wide", initial_sidebar_state="expanded")

# --- Conexão Supabase ---
try:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception:
    st.error("🚨 **Erro de Conexão:** Verifique os Secrets `supabase_url` e `supabase_key`.")
    st.stop()

# --- Estado da Sessão ---
if "logado" not in st.session_state: st.session_state.logado = False
if "nome_logado" not in st.session_state: st.session_state.nome_logado = ""

# --- Funções Auxiliares ---

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

def salvar_escala_via_excel(df_excel: pd.DataFrame, data_inicio_semana: date) -> bool:
    """
    Processa o DataFrame vindo do EXCEL e salva no banco.
    """
    try:
        datas_reais = [(data_inicio_semana + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(7)]
        
        colunas_excel = df_excel.columns.tolist()
        if 'Nome' not in colunas_excel:
            st.error("O arquivo Excel precisa ter uma coluna chamada 'Nome'. Use o modelo fornecido.")
            return False
        
        barra = st.progress(0, text="Processando arquivo...")
        total_linhas = len(df_excel)
        
        for index, row in df_excel.iterrows():
            nome = row['Nome']
            if pd.isna(nome) or str(nome).strip() == "": continue
            
            for i in range(7):
                data_str_header = datas_reais[i]
                
                horario = ""
                # Tenta pegar pelo nome exato da coluna
                if data_str_header in df_excel.columns:
                    horario = row[data_str_header]
                # Fallback: pega pela posição (Nome é 0, dia 1 é 1, etc)
                elif len(row) > i+1:
                    horario = row.iloc[i+1]
                
                if pd.isna(horario): horario = ""
                horario = str(horario).strip()
                
                data_banco = (data_inicio_semana + timedelta(days=i)).strftime('%Y-%m-%d')
                
                supabase.rpc('save_escala_dia_final', {
                    'p_nome': str(nome).strip(), 
                    'p_data': data_banco, 
                    'p_horario': horario
                }).execute()
            
            if index % 5 == 0:
                barra.progress((index + 1) / total_linhas, text=f"Importando linha {index+1}...")
                
        barra.empty()
        return True

    except Exception as e:
        st.error(f"Erro ao processar Excel: {e}")
        return False

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
    except Exception as e: st.error(f"Erro: {e}"); return False

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
                st.cache_data.clear(); st.success("Semana inicializada!"); time.sleep(1.5); st.rerun()

    st.markdown("---"); st.markdown("##### 📂 Histórico")
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
    else: st.info("Nenhuma semana criada.")

@st.fragment
def aba_editar_escala_individual(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("✏️ Editar Escala")
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return

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
        id_semana = semana_info['id']; data_ini = semana_info['data_inicio']
        df_full = carregar_escala_semana_por_id(id_semana)
        escala_colab = df_full[df_full['nome'] == colaborador] if not df_full.empty else pd.DataFrame()
        horarios_atuais = {pd.to_datetime(row['data']).date(): row['horario'] for _, row in escala_colab.iterrows()}

        st.markdown(f"**Editando:** `{colaborador}`")
        cols = st.columns(7); horarios_novos = []
        for i in range(7):
            dia_atual = data_ini + timedelta(days=i)
            dia_label = f"{DIAS_SEMANA_PT[i]}\n({dia_atual.strftime('%d/%m')})"
            horario_atual = horarios_atuais.get(dia_atual, "")
            try: idx = HORARIOS_PADRAO.index(horario_atual)
            except ValueError: idx = 0
            with cols[i]:
                st.caption(dia_label)
                key_widget = f"sel_{colaborador}_{dia_atual.strftime('%Y%m%d')}"
                val = st.selectbox("H", HORARIOS_PADRAO, index=idx, key=key_widget, label_visibility="collapsed")
                horarios_novos.append(val)
        
        st.markdown("")
        if st.button("💾 Salvar Alterações", type="primary", use_container_width=True):
            if salvar_escala_individual(colaborador, horarios_novos, data_ini):
                st.success(f"Salvo!"); time.sleep(1); st.rerun()

def aba_importar_excel(df_colaboradores: pd.DataFrame, df_semanas_ativas: pd.DataFrame):
    st.subheader("📤 Importar Escala.")
    
    st.markdown("""
    **Como usar:**
    1. Selecione a semana abaixo e clique em **'📥 Baixar Planilha Excel'**.
    2. O arquivo baixado com os horários corretos será baixado.
    3. Abra no Excel, selecione os horários e salve.
    4. Arraste o arquivo Excel (.xlsx) preenchido de volta aqui.
    """)
    
    if df_semanas_ativas.empty: st.warning("Nenhuma semana ativa."); return
    
    opcoes = {row['nome_semana']: {'id': row['id'], 'data_inicio': pd.to_datetime(row['data_inicio']).date()} for _, row in df_semanas_ativas.iterrows()}
    semana_str = st.selectbox("Selecione a semana para importar:", options=opcoes.keys(), key="sel_sem_imp")
    semana_info = opcoes[semana_str]
    
    if semana_info:
        data_ini = semana_info['data_inicio']
        datas_header = [(data_ini + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(7)]
        colunas = ['Nome'] + datas_header
        
        # Cria DataFrame para o template
        df_template = pd.DataFrame(columns=colunas)
        if not df_colaboradores.empty:
            df_template['Nome'] = sorted(df_colaboradores['nome'].unique())
        
        # --- GERAÇÃO DO EXCEL COM DROPDOWN (Validação de Dados) ---
        buffer = io.BytesIO()
        # Engine xlsxwriter é necessária para criar validações
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df_template.to_excel(writer, index=False, sheet_name='Escala')
                
                workbook = writer.book
                worksheet = writer.sheets['Escala']
                
                # Cria uma aba oculta com os horários para servir de fonte (evita limite de caracteres)
                worksheet_data = workbook.add_worksheet('Dados')
                worksheet_data.hide()
                worksheet_data.write_column('A1', HORARIOS_PADRAO)
                
                # Define o intervalo onde estão os horários na aba oculta
                fim_lista = len(HORARIOS_PADRAO)
                formula_validacao = f'=Dados!$A$1:$A${fim_lista}'
                
                # Aplica a validação nas colunas de B até H (Dias da semana)
                # Começando da linha 2 (ignora cabeçalho) até a última linha de colaboradores + 50 (margem)
                ultima_linha = len(df_template) + 50
                
                # B2:H...
                worksheet.data_validation(1, 1, ultima_linha, 7, {
                    'validate': 'list',
                    'source': formula_validacao,
                    'input_title': 'Selecione o Horário',
                    'input_message': 'Escolha um horário da lista.'
                })
                
                # Ajusta largura das colunas
                worksheet.set_column('A:A', 30) # Nome maior
                worksheet.set_column('B:H', 15) # Datas
                
        except Exception as e:
            st.error(f"Erro ao gerar Excel. Verifique se 'xlsxwriter' está instalado. Detalhe: {e}")
            return

        st.download_button(
            label="📥 Baixar Planilha Excel (.xlsx)",
            data=buffer.getvalue(),
            file_name=f"escala_{data_ini.strftime('%d-%m')}.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            type="secondary"
        )
        
        st.markdown("---")
        
        arquivo_upload = st.file_uploader("Arraste o arquivo Excel (.xlsx) aqui:", type=["xlsx"])
        
        if arquivo_upload is not None:
            try:
                df_upload = pd.read_excel(arquivo_upload)
                st.info(f"Arquivo carregado com {len(df_upload)} linhas. Clique abaixo para salvar.")
                st.dataframe(df_upload.head(3), use_container_width=True)
                
                if st.button("🚀 Processar e Salvar Escala Completa", type="primary"):
                    if salvar_escala_via_excel(df_upload, data_ini):
                        st.success("Importação concluída com sucesso!")
                        time.sleep(2)
                        st.cache_data.clear()
            except Exception as e:
                st.error(f"Erro ao ler arquivo: {e}")

def aba_gerenciar_colaboradores(df_colaboradores: pd.DataFrame):
    st.subheader("👥 Colaboradores")
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            novo = st.text_input("Novo Nome:")
            if st.button("Adicionar"):
                if novo: adicionar_colaborador(novo); st.cache_data.clear(); st.success("Ok!"); st.rerun()
    with c2:
        with st.container(border=True):
            if not df_colaboradores.empty:
                rem = st.multiselect("Remover:", df_colaboradores['nome'])
                if st.button("Remover", type="secondary"):
                    if rem: remover_colaboradores(rem); st.cache_data.clear(); st.success("Ok!"); st.rerun()
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
        # TABS Atualizadas - Note "Importar Excel"
        t1, t2, t3, t4, t5 = st.tabs(["Gerenciar Semanas", "Editar (Manual)", "Importar Excel", "Colaboradores", "Visão Geral"])
        with t1: aba_gerenciar_semanas(df_semanas)
        with t2: aba_editar_escala_individual(df_colaboradores, df_semanas_ativas)
        with t3: aba_importar_excel(df_colaboradores, df_semanas_ativas) # Nova Aba Excel
        with t4: aba_gerenciar_colaboradores(df_colaboradores)
        with t5: aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)
    else:
        aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas)

if __name__ == "__main__":
    main()