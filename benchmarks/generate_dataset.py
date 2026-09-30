"""Generate benchmarks/dataset.jsonl: 100 synthetic French texts with the exact position of each personal data item.

Every value is fake (Faker fr_FR, fixed seed) except city names and postcodes, which are public. Identifiers carry
valid check digits, as real ones would: NIR key, tax number mod 511, IBAN mod 97, card Luhn, valid phone numbers.
Texts also hold data that is not personal (dates, amounts, file numbers, company names and SIRET), so that
detectors can be wrong in both directions.

Run with `uv run python benchmarks/generate_dataset.py`; the same seed gives the same file. `--seed` and `--output`
generate a held-out set, to check that a change to the recognizers helps beyond the texts it was tuned on.
"""

import argparse
import json
import random
from collections.abc import Callable
from datetime import date as Date, timedelta
from pathlib import Path

import phonenumbers
from faker import Faker

SEED = 116
TEXTS_PER_KIND = 10
OUTPUT = Path(__file__).with_name("dataset.jsonl")

fake = Faker("fr_FR")
rng = random.Random()

# Public data: real communes and one of their postcodes.
CITIES = [
    ("Paris", "75011"), ("Paris", "75018"), ("Lyon", "69003"), ("Marseille", "13006"), ("Toulouse", "31000"),
    ("Nice", "06000"), ("Nantes", "44000"), ("Strasbourg", "67000"), ("Montpellier", "34000"), ("Bordeaux", "33000"),
    ("Lille", "59000"), ("Rennes", "35000"), ("Reims", "51100"), ("Saint-Étienne", "42000"), ("Le Havre", "76600"),
    ("Toulon", "83000"), ("Grenoble", "38000"), ("Dijon", "21000"), ("Angers", "49000"), ("Nîmes", "30000"),
    ("Villeurbanne", "69100"), ("Clermont-Ferrand", "63000"), ("Le Mans", "72000"), ("Aix-en-Provence", "13100"),
    ("Brest", "29200"), ("Tours", "37000"), ("Amiens", "80000"), ("Limoges", "87000"), ("Annecy", "74000"),
    ("Perpignan", "66000"), ("Metz", "57000"), ("Besançon", "25000"), ("Orléans", "45000"), ("Rouen", "76000"),
    ("Mulhouse", "68100"), ("Caen", "14000"), ("Nancy", "54000"), ("Montreuil", "93100"), ("Avignon", "84000"),
    ("Poitiers", "86000"), ("La Rochelle", "17000"), ("Pau", "64000"), ("Ajaccio", "20000"), ("Bastia", "20200"),
    ("Châlons-en-Champagne", "51000"), ("Boulogne-sur-Mer", "62200"), ("Saint-Malo", "35400"), ("Vannes", "56000"),
]
STREET_TYPES = ["rue", "rue", "rue", "avenue", "boulevard", "place", "chemin", "allée", "impasse", "quai", "route"]
STREET_PEOPLE = ["Victor Hugo", "Jean Jaurès", "Émile Zola", "Pasteur", "Gambetta", "Voltaire", "Jean Moulin"]
STREET_THINGS = ["de la Paix", "des Lilas", "du Port", "de la Gare", "des Écoles", "du Moulin", "de la République"]
COMPANY_NAMES = ["Horizon Gestion", "Immo Centre", "Les Tilleuls", "Atlantique Habitat", "Patrimoine et Conseil",
                 "Gestion Plus", "Val de Loire Immobilier", "Les Terrasses du Parc"]
EMAIL_DOMAINS = ["example.fr", "exemple.com", "mail.example.org", "example.net"]

Segment = str | tuple[str, str]


# --- Values with valid check digits ---------------------------------------------------------------------------


def nir(sex: int) -> str:
    department = rng.choice([f"{d:02d}" for d in range(1, 96) if d != 20] + ["2A", "2B"])
    digits = f"{sex}{rng.randint(50, 99):02d}{rng.randint(1, 12):02d}{department}{rng.randint(1, 990):03d}"
    digits += f"{rng.randint(1, 999):03d}"
    number = int(digits.replace("2A", "19").replace("2B", "18"))
    raw = f"{digits}{97 - number % 97:02d}"
    if rng.random() < 0.5:
        return raw
    return " ".join([raw[0], raw[1:3], raw[3:5], raw[5:7], raw[7:10], raw[10:13], raw[13:]])


