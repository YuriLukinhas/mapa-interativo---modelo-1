import colorsys
import json
import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from pyvis.network import Network


st.set_page_config(page_title="Grafo de Pré-requisitos", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
DISCIPLINAS_CSV = BASE_DIR / "disciplinas.csv"
CURSO_DISCIPLINA_CSV = BASE_DIR / "curso_disciplina.csv"
EXPRESSOES_CSV = BASE_DIR / "disciplinas_unidades_prerequisitos.csv"


@st.cache_data
def ler_csv(caminho):
    if not os.path.exists(caminho):
        return pd.DataFrame()

    return pd.read_csv(caminho, dtype=str, encoding="utf-8-sig").fillna("")


def forma_normal(expressao):
    """
    Converte E/OU em alternativas.

    (A E B) OU (A E C) -> [[A, B], [A, C]]
    Cada lista interna representa disciplinas que devem ser feitas juntas.
    """
    expressao = expressao.strip().upper()
    tokens = re.findall(r"\(|\)|\bOU\b|\bE\b|[A-Z]+\d+", expressao)

    if "".join(tokens) != re.sub(r"\s+", "", expressao):
        raise ValueError("caracteres não reconhecidos")

    pos = 0

    def ler_ou():
        nonlocal pos
        grupos = ler_e()

        while pos < len(tokens) and tokens[pos] == "OU":
            pos += 1
            grupos += ler_e()

        return grupos

    def ler_e():
        nonlocal pos
        grupos = ler_item()

        while pos < len(tokens) and tokens[pos] == "E":
            pos += 1
            direita = ler_item()
            grupos = [a | b for a in grupos for b in direita]

        return grupos

    def ler_item():
        nonlocal pos

        if pos >= len(tokens):
            raise ValueError("expressão incompleta")

        token = tokens[pos]
        pos += 1

        if token == "(":
            grupos = ler_ou()

            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError("parênteses não fechados")

            pos += 1
            return grupos

        if token in ("E", "OU", ")"):
            raise ValueError(f"token inesperado: {token}")

        return [frozenset([token])]

    grupos = set(ler_ou())

    if pos != len(tokens):
        raise ValueError("tokens não processados")

    # Se A já basta, a alternativa A + B é redundante.
    minimos = [
        grupo
        for grupo in grupos
        if not any(outro < grupo for outro in grupos)
    ]

    return [
        sorted(grupo)
        for grupo in sorted(minimos, key=lambda g: (len(g), sorted(g)))
    ]


@st.cache_data
def carregar_dados():
    disciplinas = ler_csv(DISCIPLINAS_CSV)
    curso_disciplina = ler_csv(CURSO_DISCIPLINA_CSV)
    expressoes = ler_csv(EXPRESSOES_CSV)

    if disciplinas.empty or not {"id", "nome"}.issubset(disciplinas.columns):
        st.error("Confira o arquivo disciplinas.csv e as colunas id e nome.")
        st.stop()

    colunas_expressoes = {
        "disciplina_id", "curso", "expressao_pre_requisitos"
    }

    if expressoes.empty or not colunas_expressoes.issubset(expressoes.columns):
        st.error(
            "Confira disciplinas_unidades_prerequisitos.csv e as colunas "
            "disciplina_id, curso e expressao_pre_requisitos."
        )
        st.stop()

    for tabela in (disciplinas, curso_disciplina, expressoes):
        for coluna in tabela.columns:
            tabela[coluna] = tabela[coluna].astype(str).str.strip()

    nomes = dict(zip(disciplinas["id"], disciplinas["nome"]))
    cargas = {}

    for _, linha in disciplinas.iterrows():
        try:
            cargas[linha["id"]] = float(
                linha.get("carga_horaria", "0") or 0
            )
        except ValueError:
            cargas[linha["id"]] = 0.0

    ofertas = {}

    if not curso_disciplina.empty:
        for coluna in ("disciplina_id", "curso", "tipo", "periodo"):
            if coluna not in curso_disciplina.columns:
                curso_disciplina[coluna] = ""

        for _, linha in curso_disciplina.iterrows():
            if linha["disciplina_id"]:
                ofertas.setdefault(linha["disciplina_id"], []).append({
                    "curso": linha["curso"],
                    "tipo": linha["tipo"],
                    "periodo": linha["periodo"],
                })

    exp_map = {}

    for _, linha in expressoes.iterrows():
        texto = linha["expressao_pre_requisitos"]

        if not texto:
            continue

        try:
            grupos = forma_normal(texto)
        except ValueError as erro:
            st.error(
                f"Expressão inválida em {linha['disciplina_id']} "
                f"({linha['curso']}): {erro}"
            )
            st.stop()

        exp_map[(linha["disciplina_id"], linha["curso"])] = {
            "texto": texto,
            "grupos": grupos,
        }

    return nomes, cargas, ofertas, exp_map


def cores_no(rgb):
    vermelho, verde, azul = rgb

    return (
        f"#{vermelho:02x}{verde:02x}{azul:02x}",
        f"rgba({vermelho}, {verde}, {azul}, 0.15)",
    )


def para_js(valor):
    # Evita que dados provenientes do CSV encerrem a tag <script>.
    return json.dumps(valor, ensure_ascii=False).replace("<", "\\u003c")


nomes, cargas, ofertas, exp_map = carregar_dados()

st.title("Visualizador de Pré-requisitos Acadêmicos")

cursos = sorted({
    item["curso"]
    for registros in ofertas.values()
    for item in registros
    if item["curso"]
})

for chave, padrao in (
    ("curso_sel", "-- Todos --"),
    ("nat_sel", "-- Todas --"),
    ("size_sel", "Fixo"),
    ("color_sel", "Padrão"),
):
    if chave not in st.session_state:
        st.session_state[chave] = padrao

with st.sidebar:
    st.header("⚙️ Filtros")

    curso = st.selectbox(
        "Curso:", ["-- Todos --"] + cursos, key="curso_sel"
    )

    periodo = "-- Todos --"

    if curso != "-- Todos --":
        periodos = {
            item["periodo"]
            for registros in ofertas.values()
            for item in registros
            if item["curso"] == curso and item["periodo"]
        }

        opcoes_periodos = (
            ["-- Todos --"]
            + sorted(
                periodos,
                key=lambda p: (0, int(p)) if p.isdigit() else (1, p),
            )
            + ["Sem período"]
        )

        if st.session_state.get("periodo_sel") not in opcoes_periodos:
            st.session_state.periodo_sel = "-- Todos --"

        periodo = st.selectbox(
            "Período:", opcoes_periodos, key="periodo_sel"
        )

    naturezas = sorted({
        item["tipo"]
        for registros in ofertas.values()
        for item in registros
        if item["tipo"]
        and (curso == "-- Todos --" or item["curso"] == curso)
    })

    opcoes_natureza = ["-- Todas --"] + naturezas

    if st.session_state.nat_sel not in opcoes_natureza:
        st.session_state.nat_sel = "-- Todas --"

    natureza = st.selectbox(
        "Natureza:", opcoes_natureza, key="nat_sel"
    )

    menor_carga = int(min(cargas.values())) if cargas else 0
    maior_carga = int(max(cargas.values())) if cargas else 120
    minimo_padrao = (menor_carga // 15) * 15
    maximo_padrao = ((maior_carga + 14) // 15) * 15

    coluna_min, coluna_max = st.columns(2)

    with coluna_min:
        min_ch = st.number_input(
            "Mín. CH:", min_value=0, max_value=maximo_padrao,
            value=minimo_padrao, step=15
        )

    with coluna_max:
        max_ch = st.number_input(
            "Máx. CH:", min_value=0, max_value=maximo_padrao,
            value=maximo_padrao, step=15
        )

    st.markdown("---")

    tamanho = st.selectbox(
        "Tamanho dos Nós:",
        ["Fixo", "Carga Horária", "Grau de Conexão"],
        key="size_sel",
    )

    coloracao = st.selectbox(
        "Colorir Nós por:",
        ["Padrão", "Carga Horária"],
        key="color_sel",
    )

    st.markdown("---")
    st.subheader("🔍 Buscar Disciplina")

    busca = st.text_input(
        "Digite o ID ou Nome:",
        placeholder="Ex: MAT101 ou Cálculo",
        key="busca_disc",
    )


# Aplica os filtros às disciplinas exibidas.
visiveis = set()

for disciplina in nomes:
    registros = ofertas.get(disciplina, [])

    if curso != "-- Todos --":
        registros = [r for r in registros if r["curso"] == curso]
        if not registros:
            continue

    if natureza != "-- Todas --":
        registros = [r for r in registros if r["tipo"] == natureza]
        if not registros:
            continue

    if periodo != "-- Todos --":
        registros = [
            r for r in registros
            if (
                r["periodo"] == ""
                if periodo == "Sem período"
                else r["periodo"] == periodo
            )
        ]

        if not registros:
            continue

    if min_ch <= cargas.get(disciplina, 0) <= max_ch:
        visiveis.add(disciplina)


# Cada pré-requisito gera uma seta simples.
# A distinção entre E e OU aparece apenas nos cartões do painel.
arestas = {}
fantasmas = set()
grau = {disciplina: 0 for disciplina in visiveis}
dados_js = {}
libera = {}

for disciplina in sorted(visiveis):
    if curso != "-- Todos --":
        cursos_alvo = [curso]
    else:
        cursos_alvo = sorted({
            r["curso"] for r in ofertas.get(disciplina, [])
            if r["curso"]
        })

    variantes = {}

    for curso_alvo in cursos_alvo:
        info = exp_map.get((disciplina, curso_alvo))

        if info:
            chave = tuple(tuple(grupo) for grupo in info["grupos"])
            variantes.setdefault(
                chave, {"texto": info["texto"], "cursos": []}
            )
            variantes[chave]["cursos"].append(curso_alvo)

    membros = set()
    prerequisitos = []

    for grupos, variante in variantes.items():
        for grupo in grupos:
            for membro in grupo:
                membros.add(membro)
                arestas.setdefault(
                    (membro, disciplina), set()
                ).update(variante["cursos"])
                libera.setdefault(membro, set()).add(disciplina)

        prerequisitos.append({
            "cursos": variante["cursos"],
            "texto": variante["texto"],
            "grupos": [list(grupo) for grupo in grupos],
        })

    grau[disciplina] += len(membros)

    for membro in membros:
        if membro in visiveis:
            grau[membro] += 1
        else:
            fantasmas.add(membro)

    dados_js[disciplina] = {
        "nome": nomes[disciplina],
        "ch": int(cargas.get(disciplina, 0)),
        "prereqs": prerequisitos,
    }

for fantasma in fantasmas:
    dados_js[fantasma] = {
        "nome": nomes.get(fantasma, "(não cadastrada)"),
        "ch": int(cargas.get(fantasma, 0)),
        "prereqs": [],
    }

for disciplina, dados in dados_js.items():
    dados["libera"] = sorted(
        destino
        for destino in libera.get(disciplina, set())
        if destino in visiveis
    )

st.write(
    f"Exibindo **{len(visiveis)}** disciplinas e "
    f"**{len(arestas)}** conexões."
)

st.markdown(
    "➡️ **Seta cinza:** pré-requisito → disciplina. "
    "👆 Clique numa disciplina para ver as opções no painel do grafo. "
    "Clique numa opção para destacar apenas aquele caminho. "
    "⚪ Nó cinza: pré-requisito fora do filtro ou não cadastrado."
)

if not visiveis:
    st.warning("Nenhuma disciplina corresponde aos filtros selecionados.")
    st.stop()


rede = Network(
    height="720px",
    width="100%",
    directed=True,
    bgcolor="#000000",
    cdn_resources="in_line",
)

rede.toggle_physics(True)

rede.set_options("""
{
  "physics": {
    "solver": "forceAtlas2Based",
    "forceAtlas2Based": {
      "gravitationalConstant": -100,
      "centralGravity": 0.005,
      "springLength": 140,
      "springConstant": 0.05,
      "damping": 0.3,
      "avoidOverlap": 0.8
    },
    "stabilization": {"enabled": true, "iterations": 100}
  },
  "edges": {
    "width": 1,
    "smooth": false,
    "arrows": {"to": {"enabled": true, "scaleFactor": 0.6}}
  }
}
""")

min_vis = min(cargas[d] for d in visiveis)
max_vis = max(cargas[d] for d in visiveis)
cores_js = {}

for disciplina in sorted(visiveis):
    nome = nomes[disciplina]
    ch = cargas.get(disciplina, 0)

    if tamanho == "Carga Horária":
        proporcao = (
            (ch - min_vis) / (max_vis - min_vis)
            if max_vis != min_vis else 0.5
        )
        tamanho_no = int(10 + proporcao * 90)
    elif tamanho == "Grau de Conexão":
        tamanho_no = 15 + grau[disciplina] * 8
    else:
        tamanho_no = 25

    if coloracao == "Carga Horária" and max_vis != min_vis:
        proporcao = (ch - min_vis) / (max_vis - min_vis)
        matiz = (120 - proporcao * 120) / 360
        componentes = colorsys.hls_to_rgb(matiz, 0.50, 0.85)
        rgb = tuple(int(c * 255) for c in componentes)
    else:
        rgb = (15, 82, 186)

    cor, cor_apagada = cores_no(rgb)
    cores_js[disciplina] = [cor, cor_apagada]

    cursos_no = (
        [curso]
        if curso != "-- Todos --"
        else sorted({
            r["curso"] for r in ofertas.get(disciplina, [])
            if r["curso"]
        })
    )

    rede.add_node(
        disciplina,
        label=f"{disciplina}\n{nome[:15]}...",
        title=(
            f"{disciplina} — {nome}\n"
            f"Carga horária: {int(ch)}h\n"
            f"Cursos: {', '.join(cursos_no) or '-'}\n\n"
            "Clique para ver as opções de pré-requisito."
        ),
        size=tamanho_no,
        color=cor,
    )

for fantasma in sorted(fantasmas):
    cor, cor_apagada = cores_no((107, 114, 128))
    cores_js[fantasma] = [cor, cor_apagada]

    motivo = (
        "Fora do filtro atual"
        if fantasma in nomes
        else "Não cadastrada em disciplinas.csv"
    )

    rede.add_node(
        fantasma,
        label=fantasma,
        title=f"{fantasma} — {nomes.get(fantasma, '(sem nome)')}\n{motivo}",
        size=14,
        color=cor,
        shape="dot",
    )

for (origem, destino), cursos_aresta in arestas.items():
    rede.add_edge(
        origem,
        destino,
        title=(
            f"{origem} → {destino}\n"
            f"Cursos: {', '.join(sorted(cursos_aresta))}"
        ),
        color="#9aa0a6",
        width=1,
        arrowStrikethrough=False,
    )

id_buscado = ""

if busca.strip():
    termo = busca.strip().lower()

    for disciplina in sorted(visiveis):
        if (
            termo == disciplina.lower()
            or termo in nomes[disciplina].lower()
        ):
            id_buscado = disciplina
            break


# PyVis gera o HTML; o trecho abaixo adiciona o painel interativo.
try:
    html = rede.generate_html()

    interatividade = r"""
<style>
html, body {
    margin: 0;
    padding: 0;
    background: #000000 !important;
    overflow: hidden;
}
#mynetwork {
    border: 2px solid #5797ff !important;
    border-radius: 16px;
    box-sizing: border-box;
    height: 700px !important;
    width: 100% !important;
}
div.vis-tooltip {
    background: rgba(33, 37, 41, .95) !important;
    color: white !important;
    border: 2px solid #5797ff !important;
    border-radius: 12px;
    padding: 10px !important;
    white-space: pre-line;
    max-width: 440px;
}
#painel-info {
    position: fixed;
    top: 20px;
    right: 20px;
    width: 330px;
    max-height: 660px;
    overflow: auto;
    display: none;
    z-index: 9999;
    padding: 14px;
    border: 2px solid #5797ff;
    border-radius: 12px;
    background: rgba(14, 17, 23, .96);
    color: white;
    font: 13px/1.45 sans-serif;
    overflow-wrap: anywhere;
}
#painel-info h3 { margin: 0 20px 2px 0; font-size: 15px; }
#painel-info .sub { color: #9aa0a6; font-size: 12px; }
#painel-info .secao {
    margin: 12px 0 6px;
    font-weight: bold;
    font-size: 12px;
    text-transform: uppercase;
    color: #8ab4ff;
}
#painel-info .cursos {
    color: #9aa0a6;
    font-size: 11px;
    margin-bottom: 4px;
}
#painel-info .regra {
    color: #cfd3d8;
    font-size: 12px;
    margin: 2px 0 6px;
}
#painel-info .cartao {
    border: 1px solid #3b4252;
    border-radius: 10px;
    padding: 8px 10px;
    margin-bottom: 6px;
    cursor: pointer;
    background: #161b22;
}
#painel-info .cartao:hover { border-color: #5797ff; }
#painel-info .cartao.ativo {
    border-color: #5797ff;
    background: #1b2a47;
}
#painel-info .titulo {
    font-weight: bold;
    font-size: 12px;
    margin-bottom: 4px;
}
#painel-info .chip {
    display: inline-block;
    padding: 2px 8px;
    margin: 2px 2px 2px 0;
    border-radius: 999px;
    background: #2a3140;
    font-size: 12px;
}
#painel-info .chip.link {
    cursor: pointer;
    background: #22304d;
}
#painel-info .chip.link:hover { background: #2f4372; }
#painel-info .mais {
    color: #8ab4ff;
    margin: 0 2px;
    font-weight: bold;
}
#painel-info .botao {
    margin-top: 6px;
    padding: 4px 10px;
    border-radius: 8px;
    cursor: pointer;
    border: 1px solid #5797ff;
    background: transparent;
    color: #8ab4ff;
    font-size: 12px;
}
#painel-info .fechar {
    position: absolute;
    top: 8px;
    right: 10px;
    cursor: pointer;
    color: #9aa0a6;
    font-size: 16px;
    background: none;
    border: 0;
}
#painel-info .vazio {
    color: #9aa0a6;
    font-style: italic;
}
</style>

<div id="painel-info"></div>

<script>
const DADOS = __DADOS__;
const CORES = __CORES__;

setTimeout(function () {
    if (
        typeof network === "undefined" ||
        typeof nodes === "undefined" ||
        typeof edges === "undefined"
    ) {
        return;
    }

    const painel = document.getElementById("painel-info");
    const nosOriginais = nodes.get();
    const arestasOriginais = edges.get();

    function elemento(tag, classe, texto) {
        const e = document.createElement(tag);
        if (classe) e.className = classe;
        if (texto !== undefined) e.textContent = texto;
        return e;
    }

    function pintar(nosAtivos, arestasAtivas) {
        edges.update(arestasOriginais.map(function (a) {
            const ativo = arestasAtivas.has(a.id);
            return {
                id: a.id,
                color: ativo
                    ? {color: "#5797ff", opacity: 1}
                    : {color: "#888888", opacity: 0.1},
                width: ativo ? 3 : 1
            };
        }));

        nodes.update(nosOriginais.map(function (no) {
            const ativo = nosAtivos.has(no.id);
            const cor = CORES[no.id] || [no.color, no.color];
            return {
                id: no.id,
                color: ativo ? cor[0] : cor[1],
                font: {
                    color: ativo
                        ? "#ffffff"
                        : "rgba(150, 150, 150, 0.3)"
                }
            };
        }));
    }

    function ajustar(nos) {
        network.fit({
            nodes: Array.from(nos),
            animation: {
                duration: 500,
                easingFunction: "easeInOutQuad"
            }
        });
    }

    function mostrarTodos(id) {
        const dados = DADOS[id];
        const nos = new Set([id]);
        const linhas = new Set();

        dados.prereqs.forEach(function (variante) {
            variante.grupos.forEach(function (grupo) {
                grupo.forEach(function (membro) {
                    nos.add(membro);
                });
            });
        });

        dados.libera.forEach(function (destino) {
            nos.add(destino);
        });

        arestasOriginais.forEach(function (a) {
            if (a.to === id || a.from === id) {
                linhas.add(a.id);
            }
        });

        pintar(nos, linhas);
        ajustar(nos);
    }

    function mostrarCaminho(id, grupo) {
        const nos = new Set([id].concat(grupo));
        const linhas = new Set();

        arestasOriginais.forEach(function (a) {
            if (a.to === id && grupo.includes(a.from)) {
                linhas.add(a.id);
            }
        });

        pintar(nos, linhas);
        ajustar(nos);
    }

    function restaurar() {
        edges.update(arestasOriginais.map(function (a) {
            return {id: a.id, color: a.color, width: a.width};
        }));

        nodes.update(nosOriginais.map(function (no) {
            const cor = CORES[no.id] || [no.color, no.color];
            return {
                id: no.id,
                color: cor[0],
                font: {color: "#ffffff"}
            };
        }));
    }

    function limpar() {
        painel.style.display = "none";
        restaurar();
        network.fit({
            animation: {
                duration: 500,
                easingFunction: "easeInOutQuad"
            }
        });
    }

    function chip(id, clicavel) {
        const info = DADOS[id];
        const e = elemento(
            "span",
            "chip" + (clicavel ? " link" : ""),
            id
        );

        e.title = info ? info.nome : "";

        if (clicavel && nodes.get(id)) {
            e.addEventListener("click", function (evento) {
                evento.stopPropagation();
                network.selectNodes([id]);
                selecionar(id);
            });
        }

        return e;
    }

    function montarPainel(id) {
        const dados = DADOS[id];
        const cartoes = [];

        // textContent impede interpretar os dados do CSV como HTML.
        painel.textContent = "";

        const fechar = elemento("button", "fechar", "✕");
        fechar.addEventListener("click", function () {
            network.unselectAll();
            limpar();
        });
        painel.appendChild(fechar);

        painel.appendChild(
            elemento("h3", "", id + " — " + dados.nome)
        );
        painel.appendChild(
            elemento("div", "sub", dados.ch + "h de carga horária")
        );
        painel.appendChild(
            elemento("div", "secao", "Pré-requisitos")
        );

        if (!dados.prereqs.length) {
            painel.appendChild(
                elemento("div", "vazio", "Sem pré-requisitos.")
            );
        }

        dados.prereqs.forEach(function (variante) {
            painel.appendChild(
                elemento(
                    "div",
                    "cursos",
                    "Curso(s): " + variante.cursos.join(", ")
                )
            );

            painel.appendChild(
                elemento(
                    "div",
                    "regra",
                    variante.grupos.length === 1
                        ? "Cumpra TODAS as disciplinas abaixo:"
                        : "Cumpra UMA das opções abaixo:"
                )
            );

            variante.grupos.forEach(function (grupo, indice) {
                const cartao = elemento("div", "cartao");

                cartao.appendChild(
                    elemento(
                        "div",
                        "titulo",
                        variante.grupos.length === 1
                            ? "Caminho único"
                            : "Opção " + (indice + 1)
                    )
                );

                grupo.forEach(function (membro, posicao) {
                    if (posicao > 0) {
                        cartao.appendChild(
                            elemento("span", "mais", "+")
                        );
                    }
                    cartao.appendChild(chip(membro, false));
                });

                cartao.addEventListener("click", function () {
                    const jaAtivo = cartao.classList.contains("ativo");

                    cartoes.forEach(function (outro) {
                        outro.classList.remove("ativo");
                    });

                    if (jaAtivo) {
                        mostrarTodos(id);
                    } else {
                        cartao.classList.add("ativo");
                        mostrarCaminho(id, grupo);
                    }
                });

                cartoes.push(cartao);
                painel.appendChild(cartao);
            });
        });

        if (dados.prereqs.length) {
            const botao = elemento(
                "button",
                "botao",
                "Ver todos os caminhos"
            );

            botao.addEventListener("click", function () {
                cartoes.forEach(function (cartao) {
                    cartao.classList.remove("ativo");
                });
                mostrarTodos(id);
            });

            painel.appendChild(botao);
        }

        if (dados.libera.length) {
            painel.appendChild(
                elemento(
                    "div",
                    "secao",
                    "Libera (é pré-requisito de)"
                )
            );

            const caixa = elemento("div");

            dados.libera.forEach(function (destino) {
                caixa.appendChild(chip(destino, true));
            });

            painel.appendChild(caixa);
        }

        painel.style.display = "block";
        painel.scrollTop = 0;
    }

    function selecionar(id) {
        if (!DADOS[id]) return;
        montarPainel(id);
        mostrarTodos(id);
    }

    network.on("selectNode", function (params) {
        if (params.nodes.length) {
            selecionar(params.nodes[0]);
        }
    });

    network.on("deselectNode", function (params) {
        if (!params.nodes || !params.nodes.length) {
            limpar();
        }
    });

    const idBuscado = __ID_BUSCADO__;

    if (idBuscado && nodes.get(idBuscado)) {
        network.selectNodes([idBuscado]);
        selecionar(idBuscado);
    }
}, 500);
</script>
"""

    interatividade = (
        interatividade
        .replace("__DADOS__", para_js(dados_js))
        .replace("__CORES__", para_js(cores_js))
        .replace("__ID_BUSCADO__", para_js(id_buscado))
    )

    html = html.replace("</body>", interatividade + "</body>")
    components.html(html, height=750, scrolling=False)

except Exception as erro:
    st.error("Erro ao gerar visualização: " + str(erro))
