# ============================================================
# Análises BRASFI — Gráficos (barras, pizza) e Wordcloud PT-BR
# ============================================================
# Requisitos: pandas, matplotlib, seaborn, wordcloud, openpyxl

import os, re, math, textwrap, unicodedata
import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns
from cycler import cycler
from wordcloud import WordCloud, STOPWORDS

# ----------------- Aparência (fonte, dpi, grelha) -----------------
sns.set_theme(style="whitegrid", context="talk")
mpl.rcParams.update({
    "font.family": "DejaVu Sans",   # bom suporte a acentos
    "figure.dpi": 120,              # DPI de visualização
    "savefig.dpi": 400,             # DPI de exportação (↑ resolução)
    "axes.titlesize": 18,
    "axes.titleweight": 600,
    "axes.labelsize": 14,
    "xtick.labelsize": 12,
    "ytick.labelsize": 12,
    "legend.fontsize": 12,
    "axes.edgecolor": "#9E9E9E",
    "grid.color": "#DADADA",
    "grid.alpha": 0.6,
})

# ----------------- Paleta (verdes, amarelos, cinzas; sem azul) -----------------
GREENS  = ["#1B5E20", "#2E7D32", "#388E3C", "#43A047", "#66BB6A"]
YELLOWS = ["#F9A825", "#FBC02D", "#FDD835"]
GREYS   = ["#616161", "#9E9E9E", "#BDBDBD", "#E0E0E0"]
COLOR_OTHER = "#9E9E9E"

# Define ciclo de cores padrão sem azuis
mpl.rcParams["axes.prop_cycle"] = cycler(color=(GREENS + YELLOWS + GREYS))

def get_palette(n, prefer="greens", include_yellow=True):
    base = (GREENS if prefer=="greens" else GREENS)[:]  # sempre verdes como base
    if include_yellow:
        base = base + YELLOWS
    base = base + GREYS
    if n <= len(base):
        return base[:n]
    # Repete ciclo se n > len(base), mantendo padrão sem azul
    reps = (n + len(base) - 1) // len(base)
    return (base * reps)[:n]

# ----------------- Helpers -----------------
def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(name))

def clean_col(c):
    return re.sub(r"\s+", " ", str(c)).strip()

def strip_accents(s: str) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return s
    s = str(s)
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")

def wrap_title(t, width=72):
    return textwrap.fill(str(t), width)

def auto_text_color(bg_hex: str) -> str:
    """Define cor do rótulo (preto/branco) pelo contraste com a cor de fundo."""
    bg_hex = bg_hex.strip("#")
    r, g, b = tuple(int(bg_hex[i:i+2], 16) for i in (0, 2, 4))
    # luminância relativa simples
    lum = (0.2126*r + 0.7152*g + 0.0722*b)/255.0
    return "#000000" if lum > 0.6 else "#FFFFFF"

def format_pct(x, total):
    if total == 0: return "0,00%"
    return f"{(100.0*x/total):.2f}%".replace(".", ",")

# ----------------- Leitura do arquivo -----------------
file_path = "/cloud/project/survey_data.xlsx"
df_raw = pd.read_excel(file_path, sheet_name="Respostas ao formulário 1", engine="openpyxl")
# Remove 1ª (timestamp) e última (P.I.I.)
df = df_raw.iloc[:, 1:-1].copy()
df.columns = [clean_col(c) for c in df.columns]

# === PATCH (ATUALIZADO): recodificação da pergunta de alinhamento ===
ALINH_PREFIX = "Você sente que existe alinhamento entre suas entregas para a BRASFI e o retorno que você esperava"
alin_cols = [c for c in df.columns if c.startswith(ALINH_PREFIX)]
if alin_cols:
    alin_col = alin_cols[0]
    s_norm = df[alin_col].astype(str).str.lower().map(strip_accents)
    mask_nao_1   = s_norm.str.contains("sinto que o retorno nao esta alinhado", na=False)
    mask_nao_2   = s_norm.str.contains("sinto que entreguei mais do que obtive", na=False)
    mask_sim_1   = s_norm.str.strip().eq("sim")
    mask_sim_2   = s_norm.str.contains("sinto que e uma troca justa", na=False)
    before = df[alin_col].value_counts(dropna=False)
    df.loc[mask_nao_1 | mask_nao_2, alin_col] = "Não"
    df.loc[mask_sim_1 | mask_sim_2, alin_col] = "Sim"
    after = df[alin_col].value_counts(dropna=False)
    print("\n[Recodificação — Alinhamento]")
    print("Antes:\n", before)
    print("\nDepois:\n", after)
