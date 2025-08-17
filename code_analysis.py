# ============================================================
# Análises BRASFI — Gráficos (barras, pizza) e Wordcloud PT-BR
# ============================================================
# Requisitos: pandas, matplotlib, seaborn, wordcloud, openpyxl
# Ambiente: RStudio Cloud com reticulate

import os, re, math, textwrap, unicodedata
import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
from wordcloud import WordCloud, STOPWORDS

# ---------- Aparência ----------
mpl.rcParams["font.family"] = "DejaVu Sans"  # bom suporte a acentos
plt.style.use("seaborn-v0_8")

# ---------- Paleta ----------
AVOCADO = ["#568203", "#6B8E23", "#A9BA9D", "#B2D3C2", "#D0F0C0"]
def get_palette(n):
    if n <= len(AVOCADO):
        return AVOCADO[:n]
    return sns.color_palette("Greens", n)

# ---------- Helpers básicos ----------
def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))

def clean_col(c):
    return re.sub(r"\s+", " ", str(c)).strip()

def strip_accents(s: str) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return s
    s = str(s)
    # Remove marcas de acento via unicodedata (sem dependências externas)
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")

# ---------- Leitura do arquivo ----------
file_path = "/cloud/project/survey_data.xlsx"
df_raw = pd.read_excel(file_path, sheet_name="Respostas ao formulário 1", engine="openpyxl")

# Remove 1ª (timestamp) e última (P.I.I.)
df = df_raw.iloc[:, 1:-1].copy()
df.columns = [clean_col(c) for c in df.columns]

# === PATCH (ATUALIZADO): agrupar respostas negativas em "Não" e positivas em "Sim" ===
import unicodedata
import pandas as pd
import numpy as np

def strip_accents(s: str) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return s
    s = str(s)
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")

# Prefixo da pergunta (localiza a coluna após clean_col)
ALINH_PREFIX = "Você sente que existe alinhamento entre suas entregas para a BRASFI e o retorno que você esperava"
alin_cols = [c for c in df.columns if c.startswith(ALINH_PREFIX)]

if alin_cols:
    alin_col = alin_cols[0]

    # Série normalizada para matching (minúsculas + sem acentos)
    s_norm = df[alin_col].astype(str).str.lower().map(strip_accents)

    # ---- Negativos a agrupar em "Não" ----
    mask_nao_1 = s_norm.str.contains("sinto que o retorno nao esta alinhado", na=False)
    mask_nao_2 = s_norm.str.contains("sinto que entreguei mais do que obtive", na=False)

    # ---- Positivos a agrupar em "Sim" ----
    mask_sim_plain  = s_norm.str.strip().eq("sim")  # "Sim"
    mask_sim_justa  = s_norm.str.contains("sinto que e uma troca justa", na=False)  # "Sim, sinto que é uma troca justa"

    # Contagem antes/depois (para conferência)
    before = df[alin_col].value_counts(dropna=False)

    # Aplica recodificação
    df.loc[mask_nao_1 | mask_nao_2, alin_col] = "Não"
    df.loc[mask_sim_plain | mask_sim_justa, alin_col] = "Sim"

    after = df[alin_col].value_counts(dropna=False)

    print("\n[Recodificação — Alinhamento]")
    print("Antes:\n", before)
    print("\nDepois:\n", after)
else:
    print("Aviso: não encontrei a coluna da pergunta de alinhamento. Verifique o cabeçalho.")


# ---------- Pastas de saída ----------
os.makedirs("charts", exist_ok=True)
os.makedirs("wordclouds", exist_ok=True)
os.makedirs("legends", exist_ok=True)

# ---------- Detecção de múltipla seleção ----------
def is_multiselect(series: pd.Series) -> bool:
    s = series.dropna().astype(str)
    if s.empty:
        return False
    # presença de vírgula ou ponto e vírgula em parte relevante das respostas
    return (s.str.contains(r",|;")).mean() >= 0.15

def expand_multiselect(series: pd.Series, pattern=r"\s*,\s*|\s*;\s*") -> pd.Series:
    s = series.dropna().astype(str)
    s = s.str.split(pattern).explode().str.strip()
    return s[s != ""]

# ---------- Classificador de tipo de pergunta ----------
def classify_question(series: pd.Series, open_text_hints=None):
    s = series.dropna().astype(str)
    if open_text_hints and series.name in open_text_hints:
        return "open"
    n_unique = s.nunique()
    avg_len = s.str.len().mean() if not s.empty else 0
    unique_ratio = n_unique / max(len(s), 1)
    if n_unique >= 30 or unique_ratio > 0.8:
        return "open"
    if n_unique <= 30 and (avg_len >= 30):
        return "long_categorical"
    return "categorical"

