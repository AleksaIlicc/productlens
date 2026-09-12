"""Hardkodirani podaci sastrugani sa dve prodavnice — jedan te isti artikal.

Tekst je prepisan doslovno sa stranica proizvoda, zato su linije duge (ruff: E501).
"""

from pydantic import BaseModel

INCI = (
    "AQUA - UNDECANE - DIMETHICONE - GLYCERIN - TRIDECANE - POLYGLYCERYL-4 ISOSTEARATE - "
    "PENTYLENE GLYCOL - CETYL PEG/PPG-10/1 DIMETHICONE - HEXYL LAURATE - MAGNESIUM SULFATE - "
    "DISTEARDIMONIUM HECTORITE - CELLULOSE GUM - ALUMINUM HYDROXIDE - DISODIUM STEAROYL "
    "GLUTAMATE - TRISTEARIN - ACETYLATED GLYCOL STEARATE - ACRYLATES COPOLYMER - "
    "ETHYLHEXYLGLYCERIN - CI 77891 - CI 77492 - CI 77491 - CI 77499"
)

JANKOVIC_OPIS = """Vichy DERMABLEND CORRECTOR Tečni korektivni puder SPF35, 35 Sand
Savršeno prekrivanje 16h, osećaj „gole kože”. Mat efekat. Za žene koje žele prekriti lagane do umerene nepravilnosti na koži (neravnomeran ten, podočnjaci, crvenilo, ožiljci itd.).
Njegova hipoalergena formula visoke tolerancije testirana je pod dermatološkim nadzorom na osetljivoj koži.
Nekomedogeno, bez mirisa, SPF 35. 24-časovna hidratacija.
Formula korektivnog tečnog pudera za lice Dermablend spaja visoku koncentraciju pigmenata za optimalno prekrivanje i izuzetno upijajuću i laganu teksturu koja koži daje prirodan izgled i osećaj prijatnosti tokom celog dana. U kontaktu sa epidermisom tekstura postaje tečnija a pigmenti boje se slivaju po celoj površini i potpuno prekrivaju nepravilnosti na koži, a da se ne nakupljaju u grudvice ili stvaraju utisak suve maske.
Ovaj puder Vam nudi trostruko delovanje: visoku moć pokrivanja 16h + prirodan izgled lepote + optimalan osećaj prijatnosti: 24-satna hidratacija.
1. 30% koncentracija pigmenata za savršeno pokrivanje.
2. Pigmenti „soft-focus”, koji prekrivaju nepravilnosti i tako stvaraju lepu kožu kao klasični puderi za lice.
3. Obogaćen glicerinom i eteričnim uljem biljnog porekla, koji ga čine glatkim, tečnim i prijatnim.
U dodiru sa toplotom kože pretvara se u fluid, a njegova tekstura stvara izuzetno tanak sloj bez naglašavanja bora i bez masnog traga na koži. Ten je u potpunosti ujednačen sa prirodnim efektom „gole kože”.
Nepravilnosti kože su u trenutku prekrivene bez tragova ili grudvica. Ten je ravnomeran i sjajan, koža je elastična i izgleda prirodno, prati je osećaj prijatnosti. Bez efekta maske."""

JANKOVIC_UPOTREBA = """1. Nanesite korektivni tečni puder vrhovima prstiju ili pomoću sunđerčića na kožu laganim pokretima i razmažite od sredine lica prema krajevima. U slučaju većih nepravilnosti utapkajte puder na to područje i nežno ga razmažite kružnim pokretima.
2. Razmažite prema vratu, ušima i ka liniji kose pa obrišite ivice.
3. Ponovite nanošenje dok ne dobijete željenu prekrivenost."""

LILLY_OPIS = """Formula korektivnog tečnog pudera za lice Dermablend spaja visoku koncentraciju pigmenata za optimalno prekrivanje i izuzetno upijajuću i laganu teksturu koja koži daje prirodan izgled i osećaj prijatnosti tokom celog dana.
U kontaktu sa epidermisom tekstura postaje tečnija a pigmenti boje se slivaju po celoj površini i potpuno prekrivaju nepravilnosti na koži, a da se ne nakupljaju u grudvice ili stvaraju utisak suve maske.
U dodiru sa toplotom kože pretvara se u fluid, a njegova tekstura stvara izuzetno tanak sloj bez naglašavanja bora i bez masnog traga na koži. Ten je u potpunosti ujednačen sa prirodnim efektom „gole kože”.
Njegova hipoalergena formula visoke tolerancije testirana je pod dermatološkim nadzorom na osetljivoj koži. Nepravilnosti kože su u trenutku prekrivene bez tragova ili grudvica. Ten je ravnomeran i sjajan, koža je elastična i izgleda prirodno, prati je osećaj prijatnosti.
Bez efekta maske.
Nijansa: 35 Sand."""

