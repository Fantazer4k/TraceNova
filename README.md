# TraceNova

TraceNova is an OSINT and digital-intelligence learning project built with Python and FastAPI. It is designed to collect information from publicly available sources and present results through a simple web interface.

> **Educational / responsible use:** TraceNova is intended for learning, research, and defensive security work. Only investigate information you are authorized to access or information that is publicly available. Do not use it to harass, stalk, impersonate, or access private accounts.

## Features

- Domain and IP analysis
- Username searches across public platforms
- Email-related public-source checks
- Phone-number validation and public-source checks
- DNS and basic network information
- Data-breach checks where supported by the configured service
- FastAPI backend with a browser-based frontend

## Project structure

```text
TraceNova/
└── tracenova/
    ├── backend/        # FastAPI application and configuration
    ├── frontend/       # HTML, CSS and JavaScript UI
    ├── services/       # Public-source lookup services
    ├── utils/          # Utility modules
    ├── main.py         # Application entry point
    └── requirements.txt
```

## Requirements

- Python 3.10+
- pip

## Installation

```bash
git clone https://github.com/Fantazer4k/TraceNova.git
cd TraceNova/tracenova
python -m venv .venv
```

Activate the virtual environment:

### Windows

```bash
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` when environment variables are required.

```bash
cp .env.example .env
```

Never commit real API keys, passwords, tokens, cookies, or other credentials. Keep secrets in `.env` or another secret-management system.

## Running

From the `tracenova` directory:

```bash
python main.py
```

The development server runs on `http://127.0.0.1:8000` by default.

## Responsible use

TraceNova is designed around public and permitted information sources. Results may be incomplete or inaccurate, and a matching username, email, or phone number does not prove that two records belong to the same person.

Respect the terms of service and applicable laws of every service you query.

## Status

TraceNova is an experimental learning project and is under active development. Some integrations are prototypes and may require changes as third-party APIs and websites evolve.

## License

No license has been selected for this repository yet. Until a license is added, the source code should not be assumed to be freely reusable by others.
