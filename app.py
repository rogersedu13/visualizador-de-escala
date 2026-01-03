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
DIAS_SEMANA_FULL = ["SEGUNDA-FEIRA", "TERÇA-FEIRA", "QUARTA-FEIRA", "QUINTA-FEIRA", "SEXTA-FEIRA", "SÁBADO", "DOMINGO"]

FUNCOES_LOJA = ["Operador(a) de Caixa", "Empacotador(a)", "Fiscal de Caixa", "Recepção"]

HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:30 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

HORARIOS_MANHA = [h for h in HORARIOS_PADRAO if "HRS" in h and int(h.split(':')[0]) <= 10]
HORARIOS_TARDE = [h for h in HORARIOS_PADRAO if "HRS" in h and int(h.split(':')[0]) > 10]

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

@st.cache_data(ttl=1) 
def carregar_colaboradores() -> pd.DataFrame:
    try:
        response = supabase.table('colaboradores').select('*').execute()
        df = pd.DataFrame(response.data)
        if not df.empty: 
            df['nome'] = df['nome'].str.strip()
            if 'funcao' not in df.columns: df['funcao'] = 'Operador(a) de Caixa'
            df['funcao'] = df['funcao'].fillna('Operador(a) de Caixa')
        return df
    except Exception as e: return pd.DataFrame()

@st.cache_data(ttl=60)
def carregar_indice_semanas(apenas_ativas: bool = False) -> pd.DataFrame:
    try:
        query = supabase.table('semanas').select('id, nome_semana, data_inicio, ativa').order('data_inicio', desc=True)
        if apenas_ativas: query = query.eq('ativa', True)
        response = query.execute()
        return pd.DataFrame(response.data)
    except Exception as e: st.error(f"Erro ao carregar semanas: {e}"); return pd.DataFrame()

@st.cache_data(ttl=10)
def carregar_escala_semana_por_id(id_semana: int) -> pd.DataFrame:
    try:
        params = {'p_semana_id': id_semana}
        response = supabase.rpc('get_escala_semana', params).execute()
        df = pd.DataFrame(response.data)
        if not df.empty:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
            df['nome'] = df['nome'].str.strip()
            df_colabs = carregar_colaboradores()
            if not df_colabs.empty and 'funcao' in df_colabs.columns:
                df_colabs_unique = df_colabs.drop_duplicates(subset=['nome'])
                df = df.merge(df_colabs_unique[['nome', 'funcao']], on='nome', how='left')
                df['funcao'] = df['funcao'].fillna('Operador(a) de Caixa')
        return df
    except Exception as e: st.error(f"Erro ao carregar escala: {e}"); return pd.DataFrame()

def salvar_escala_individual(nome: str, horarios: list, data_inicio: date) -> bool:
    try:
        for i, horario in enumerate(horarios):
            data_dia = data_inicio + timedelta(days=i)
            supabase.rpc('save_escala_dia_final', {'p_nome': nome.strip(), 'p_data': data_dia.strftime('%Y-%m-%d'), 'p_horario': horario}).execute()
        return True
    except Exception as e: st.error(f"Erro ao salvar: {e}"); return False