def fiscal_number() -> str:
    first = f"{rng.randint(0, 3)}{rng.randint(0, 999_999_999):09d}"
    raw = f"{first}{int(first) % 511:03d}"
    return raw if rng.random() < 0.4 else f"{raw[:2]} {raw[2:4]} {raw[4:7]} {raw[7:10]} {raw[10:]}"


def iban() -> str:
    raw = fake.iban()
    return raw if rng.random() < 0.3 else " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def card() -> str:
    raw = fake.credit_card_number(card_type=rng.choice(["visa16", "mastercard"]))
    return raw if rng.random() < 0.3 else " ".join(raw[i : i + 4] for i in range(0, len(raw), 4))


def phone() -> str:
    while True:
        national = f"0{rng.choice('1234567')}{rng.randint(10_000_000, 99_999_999)}"
        if phonenumbers.is_valid_number(phonenumbers.parse(national, "FR")):
            break
    pairs = [national[i : i + 2] for i in range(0, 10, 2)]
    return rng.choice([
        " ".join(pairs),
        ".".join(pairs),
        national,
        "+33 " + national[1] + " " + " ".join(pairs[1:]),
        "+33 (0)" + national[1] + " " + " ".join(pairs[1:]),
    ])


# --- People and places ----------------------------------------------------------------------------------------


def ascii_fold(text: str) -> str:
    table = str.maketrans("àâäçéèêëîïôöùûüÿ", "aaaceeeeiioouuuy")
    return text.lower().translate(table).replace(" ", "").replace("'", "")


def person() -> dict:
    sex = rng.choice([1, 2])
    first = fake.first_name_male() if sex == 1 else fake.first_name_female()
    last = fake.last_name()
    city, postcode = rng.choice(CITIES)
    kind = rng.random()
    if kind < 0.3:
        street_name = rng.choice(STREET_PEOPLE)
    elif kind < 0.6:
        street_name = rng.choice(STREET_THINGS)
    else:
        street_name = rng.choice(["", "de ", "du Général "]) + fake.last_name()
    number = str(rng.randint(1, 180)) + rng.choice(["", "", "", " bis"])
    street = f"{number}{rng.choice([' ', ', '])}{rng.choice(STREET_TYPES)} {street_name}"
    return {
        "sex": sex,
        "title": "M." if sex == 1 else "Mme",
        "first": first,
        "last": last,
        "name": f"{first} {last}",
        "street": street,
        "postcode": postcode,
        "city": city,
        "email": f"{ascii_fold(first)}.{ascii_fold(last)}@{rng.choice(EMAIL_DOMAINS)}",
        "phone": phone(),
    }


def address(p: dict, separator: str | None = None) -> str:
    return f"{p['street']}{separator or rng.choice([', ', ' ', ', '])}{p['postcode']} {p['city']}"


def company() -> str:
    # Capitalized words that are not personal data. Faker's companies are built from surnames, which would make
    # a detection there neither clearly right nor clearly wrong.
    return rng.choice(["Agence ", "Cabinet ", "SCI "]) + rng.choice(COMPANY_NAMES)


def siret() -> str:
    # Company identifier, not personal data: a distractor for the number recognizers.
    return " ".join(["".join(str(rng.randint(0, 9)) for _ in range(3)) for _ in range(3)]) + f" {rng.randint(0, 99999):05d}"


def day_between(first: Date, last: Date) -> Date:
    # Not Faker's date_between: it goes through local timestamps, so the dates depend on the machine's time zone
    # (the file generated in Paris differed from the one generated on a UTC CI runner).
    return first + timedelta(days=rng.randint(0, (last - first).days))


def date() -> str:
    return day_between(Date(2023, 1, 1), Date(2026, 6, 30)).strftime("%d/%m/%Y")


def sorted_dates(count: int) -> list[str]:
    days = sorted(day_between(Date(2023, 1, 1), Date(2026, 6, 30)) for _ in range(count))
    return [day.strftime("%d/%m/%Y") for day in days]


def birth_date() -> str:
    return day_between(Date(1945, 1, 1), Date(2006, 12, 31)).strftime("%d/%m/%Y")


def amount() -> str:
    return f"{rng.randint(50, 3000)},{rng.choice(['00', '50', '90'])} €"


def reference() -> str:
    return f"{rng.choice(['dossier', 'contrat', 'sinistre', 'commande'])} n° {rng.randint(2021, 2026)}-{rng.randint(1000, 99999)}"


# --- Templates: a list of plain strings and (entity type, value) pairs ---------------------------------------


