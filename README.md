# ProductLens

Automatizovana kontrola konzistentnosti proizvoda: da li isti proizvod na dva
prodajna kanala (brend sajt, retailer, marketplace...) ima istu nijansu,
zapreminu, sastojke i upozorenja, i da li se fotografije poklapaju sa
deklarisanim tekstom. Cena, dostupnost, SKU i kategorija namerno nisu u
fokusu — to je komercijalni sadržaj svakog kanala, ne pitanje brend
konzistentnosti.

Nema hardkodiranih demo podataka: ponude dolaze isključivo uživo, preko
ugrađenog scraper-a (pretraga interneta + skrejpovanje, vidi
[docs/scraping.md](docs/scraping.md)).

**Aplikacija je na engleskom** — i interfejs i sve što model vrati
(objašnjenja, verdikt, beleške sa slika).

## Workflow

Korisnik unese jedno ime proizvoda i gleda kako run teče.

1. **Pretraga i skrejpovanje** — backend nađe najbolje strane (domaće i
   svetske), skrejpuje ih (do 10) i izvuče tekst, specifikaciju i galeriju.
   Bira se prvo po jedna strana po prodavnici, pa tek onda druga iz iste —
   poređenje je između kanala, pa je nova prodavnica uvek vrednija.
2. **Izbor kanala** — korisnik čekira koje ponude hoće da uporedi (2 do 8);
   par se ne nameće. Unapred su čekirane najbolje ponude iz različitih
   prodavnica i, ako postoji, iz različitih regiona.
3. **Podaci sa slika** — fotografije se preuzimaju sa udaljenih URL-ova; ako
   ih ima 3 ili više, jeftiniji/brži model (`xai_filter_model`) prvo odbaci
   one koje ne prikazuju baš taj proizvod (stranica zna da povuče i slike
   povezanih proizvoda ili druge nijanse). Tek onda glavni (reasoning) model
   pročita preostale fotografije i vrati strukturirane podatke (tekst sa
   ambalaže, nijansa, zapremina, sastojci, upozorenja, tvrdnje). Rezultat se
   kešira u `backend/data/image_facts.cache.json`.
4. **Poređenje** — svi izabrani kanali (sajt + slike) idu u jedan poziv koji
   proverava tačno 6 unapred definisanih dimenzija (`product_identity`,
   `shade`, `volume`, `ingredients`, `warnings`, `images_vs_text` —
   vidi `ComparisonField` u `backend/src/schemas.py`) sa statusom (`match` /
   `minor` / `mismatch` / `missing`), ozbiljnošću i objašnjenjem. Taj fiksni
   skup polja je namerno zatvoren (ne slobodan tekst) da model ne bi flagovao
   nebitne stvari (cenu, šifru, kategoriju) niti izmišljao nova polja.

   Svaka dimenzija vraća po jednu vrednost za SVAKI kanal (`values`, vezano
   za labelu A/B/C/...) plus `flagged` — koji kanali nose problem, tj. šta bi
   neko morao da ispravi. Kod `images_vs_text` to je svaka ponuda čije slike
   protivreče njenom sopstvenom tekstu, ne manjina.

Pretraga traje ~15-60 s, a audit ~2-5 minuta (raste sa brojem kanala), pa
nijedno ne ide kao jedan dug zahtev nego kao posao: `POST` vrati `job_id`, a
frontend povlači `GET /api/analyze/{id}`
i prikazuje šta se stvarno dešava (koji su sajtovi nađeni, koja strana je
upravo pročitana, koje se fotografije trenutno gledaju). Poslovi žive u memoriji
procesa — `uvicorn --reload` ih obriše pri svakoj izmeni backend koda.

## Pokretanje

```sh
# backend (http://127.0.0.1:8000)
cd backend
cp .env.example .env   # upiši XAI_API_KEY, FIRECRAWL_API_KEY, EXA_API_KEY
uv run uvicorn main:app --reload --app-dir src

# frontend (http://localhost:5173), proksira /api na backend
cd frontend
npm install
npm run dev
```

## API

| Ruta | Opis |
| --- | --- |
| `POST /api/analyze` | `{"query": "..."}` → `{job_id}`; pretraga + skrejpovanje |
| `POST /api/analyze/compare` | `{"listings": [Product, ...]}` (2-8) → `{job_id}`; audit izabranih kanala |
| `GET /api/analyze/{job_id}?cursor=N` | događaji od `cursor` nadalje + rezultat kad je gotovo |
| `POST /api/compare` | isti posao kao gore, ali kao jedan blokirajući zahtev (bez progresa) |
| `POST /api/scraper/discover` | pretraga + skrejpovanje po imenu proizvoda (vidi [docs/scraping.md](docs/scraping.md)) |

`Product` = `{id, source, url, title, raw_text, images}`; gradi ga
`_to_product` u `backend/src/analyze.py` od jedne ponude koju vrati scraper.

`/scraper` u frontendu je i dalje napredni prikaz celog scraper run-a
(kandidati, skorovi, pozivi provajdera) — koristan za debug, nije deo demo
toka.

## Struktura

```
backend/
  src/
    config.py, main.py, llm.py, products.py, schemas.py   # aplikacioni kod
    analyze.py, jobs.py                                    # run kao posao + progres
    scraper/                                               # pretraga + skrejpovanje (izolovano, vidi docs/scraping.md)
  tests/        # manuelna provera konekcije ka xAI API-ju
  data/         # keš pročitanih slika i scraper runova

frontend/src/
  App.tsx, useRun.ts, api.ts, ui.tsx   # ljuska, poll petlja, tokeni dizajna
  views/                               # SearchView / RunView / SelectView / ReportView
  scraper/                             # napredni scraper prikaz
```
