# Grafo de Pré-requisitos Acadêmicos

Aplicação interativa em Streamlit com PyVis para visualização e análise de cadeias de pré-requisitos entre disciplinas.

## Estrutura do Projeto
- `app.py`: Código principal da aplicação (fundo do grafo em preto, painel interativo).
- `disciplinas.csv`: Dados das disciplinas (id, nome, carga horária).
- `curso_disciplina.csv`: Relação entre cursos, períodos e disciplinas.
- `disciplinas_unidades_prerequisitos.csv`: Regras e expressões booleanas de pré-requisitos.
- `requirements.txt`: Dependências necessárias para execução.
- `.streamlit/config.toml`: Configuração do tema escuro.

## Como rodar localmente
1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
2. Execute a aplicação:
   ```bash
   streamlit run app.py
   ```

## Deploy no Streamlit Cloud
1. Suba esta pasta para um repositório no GitHub.
2. No [Streamlit Cloud](https://share.streamlit.io), conecte seu GitHub e selecione o repositório.
3. Defina `app.py` como Main file path e clique em **Deploy**.
