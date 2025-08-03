import streamlit as st
import pandas as pd
import datetime
from datetime import timedelta
from supabase import create_client, Client
import base64
from io import BytesIO
from fpdf import FPDF
import time

# --- Constantes ---
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
HORARIOS_PADRAO = [
    "", "Folga", "5:50 HRS", "6:50 HRS", "7:30 HRS", "8:00 HRS", "8:30 HRS",
    "9:00 HRS", "9:30 HRS", "10:00 HRS", "10:30 HRS", "11:00 HRS", "11:30 HRS",
    "12:00 HRS", "12:30 HRS", "13:00 HRS", "13:30 HRS", "14:00 HRS",
    "14:30 HRS", "15:00 HRS", "15:30 HRS", "16:00 HRS", "16:30 HRS", "Ferias",
    "Afastado(a)", "Atestado",
]

# --- Configuração da Página ---
st.set_page_config(page_title="Visualizador de Escala", layout="wide", initial_sidebar_state="expanded")

# --- Conexão com o Supabase ---
try:
    url = st.secrets["supabase_url"]
    key = st.secrets["supabase_key"]
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error("Falha na conexão com o banco de dados. Verifique a configuração dos 'Secrets'.")
    st.info("Certifique-se de que os nomes nos Secrets são 'supabase_url' e 'supabase_key'.")
    st.stop()

# --- Funções de Dados (usando Supabase) ---
@st.cache_data(ttl=30)
def carregar_colaboradores():
    try:
        response = supabase.table('colaboradores').select('nome').order('nome').execute()
        df = pd.DataFrame(response.data)
        return df if not df.empty else pd.DataFrame(columns=['nome'])
    except Exception as e:
        st.error(f"Erro ao carregar colaboradores: {e}")
        return pd.DataFrame(columns=['nome'])

@st.cache_data(ttl=30)
def carregar_escalas():
    try:
        response = supabase.table('escalas').select('nome, data, horario').execute()
        df = pd.DataFrame(response.data)
        if df.empty:
            return pd.DataFrame(columns=['nome', 'data', 'horario'])
        
        if 'data' in df.columns:
            df['data'] = pd.to_datetime(df['data'], errors='coerce')
        return df
    except Exception as e:
        st.error(f"Erro ao carregar escalas: {e}")
        return pd.DataFrame(columns=['nome', 'data', 'horario'])

# --- FUNÇÃO DE SALVAMENTO FINAL E SEGURA ---
def salvar_escala_individual(registros_da_semana):
    """Apaga todos os registros da semana para um colaborador e insere os novos."""
    try:
        if not registros_da_semana:
            return True # Nada a fazer

        nome_colaborador = registros_da_semana[0]['nome']
        datas_da_semana_str = [reg['data'] for reg in registros_da_semana]

        # Passo 1: Deleção segura e específica para o colaborador e a semana em questão.
        supabase.table('escalas').delete().match({
            'nome': nome_colaborador
        }).in_('data', datas_da_semana_str).execute()
        
        # Passo 2: Prepara a lista de novos registros para inserir (filtrando os vazios)
        registros_para_inserir = [
            reg for reg in registros_da_semana if reg['horario'] not in ["", None]
        ]

        # Passo 3: Insere os novos registros em um único comando, se houver algum.
        if registros_para_inserir:
            supabase.table('escalas').insert(registros_para_inserir).execute()
            
        return True
    except Exception as e:
        st.error(f"ERRO DETALHADO AO SALVAR: {e}")
        return False

def adicionar_colaborador(nome):
    try:
        supabase.table('colaboradores').insert({"nome": nome}).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao adicionar colaborador: {e}")
        return False

def remover_colaboradores(lista_nomes):
    try:
        supabase.table('colaboradores').delete().in_('nome', lista_nomes).execute()
        supabase.table('escalas').delete().in_('nome', lista_nomes).execute()
        return True
    except Exception as e:
        st.error(f"Erro ao remover colaboradores: {e}")
        return False