else:
    print("Aviso: não encontrei a coluna da pergunta de alinhamento. Verifique o cabeçalho.")

# ----------------- Pastas de saída -----------------
os.makedirs("charts", exist_ok=True)
os.makedirs("wordclouds", exist_ok=True)
os.makedirs("legends", exist_ok=True)

# ----------------- Múltipla seleção -----------------
def is_multiselect(series: pd.Series) -> bool:
    s = series.dropna().astype(str)
    if s.empty:
        return False
    return (s.str.contains(r",|;")).mean() >= 0.15

def expand_multiselect(series: pd.Series, pattern=r"\s*,\s*|\s*;\s*") -> pd.Series:
    s = series.dropna().astype(str)
    s = s.str.split(pattern).explode().str.strip()
    return s[s != ""]

# ----------------- Classificador de tipo de pergunta -----------------
def classify_question(series: pd.Series, open_text_hints=None):
    s = series.dropna().astype(str)
    if open_text_hints and series.name in open_text_hints:
        return "open"
    n_unique = s.nunique()
    avg_len  = s.str.len().mean() if not s.empty else 0
    unique_ratio = n_unique / max(len(s), 1)
    if n_unique >= 30 or unique_ratio > 0.8:
        return "open"
    if n_unique <= 30 and (avg_len >= 30):
        return "long_categorical"
    return "categorical"