def salvar_escala_via_excel(df_excel: pd.DataFrame, data_inicio_semana: date) -> bool:
    try:
        datas_reais = [(data_inicio_semana + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(7)]
        for index, row in df_excel.iterrows():
            nome = row.get('Nome')
            if pd.isna(nome) or str(nome).strip() == "" or "TOTAL" in str(nome) or "Manhã" in str(nome) or "Tarde" in str(nome): continue
            for i in range(7):
                data_str_header = datas_reais[i]
                horario = row.get(data_str_header, "")
                if pd.isna(horario): horario = ""
                horario = str(horario).strip()
                data_banco = (data_inicio_semana + timedelta(days=i)).strftime('%Y-%m-%d')
                supabase.rpc('save_escala_dia_final', {'p_nome': str(nome).strip(), 'p_data': data_banco, 'p_horario': horario}).execute()
        return True
    except Exception as e: st.error(f"Erro Excel: {e}"); return False

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
    except Exception: return False

def arquivar_reativar_semana(id_semana: int, novo_status: bool):
    try:
        func = 'reativar_semana' if novo_status else 'arquivar_semana'
        supabase.rpc(func, {'p_semana_id': id_semana}).execute()
        return True
    except Exception: return False

def adicionar_colaborador(nome: str, funcao: str) -> bool:
    try:
        supabase.table('colaboradores').insert({'nome': nome.strip(), 'funcao': funcao}).execute()
        return True
    except Exception as e: st.error(f"Erro: {e}"); return False

def remover_colaboradores(lista_nomes: list) -> bool:
    try:
        supabase.rpc('delete_colaboradores', {'p_nomes': [n.strip() for n in lista_nomes]}).execute(); return True
    except Exception: return False

def atualizar_funcao_colaborador(nome: str, nova_funcao: str):
    try:
        supabase.table('colaboradores').update({'funcao': nova_funcao}).eq('nome', nome).execute()
        return True
    except Exception: return False

@st.cache_data
def carregar_fiscais() -> pd.DataFrame:
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"},
        {"codigo": 1015, "nome": "Gisele", "senha": "3"},
        {"codigo": 1005, "nome": "Fabiana", "senha": "4"},
        {"codigo": 1016, "nome": "Amanda", "senha": "5"}
    ])