def carregar_fiscais():
    return pd.DataFrame([
        {"codigo": 1017, "nome": "Rogério", "senha": "1"},
        {"codigo": 1002, "nome": "Andrews", "senha": "2"}
    ])

def formatar_data_manual(data_timestamp):
    if pd.isna(data_timestamp):
        return ""
    dia_semana_str = DIAS_SEMANA_PT[data_timestamp.weekday()]
    return data_timestamp.strftime(f'%d/%m/%Y ({dia_semana_str})')

# --- Classe para Geração de PDF ---
class PDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, "Boa Semana e Bom Trabalho", 0, 0, "C")

# --- Carregamento inicial dos dados ---
df_colaboradores = carregar_colaboradores()
df_escalas = carregar_escalas()

# --- Interface Principal ---
st.title("📅 Visualizador de Escala")
st.markdown("<p style='text-align: center; font-size: 12px;'>Versão 1.0</p>", unsafe_allow_html=True)

st.sidebar.title("Modo de Acesso")
aba_principal = st.sidebar.radio("", ["Consultar minha escala", "Área do Fiscal"])

if "logado" not in st.session_state:
    st.session_state.logado = False

if st.session_state.logado:
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.logado = False
        st.rerun()

# --- Aba: Consultar Minha Escala ---
if aba_principal == "Consultar minha escala":
    st.header("🔎 Buscar minha escala")
    nomes_disponiveis = sorted(df_colaboradores["nome"].dropna().unique()) if not df_colaboradores.empty else []
    if not nomes_disponiveis:
        st.warning("Nenhum(a) colaborador(a) cadastrado(a) no sistema. Fale com o fiscal.")
    else:
        nome_digitado = st.text_input("Digite seu nome para buscar:", placeholder="Comece a digitar seu nome aqui...")
        nome_confirmado = None
        if nome_digitado:
            sugestoes = [n for n in nomes_disponiveis if nome_digitado.lower() in n.lower()]
            if sugestoes:
                st.info("Encontramos nomes correspondentes. Por favor, confirme o seu na lista abaixo.")
                nome_confirmado = st.selectbox("Confirme seu nome:", options=sugestoes)
            else:
                st.warning("Nenhum nome correspondente encontrado. Verifique a digitação.")

        if nome_confirmado:
            hoje = pd.Timestamp.today().normalize()
            data_fim = hoje + timedelta(days=30)
            st.info(f"Mostrando sua escala para **{nome_confirmado}** de hoje até {data_fim.strftime('%d/%m/%Y')}.")
            
            if not df_escalas.empty:
                resultados = df_escalas[
                    (df_escalas["nome"].str.lower() == nome_confirmado.lower()) &
                    (df_escalas["data"] >= hoje) &
                    (df_escalas["data"] <= data_fim)
                ].sort_values("data")
            else:
                resultados = pd.DataFrame()

            if not resultados.empty:
                resultados_display = resultados.copy()
                resultados_display["data"] = resultados_display["data"].apply(formatar_data_manual)
                st.dataframe(resultados_display[["data", "horario"]], use_container_width=True, hide_index=True)
                
                if st.button("📥 Baixar em PDF"):
                    pdf = PDF()
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 16)
                    pdf.cell(0, 10, f"Escala de Trabalho: {nome_confirmado}", ln=True, align="C")
                    pdf.ln(10)
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(95, 10, 'Data', 1, 0, 'C')
                    pdf.cell(95, 10, 'Horario', 1, 1, 'C')
                    pdf.set_font("Arial", "", 12)
                    for _, row in resultados_display.iterrows():
                        data_pdf = row['data'].encode('latin-1', 'replace').decode('latin-1')
                        horario_pdf = str(row['horario']).encode('latin-1', 'replace').decode('latin-1')
                        pdf.cell(95, 10, data_pdf, 1, 0, 'C')
                        pdf.cell(95, 10, horario_pdf, 1, 1, 'C')
                    pdf_bytes = pdf.output(dest='S').encode('latin-1')
                    b64 = base64.b64encode(pdf_bytes).decode()
                    href = f'<a href="data:application/pdf;base64,{b64}" download="escala_{nome_confirmado}.pdf" target="_blank">Clique aqui para baixar o PDF</a>'
                    st.markdown(href, unsafe_allow_html=True)
            else:
                st.success(f"**{nome_confirmado}**, você não possui escalas agendadas para os próximos 30 dias.")

