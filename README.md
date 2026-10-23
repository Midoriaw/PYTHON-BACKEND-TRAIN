<p align="center">
  <img src="docs/banner.png" alt="Python Backend Trainer" width="100%">
</p>

<h1 align="center">Python Backend Trainer</h1>

<p align="center">
  <strong>Standalone desktop environment for practical Python backend training.</strong>
</p>

<p align="center">
  Interactive Training · Code Sandbox · Python Assistant · Knowledge Base · Spaced Repetition
</p>

---

## Overview

**Python Backend Trainer** is a standalone desktop application built for systematic Python backend practice.

It combines an interactive code editor, isolated code execution, a local knowledge base, a Python assistant, automated validation and spaced repetition into one application.

The project is built as a complete software system with its own architecture, testing infrastructure, data layer and desktop interface.

## Core Features

- **39 practical Python tasks** with tests, hints and cheat sheets
- **Code sandbox** for running and validating solutions
- **CodeMirror editor** integrated into the application
- **Python assistant** powered by a local knowledge base with **269 cards**
- Code and error analysis with contextual responses
- Task types: `stdout`, `function`, `FastAPI`, `quiz`
- **Spaced repetition:** 1 → 3 → 7 → 14 → 30 days
- Assistant regression and blind evaluation
- Built-in application self-test
- Windows `.exe` packaging with PyInstaller
- Custom UI and animated SVG character system

## Architecture

```text
Python Backend Trainer
│
├── assistant/       Assistant, search, context & code analysis
├── data/
│   ├── tasks/       Training tasks and validation tests
│   └── kb/          Assistant knowledge base
├── tests/           Automated quality checks
├── ui/              Desktop interface
├── sandbox.py       Isolated code execution
├── tasks.py         Task loading and validation
└── app.py           Application entry point
```

## Quality

The project includes automated checks for:

- knowledge-base code examples
- assistant search regression
- blind assistant evaluation
- application resources
- sandbox functionality

Unanswered assistant questions are collected automatically, creating a feedback loop for expanding the knowledge base.

## Run

```bash
pip install -r requirements.txt
python app.py
```

Run the built-in self-test:

```bash
python app.py --selftest
```

Build the Windows executable:

```bash
pyinstaller --noconfirm Trainer.spec
```

## Project Status

**Active development.**

The application is continuously extended with new training content, assistant capabilities, validation systems and desktop features.

## Author

**Midoriaw**  
Python Backend Developer

[GitHub](https://github.com/Midoriaw)