def tenant_letter() -> list[Segment]:
    tenant, landlord = person(), person()
    return [
        ("PERSON", tenant["name"]), "\n", ("FR_ADDRESS", address(tenant)), "\n\n",
        f"{landlord['title']} ", ("PERSON", landlord["name"]), "\n", ("FR_ADDRESS", address(landlord)), "\n\n",
        f"Objet : restitution du dépôt de garantie\n\n{landlord['title']},\n\n",
        "J'ai quitté le logement situé ", ("FR_ADDRESS", tenant["street"]),
        f" le {date()} et l'état des lieux de sortie ne relève aucune dégradation. Conformément à l'article 22 de la loi du 6 juillet 1989, je vous remercie de me "
        f"restituer le dépôt de garantie de {amount()} par virement sur le compte ",
        ("IBAN_CODE", iban()), ".\n\nVous pouvez me joindre au ", ("PHONE_NUMBER", tenant["phone"]), ".\n\n",
        ("PERSON", tenant["name"]),
    ]


def complaint_email() -> list[Segment]:
    p = person()
    segments: list[Segment] = [
        f"Bonjour,\n\nJe conteste le prélèvement de {amount()} du {date()} ({reference()}). ",
        "Il a été débité sur ma carte ", ("CREDIT_CARD", card()), " alors que la commande a été annulée.\n",
    ]
    if rng.random() < 0.5:
        segments += ["La connexion suspecte venait de l'adresse IP ", ("IP_ADDRESS", fake.ipv4_public()), ".\n"]
    segments += [
        "Merci de me répondre à ", ("EMAIL_ADDRESS", p["email"]), " ou au ", ("PHONE_NUMBER", p["phone"]), ".\n\n",
        "Cordialement,\n", ("PERSON", p["name"]),
    ]
    return segments


def short_message() -> list[Segment]:
    p, friend = person(), person()
    return rng.choice([
        ["Salut ", ("PERSON", friend["first"]), ", c'est ", ("PERSON", p["first"]),
         ". Je suis coincé à ", ("LOCATION", p["city"]), " jusqu'à jeudi, rappelle-moi au ",
         ("PHONE_NUMBER", p["phone"]), " !"],
        ["Coucou, le colis de ", ("PERSON", p["name"]), " est arrivé au ", ("FR_ADDRESS", address(p)),
         ". Tu peux passer le chercher avant 18 h ?"],
        ["RDV confirmé le ", date(), f" à 14 h avec {p['title']} ", ("PERSON", p["last"]),
         ". Son mail : ", ("EMAIL_ADDRESS", p["email"]), "."],
    ])


def membership_form() -> list[Segment]:
    p = person()
    return [
        "FORMULAIRE D'ADHÉSION\n", f"Civilité : {p['title']}\n",
        "Nom : ", ("PERSON", p["last"]), "\nPrénom : ", ("PERSON", p["first"]),
        f"\nDate de naissance : {birth_date()}\n",
        "Adresse : ", ("FR_ADDRESS", p["street"]), f"\nCode postal : {p['postcode']}\nVille : ", ("LOCATION", p["city"]),
        "\nTéléphone : ", ("PHONE_NUMBER", p["phone"]), "\nCourriel : ", ("EMAIL_ADDRESS", p["email"]),
        "\nN° de sécurité sociale : ", ("FR_NIR", nir(p["sex"])), f"\nCotisation annuelle : {amount()}",
    ]


def tax_letter() -> list[Segment]:
    p = person()
    return [
        ("PERSON", p["name"]), "\n", ("FR_ADDRESS", address(p, "\n")), "\n\n",
        "Service des impôts des particuliers de ", ("LOCATION", rng.choice(CITIES)[0]), "\n\n",
        "Objet : demande de délai de paiement\nNuméro fiscal : ", ("FR_FISCAL_NUMBER", fiscal_number()),
        f"\n\nMadame, Monsieur,\n\nSuite à la réception de mon avis d'impôt sur le revenu de {rng.randint(2022, 2025)}, "
        f"d'un montant de {amount()}, je sollicite un échelonnement du paiement en trois mensualités. ",
        "Ma situation a changé depuis mon licenciement le ", date(), ".\n\nJe reste joignable au ",
        ("PHONE_NUMBER", p["phone"]), ".\n\n", ("PERSON", p["name"]),
    ]