LILLY_DEJSTVO = """Savršeno prekrivanje 16h, osećaj „gole kože”. Mat efekat. Za žene koje žele prekriti lagane do umerene nepravilnosti na koži (neravnomeran ten, podočnjaci, crvenilo, ožiljci itd.). Njegova hipoalergena formula visoke tolerancije testirana je pod dermatološkim nadzorom na osetljivoj koži. Nekomedogeno, bez mirisa, SPF 35. 24-časovna hidratacija. Formula korektivnog tečnog pudera za lice Dermablend spaja visoku koncentraciju pigmenata za optimalno prekrivanje i izuzetno upijajuću i laganu teksturu koja koži daje prirodan izgled i osećaj prijatnosti tokom celog dana. U kontaktu sa epidermisom tekstura postaje tečnija a pigmenti boje se slivaju po celoj površini i potpuno prekrivaju nepravilnosti na koži, a da se ne nakupljaju u grudvice ili stvaraju utisak suve maske. Ovaj puder Vam nudi trostruko delovanje: visoku moć pokrivanja 16h + prirodan izgled lepote + optimalan osećaj prijatnosti: 24-satna hidratacija. 1. 30% koncentracija pigmenata za savršeno pokrivanje. 2. Pigmenti „soft-focus”, koji prekrivaju nepravilnosti i tako stvaraju lepu kožu kao klasični puderi za lice. 3. Obogaćen glicerinom i eteričnim uljem biljnog porekla, koji ga čine glatkim, tečnim i prijatnim. U dodiru sa toplotom kože pretvara se u fluid, a njegova tekstura stvara izuzetno tanak sloj bez naglašavanja bora i bez masnog traga na koži. Ten je u potpunosti ujednačen sa prirodnim efektom „gole kože”. Nepravilnosti kože su u trenutku prekrivene bez tragova ili grudvica. Ten je ravnomeran i sjajan, koža je elastična i izgleda prirodno, prati je osećaj prijatnosti. Bez efekta maske."""


class Product(BaseModel):
    id: str
    source: str
    url: str
    title: str
    brand: str
    price: str
    availability: str
    specs: dict[str, str]
    sections: dict[str, str]
    images: list[str]


PRODUCTS: list[Product] = [
    Product(
        id="jankovic",
        source="Apoteka Janković",
        url="https://www.apotekajankovic.rs/vichy-dermablend-corrector-tecni-korektivni-puder-spf-35-30-ml-35-sand",
        title="VICHY DERMABLEND CORRECTOR Tečni korektivni puder SPF 35, 30 ml, 35 Sand",
        brand="VICHY",
        price="2.904,81 RSD",
        availability="Na stanju",
        specs={
            "Šifra": "4004",
            "Proizvođač": "VICHY",
            "Pakovanje": "30 ml",
            "Kategorija": "Medicinska kozmetika » Lice » Osetljiva koža",
        },
        sections={
            "Opis": JANKOVIC_OPIS,
            "Način upotrebe": JANKOVIC_UPOTREBA,
            "Sastav": INCI + ".",
            "Pakovanje": "30ml",
        },
        images=["1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg", "6.jpg"],
    ),
    Product(
        id="lilly",
        source="Lilly Drogerie",
        url="https://www.lilly.rs/vichy-dermablend-corrector-tecni-korektivni-puder-spf-35-30-ml-35-sand-53950",
        title="Vichy Dermablend Corrector Tečni korektivni puder SPF 35, 30 ml, 35 Sand",
        brand="VICHY",
        price="3.259,99 RSD",
        availability="Na stanju",
        specs={
            "SKU": "53950",
            "Brend": "VICHY",
            "Barcode": "3337871316617",
            "Cena po jedinici": "10.866,63 RSD za 100ML",
            "Ocena": "5/5 (1 recenzija)",
        },
        sections={
            "Opis": LILLY_OPIS,
            "Namena": "Puder za lice.",
            "Sastav": INCI,
            "Dejstvo": LILLY_DEJSTVO,
        },
        images=["1.jpg", "2.jpg", "3.jpg", "4.jpg", "5.jpg"],
    ),
]

BY_ID: dict[str, Product] = {p.id: p for p in PRODUCTS}
