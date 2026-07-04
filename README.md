<div align="center">

# LAMBDA
### LArge Model-based Data Analysis Agent System
[![Online App](https://img.shields.io/badge/Online%20App-Live%20Demo-ff6b6b?style=flat&logo=rocket&logoColor=white)](https://lambda.com.ai)
[![Blog](https://img.shields.io/badge/Blog-Site-blue?style=flat&logo=readme&logoColor=white)](https://lambda.org.ai)
[![Cases](https://img.shields.io/badge/Cases-Gallery-9cf?style=flat&logo=databricks&logoColor=white)](https://lambda.com.ai/cases)
[![Project](https://img.shields.io/badge/Project-Webpage-brightgreen)](https://www.polyu.edu.hk/ama/cmfai/lambda.html)
[![Paper](https://img.shields.io/badge/Paper-JASA-red)](https://www.tandfonline.com/doi/full/10.1080/01621459.2025.2510000)

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-Frontend-61DAFB?style=flat&logo=react&logoColor=111111)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-UI-3178C6?style=flat&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Storage-003B57?style=flat&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![OpenAI Compatible](https://img.shields.io/badge/OpenAI--compatible-Models-412991?style=flat&logo=openai&logoColor=white)](https://platform.openai.com/docs/api-reference/chat)

<img width="1280" height="804" alt="lambda_gif-ezgif com-optimize" src="https://github.com/user-attachments/assets/a98a3258-8aef-4790-b25d-4521e9be966f" />
</div>

LAMBDA is a data analysis agent that turns natural-language questions into
reproducible analysis workflows. Upload a dataset, ask a question, and LAMBDA
can inspect the data, write and run code, create visualizations, summarize
findings, and generate reports or notebooks from the session.

The public web app is available at **https://lambda.com.ai**. This repository
contains the runnable LAMBDA codebase, including the React frontend, FastAPI
backend, model interface, file workspace, and analysis tools.

## Features

- Conversational data analysis with executable Python and shell tools.
- Beautiful and intuitive UI for data analysis.
- Autonomous dataset exploration for CSV, Excel, text, and other common files.
- Persistent workspace per conversation, so variables and generated files stay
  available throughout the analysis.
- Automatic chart, table, report, notebook, and artifact tracking in the Files
  panel.
- Export to Jupyter Notebook, Markdown/report bundles, PDF reports, and slides.
- English and Chinese UI support, including Chinese report generation when
  XeLaTeX and CJK fonts are installed.
- Configurable OpenAI-style model endpoint and model list.
- Local SQLite storage for conversations, uploads, and generated artifacts.

## Quick Start

Requirements:

- Python 3.11 or newer
- Node.js 20 or newer
- npm
- Optional for PDF/Chinese reports: TeX Live with XeLaTeX

Create your backend configuration and start both services:

```bash
cp backend/.env.example backend/.env
# Edit backend/.env and set OPENAI_API_KEY, OPENAI_BASE_URL, and MODEL_LIST.
./start.sh
```

Open the app:

```text
http://localhost:3000
```

Stop the app:

```bash
./stop.sh
```

If the default ports are already in use:

```bash
BACKEND_PORT=8010 FRONTEND_PORT=3010 ./start.sh
```

## Model Configuration

LAMBDA talks to models through an OpenAI-style chat completions interface. Set
the endpoint and the models you want to expose in `backend/.env`:

```env
OPENAI_API_KEY=your-api-key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_LIST='["mimo-v2.5-pro","deepseek-v4-pro"]'
```

`OPENAI_BASE_URL` should be the base URL of an OpenAI-compatible API. LAMBDA
will call:

```text
{OPENAI_BASE_URL}/chat/completions
```

`MODEL_LIST` is a JSON array of model IDs. These IDs appear in the model picker
and are sent to the provider unchanged. The first model in the list is used as
the default model unless `DEFAULT_MODEL` is also set.

## How To Use

1. Open `http://localhost:3000`.
2. Choose a model from the picker.
3. Upload one or more data files, or start with an example dataset.
4. Ask a question, such as:

```text
Analyze this dataset, identify the main patterns, create visualizations, and
write a report with the most important findings.
```

For a hands-off workflow, use Autonomous Exploration. LAMBDA will inspect the
dataset, plan the analysis, run code, build charts, and produce a report.

## Exports And Files

Each conversation has its own workspace under:

```text
backend/data/workspaces/<conversation_id>/
```

Uploaded files, charts, reports, notebooks, and other generated artifacts are
shown in the Files panel. Runtime data is stored under `backend/data/`, including:

```text
backend/data/
  lambda_local.db
  uploads/
  workspaces/
```

These files are intentionally ignored by git.

## Manual Setup

Backend:

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## PDF And Chinese Report Support

For LaTeX/PDF reports, especially Chinese reports, install the optional system
dependencies once:

```bash
./scripts/install-system-deps.sh
```

This installs `pdflatex`, `xelatex`, Chinese LaTeX packages, and Noto CJK fonts
for Chinese charts and reports. You can also let `start.sh` install them when
missing:

```bash
LAMBDA_AUTO_INSTALL_SYSTEM_DEPS=1 ./start.sh
```

This uses `sudo apt-get`, so it is opt-in.

## Runtime Note

LAMBDA executes analysis code on the machine where the backend is running. Use
it with trusted users and trusted data, and do not expose the backend directly
to untrusted traffic without adding sandboxing or other isolation.

## Versions

The latest code is on `main` and tagged as `lambda-v2`.

The previous open-source version is preserved at:

- Branch: `legacy-open-source`
- Tag: `lambda-v1`

## Acknowledgements

Thank the contributors and the communities for their support and feedback.

---

> If you find our work useful in your research, consider citing our paper by:

```bibtex
@article{sun2026lambda,
  title={Lambda: A large model based data agent},
  author={Sun, Maojun and Han, Ruijian and Jiang, Binyan and Qi, Houduo and Sun, Defeng and Yuan, Yancheng and Huang, Jian},
  journal={Journal of the American Statistical Association},
  volume={121},
  number={553},
  pages={1--13},
  year={2026},
  publisher={Taylor \& Francis}
}

@article{sun2025survey,
  title={A survey on large language model-based agents for statistics and data science},
  author={Sun, Maojun and Han, Ruijian and Jiang, Binyan and Qi, Houduo and Sun, Defeng and Yuan, Yancheng and Huang, Jian},
  journal={The American Statistician},
  pages={1--14},
  year={2025},
  publisher={Taylor \& Francis}
}

@article{sun2026rejoinder,
  title={Rejoinder to the Discussions on {LAMBDA}: A Large Model Based Data Agent},
  author={Sun, Maojun and Han, Ruijian and Jiang, Binyan and Qi, Houduo and Sun, Defeng and Yuan, Yancheng and Huang, Jian},
  journal={Journal of the American Statistical Association},
  volume={121},
  number={553},
  pages={36--43},
  year={2026},
  publisher={Taylor \& Francis}
}
```

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=AMA-CMFAI/LAMBDA&type=Date)](https://www.star-history.com/#AMA-CMFAI/LAMBDA&Date)