def lodging_certificate() -> list[Segment]:
    host, guest = person(), person()
    birth_city = rng.choice(CITIES)[0]
    return [
        "ATTESTATION D'HÉBERGEMENT\n\nJe soussigné(e) ", ("PERSON", host["name"]), ", demeurant au ",
        ("FR_ADDRESS", address(host)), ", atteste sur l'honneur héberger à mon domicile ",
        ("PERSON", guest["name"]), f", né(e) le {birth_date()} à ",
        ("LOCATION", birth_city), f", depuis le {date()}.\n\nFait à ", ("LOCATION", host["city"]),
        f", le {date()}, pour servir et valoir ce que de droit.",
    ]


def sick_leave_note() -> list[Segment]:
    p, manager = person(), person()
    return [
        "Note RH – arrêt de travail\n\nSalarié : ", ("PERSON", p["name"]), f"\nMatricule : {rng.randint(10000, 99999)}\n",
        "N° de sécurité sociale : ", ("FR_NIR", nir(p["sex"])),
        "\nArrêt du {} au {}, transmis à la CPAM le {}.\n".format(*sorted_dates(3)),
        "Manager prévenu : ", ("PERSON", manager["name"]), ". Contact du salarié pendant l'arrêt : ",
        ("PHONE_NUMBER", p["phone"]), ".",
    ]


def refund_request() -> list[Segment]:
    p = person()
    return [
        "Bonjour,\n\nJe vous adresse la facture de consultation du ", date(), f" ({amount()}) pour remboursement. ",
        "Assuré : ", ("PERSON", p["name"]), ", numéro de sécurité sociale ", ("FR_NIR", nir(p["sex"])),
        ".\nMerci de verser le remboursement sur le compte ", ("IBAN_CODE", iban()), ".\n\nBien à vous,\n",
        ("PERSON", p["first"]),
    ]


def appointment_request() -> list[Segment]:
    p, doctor = person(), person()
    return [
        "Bonjour Docteur ", ("PERSON", doctor["last"]), ",\n\nJe souhaiterais un rendez-vous pour mon fils ",
        ("PERSON", fake.first_name_male()), f" la semaine du {date()}. Nous avons déménagé à ",
        ("LOCATION", p["city"]), " et le cabinet est désormais à 20 minutes.\nVous pouvez me rappeler au ",
        ("PHONE_NUMBER", p["phone"]), " ou m'écrire à ", ("EMAIL_ADDRESS", p["email"]), ".\n\n",
        ("PERSON", p["name"]),
    ]


def rent_reminder() -> list[Segment]:
    p = person()
    agency = company()
    return [
        f"{agency}\nSIRET {siret()}\n\n", f"{p['title']} ", ("PERSON", p["name"]), "\n",
        ("FR_ADDRESS", address(p)), "\n\n",
        f"Objet : relance loyer impayé – {reference()}\n\n{p['title']},\n\n",
        f"Sauf erreur de notre part, le loyer de {amount()} dû le {date()} ne nous est pas parvenu. ",
        "Nous vous invitons à régulariser sous huit jours par virement sur le compte ", ("IBAN_CODE", iban()),
        ".\n\nNotre gestionnaire, ", ("PERSON", fake.name()), f", reste à votre disposition.\n\n{agency}",
    ]


KINDS: dict[str, Callable[[], list[Segment]]] = {
    "tenant_letter": tenant_letter,
    "complaint_email": complaint_email,
    "short_message": short_message,
    "membership_form": membership_form,
    "tax_letter": tax_letter,
    "lodging_certificate": lodging_certificate,
    "sick_leave_note": sick_leave_note,
    "refund_request": refund_request,
    "appointment_request": appointment_request,
    "rent_reminder": rent_reminder,
}


def render(segments: list[Segment]) -> tuple[str, list[dict]]:
    text, entities = "", []
    for segment in segments:
        if isinstance(segment, str):
            text += segment
            continue
        entity_type, value = segment
        entities.append({"type": entity_type, "start": len(text), "end": len(text) + len(value), "value": value})
        text += value
    return text, entities


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    Faker.seed(args.seed)
    rng.seed(args.seed)

    lines = []
    for kind, template in KINDS.items():
        for i in range(TEXTS_PER_KIND):
            text, entities = render(template())
            lines.append(json.dumps({"id": f"{kind}-{i}", "kind": kind, "text": text, "entities": entities}, ensure_ascii=False))
    args.output.write_text("\n".join(lines) + "\n")
    print(f"{len(lines)} texts written to {args.output}")


if __name__ == "__main__":
    main()