# ----------------- Barras horizontais (com percentuais) -----------------
def barh_with_pct(series: pd.Series, title: str, filename_prefix: str,
                  numeric_codes: bool=False, order="frequency"):
    s = series.dropna().astype(str)
    counts = s.value_counts(dropna=False)
    total  = int(counts.sum())
    if total == 0:
        return None

    # Ordenação
    if order == "frequency":
        labels = list(counts.index)  # já em ordem desc.
    else:
        labels = sorted(counts.index, key=lambda x: str(x))

    # Preparação do dataframe de plotagem
    plot_df = pd.DataFrame({
        "label": labels,
        "count": [counts[lab] for lab in labels]
    })
    plot_df["pct"] = plot_df["count"] / total
    plot_df = plot_df.sort_values("count", ascending=True)

    # Códigos numéricos para categorias longas
    if numeric_codes:
        plot_df["code"] = range(1, len(plot_df)+1)
        y_ticks = plot_df["code"]
        y_ticklabels = plot_df["code"]
        legend_pairs = list(zip(plot_df["code"], plot_df["label"]))
    else:
        y_ticks = np.arange(len(plot_df))
        # Quebra de linha em rótulos longos para ocupar menos altura
        y_ticklabels = [textwrap.fill(lab, 48) for lab in plot_df["label"]]
        legend_pairs = None

    # Figura proporcional ao nº de categorias
    fig_h = max(4, 0.48 * len(plot_df))
    fig, ax = plt.subplots(figsize=(11, fig_h), constrained_layout=True)

    # Cores: "Outros" em cinza, demais em verdes; destaque top-1 em amarelo opcional
    colors = []
    for lab in plot_df["label"]:
        if strip_accents(str(lab)).lower() == "outros":
            colors.append(COLOR_OTHER)
        else:
            colors.append(GREENS[min(3, len(GREENS)-1)])  # verde forte por padrão
    # Se quiser variar por categoria com segurança, use get_palette:
    # colors = [COLOR_OTHER if strip_accents(str(l)).lower()=="outros" else get_palette(len(plot_df))[i]
    #           for i, l in enumerate(plot_df["label"])]

    ax.barh(y_ticks, plot_df["count"], color=colors, edgecolor="white")

    # Títulos e eixos
    ax.set_title(wrap_title(title), loc="left")
    ax.set_xlabel("Frequência")
    ax.set_yticks(y_ticks)
    ax.set_yticklabels(y_ticklabels)

    # Anotações: n (xx,xx%)
    maxv = plot_df["count"].max()
    for i, (cnt, pct) in enumerate(zip(plot_df["count"], plot_df["pct"])):
        label = f"{cnt} ({pct*100:0.2f}%)".replace(".", ",")
        # posição y:
        y_i = y_ticks.iloc[i] if isinstance(y_ticks, pd.Series) else y_ticks[i]
        # cor do texto baseada na cor da barra (melhor contraste)
        bg = colors[i]
        inside = cnt > 0.7 * maxv  # se barra muito longa, escreve por dentro
        txt_color = auto_text_color(bg) if inside else "#000000"
        x_pos = cnt - maxv*0.02 if inside else (cnt + maxv*0.012)
        ha = "right" if inside else "left"
        ax.text(x_pos, y_i, label, va="center", ha=ha, color=txt_color, fontsize=12)

    # Aparência
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_locator(mpl.ticker.MaxNLocator(integer=True))
    ax.grid(axis='x', linestyle=":", alpha=0.6)

    # Salvar
    out_png = os.path.join("charts", f"{filename_prefix}{'_barh_numeric' if numeric_codes else '_barh'}.png")
    out_svg = os.path.join("charts", f"{filename_prefix}{'_barh_numeric' if numeric_codes else '_barh'}.svg")
    plt.savefig(out_png, bbox_inches="tight")
    plt.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)

    # Se houver códigos numéricos, exporta legenda melhorada
    legend_assets = {}
    if numeric_codes and legend_pairs:
        legend_txt = os.path.join("legends", f"{filename_prefix}_legend.txt")
        legend_csv = os.path.join("legends", f"{filename_prefix}_legend.csv")
        with open(legend_txt, "w", encoding="utf-8") as f:
            f.write(f"Legenda — {title}\n\n")
            for code, lab in legend_pairs:
                f.write(f"{code}: {lab}\n")
        pd.DataFrame({"code": [c for c, _ in legend_pairs],
                      "label": [l for _, l in legend_pairs]}).to_csv(legend_csv, index=False, encoding="utf-8")

        # Tabela PNG com zebra
        fig_lg, ax_lg = plt.subplots(figsize=(11, max(1.2, 0.42 * len(legend_pairs))), constrained_layout=True)
        ax_lg.axis("off")
        table_data = [[c, l] for c, l in legend_pairs]
        table = ax_lg.table(cellText=table_data, colLabels=["Código", "Categoria"],
                            loc="center", cellLoc="left", colLoc="left")
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        table.scale(1, 1.25)
        # zebra
        for i in range(len(table_data)):
            color = "#F5F5F5" if i % 2 == 1 else "#FFFFFF"
            table[(i+1, 0)].set_facecolor(color)
            table[(i+1, 1)].set_facecolor(color)
        legend_img = os.path.join("legends", f"{filename_prefix}_legend.png")
        plt.title(f"Legenda — {title}", loc="left")
        plt.savefig(legend_img, bbox_inches="tight")
        plt.close(fig_lg)
        legend_assets = {"legend_txt": legend_txt, "legend_csv": legend_csv, "legend_img": legend_img}

    return {"chart_png": out_png, "chart_svg": out_svg, **legend_assets}