# ---------- Barras horizontais com códigos numéricos ----------
def barh_numeric(series: pd.Series, title: str, filename_prefix: str, order="frequency"):
    s = series.dropna().astype(str)
    counts = s.value_counts(dropna=False)
    if counts.sum() == 0:
        return None

    if order == "frequency":
        labels = list(counts.index)  # já em ordem de frequência (desc)
    else:
        labels = sorted(counts.index, key=lambda x: str(x))

    codes = list(range(1, len(labels) + 1))
    label_map = {lab: code for lab, code in zip(labels, codes)}

    plot_df = pd.DataFrame({
        "code": [label_map[lab] for lab in labels],
        "label": labels,
        "count": [counts[lab] for lab in labels]
    }).sort_values("count", ascending=True)

    plt.figure(figsize=(10, max(4, 0.45 * len(plot_df))))
    palette = get_palette(len(plot_df))
    bars = plt.barh(plot_df["code"], plot_df["count"], color=palette)
    plt.yticks(plot_df["code"], plot_df["code"])
    plt.xlabel("Frequência")
    plt.ylabel("Código da categoria")
    plt.title(title, loc="left", wrap=True)

    maxv = plot_df["count"].max()
    for bar, val in zip(bars, plot_df["count"]):
        plt.text(bar.get_width() + maxv*0.01, bar.get_y() + bar.get_height()/2,
                 f"{val}", va="center", fontsize=9)

    plt.tight_layout()
    out_chart = os.path.join("charts", f"{filename_prefix}_barh_numeric.png")
    plt.savefig(out_chart, dpi=200, bbox_inches="tight")
    plt.close()

    # Legendas: TXT, CSV e PNG (tabela)
    legend_txt = os.path.join("legends", f"{filename_prefix}_legend.txt")
    legend_csv = os.path.join("legends", f"{filename_prefix}_legend.csv")
    with open(legend_txt, "w", encoding="utf-8") as f:
        f.write(f"Legenda — {title}\n\n")
        for lab in labels:
            f.write(f"{label_map[lab]}: {lab}\n")
    pd.DataFrame({"code": codes, "label": labels}).to_csv(legend_csv, index=False, encoding="utf-8")

    fig, ax = plt.subplots(figsize=(10, max(1.2, 0.38 * len(labels))))
    ax.axis("off")
    table_data = [[label_map[lab], lab] for lab in labels]
    table = ax.table(cellText=table_data, colLabels=["Código", "Categoria"], loc="center", cellLoc="left", colLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.2)
    legend_img = os.path.join("legends", f"{filename_prefix}_legend.png")
    plt.title(f"Legenda — {title}", loc="left")
    plt.savefig(legend_img, dpi=200, bbox_inches="tight")
    plt.close()

    return {"chart": out_chart, "legend_txt": legend_txt, "legend_csv": legend_csv, "legend_img": legend_img}

# ---------- Pizza com "% (n=contagem)" e "Outros" ----------
def pie_with_counts(series: pd.Series, title: str, filename_prefix: str, min_pct_other: float = 0.03):
    s = series.dropna().astype(str)
    counts = s.value_counts()
    total = int(counts.sum())
    if total == 0:
        return None

    if min_pct_other and 0 < min_pct_other < 1:
        pct = counts / total
        small = pct[pct < min_pct_other]
        if not small.empty:
            counts = counts[pct >= min_pct_other]
            counts.loc["Outros"] = small.sum()

    labels = list(counts.index)
    values = list(counts.values)
    palette = get_palette(len(values))

    def autopct_fmt(pct):
        n = int(round(pct/100.0 * total))
        return f"{pct:.1f}% (n={n})" if n > 0 else ""

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(values, startangle=140, colors=palette,
                                      autopct=autopct_fmt, wedgeprops=dict(edgecolor="white"))
    ax.set_title(title, loc="left")
    legend_labels = [f"{lab} (n={val})" for lab, val in zip(labels, values)]
    ax.legend(wedges, legend_labels, title="Categorias", loc="center left", bbox_to_anchor=(1, 0.5))
    ax.axis("equal")
    plt.tight_layout()
    out_path = os.path.join("charts", f"{filename_prefix}_pie.png")
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    return out_path

