import streamlit as st
import pdfplumber
import re
import io
from collections import Counter, defaultdict

# Configuração da página
st.set_page_config(page_title="FIVA 13.0 - Extrator de Dadores", layout="wide")

st.title("FIVA 13.0 - Extrator de Dadores")
st.markdown("""
Esta aplicação extrai emails e dados de dadores a partir de ficheiros PDF, 
ordenando-os sequencialmente e corrigindo erros comuns.
""")

# ============================================================================
# VARIÁVEL GLOBAL (State)
# ============================================================================
if 'log_correcoes' not in st.session_state:
    st.session_state.log_correcoes = []

# ============================================================================
# 1. FUNÇÕES DE LIMPEZA E CORREÇÃO
# ============================================================================

def limpar_lixo_final_pt(email):
    """Corta o email APÓS a extensão válida."""
    if not email: return ""

    extensoes_validas = [
        '.mail.telepac.pt', '.telepac.pt', '.yahoo.pt', '.sapo.pt', '.iol.pt',
        '.netcabo.pt', '.clix.pt', '.vodafone.pt', '.nos.pt', '.mail.pt',
        '.com.pt', '.org.pt', '.gov.pt', '.edu.pt', '.net.pt', '.int.pt',
        '.protonmail.com', '.icloud.com', '.outlook.com', '.hotmail.com',
        '.live.com', '.gmail.com', '.me.com', '.yahoo.com',
        '.pt', '.com', '.net', '.org', '.eu', '.br', '.fr', '.es', '.uk', '.co.uk'
    ]

    email_lower = email.lower()
    corte_realizado = False

    for ext in extensoes_validas:
        idx = email_lower.find(ext)
        if idx != -1:
            fim_extensao = idx + len(ext)
            if len(email) > fim_extensao:
                email = email[:fim_extensao]
                corte_realizado = True
            break

    if not corte_realizado and "@" in email:
        if email.endswith(".con"): email = email[:-1] + "m"
        elif email.endswith(".c"): email = email + "om"
        elif email.endswith(".co") and not email.endswith(".co.uk"): email = email + "m"
        elif email.endswith("..com"): email = email.replace("..com", ".com")

    return email

def limpar_prefixos(email):
    """Remove lixo no início."""
    if not email: return ""

    email = re.sub(r'^(Email|Ultima|Dador|Nome|Data|Conclusao|TRCL)', '', email, flags=re.IGNORECASE)

    mudou = True
    while mudou:
        mudou = False
        old = email
        email = re.sub(r'^[\d/\.-]+', '', email)
        email = re.sub(r'^(APTO|SUSPENSO|ELIMINADO)+', '', email, flags=re.IGNORECASE)
        if email != old: mudou = True

    match_nome = re.search(r'^([A-ZÇÁÉÍÓÚÀÃÕÊÔ\s]{2,})([a-z].*@)', email)
    if match_nome: email = match_nome.group(2)

    return email

def corrigir_dominio_pt(email):
    """Correção de domínios específicos."""
    if not email or "@" not in email: return email

    email = email.replace(" ", "")
    try:
        user, domain = email.split('@', 1)
    except: return email

    correcoes = {
        r'^gmal\.': 'gmail.', r'^gmil\.': 'gmail.', r'^gmial\.': 'gmail.', r'^gail\.': 'gmail.',
        r'^hotmai\.': 'hotmail.', r'^hotml\.': 'hotmail.', r'^otmail\.': 'hotmail.',
        r'^ouclood\.': 'outlook.', r'^outlok\.': 'outlook.', r'^outloock\.': 'outlook.',
        r'^yaho\.': 'yahoo.',
        r'^sapo\.com': 'sapo.pt', r'^sapo$': 'sapo.pt',
        r'^netcabo\.com': 'netcabo.pt', r'^netcabo$': 'netcabo.pt',
        r'^iol\.com': 'iol.pt', r'^telepac\.com': 'telepac.pt',
        r'^vodafone\.com$': 'vodafone.pt', r'^nos\.com$': 'nos.pt'
    }

    for pat, repl in correcoes.items():
        if re.search(pat, domain):
            domain = re.sub(pat, repl, domain)
            break

    return f"{user}@{domain}"

# ============================================================================
# 2. MOTOR DE EXTRAÇÃO
# ============================================================================

