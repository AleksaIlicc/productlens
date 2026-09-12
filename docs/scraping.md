# Scraping lab (privremeno)

Ovo je **naš deo** ProductLens-a: pretraga interneta + skrejpovanje, bez ikakve LLM
obrade. Cilj je da za uneto ime proizvoda nađemo **sve linkove do tog proizvoda —
i domaće (.rs) i svetske** — skrejpujemo najbolje strane i spremimo čist paket
podataka (`payload.offers`) koji LLM korak za poređenje kasnije samo pojede.

Sve živi u novim fajlovima (`backend/src/lab/**`, `frontend/src/lab/**`) i visi na
`/api/lab/*` i strani `/lab`, da se ne sudara sa LLM delom. Jedine izmene u
postojećim fajlovima su dve linije u `backend/src/main.py` i dve u
`frontend/src/main.tsx` (uključivanje rute).

## Pokretanje

```sh
# backend (http://127.0.0.1:8000)
cd backend
cp .env.example .env    # upiši FIRECRAWL_API_KEY i EXA_API_KEY (i XAI_API_KEY za LLM deo)
uv sync
uv run uvicorn main:app --reload --app-dir src

# frontend (http://localhost:5173) — lab strana je na /lab
cd frontend
npm install
npm run dev
```

> Na Windows-u sa cp1252 lokalom `backend/src/products.py` pada pri startu
> (`products.json` se čita bez `encoding="utf-8"`). Do ispravke u tom fajlu,
> pokreni backend sa UTF-8 modom: `PYTHONUTF8=1 uv run uvicorn main:app --app-dir src`.

Otvori **http://localhost:5173/lab**, unesi npr. `Vichy Dermablend Corrector 35 Sand`
i pokreni pretragu. Traje 15–60 s za prvi put, ponovljeni isti upit ide iz keša
(~2 s, bez troška).

## Rute

| Ruta | Opis |
| --- | --- |
| `GET /api/lab/health` | ima li ključeva, stanje keša, broj sačuvanih runova. `?ping=true` pozove provajdere (troši kredite) |
| `POST /api/lab/discover` | glavna ruta: pretraga → rangiranje → skrejpovanje → podaci + slike + `payload` |
| `POST /api/lab/scrape` | skrejpuj jedan URL (`{"url": "...", "provider": "firecrawl"}`) |
| `GET /api/lab/runs` | lista prethodnih runova (sačuvani na disku) |
| `GET /api/lab/runs/{run_id}` | ceo odgovor jednog runa, bez novih API poziva |
| `GET /api/lab/image?url=...` | proxy za slike (neki sajtovi blokiraju hotlink); odbija privatne adrese i ne-slike |

```sh
curl -s http://127.0.0.1:8000/api/lab/health

curl -s -X POST http://127.0.0.1:8000/api/lab/discover \
  -H "Content-Type: application/json" \
  -d '{"query":"Vichy Dermablend Corrector 35 Sand","scrape_top":6}'
```

## Opcije `discover`

| Polje | Default | Šta radi |
| --- | --- | --- |
| `query` | — | ime proizvoda |
| `scope` | `both` | `both` = i domaće i svetske (ništa se ne filtrira po regionu), `rs` = samo .rs/region, `world` = samo svet |
| `limit_candidates` | 24 | koliko rangiranih linkova vraćamo |
| `scrape_top` | 6 | koliko strana zaista skrejpujemo (0 = samo linkovi, bez troška skrejpa) |
| `min_rs_pages` / `min_world_pages` | 2 / 2 | kvota: garantuje da među skrejpovanim stranama ima i domaćih i svetskih |
| `providers` | `["exa","firecrawl"]` | isključi jedan ako testiraš |
| `include_domains` / `exclude_domains` | `[]` | ručno sužavanje (npr. samo `lilly.rs, notino.com`) |
| `include_image_search` | `true` | Firecrawl image search kao dodatni izvor linkova i slika |
| `deep_domain_map` | `false` | Firecrawl `/map` po poznatim shop domenima koji se nisu pojavili u pretrazi — najveći recall, ~10 s po domenu |
| `use_cache` | `true` | čita sa diska; `false` tera nove API pozive |
| `max_markdown_chars` | 20000 | koliko markdown-a čuvamo po strani |

## Kako radi

1. **Upiti** (`pipeline.build_queries`) — za isti proizvod pravimo i domaće i
   svetske varijante: `"<ime> site:rs"` i `"<ime> cena kupovina"` (Firecrawl bez
   `site:rs` vraća .pl/.sk/amazon šum), pa `"<ime>"` i `"<ime> buy online price"`.
   Exa dobija tri poziva: sa .rs whitelistom, sa svetskim whitelistom, i bez filtera.
2. **Provajderi** — Firecrawl je recall (široka pretraga, image search, `/map`,
   skrejpovanje), Exa je precision (sa whitelistom vraća skoro isključivo prave
   product strane) i jeftin fallback čitač za strane koje Firecrawl ne može.
3. **Spajanje i rangiranje** (`merge.py`) — dedup po kanonskom URL-u (skidaju se
   `utm_*`, `srsltid`, `gclid`, `www`, trailing slash), pa skor: oba provajdera
   +2.0, tip strane (proizvod +2.0, kategorija −1.0, video −3.0), pozicija,
   poznata prodavnica +1.0 (**domaća i svetska isto**), poklapanje naziva do +2.5
   (dijakritika se normalizuje: „tečni“ == „tecni“), bez poklapanja −2.0, domen
   koji se teško skrejpuje −0.8, `.rs` preferencija samo +0.35 (tie-break, ne filter).
   Svaki doprinos se vidi u `score_reasons` (hover na skor u tabeli).
