# Desenvolvimento

## Pre-commit
1. Instale as dependências de desenvolvimento:
   ```bash
   pip install -r requirements-dev.txt
   ```
2. Instale os hooks no repositório:
   ```bash
   pre-commit install
   ```
3. Opcionalmente, execute todos os hooks localmente antes de commitar:
   ```bash
   pre-commit run --all-files
   ```