def processar_bloco(linhas, page_num):
    texto = " ".join(linhas)

    # ID
    match_id = re.search(r"^(S[PC]\.|S\.|SP\s\.|SC\s\.)[A-Z0-9\.]+\d+/\d+", linhas[0])
    id_dador = match_id.group(0) if match_id else "Desc"

    # STATUS (Posicional)
    u_text = texto.upper()
    posicoes = {}
    if "APTO" in u_text: posicoes["APTO"] = u_text.find("APTO")
    if "SUSPENSO" in u_text: posicoes["SUSPENSO"] = u_text.find("SUSPENSO")
    if "ELIMINADO" in u_text: posicoes["ELIMINADO"] = u_text.find("ELIMINADO")

    status = min(posicoes, key=posicoes.get) if posicoes else "DESCONHECIDO"

    # EMAIL
    email_raw = ""
    match_email = re.search(r"[\w\.-]+@[\w\.-]+\.[a-z]{2,10}", texto, re.IGNORECASE)

    if match_email:
        email_raw = match_email.group(0)
    else:
        txt_ns = texto.replace(" ", "")
        match_ns = re.search(r"[\w\.-]+@[\w\.-]+\.[a-z]{2,10}", txt_ns, re.IGNORECASE)
        if match_ns: email_raw = match_ns.group(0)

    # Limpeza e Registo de Correções
    email_final = ""
    if email_raw:
        # Pipeline de limpeza
        e_step1 = limpar_prefixos(email_raw)
        e_step2 = corrigir_dominio_pt(e_step1)
        e_step3 = limpar_lixo_final_pt(e_step2)
        email_final = e_step3

        if email_final != email_raw.replace(" ", ""):
            st.session_state.log_correcoes.append({
                'id': id_dador,
                'pag': page_num,
                'orig': email_raw,
                'final': email_final
            })

    # Nome
    nome = "Nome N/D"
    if match_id:
        resto = texto[match_id.end():].strip()
        split_pts = [x.start() for x in re.finditer(r"(\d{2}/\d{2}|[\w\.-]+@|APTO|SUSP|ELIM)", resto)]
        if split_pts: nome = resto[:min(split_pts)].strip()
        else: nome = resto[:40].strip()

    return {
        "ID": id_dador, "Nome": nome, "Status": status,
        "Email": email_final, "Pagina": page_num
    }

def extrair_dados(pdf_file):
    st.session_state.log_correcoes = []
    dadores = []
    buffer = []
    regex_id = re.compile(r"^(S[PC]\.|S\.|SP\s\.|SC\s\.)[A-Z0-9\.]+\d+/\d+")

    with pdfplumber.open(pdf_file) as pdf:
        total_pages = len(pdf.pages)
        progress_bar = st.progress(0)
        
        for i, page in enumerate(pdf.pages):
            progress_bar.progress((i + 1) / total_pages)
            text = page.extract_text()
            if not text: continue
            lines = text.split('\n')

            for line in lines:
                line = line.strip()
                if not line: continue

                if regex_id.match(line):
                    if buffer:
                        dadores.append(processar_bloco(buffer, page.page_number))
                    buffer = [line]
                else:
                    if buffer: buffer.append(line)

            if buffer:
                dadores.append(processar_bloco(buffer, page.page_number))
                buffer = []
                
    return dadores