4. **Izbor za skrejp** (`pick_to_scrape`) — top-N, ali max 2 strane po domenu i
   kvote po regionu, da domaće ne pojedu svetske i obrnuto.
5. **Skrejpovanje** (`providers/firecrawl.py`) — `markdown + links + images + rawHtml`,
   `onlyMainContent: false` (strip glavnog sadržaja pojede cenu i galeriju na
   nekim .rs sajtovima). `rawHtml` se **odmah svodi na digest** (JSON-LD blokovi +
   `<head>` + `itemprop` fragmenti) jer je npr. lilly.rs rawHtml 7.5 MB.
   Strana koja se skoro nije renderovala dobija jedan retry sa `waitFor: 5000`
   (dm.rs i slični Angular shopovi), a blokirana strana ide na Exa `/contents`.
6. **Ekstrakcija** (`extract.py`) — deterministički, bez LLM-a, po lestvici
   JSON-LD → microdata → meta/og → markdown regex: naslov, brend, cena (+ stara
   cena), valuta, dostupnost, SKU, GTIN/EAN, breadcrumbs, specifikacija, opis,
   varijante (SPF/ml/nijansa). GTIN se validira mod-10 proverom, a hvata se i iz
   imena fajlova slika (lilly i jankovic slike se zovu po EAN-u `3337871316617`).
7. **Slike** (`images.py`) — spajaju se Firecrawl `images`, `og:image` i Exa
   `imageLinks`, pa se čiste: izbacuju se logoi, banneri, stikeri, ikonice i
   editorial grafike; iste slike u više veličina i pod različitim cache hash-evima
   se spajaju u jednu (najveća varijanta pobeđuje), a kada shop imenuje fajlove po
   proizvodu (GTIN/SKU), zadržavaju se samo te slike — tako u galeriju ne ulaze
   „povezani proizvodi“. Glavna/`og` slika je prva.

## `payload` — spoj sa LLM delom

To je jedina stvar koju LLM korak treba od nas:

```json
{
  "product_query": "Vichy Dermablend Corrector 35 Sand",
  "generated_at": "2026-09-12T12:15:02+00:00",
  "offers": [
    {
      "url": "https://www.apotekajankovic.rs/vichy-dermablend-corrector-...",
      "domain": "apotekajankovic.rs",
      "region": "rs",
      "title": "VICHY DERMABLEND CORRECTOR Tečni korektivni puder SPF 35, 30 ml, 35 Sand",
      "brand": "VICHY",
      "price": { "raw": "2904.81", "amount": 2904.81, "currency": "RSD" },
      "availability": "Na stanju",
      "sku": "4004",
      "gtin": "3337871316617",
      "images": ["https://www.apotekajankovic.rs/image/cache/.../3337871316617_1-640x640.webp"],
      "specs": {},
      "description": "…",
      "markdown": "…"
    }
  ]
}
```

Predlog spajanja: LLM deo umesto hardkodiranih ponuda iz `products.json` uzima
`offers` (svaka je jedan sajt) — `images` su direktni URL-ovi za vision poziv,
`markdown` je tekst strane, a `gtin`/`sku`/`variant_hints` su najjači signal da li
je uopšte reč o istom proizvodu. Kada se spoji, ovaj router se briše.

## Keš i runovi

- `backend/data/lab_cache/` — sirovi odgovori provajdera (TTL 24 h), po tipu poziva.
- `backend/data/lab_runs/<run_id>.json` — ceo odgovor svakog runa, za `/runs`.
- Oba su u `.gitignore`. Brisanje: `rm -rf backend/data/lab_cache backend/data/lab_runs`.
- Keširan poziv se ne broji u trošak (`totals.cache_hits` vs `firecrawl_credits`/`exa_cost_usd`).

Realni troškovi po runu (`scrape_top: 5–6`, bez keša): ~18–23 Firecrawl kredita i
~$0.05 Exa. Sa kešom: 0.

## Poznata ograničenja

- **Cene u različitim valutama** se ne konvertuju (RSD, EUR, USD, GBP kako sajt kaže).
  Neki shopovi u meta tagu daju broj bez valute (apotekajankovic `price` je ~EUR
  vrednost) — tada `currency` ostaje prazan, a `raw` je sačuvan.
- Neki sajtovi daju podatke za **drugu nijansu/varijantu** nego što je na strani
  (apoteka-online og slika i GTIN su od „25 Nude“ na strani za „35 Sand“) — to je
  upravo tip neslaganja koje LLM korak treba da flaguje, ne krijemo ga.
- **Marketplace-ovi (amazon, ebay) i pojedini svetski shopovi** imaju bot zaštitu;
  ostaju u listi linkova ali su blago spušteni u skoru i često padnu na skrejpu.
- **Specifikacija** se izvlači samo kada je na strani u tabeli ili `key: value`
  formatu; mnogi .rs shopovi je nemaju strukturirano, pa `specs` ostaje prazan, a
  podaci su u `markdown`/`description`.
- Domenske liste u `merge.py` (`SR_SHOP_DOMAINS`, `WORLD_SHOP_DOMAINS`,
  `NOISE_DOMAINS`…) su kustomizovane ručno — dopuni ih kada naletiš na dobar shop.
