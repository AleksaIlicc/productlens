# ProductLens

Automatizovana kontrola konzistentnosti proizvoda: da li isti proizvod na dva
prodajna kanala (brend sajt, retailer, marketplace...) ima istu nijansu,
zapreminu, sastojke i upozorenja, i da li se fotografije poklapaju sa
deklarisanim tekstom. Cena, dostupnost, SKU i kategorija namerno nisu u
fokusu — to je komercijalni sadržaj svakog kanala, ne pitanje brend
konzistentnosti.

Trenutno su hardkodirana dva izvora za isti artikal (Vichy Dermablend Corrector SPF 35, 30 ml, 35 Sand):

- [Apoteka Janković](https://www.apotekajankovic.rs/vichy-dermablend-corrector-tecni-korektivni-puder-spf-35-30-ml-35-sand)
- [Lilly Drogerie](https://www.lilly.rs/vichy-dermablend-corrector-tecni-korektivni-puder-spf-35-30-ml-35-sand-53950)

## Workflow

1. **Podaci sa sajta** — naslov, brend i sirov skenirani tekst stranice (`raw_text`) su u `backend/data/products.json`, fotografije su skinute u `backend/data/images/<id>/`. Ovaj oblik je namerno blizak onome što bi scraper realno vratio (plain text + slike, bez ručno iseckanih polja) — kad kolega poveže pravi scraping, dovoljno je puniti isti `Product` oblik.
2. **Podaci sa slika** — jedan vision poziv po ponudi pročita sve fotografije i vrati strukturirane podatke (tekst sa ambalaže, nijansa, zapremina, sastojci, upozorenja, tvrdnje). Rezultat se kešira u `backend/data/image_facts.cache.json`.
3. **Poređenje** — oba skupa podataka (sajt + slike) idu u jedan poziv koji proverava tačno 7 unapred definisanih dimenzija (`product_identity`, `brand`, `shade`, `volume`, `ingredients`, `warnings`, `images_vs_text` — vidi `ComparisonField` u `backend/src/schemas.py`) sa statusom (`match` / `minor` / `mismatch` / `missing`), ozbiljnošću i objašnjenjem na srpskom. Taj fiksni skup polja je namerno zatvoren (ne slobodan tekst) da model ne bi flagovao nebitne stvari (cenu, šifru, kategoriju) niti izmišljao nova polja.

## Pokretanje

```sh
# backend (http://127.0.0.1:8000)
cd backend
cp .env.example .env   # upisi XAI_API_KEY
uv run uvicorn main:app --reload --app-dir src

# frontend (http://localhost:5173), proksira /api i /images na backend
cd frontend
npm install
npm run dev
```

## API

| Ruta | Opis |
| --- | --- |
| `GET /api/products` | Lista hardkodiranih ponuda |
| `POST /api/compare` | `{"a": "jankovic", "b": "lilly"}` → podaci sa slika + izveštaj o razlikama |
| `GET /images/<id>/<fajl>` | Fotografije proizvoda |

Poređenje traje ~2 minuta (grok-4.6 je reasoning model); čitanje slika se radi samo prvi put.

## Dodavanje novog proizvoda

Skini slike u `backend/data/images/<novi-id>/` i dodaj novi objekat (`id`, `source`, `url`, `title`, `brand`, `raw_text`, `images`) u listu u `backend/data/products.json`. Frontend ga automatski pokupi u dropdown-ovima.

## Struktura backend-a

```
backend/
  src/          # aplikacioni kod (config, main, llm, products, schemas)
  tests/        # manuelna provera konekcije ka xAI API-ju
  data/         # products.json, keš pročitanih slika, fotografije proizvoda
```