# ============================================================================
# 3. RELATÓRIO
# ============================================================================
def gerar_relatorio_str(dadores):
    output = io.StringIO()
    
    # 1. Deduplicação e Organização
    historico = defaultdict(list)
    for d in dadores:
        historico[d['ID']].append(d)

    # 'unicos' mantém a ordem de inserção do dicionário
    unicos = [lista[-1] for lista in historico.values()]

    ids_com_duplicados = [k for k, v in historico.items() if len(v) > 1]

    # 2. Separação por Status
    aptos = [d for d in unicos if d['Status'] == "APTO"]
    susp = [d for d in unicos if d['Status'] == "SUSPENSO"]
    elim = [d for d in unicos if d['Status'] == "ELIMINADO"]

    # 3. Função para extrair emails preservando ordem
    def extrair_emails_ordenados(lista_dadores):
        emails_vistos = set()
        lista_final = []
        for d in lista_dadores:
            email = d['Email']
            if email and email not in emails_vistos:
                emails_vistos.add(email)
                lista_final.append(email)
        return lista_final

    e_aptos = extrair_emails_ordenados(aptos)
    e_susp = extrair_emails_ordenados(susp)
    e_elim = extrair_emails_ordenados(elim)

    total_emails = len(e_aptos) + len(e_susp) + len(e_elim)
    total_uni = len(unicos)

    output.write("RELATÓRIO FINAL DE DADORES - FIVA 13.0 (SEQUENTIAL)\n")
    output.write("==================================================\n\n")

    # ESTATÍSTICAS
    output.write("1. ESTATÍSTICAS GERAIS\n")
    output.write("-" * 50 + "\n")
    output.write(f"Total de Registos (Linhas no PDF): {len(dadores)}\n")
    output.write(f"Total de Dadores (Pessoas Reais): {total_uni}\n")
    output.write(f"Total de Emails Válidos para Envio: {total_emails}\n")
    if total_uni > 0:
        output.write(f"Taxa de Cobertura de Email: {(total_emails/total_uni)*100:.1f}%\n\n")

    def pct(val, tot): return (val/tot)*100 if tot else 0

    output.write(f"-> APTOS: {len(aptos)} ({pct(len(aptos), total_uni):.1f}%)\n")
    output.write(f"   Emails prontos a enviar: {len(e_aptos)}\n")

    output.write(f"-> SUSPENSOS: {len(susp)} ({pct(len(susp), total_uni):.1f}%)\n")
    output.write(f"   Emails prontos a enviar: {len(e_susp)}\n")

    output.write(f"-> ELIMINADOS: {len(elim)} ({pct(len(elim), total_uni):.1f}%)\n")
    output.write(f"   Emails prontos a enviar: {len(e_elim)}\n")

    # LISTAS DE ENVIO (SEQUENCIAIS)
    output.write("\n" + "="*50 + "\n")
    output.write("2. LISTAS DE EMAILS (Ordenados por Página)\n")
    output.write("-" * 50 + "\n")

    output.write(f"[APTOS] ({len(e_aptos)})\n"); output.write("; ".join(e_aptos) + "\n\n")
    output.write(f"[SUSPENSOS] ({len(e_susp)})\n"); output.write("; ".join(e_susp) + "\n\n")
    output.write(f"[ELIMINADOS] ({len(e_elim)})\n"); output.write("; ".join(e_elim) + "\n\n")

    # AUDITORIA DE DUPLICADOS
    output.write("="*50 + "\n")
    output.write(f"3. IDENTIFICAÇÃO DE DUPLICADOS ({len(ids_com_duplicados)} casos)\n")
    output.write("-" * 50 + "\n")

    if ids_com_duplicados:
        for id_d in sorted(ids_com_duplicados):
            output.write(f"\nID: {id_d}\n")
            lista = historico[id_d]
            for i, reg in enumerate(lista, 1):
                usado = " [USADO]" if i == len(lista) else " [IGNORADO]"
                output.write(f"   {i}ª vez (Pág {reg['Pagina']}): {reg['Status']} - {reg['Email']}{usado}\n")
    else:
        output.write("Nenhum duplicado detetado.\n")

    # AUDITORIA DE CORREÇÕES TÉCNICAS
    output.write("\n" + "="*50 + "\n")
    output.write(f"4. AUDITORIA DE CORREÇÕES TÉCNICAS ({len(st.session_state.log_correcoes)} intervenções)\n")
    output.write("-" * 50 + "\n")

    if st.session_state.log_correcoes:
        for item in st.session_state.log_correcoes:
            output.write(f"Pág {item['pag']} | ID {item['id']}\n")
            output.write(f"   Original: {item['orig']}\n")
            output.write(f"   Corrigido: {item['final']}\n")
            output.write("-" * 20 + "\n")
    else:
        output.write("Nenhuma correção técnica complexa foi necessária.\n")
        
    return output.getvalue()

# ============================================================================
# INTERFACE PRINCIPAL
# ============================================================================

uploaded_file = st.file_uploader("Carregue o seu ficheiro PDF", type="pdf")

if uploaded_file is not None:
    if st.button("Processar PDF"):
        with st.spinner("A processar e a corrigir dados..."):
            try:
                dados_extraidos = extrair_dados(uploaded_file)
                relatorio = gerar_relatorio_str(dados_extraidos)
                
                st.success("Processamento concluído com sucesso!")
                
                # Botão de Download
                st.download_button(
                    label="📥 Descarregar Relatório Final (TXT)",
                    data=relatorio,
                    file_name="FIVA_Relatorio_Final_V13.txt",
                    mime="text/plain"
                )
                
                # Preview simples das estatísticas no ecrã
                st.subheader("Pré-visualização do Relatório")
                st.text_area("Conteúdo do Relatório:", relatorio, height=400)
                
            except Exception as e:
                st.error(f"Ocorreu um erro ao processar o ficheiro: {e}")
