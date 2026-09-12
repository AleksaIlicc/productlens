# Scraping

Pretraga interneta + skrejpovanje, bez ikakve LLM obrade — za uneto ime
proizvoda nalazi **sve linkove do tog proizvoda, i domaće (.rs) i svetske**,
skrejpuje najbolje strane i sprema čist paket podataka (`payload.offers`) koji
LLM korak za poređenje pojede.

Kod živi izolovano (`backend/src/scraper/**`, `frontend/src/scraper/**`,
`/api/scraper/*`) da bi se lako menjao bez diranja LLM/poređenje dela; jedine
dodirne tačke su import + `include_router` u `backend/src/main.py`, ruta u
`frontend/src/main.tsx`, i `frontend/src/search.ts` koji ponude pretvara u
`Product` za `/api/compare` (vidi „Spoj sa LLM delom" ispod). Glavna strana
(`/`) zove ovo za pretragu proizvoda; strana `/scraper` je napredni/debug
prikaz istog `/discover` poziva sa punim detaljima (kandidati, skorovi,
pozivi provajdera).

## Pokretanje

```sh
# backend (http://127.0.0.1:8000)
cd backend
cp .env.example .env    # upiši FIRECRAWL_API_KEY i EXA_API_KEY (i XAI_API_KEY za LLM deo)
uv sync
uv run uvicorn main:app --reload --app-dir src

# frontend (http://localhost:5173) — scraper strana je na /scraper
cd frontend
npm install
npm run dev
```

Otvori **http://localhost:5173/scraper**, unesi npr. `Vichy Dermablend Corrector 35 Sand`
i pokreni pretragu. Traje 15–60 s za prvi put, ponovljeni isti upit ide iz keša
(~2 s, bez troška).

## Rute

| Ruta | Opis |
| --- | --- |
| `GET /api/scraper/health` | ima li ključeva, stanje keša, broj sačuvanih runova. `?ping=true` pozove provajdere (troši kredite) |
| `POST /api/scraper/discover` | glavna ruta: pretraga → rangiranje → skrejpovanje → podaci + slike + `payload` |
| `POST /api/scraper/scrape` | skrejpuj jedan URL (`{"url": "...", "provider": "firecrawl"}`) |
| `GET /api/scraper/runs` | lista prethodnih runova (sačuvani na disku) |
| `GET /api/scraper/runs/{run_id}` | ceo odgovor jednog runa, bez novih API poziva |
| `GET /api/scraper/image?url=...` | proxy za slike (neki sajtovi blokiraju hotlink); odbija privatne adrese i ne-slike |

```sh
curl -s http://127.0.0.1:8000/api/scraper/health

curl -s -X POST http://127.0.0.1:8000/api/scraper/discover \
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
   editorial grafike (i kad im se pravo ime/ekstenzija krije u `?url=`
   query parametru nekog CDN proxy-ja, npr. Next.js image optimizera); iste
   slike u više veličina i pod različitim cache hash-evima se spajaju u
   jednu (najveća varijanta pobeđuje), a kada shop imenuje fajlove po
   proizvodu (GTIN/SKU), zadržavaju se samo te slike — tako u galeriju ne
   ulaze „povezani proizvodi“. Glavna/`og` slika je prva. Ovo je čisto
   heuristika (ime fajla/putanje); fotografije koje su suštinski PRAVE
   fotografije nekog DRUGOG proizvoda (npr. generalni retailer koji na
   istoj strani ubaci i slike iz drugih linija) prolaze ovaj filter i
   hvata ih tek LLM korak niže (vidi ispod).

## `payload` — spoj sa LLM delom

To je jedina stvar koju LLM korak treba od nas — namerno uzak oblik, ne dump
svega što `extract.py` nađe (cena/dostupnost/SKU/GTIN ostaju samo na
`pages[].facts` za napredni prikaz, van su domašaja poređenja):

```json
{
  "product_query": "Vichy Dermablend Corrector 35 Sand",
  "generated_at": "2026-09-12T12:15:02+00:00",
  "offers": [
    {
      "url": "https://www.apotekajankovic.rs/vichy-dermablend-corrector-...",
      "domain": "apotekajankovic.rs",
      "title": "VICHY DERMABLEND CORRECTOR Tečni korektivni puder SPF 35, 30 ml, 35 Sand",
      "images": ["https://www.apotekajankovic.rs/image/cache/.../3337871316617_1-640x640.webp"],
      "specs": {},
      "description": "…",
      "markdown": "…"
    }
  ]
}
```

**Ovo je spojeno** sa LLM delom (`frontend/src/search.ts`): svaki `offer` se
klijentski pretvori u `Product` (`description`/`specs` → `raw_text`, `images`
ostaju puni URL-ovi) i ide direktno na `POST /api/compare` — korisnik na
glavnoj strani pretraži proizvod, dobijene ponude se dodaju u padajuće liste,
i bira bilo koje dve za poređenje. Nema hardkodiranih/demo proizvoda; `a`/`b`
u `/api/compare` su uvek ceo `Product` objekat. Slike sa udaljenih URL-ova se
za vision poziv preuzimaju preko istog SSRF-bezbednog fetch-a koji koristi i
`/api/scraper/image` (`scraper/http.fetch_image_bytes`).
Ovaj router ostaje — sad služi kao napredni prikaz jednog runa (kandidati,
skorovi, pozivi provajdera), dok glavna strana zove isti `/discover` sa
razumnim podrazumevanim opcijama i ne prikazuje te detalje.

**Drugi filter slika, na LLM strani** (`backend/src/llm.py`): pošto se slike
preuzmu, ako ih ima 3+ jedan manji model (`xai_filter_model`) dobije naziv
proizvoda plus sve fotografije i vrati koje pripadaju toj ponudi. Ovo hvata
ono što heuristika u `images.py` ne može — prave fotografije DRUGOG proizvoda
sa iste strane (npr. generalni retailer sa „srodni proizvodi" galerijom).

Granica je namerno postavljena ovako: **drugi proizvod i chrome sajta se
bacaju, ista linija u pogrešnoj nijansi/varijanti se ZADRŽAVA.** Prodavnica
koja uz „35 Sand" prikazuje baner sa tubom „25 Nude" je upravo nalaz koji
poređenje treba da prijavi, pa filter ne sme tiho da ukloni dokaz. Uz to,
prompt greši u korist zadržavanja („ako nisi siguran, zadrži") da ne bismo
za neku ponudu ostali bez ijedne slike.

Pre slanja se odbacuju i slike manje od 512 piksela, kao i formati koje API
ne dekodira (GIF, BMP, AVIF — Pillow ih otvara, xAI ne prima). Oba su nužna
jer xAI vision API zbog **jedne** neupotrebljive slike odbije ceo poziv, a
svaka slika se šalje sa svojim stvarnim media tipom, ne paušalno kao JPEG. Odgovor `/api/compare` vraća `a`/`b` sa `images` suženim na
ono što je stvarno analizirano (`main._analyzed`), tako da UI posle poređenja
prikazuje istu galeriju koju je i model video.

## Keš i runovi

- `backend/data/scraper_cache/` — sirovi odgovori provajdera (TTL 24 h), po tipu poziva.
- `backend/data/scraper_runs/<run_id>.json` — ceo odgovor svakog runa, za `/runs`.
- Oba su u `.gitignore`. Brisanje: `rm -rf backend/data/scraper_cache backend/data/scraper_runs`.
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
- **Sephora.com odbija i preuzimanje slika**, ne samo skrejp stranice: CDN
  (`sephora.com/productimages/...`) vraća grešku serverskom fetch-u čak i kad je
  sama stranica uspešno pročitana (potvrđeno uživo). Vision korak tada dobije
  prazne `ImageFacts` za tu stranu i poređenje se oslanja samo na tekst.
- **Specifikacija** se izvlači samo kada je na strani u tabeli ili `key: value`
  formatu; mnogi .rs shopovi je nemaju strukturirano, pa `specs` ostaje prazan, a
  podaci su u `markdown`/`description`.
- Domenske liste u `merge.py` (`SR_SHOP_DOMAINS`, `WORLD_SHOP_DOMAINS`,
  `NOISE_DOMAINS`…) su kustomizovane ručno — dopuni ih kada naletiš na dobar shop.