# --- Aba: Área do Fiscal ---
elif aba_principal == "Área do Fiscal":
    df_fiscais = carregar_fiscais()
    if not st.session_state.logado:
        st.header("🔐 Login do Fiscal")
        with st.form("login_form"):
            codigo = st.text_input("Código do fiscal")
            senha = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
            if submitted:
                if not codigo or not senha:
                    st.error("Por favor, preencha o código e a senha.")
                elif not codigo.isdigit():
                    st.error("Código inválido. Digite apenas números.")
                else:
                    fiscal_auth = df_fiscais[(df_fiscais["codigo"] == int(codigo)) & (df_fiscais["senha"] == senha)]
                    if not fiscal_auth.empty:
                        st.session_state.logado = True
                        st.session_state.nome_logado = fiscal_auth.iloc[0]["nome"]
                        st.rerun()
                    else:
                        st.error("Código ou senha incorretos.")
    else: # Se já estiver logado
        st.header(f"Bem-vindo, {st.session_state.get('nome_logado', '')}!")
        
        opcoes_abas = ["Visão Geral da Escala", "Editar Escala Semanal", "Gerenciar Colaboradores"]
        aba_selecionada = st.radio("Navegação do Fiscal", opcoes_abas, horizontal=True, label_visibility="collapsed")
        
        if aba_selecionada == "Visão Geral da Escala":
            st.subheader("🗓️ Visão Geral da Escala")
            data_inicio_visao = st.date_input("Ver escala a partir de:", datetime.date.today())
            if data_inicio_visao:
                data_fim_visao = data_inicio_visao + timedelta(days=6)
                st.info(f"Mostrando escalas de {data_inicio_visao.strftime('%d/%m')} a {data_fim_visao.strftime('%d/%m')}")
                
                if not df_escalas.empty:
                    df_view = df_escalas[
                        (df_escalas['data'] >= pd.to_datetime(data_inicio_visao)) &
                        (df_escalas['data'] <= pd.to_datetime(data_fim_visao))
                    ].copy()
                else:
                    df_view = pd.DataFrame()

                if df_view.empty:
                    st.info("Nenhuma escala encontrada para este período.")
                else:
                    df_view['data'] = df_view['data'].apply(formatar_data_manual)
                    st.dataframe(df_view.sort_values(["data", "nome"]), use_container_width=True, hide_index=True)

        elif aba_selecionada == "Editar Escala Semanal":
            st.subheader("✏️ Editar Escala Semanal")
            if df_colaboradores.empty:
                st.warning("Adicione colaboradores na aba 'Gerenciar Colaboradores' primeiro.")
            else:
                col1, col2 = st.columns(2)
                with col1:
                    dia_selecionado = st.date_input("Selecione uma data para a semana:", datetime.date.today())
                with col2:
                    nomes_lista = [""] + df_colaboradores["nome"].tolist()
                    colaborador_selecionado = st.selectbox("Selecione o colaborador para editar:", nomes_lista, index=0)

                if colaborador_selecionado:
                    dia_inicio_semana = dia_selecionado - timedelta(days=dia_selecionado.weekday())
                    st.info(f"Editando a semana de **{dia_inicio_semana.strftime('%d/%m/%Y')}** para **{colaborador_selecionado}**")
                    
                    datas_da_semana_obj = [dia_inicio_semana + timedelta(days=i) for i in range(7)]
                    datas_da_semana_ts = [pd.to_datetime(d) for d in datas_da_semana_obj]

                    escala_atual_colaborador = df_escalas[
                        (df_escalas['nome'] == colaborador_selecionado) &
                        (df_escalas['data'].isin(datas_da_semana_ts))
                    ]
                    
                    with st.form(key=f"form_{colaborador_selecionado}_{dia_inicio_semana.strftime('%Y%m%d')}"):
                        cols = st.columns(7)
                        for i, data_obj in enumerate(datas_da_semana_obj):
                            dia_str = DIAS_SEMANA_PT[i]
                            
                            horario_atual_df = escala_atual_colaborador[escala_atual_colaborador['data'].dt.date == data_obj]
                            horario_atual = horario_atual_df['horario'].iloc[0] if not horario_atual_df.empty else ""
                            
                            index_horario = HORARIOS_PADRAO.index(horario_atual) if horario_atual in HORARIOS_PADRAO else 0
                            
                            with cols[i]:
                                widget_key = f"horario_{i}_{dia_inicio_semana.strftime('%Y%m%d')}"
                                st.selectbox(
                                    f"{dia_str} ({data_obj.strftime('%d/%m')})",
                                    options=HORARIOS_PADRAO,
                                    index=index_horario,
                                    key=widget_key 
                                )
                        
                        submitted = st.form_submit_button("Salvar Escala de " + colaborador_selecionado)
                        
                        if submitted:
                            registros_para_salvar = []
                            for i, data_obj in enumerate(datas_da_semana_obj):
                                widget_key = f"horario_{i}_{dia_inicio_semana.strftime('%Y%m%d')}"
                                novo_horario = st.session_state[widget_key]
                                
                                registro = {
                                    "nome": colaborador_selecionado,
                                    "data": data_obj.strftime('%Y-%m-%d'),
                                    "horario": novo_horario
                                }
                                registros_para_salvar.append(registro)
                            
                            with st.spinner("Salvando..."):
                                if salvar_escala_individual(registros_para_salvar):
                                    st.cache_data.clear()
                                    st.success("Escala salva com sucesso!")
                                    time.sleep(1)
                                    st.rerun()

        elif aba_selecionada == "Gerenciar Colaboradores":
            st.subheader("👥 Gerenciar Colaboradores")
            col1, col2 = st.columns([0.6, 0.4])
            with col1:
                st.write("**Colaboradores Atuais:**")
                st.dataframe(df_colaboradores, use_container_width=True, hide_index=True)
            with col2:
                st.write("**Adicionar novo(a) colaborador(a):**")
                novo_nome = st.text_input("Nome").strip()
                if st.button("Adicionar Colaborador(a)"):
                    if novo_nome and (df_colaboradores.empty or novo_nome not in df_colaboradores["nome"].values):
                        if adicionar_colaborador(novo_nome):
                            st.cache_data.clear()
                            st.success(f"'{novo_nome}' adicionado(a) com sucesso!")
                            st.rerun()
                    else:
                        st.error("Nome inválido ou já existente.")
                
                st.write("**Remover colaborador(a):**")
                if not df_colaboradores.empty:
                    nomes_para_remover = st.multiselect("Selecione para remover", options=df_colaboradores["nome"].tolist())
                    if st.button("Remover Selecionados", type="secondary"):
                        if nomes_para_remover:
                            if remover_colaboradores(nomes_para_remover):
                                st.cache_data.clear()
                                st.success("Colaboradores removidos com sucesso!")
                                st.rerun()

# --- RODAPÉ ---
st.markdown("---")
st.markdown(
    """
    <p style='text-align: center; color: grey;'>
        Desenvolvido por @Rogério Souza
    </p>
    """,
    unsafe_allow_html=True
)