# ----------------- Pizza com % (n=…) e "Outros" -----------------
def pie_with_counts(series: pd.Series, title: str, filename_prefix: str,
                    min_pct_other: float = 0.03, ncol_legend: int = 1):
    s = series.dropna().astype(str)
    counts = s.value_counts()
    total = int(counts.sum())
    if total == 0:
        return None

    # Agrega "miúdos" em "Outros"
    if min_pct_other and 0 < min_pct_other < 1:
        pct = counts / total
        small = pct[pct < min_pct_other]
        if not small.empty:
            counts = counts[pct >= min_pct_other]
            counts.loc["Outros"] = int(small.sum())

    labels = list(counts.index)
    values = list(counts.values)
    # Ordena desc. para legenda mais clara
    pairs = sorted(zip(labels, values), key=lambda x: x[1], reverse=True)
    labels, values = zip(*pairs)

    # Paleta sem azul; "Outros" cinza
    colors = []
    for lab in labels:
        if strip_accents(str(lab)).lower() == "outros":
            colors.append(COLOR_OTHER)
        else:
            colors.append(get_palette(len(labels))[len(colors)])

    def autopct_fmt(pct):
        n = int(round(pct/100.0 * total))
        return f"{pct:.1f}%\n(n={n})" if n > 0 else ""

    fig, ax = plt.subplots(figsize=(8.8, 6.8), constrained_layout=True)
    wedges, texts, autotexts = ax.pie(
        values, startangle=130, colors=colors,
        autopct=autopct_fmt, pctdistance=0.7,
        wedgeprops=dict(edgecolor="white")
    )
    # Melhor contraste para o texto dentro das fatias
    for w, t in zip(wedges, autotexts):
        facecolor = mpl.colors.to_hex(w.get_facecolor())
        t.set_color(auto_text_color(facecolor))
        t.set_fontsize(12)
        t.set_weight(600)

    ax.set_title(wrap_title(title), loc="left")
    ax.axis("equal")

    # Legenda externa com % e n
    legend_labels = [f"{lab} — {format_pct(val, total)} (n={val})" for lab, val in zip(labels, values)]
    ax.legend(wedges, legend_labels, title="Categorias", loc="center left",
              bbox_to_anchor=(1, 0.5), ncol=ncol_legend, frameon=False)

    out_png = os.path.join("charts", f"{filename_prefix}_pie.png")
    out_svg = os.path.join("charts", f"{filename_prefix}_pie.svg")
    plt.savefig(out_png, bbox_inches="tight")
    plt.savefig(out_svg, bbox_inches="tight")
    plt.close(fig)
    return out_png

# ----------------- Stopwords PT-BR -----------------
def build_pt_stopwords(extra=None):
    sw = set(STOPWORDS)
    # Tenta incluir NLTK se disponível
    try:
        import nltk
        try:
            nltk.data.find("corpora/stopwords")
        except LookupError:
            try: nltk.download("stopwords", quiet=True)
            except Exception: pass
        from nltk.corpus import stopwords as nltk_sw
        sw.update(nltk_sw.words("portuguese"))
    except Exception:
        pass
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
    sw_noacc = {strip_accents(x) for x in sw}
    sw.update(sw_noacc)
    if extra:
        extra_norm = {e.lower().strip() for e in extra}
        sw.update(extra_norm)
        sw.update({strip_accents(e) for e in extra_norm})
    return sw

# ----------------- Wordcloud -----------------
def wordcloud_pt(text_series: pd.Series, title: str, filename_prefix: str,
                 extra_stopwords=None, width=1800, height=1000):
    s = text_series.dropna().astype(str)
    if s.empty:
        return None
    text = " ".join(s.tolist())
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    sw = build_pt_stopwords(extra_stopwords)
    wc = WordCloud(width=width, height=height, background_color="white",
                   stopwords=sw, collocations=False, prefer_horizontal=0.95,
                   colormap="summer").generate(text)  # verde→amarelo (sem azul)
    fig, ax = plt.subplots(figsize=(14, 8), constrained_layout=True)
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(wrap_title(title), loc="left")
    out_path = os.path.join("wordclouds", f"{filename_prefix}_wordcloud.png")
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return out_path

# ----------------- Pipeline -----------------
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
        # Para muitas categorias, use ncol_legend=2
        pie_with_counts(s, title=col_clean, filename_prefix=fname, min_pct_other=0.03, ncol_legend=1)

        # Barras: se rótulos longos, usa codificação numérica + legenda; senão, rótulo direto
        if qtype == "long_categorical":
            barh_with_pct(s, title=col_clean, filename_prefix=fname, numeric_codes=True, order="frequency")
        else:
            barh_with_pct(s, title=col_clean, filename_prefix=fname, numeric_codes=False, order="frequency")

print("✅ Concluído: gráficos em 'charts/' (PNG + SVG), nuvens de palavras em 'wordclouds/' e legendas em 'legends/'.")
