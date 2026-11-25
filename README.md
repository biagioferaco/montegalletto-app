# Ascensore Montegalletto

App web installabile (PWA) che mostra se l'ascensore Castello D'Albertis – Montegalletto
(via Balbi ⇄ corso Dogali, Genova) è aperto, quando chiude o riapre, gli orari di oggi e
l'ultimo avviso pubblicato da AMT. Sostituisce il bot Telegram `montegalletto_bot`.

## Come funziona

```
GitHub Actions (ogni 20 min)                         GitHub Pages
  scraper/build_status.py  ──►  docs/status.json  ──►  docs/ (PWA)
      │                                                   │
      └─ API WordPress di AMT                             └─ calcola lo stato nel browser
         /amt/wp-json/wp/v2/posts?search=montegalletto       (orari, festivi, chiusure)
```

- **Fonte avvisi**: il sito AMT è WordPress ed espone l'API JSON standard, molto più stabile
  dello scraping HTML. Si leggono gli ultimi 30 avvisi con "montegalletto" nel titolo.
- **Chiusure**: `scraper/parser.py` ricava dagli avvisi gli intervalli di chiusura
  (es. "dalle ore 14.00 di mercoledì 4 novembre alle ore 20.00 di giovedì 5 novembre",
  "da lunedì 30 settembre a venerdì 4 ottobre", "fino alle ore 13.00", "seguiranno
  aggiornamenti"…). Gestisce anche gli aggiornamenti dentro lo stesso avviso
  ("Aggiornamento: servizio ripristinato alle 17.00") e i post di ripristino che chiudono
  una sospensione senza data di fine. Se un avviso parla di chiusura ma il testo non è
  riconosciuto, l'app lo mostra come **avviso da controllare** invece di indovinare.
- **Orari** (pagina Ascensori di AMT): feriali, sabato compreso, 7.10–19.50; domeniche e
  festivi 7.15–20.55; una corsa circa ogni 7 minuti. Le festività (nazionali, Pasquetta,
  San Giovanni 24 giugno, San Francesco 4 ottobre dal 2026) sono calcolate in `docs/schedule.js`.
- **Stato**: calcolato nel browser con l'ora di Genova, quindi resta giusto anche se
  `status.json` è di qualche minuto prima. Se i dati hanno più di 90 minuti l'app lo segnala.

## Sviluppo in locale

Serve solo Python 3.10+ (nessuna dipendenza) e, per i test della parte web, Node 20+.

```bash
python -m unittest discover -s tests          # test del parser sui veri avvisi AMT
node --test tests/schedule.test.mjs           # test di orari e stato
python scraper/build_status.py                # scarica gli avvisi e scrive docs/status.json
python scraper/build_status.py --fixture tests/fixtures/posts.json   # senza rete
python -m http.server -d docs 8000            # poi apri http://localhost:8000
```

## Pubblicazione

1. Crea un repository su GitHub (pubblico: Pages e Actions sono gratuiti) e fai push di questa cartella su `main`.
2. Nel repository: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Il workflow `.github/workflows/pages.yml` parte a ogni push, ogni 20 minuti e a mano
   (Actions → "Aggiorna stato e pubblica" → Run workflow).
4. L'app sarà su `https://<utente>.github.io/<repository>/`. Dal telefono: menu del browser →
   "Aggiungi a schermata Home".

Note:
- GitHub sospende i workflow programmati dei repository pubblici dopo 60 giorni senza commit:
  in quel caso basta riattivarli dalla scheda Actions (o fare un commit).
- Se AMT dovesse bloccare le richieste da GitHub, lo step "Leggi gli avvisi AMT" fallisce,
  il sito resta all'ultima versione e l'app mostra l'avviso di dati non aggiornati.

## Struttura

```
scraper/parser.py         riconoscimento delle chiusure negli avvisi
scraper/build_status.py   download dall'API AMT e scrittura di status.json
docs/                     la PWA (index.html, app.js, schedule.js, style.css, sw.js, icone)
tests/                    test Python e Node, con avvisi AMT reali in tests/fixtures/posts.json
```
