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

## Workflow

1. **Pretraga** — na glavnoj strani se unese ime proizvoda; backend
   (`/api/scraper/discover`) nađe najbolje strane (domaće i svetske),
   skrejpuje ih i vrati listu ponuda (naslov, sirov tekst stranice,
   URL-ovi fotografija).
2. **Izbor** — korisnik iz padajućih listi bira bilo koje dve ponude za
   poređenje.
3. **Podaci sa slika** — fotografije se preuzimaju sa udaljenih URL-ova; ako
   ih ima 3 ili više, jeftiniji/brži model (`xai_filter_model`) prvo odbaci
   one koje ne prikazuju baš taj proizvod (stranica zna da povuče i slike
   povezanih proizvoda ili druge nijanse). Tek onda glavni (reasoning) model
   pročita preostale fotografije i vrati strukturirane podatke (tekst sa
   ambalaže, nijansa, zapremina, sastojci, upozorenja, tvrdnje). Rezultat se
   kešira u `backend/data/image_facts.cache.json`; odgovor takođe vraća
   proizvod sa slikama suženim na ono što je stvarno analizirano.
4. **Poređenje** — oba skupa podataka (sajt + slike) idu u jedan poziv koji
   proverava tačno 6 unapred definisanih dimenzija (`product_identity`,
   `shade`, `volume`, `ingredients`, `warnings`, `images_vs_text` —
   vidi `ComparisonField` u `backend/src/schemas.py`) sa statusom (`match` /
   `minor` / `mismatch` / `missing`), ozbiljnošću i objašnjenjem na srpskom.
   Taj fiksni skup polja je namerno zatvoren (ne slobodan tekst) da model ne
   bi flagovao nebitne stvari (cenu, šifru, kategoriju) niti izmišljao nova
   polja.

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
| `POST /api/compare` | `{"a": Product, "b": Product}` → podaci sa slika + izveštaj o razlikama |
| `POST /api/scraper/discover` | pretraga + skrejpovanje po imenu proizvoda (vidi [docs/scraping.md](docs/scraping.md)) |

`Product` = `{id, source, url, title, raw_text, images}`; `frontend/src/search.ts`
gradi ovaj oblik od jedne ponude koju vrati `/api/scraper/discover`.

Poređenje traje ~2-4 minuta (grok-4.6 je reasoning model, plus preuzimanje
udaljenih slika); čitanje slika po ponudi se kešira.

## Struktura backend-a

```
backend/
  src/
    config.py, main.py, llm.py, products.py, schemas.py   # aplikacioni kod
    scraper/                                               # pretraga + skrejpovanje (izolovano, vidi docs/scraping.md)
  tests/        # manuelna provera konekcije ka xAI API-ju
  data/         # keš pročitanih slika i scraper runova
```
