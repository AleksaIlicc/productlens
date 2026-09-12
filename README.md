# ProductLens

Poredi istu stavku na dve online prodavnice i flaguje neslaganja preko LLM-a (xAI Grok).

Trenutno su hardkodirana dva izvora za isti artikal (Vichy Dermablend Corrector SPF 35, 30 ml, 35 Sand):

- [Apoteka Janković](https://www.apotekajankovic.rs/vichy-dermablend-corrector-tecni-korektivni-puder-spf-35-30-ml-35-sand)
- [Lilly Drogerie](https://www.lilly.rs/vichy-dermablend-corrector-tecni-korektivni-puder-spf-35-30-ml-35-sand-53950)

## Workflow

1. **Podaci sa sajta** — naslov, cena, specifikacija i opisne sekcije su prepisani u `backend/products.py`, fotografije su skinute u `backend/data/images/<id>/`.
2. **Podaci sa slika** — jedan vision poziv po ponudi pročita sve fotografije i vrati strukturirane podatke (tekst sa ambalaže, nijansa, zapremina, SPF, tvrdnje). Rezultat se kešira u `backend/data/image_facts.cache.json`.
3. **Poređenje** — oba skupa podataka (sajt + slike) idu u jedan poziv koji vraća listu polja sa statusom (`match` / `minor` / `mismatch` / `missing`), ozbiljnošću i objašnjenjem razlike na srpskom.

## Pokretanje

```sh
# backend (http://127.0.0.1:8000)
cd backend
cp .env.example .env   # upisi XAI_API_KEY
uv run uvicorn main:app --reload

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

Skini slike u `backend/data/images/<novi-id>/` i dodaj `Product(...)` u `PRODUCTS` u `backend/products.py`. Frontend ga automatski pokupi u dropdown-ovima.