# --- FUNÇÃO GERADORA DE LAYOUT DIÁRIO (IGUAL FOTO) ---
def gerar_html_diario(df_dia: pd.DataFrame, dia_semana_str: str, data_str: str):
    # Separa por função
    operadores = df_dia[df_dia['funcao'] == 'Operador(a) de Caixa'].sort_values('nome')
    empacotadores = df_dia[df_dia['funcao'] == 'Empacotador(a)'].sort_values('nome')
    
    # Filtra folgas
    folgas_op = operadores[operadores['horario'].isin(['Folga', 'Ferias', 'Atestado', 'Afastado(a)'])]
    folgas_emp = empacotadores[empacotadores['horario'].isin(['Folga', 'Ferias', 'Atestado', 'Afastado(a)'])]
    
    # Filtra quem trabalha
    trab_op = operadores[~operadores['horario'].isin(['Folga', 'Ferias', 'Atestado', 'Afastado(a)', ''])]
    trab_emp = empacotadores[~empacotadores['horario'].isin(['Folga', 'Ferias', 'Atestado', 'Afastado(a)', ''])]

    # HTML
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; -webkit-print-color-adjust: exact; }}
            .header {{ text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 5px; border-bottom: 2px solid black; padding-bottom: 5px; }}
            .sub-header {{ text-align: center; font-size: 14px; margin-bottom: 10px; }}
            .container {{ display: flex; width: 100%; }}
            .col {{ flex: 1; padding: 0 5px; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
            th {{ background-color: #333; color: white; padding: 4px; text-align: center; }}
            td {{ border: 1px solid #999; padding: 3px; text-align: center; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .folgas-box {{ margin-top: 20px; border: 1px solid black; padding: 5px; font-size: 11px; }}
            .titulo-funcao {{ background-color: #ddd; font-weight: bold; text-align: center; padding: 5px; margin-top: 5px; border: 1px solid #999; }}
        </style>
    </head>
    <body>
        <div class="header">{dia_semana_str} - DATA: {data_str}</div>
        
        <div class="container">
            <div class="col">
                <div class="titulo-funcao">OPERADORES ({len(trab_op)})</div>
                <table>
                    <thead><tr><th>NOME</th><th>HORÁRIO</th></tr></thead>
                    <tbody>
    """
    for _, row in trab_op.iterrows():
        html += f"<tr><td>{row['nome']}</td><td>{row['horario']}</td></tr>"
    
    html += """
                    </tbody>
                </table>
            </div>
            
            <div class="col">
                <div class="titulo-funcao">EMPACOTADORES ({})</div>
                <table>
                    <thead><tr><th>NOME</th><th>HORÁRIO</th></tr></thead>
                    <tbody>
    """.format(len(trab_emp))
    
    for _, row in trab_emp.iterrows():
        html += f"<tr><td>{row['nome']}</td><td>{row['horario']}</td></tr>"

    html += """
                    </tbody>
                </table>
            </div>
        </div>

        <div class="folgas-box">
            <b>FOLGAS / AFASTAMENTOS DO DIA:</b><br>
            <b>OP:</b> {}<br>
            <b>EMP:</b> {}
        </div>
    </body>
    </html>
    """.format(
        ", ".join(folgas_op['nome'].tolist()),
        ", ".join(folgas_emp['nome'].tolist())
    )
    return html

# --- ABAS ---

@st.fragment
def aba_consultar_escala_publica(df_colaboradores, df_semanas_ativas):
    st.header("🔎 Consultar Minha Escala")
    if df_colaboradores.empty: st.warning("Nenhum colaborador."); return
    nome_sel = st.selectbox("1. Selecione seu nome:", [""] + sorted(df_colaboradores["nome"].unique()))
    if nome_sel:
        semana_str = st.selectbox("2. Semana:", options=[r['nome_semana'] for i, r in df_semanas_ativas.iterrows()])
        if semana_str:
            row = df_semanas_ativas[df_semanas_ativas['nome_semana'] == semana_str].iloc[0]
            df = carregar_escala_semana_por_id(row['id'])
            final = df[df['nome'] == nome_sel].sort_values("data")
            if not final.empty:
                final['Data'] = final['data'].apply(formatar_data_completa)
                st.dataframe(final[['Data', 'horario']], hide_index=True)

def aba_gerenciar_semanas(df_semanas):
    st.subheader("🗓️ Gerenciar Semanas")
    with st.container(border=True):
        data_sel = st.date_input("Início da Semana:", value=date.today())
        if st.button("✨ Inicializar Semana", type="primary"):
            if inicializar_semana_simples(data_sel - timedelta(days=data_sel.weekday())):
                st.success("Criada!"); time.sleep(1); st.rerun()
    
    st.markdown("---")
    for _, row in df_semanas.iterrows():
        c1, c2 = st.columns([4, 1])
        c1.write(f"{'🟢' if row['ativa'] else '📁'} {row['nome_semana']}")
        if row['ativa']: 
            if c2.button("Arquivar", key=f"arch_{row['id']}"): arquivar_reativar_semana(row['id'], False); st.rerun()
        else:
            if c2.button("Reativar", key=f"react_{row['id']}"): arquivar_reativar_semana(row['id'], True); st.rerun()

@st.fragment
def aba_editar_individual(df_colaboradores, df_semanas_ativas):
    st.subheader("✏️ Editar Escala")
    if df_semanas_ativas.empty: st.warning("Nenhuma semana."); return
    
    semana_str = st.selectbox("Semana:", options=[r['nome_semana'] for i, r in df_semanas_ativas.iterrows()])
    semana_info = df_semanas_ativas[df_semanas_ativas['nome_semana'] == semana_str].iloc[0]
    
    filtro = st.selectbox("Função:", ["Todos"] + FUNCOES_LOJA)
    df_show = df_colaboradores if filtro == "Todos" else df_colaboradores[df_colaboradores['funcao'] == filtro]
    
    colab = st.selectbox("Colaborador:", sorted(df_show['nome'].unique()))
    
    if colab:
        df_escala = carregar_escala_semana_por_id(semana_info['id'])
        escala_user = df_escala[df_escala['nome'] == colab]
        horarios_atuais = {pd.to_datetime(r['data']).date(): r['horario'] for _, r in escala_user.iterrows()}
        
        cols = st.columns(7)
        novos = []
        for i in range(7):
            dia = pd.to_datetime(semana_info['data_inicio']).date() + timedelta(days=i)
            atual = horarios_atuais.get(dia, "")
            idx = HORARIOS_PADRAO.index(atual) if atual in HORARIOS_PADRAO else 0
            with cols[i]:
                st.caption(f"{DIAS_SEMANA_PT[i]} {dia.strftime('%d/%m')}")
                novos.append(st.selectbox("H", HORARIOS_PADRAO, index=idx, key=f"s_{colab}_{i}", label_visibility="collapsed"))
        
        if st.button("💾 Salvar"):
            salvar_escala_individual(colab, novos, pd.to_datetime(semana_info['data_inicio']).date())
            st.success("Salvo!"); time.sleep(0.5); st.rerun()

def aba_importar_excel(df_colaboradores, df_semanas_ativas):
    st.subheader("📤 Importar Excel")
    if df_semanas_ativas.empty: return
    
    semana_str = st.selectbox("Semana:", options=[r['nome_semana'] for i, r in df_semanas_ativas.iterrows()], key="imp_sem")
    funcao = st.selectbox("Função:", FUNCOES_LOJA, key="imp_func")
    
    semana_info = df_semanas_ativas[df_semanas_ativas['nome_semana'] == semana_str].iloc[0]
    data_ini = pd.to_datetime(semana_info['data_inicio']).date()
    
    if st.button("📥 Baixar Modelo"):
        df_filt = df_colaboradores[df_colaboradores['funcao'] == funcao]
        if df_filt.empty: st.error("Sem colaboradores."); return
        
        cols = ['Nome'] + [(data_ini + timedelta(days=i)).strftime('%d/%m/%Y') for i in range(7)]
        df_tpl = pd.DataFrame(columns=cols)
        df_tpl['Nome'] = sorted(df_filt['nome'].unique())
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_tpl.to_excel(writer, index=False, sheet_name='Escala')
            wb = writer.book; ws = writer.sheets['Escala']
            ws_d = wb.add_worksheet('D'); ws_d.hide(); ws_d.write_column('A1', HORARIOS_PADRAO)
            ws.data_validation(1, 1, 100, 7, {'validate': 'list', 'source': '=D!$A$1:$A$'+str(len(HORARIOS_PADRAO))})
            
            # Cabeçalhos simplificados para visualização
            map_n = {"Operador(a) de Caixa": "Operadoras", "Empacotador(a)": "Empacotadores", "Fiscal de Caixa": "Fiscais", "Recepção": "Recepção"}
            nome_s = map_n.get(funcao, funcao)
            ws.write(len(df_tpl)+2, 0, f"{nome_s} Manhã")
            ws.write(len(df_tpl)+3, 0, f"{nome_s} Tarde")
            
            # Fórmulas
            cols_l = ['B','C','D','E','F','G','H']
            for i, l in enumerate(cols_l):
                rng = f"{l}2:{l}{len(df_tpl)+1}"
                crit_m = ",".join([f'COUNTIF({rng},"{h}")' for h in HORARIOS_MANHA])
                crit_t = ",".join([f'COUNTIF({rng},"{h}")' for h in HORARIOS_TARDE])
                ws.write_formula(len(df_tpl)+2, i+1, f"=SUM({crit_m})")
                ws.write_formula(len(df_tpl)+3, i+1, f"=SUM({crit_t})")
                
        st.download_button("Baixar .xlsx", buffer.getvalue(), f"escala_{funcao}.xlsx")

    up = st.file_uploader("Upload Excel", type=["xlsx"])
    if up and st.button("Processar"):
        if salvar_escala_via_excel(pd.read_excel(up), data_ini):
            st.success("Sucesso!"); time.sleep(1); st.cache_data.clear()

@st.fragment
def aba_gerar_pdf_diario(df_colaboradores, df_semanas_ativas):
    st.subheader("🖨️ Gerar Escala Diária")
    
    if df_semanas_ativas.empty: st.warning("Selecione uma semana."); return
    
    # 1. Seleciona Semana
    semana_str = st.selectbox("Selecione a Semana:", options=[r['nome_semana'] for i, r in df_semanas_ativas.iterrows()])
    semana_info = df_semanas_ativas[df_semanas_ativas['nome_semana'] == semana_str].iloc[0]
    data_ini = pd.to_datetime(semana_info['data_inicio']).date()
    
    # 2. Seleciona o Dia da Semana
    dias_opcoes = [f"{DIAS_SEMANA_FULL[i]} - {(data_ini + timedelta(days=i)).strftime('%d/%m/%Y')}" for i in range(7)]
    dia_selecionado_str = st.selectbox("Selecione o Dia para Imprimir:", dias_opcoes)
    
    if dia_selecionado_str:
        # Extrai a data real da string selecionada
        index_dia = dias_opcoes.index(dia_selecionado_str)
        data_alvo = data_ini + timedelta(days=index_dia)
        
        # 3. Busca dados do banco para aquele dia
        df_full = carregar_escala_semana_por_id(semana_info['id'])
        
        # Filtra apenas para a data selecionada
        df_dia = df_full[pd.to_datetime(df_full['data']).dt.date == data_alvo]
        
        if df_dia.empty:
            st.info("Nenhum horário lançado para este dia ainda.")
        else:
            # Gera o HTML visual
            html_content = gerar_html_diario(df_dia, DIAS_SEMANA_FULL[index_dia], data_alvo.strftime('%d/%m/%Y'))
            
            # Mostra preview na tela
            st.markdown("### 👁️ Pré-visualização")
            st.components.v1.html(html_content, height=600, scrolling=True)
            
            # Botão de Download/Impressão
            b64 = base64.b64encode(html_content.encode('utf-8')).decode()
            href = f'<a href="data:text/html;charset=utf-8;base64,{b64}" download="Escala_{DIAS_SEMANA_PT[index_dia]}_{data_alvo.strftime("%d%m")}.html" style="background-color:#E31B23; color:white; padding:10px 20px; text-decoration:none; border-radius:5px; font-weight:bold;">🖨️ CLIQUE AQUI PARA IMPRIMIR</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.caption("Ao abrir o arquivo, pressione Ctrl+P para salvar como PDF ou Imprimir.")

def aba_gerenciar_colaboradores(df_colaboradores):
    st.subheader("👥 Colaboradores")
    if not df_colaboradores.empty:
        df_ed = st.data_editor(df_colaboradores[['nome', 'funcao']], column_config={"nome": st.column_config.TextColumn(disabled=True), "funcao": st.column_config.SelectboxColumn(options=FUNCOES_LOJA)}, key="edit_col", use_container_width=True)
        if st.button("Salvar Cargos"):
            for i, r in df_ed.iterrows():
                old = df_colaboradores[df_colaboradores['nome']==r['nome']]['funcao'].iloc[0]
                if r['funcao'] != old: atualizar_funcao_colaborador(r['nome'], r['funcao'])
            st.success("Ok!"); time.sleep(1); st.cache_data.clear(); st.rerun()
    
    c1, c2 = st.columns(2)
    with c1:
        n, f = st.text_input("Nome:"), st.selectbox("Função:", FUNCOES_LOJA)
        if st.button("Adicionar"): adicionar_colaborador(n, f); st.cache_data.clear(); st.rerun()
    with c2:
        rem = st.multiselect("Remover:", df_colaboradores['nome'] if not df_colaboradores.empty else [])
        if st.button("Remover"): remover_colaboradores(rem); st.cache_data.clear(); st.rerun()

# --- Main ---
def main():
    st.title("📅 Sistema de Escalas")
    df_fiscais = carregar_fiscais()
    df_colab = carregar_colaboradores()
    df_sem = carregar_indice_semanas()
    df_sem_ativas = df_sem[df_sem['ativa']==True] if not df_sem.empty else pd.DataFrame()

    with st.sidebar:
        if not st.session_state.logado:
            c = st.text_input("Código"); s = st.text_input("Senha", type="password")
            if st.button("Entrar"):
                if not df_fiscais[(df_fiscais['codigo']==int(c)) & (df_fiscais['senha']==s) if c.isdigit() else False].empty:
                    st.session_state.logado = True; st.rerun()
                else: st.error("Erro")
        else:
            if st.button("Sair"): st.session_state.logado = False; st.rerun()

    if st.session_state.logado:
        # NOVA ORDEM DAS ABAS
        t1, t2, t3, t4, t5, t6 = st.tabs(["Gerenciar Semanas", "Editar Escala Manual", "Importar Excel", "🖨️ Gerar Escala Diária", "Colaboradores", "Visão Geral"])
        with t1: aba_gerenciar_semanas(df_sem)
        with t2: aba_editar_individual(df_colab, df_sem_ativas)
        with t3: aba_importar_excel(df_colab, df_sem_ativas)
        with t4: aba_gerar_pdf_diario(df_colab, df_sem_ativas) # NOVA ABA AQUI
        with t5: aba_gerenciar_colaboradores(df_colab)
        with t6: aba_consultar_escala_publica(df_colab, df_sem_ativas)
    else:
        aba_consultar_escala_publica(df_colab, df_sem_ativas)

if __name__ == "__main__":
    main()