# ---------- Stopwords PT-BR (com variações sem acento) ----------
def build_pt_stopwords(extra=None):
    sw = set(STOPWORDS)
    # Tenta incluir NLTK (se disponível no ambiente)
    try:
        import nltk
        try:
            nltk.data.find("corpora/stopwords")
        except LookupError:
            try:
                nltk.download("stopwords", quiet=True)
            except Exception:
                pass
        from nltk.corpus import stopwords as nltk_sw
        sw.update(nltk_sw.words("portuguese"))
    except Exception:
        pass

    # Lista customizada (baseada na sua)
    custom = {
        "a","à","acho","acredito","ajudar","algo","algum","alguns","além","ao","aos","após","as",
        "atividade","até","bem","brasfi","cada","como","consigo","cop30","da","das","de","do","dos",
        "e","em","entanto","entre","essa","essas","esse","esses","esta","estao","estas","estou","estão",
        "etc","eu","fazendo","gt","ir","isso","isto","já","maior","mais","mas","meio","menor","menos",
        "meu","mim","minha","minhas","momento","muito","na","nada","nas","neste","no","no entanto","nos",
        "nossa","nossas","não","o","os","ou","para","participar","pela","pelas","pelos","poderia","pois",
        "por","porque","porém","posso","pra","pouco","quais","que","quem","queria","s2","se","ser","sei",
        "seria","sinto","sobre","são","só","tem","tenho","ter","todos","tudo","um","uma","umas","uns",
        "usar","vezes","vi","vir","vivi","vocês","é","uso","faz"
    }
    sw.update(custom)

    # Adicionar formas sem acento para capturar digitações variadas
    sw_noacc = {strip_accents(x) for x in sw}
    sw.update(sw_noacc)

    if extra:
        extra_norm = {e.lower().strip() for e in extra}
        sw.update(extra_norm)
        sw.update({strip_accents(e) for e in extra_norm})

    return sw

# ---------- Wordcloud ----------
def wordcloud_pt(text_series: pd.Series, title: str, filename_prefix: str,
                 extra_stopwords=None, width=1000, height=500):
    s = text_series.dropna().astype(str)
    if s.empty:
        return None
    text = " ".join(s.tolist())
    # Limpeza leve
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()

    sw = build_pt_stopwords(extra_stopwords)

    wc = WordCloud(width=width, height=height, background_color="white",
                   stopwords=sw, collocations=False, prefer_horizontal=0.95,
                   colormap="summer").generate(text)

    plt.figure(figsize=(12, 6))
    plt.imshow(wc, interpolation="bilinear")
    plt.axis("off")
    plt.title(title, loc="left")
    out_path = os.path.join("wordclouds", f"{filename_prefix}_wordcloud.png")
    plt.tight_layout()
    plt.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close()
    return out_path

# ---------- Pipeline ----------
OPEN_TEXT_HINTS = {
    "O que normalmente te impede de participar das atividades da BRASFI?",
    "O que mais te motivaria a participar ativamente da BRASFI?",
    "O que podemos ajustar para facilitar sua participação e engajamento? (Você pode selecionar mais de uma opção)",
    "Qual tema ou formato de atividade te interessaria mais neste momento?",
    "Se você pudesse mudar algo na BRASFI com um estalar de dedos, o que seria?",
    "De que forma você poderia ajudar a potencializar a BRASFI? (Você pode selecionar mais de uma opção)"
}

for col in df.columns:
    series = df[col]
    col_clean = clean_col(col)
    fname = sanitize_filename(col_clean)

    # Explode se for múltipla seleção
    s = expand_multiselect(series) if is_multiselect(series) else series

    # Classificar a pergunta
    qtype = classify_question(s, open_text_hints=OPEN_TEXT_HINTS)

    if qtype == "open":
        # Wordcloud
        wordcloud_pt(s, title=col_clean, filename_prefix=fname)
    else:
        # Pizza com % + n (agrega <3% em "Outros")
        pie_with_counts(s, title=col_clean, filename_prefix=fname, min_pct_other=0.03)

        # Barras: se rótulos longos, usa codificação numérica + legenda
        if qtype == "long_categorical":
            barh_numeric(s, title=col_clean, filename_prefix=fname, order="frequency")
        else:
            # Barras tradicionais (referência visual)
            counts = s.dropna().astype(str).value_counts()
            if counts.sum() > 0:
                plt.figure(figsize=(10, max(4, 0.45 * len(counts))))
                sns.barplot(x=counts.values, y=counts.index, color=AVOCADO[0])
                plt.xlabel("Frequência")
                plt.ylabel("Categoria")
                plt.title(col_clean, loc="left")
                maxv = counts.max()
                for i, v in enumerate(counts.values):
                    plt.text(v + maxv*0.01, i, str(v), va="center", fontsize=9)
                plt.tight_layout()
                plt.savefig(os.path.join("charts", f"{fname}_barh.png"), dpi=200, bbox_inches="tight")
                plt.close()

print("✅ Concluído: gráficos em 'charts/', nuvens de palavras em 'wordclouds/' e legendas em 'legends/'.")
