# olx-watcher

Bot care monitorizează căutări OLX.ro și trimite anunțurile noi pe Telegram. Rulează gratuit pe GitHub Actions.

## Setup

### 1. Creează botul Telegram

1. Deschide [@BotFather](https://t.me/BotFather) pe Telegram
2. Trimite `/newbot` și urmează instrucțiunile
3. Salvează **token-ul** primit (ex: `123456:ABCdef...`)

### 2. Află chat_id-ul tău

1. Trimite orice mesaj botului tău pe Telegram
2. Deschide în browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Caută `"chat":{"id": 123456789}` — acela e **chat_id-ul** tău

### 3. Configurează repo-ul pe GitHub

1. Fork/clone acest repo
2. Du-te la **Settings → Secrets and variables → Actions**
3. Adaugă două secrete:
   - `TELEGRAM_BOT_TOKEN` — token-ul de la BotFather
   - `TELEGRAM_CHAT_ID` — ID-ul de chat

### 4. Configurează căutările

Editează `config.yaml`:

```yaml
searches:
  - name: "Untold Cluj - apartamente"
    url: "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-inchiriat/cluj-napoca/"
    max_price: 500          # opțional — preț maxim în moneda anunțului
    include_keywords: []    # opțional — cel puțin unul trebuie să apară în titlu
    exclude_keywords:       # opțional — niciun cuvânt din listă nu trebuie să apară
      - cumpar
      - caut
```

**URL-ul**: deschide OLX.ro, aplică filtrele dorite (categorie, oraș, preț), apoi copiază URL-ul din browser.

Poți adăuga oricâte căutări.

### 5. Rulare locală

```bash
# Instalare
pip install curl_cffi beautifulsoup4 pyyaml

# Rulare cu dry-run (fără Telegram)
python -m watcher --dry-run

# Rulare cu Telegram
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python -m watcher
```

## Cum funcționează

- La fiecare rulare, botul verifică fiecare URL din `config.yaml`
- Extrage anunțurile prin API-ul intern OLX (JSON), cu fallback pe datele embedded din pagină
- Compară cu `seen.json` pentru a detecta anunțurile noi
- La **prima rulare** nu trimite nimic — doar marchează anunțurile existente
- Anunțurile noi sunt trimise pe Telegram cu: titlu, preț, locație, data publicării, poză și link
- Dacă apar peste 10 anunțuri noi, trimite primele 10 + un mesaj rezumat
- `seen.json` se curăță automat de intrări mai vechi de 30 de zile

## Erori

- Dacă o căutare eșuează, celelalte continuă normal
- După 3 eșecuri consecutive pentru aceeași căutare, primești o alertă pe Telegram
- Workflow-ul returnează mereu exit code 0 ca să nu fie dezactivat automat

## Structura

```
watcher/
  __main__.py       → entrypoint
  main.py           → orchestrare
  config.py         → încarcă config.yaml
  sources/olx.py    → extragere anunțuri OLX
  filters.py        → filtre keywords + preț
  state.py          → seen.json management
  notify.py         → Telegram notifications
tests/              → pytest
.github/workflows/  → GitHub Actions cron
```
