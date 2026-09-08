"""Legal Metrology (Packaged Commodities) Rules, 2011 - clause corpus.

This is the statutory ground truth the RAG retriever indexes and the verifier
cites. It ships as a seed corpus; admins can upload amendments at runtime via
POST /api/rules, which re-embeds the vector store instantly (no redeploy).
"""

SEED_CLAUSES: list[dict] = [
    {
        "clause_id": "PCR-2011-R6.1.a",
        "rule_number": "6(1)(a)",
        "title": "Name and address of the manufacturer, packer or importer",
        "text": (
            "Every package shall bear the name and complete address of the manufacturer, "
            "or where the manufacturer is not the packer, the name and complete address of "
            "the manufacturer and the packer. If the commodity is imported, the name and "
            "complete address of the importer shall be declared. A complete address includes "
            "the street, locality, city and PIN code sufficient to locate the premises."
        ),
        "field": "manufacturer",
        "severity": "critical",
    },
    {
        "clause_id": "PCR-2011-R6.1.b",
        "rule_number": "6(1)(b)",
        "title": "Common or generic name of the commodity",
        "text": (
            "Every package shall bear the common or generic name of the commodity contained "
            "in the package. Where the package contains more than one product, the name and "
            "number or quantity of each product shall be declared on the package."
        ),
        "field": "commodity_name",
        "severity": "major",
    },
    {
        "clause_id": "PCR-2011-R6.1.c",
        "rule_number": "6(1)(c)",
        "title": "Net quantity declaration",
        "text": (
            "Every package shall declare the net quantity, in terms of the standard unit of "
            "weight or measure, of the commodity contained in the package. Where the commodity "
            "is sold by number, the number of the commodity contained in the package shall be "
            "declared. The net quantity shall be expressed in metric units: gram (g), kilogram "
            "(kg), millilitre (ml), litre (l), metre (m), or as a count. The expression "
            "net quantity or net weight shall precede the declaration."
        ),
        "field": "net_quantity",
        "severity": "critical",
    },
    {
        "clause_id": "PCR-2011-R6.1.d",
        "rule_number": "6(1)(d)",
        "title": "Month and year of manufacture, packing or import",
        "text": (
            "Every package shall bear the month and year in which the commodity was "
            "manufactured or pre-packed or imported. The declaration shall be in the form "
            "Manufactured in MM/YYYY, Packed in MM/YYYY or Imported in MM/YYYY. For packages "
            "of food articles, the provisions of the Food Safety and Standards Act, 2006 and "
            "the rules made thereunder shall apply."
        ),
        "field": "manufacture_date",
        "severity": "critical",
    },
    {
        "clause_id": "PCR-2011-R6.1.e",
        "rule_number": "6(1)(e)",
        "title": "Retail sale price - maximum retail price inclusive of all taxes",
        "text": (
            "Every package shall bear the retail sale price declared as Maximum or Max. retail "
            "price Rs. inclusive of all taxes, or in the form MRP Rs. incl. of all taxes. The "
            "retail sale price shall be printed in Indian currency and shall be rounded off to "
            "the nearest rupee or fifty paise. No person shall sell any packaged commodity at a "
            "price exceeding the declared retail sale price."
        ),
        "field": "mrp",
        "severity": "critical",
    },
    {
        "clause_id": "PCR-2011-R6.1.f",
        "rule_number": "6(1)(f)",
        "title": "Consumer care details",
        "text": (
            "Every package shall bear the name, address, telephone number and e-mail address, "
            "if available, of the person who can be, or the office which can be, contacted in "
            "case of consumer complaints. This consumer care declaration must be legible and "
            "accessible on the principal display panel or an adjacent panel."
        ),
        "field": "consumer_care",
        "severity": "major",
    },
    {
        "clause_id": "PCR-2011-R6.1.g",
        "rule_number": "6(1)(g)",
        "title": "Country of origin for imported packages",
        "text": (
            "Every package of an imported commodity shall bear the name of the country of "
            "origin of the commodity. Where the commodity is manufactured in India, this "
            "declaration is not mandatory."
        ),
        "field": "country_of_origin",
        "severity": "minor",
    },
    {
        "clause_id": "PCR-2011-R9.1",
        "rule_number": "9(1)",
        "title": "Declarations to be legible, prominent and conspicuous",
        "text": (
            "Every declaration required under these rules shall be legible and prominent, "
            "printed in a colour that contrasts conspicuously with the background of the label. "
            "The declaration shall not form part of any other information, shall not be hidden "
            "by any other matter, obscured by folds, or affixed on a part of the package that "
            "is discarded on opening. A contrast ratio below 3 to 1 between the text and its "
            "background renders the declaration non-conspicuous."
        ),
        "field": "contrast",
        "severity": "major",
    },
    {
        "clause_id": "PCR-2011-R9.2",
        "rule_number": "9(2)",
        "title": "Principal display panel and mandatory grouping",
        "text": (
            "The particulars of declaration required under these rules shall be grouped "
            "together and given at one place on the principal display panel. The principal "
            "display panel shall present the declarations to the purchaser under customary "
            "conditions of display for retail sale."
        ),
        "field": "layout",
        "severity": "minor",
    },
    {
        "clause_id": "PCR-2011-R9.3",
        "rule_number": "9(3)",
        "title": "Minimum height of numerals and letters - Second Schedule",
        "text": (
            "The height of any numeral or letter in a declaration required under these rules "
            "shall not be less than 1 millimetre where the area of the principal display panel "
            "is up to 100 square centimetres; not less than 2 millimetres for panels above 100 "
            "and up to 500 square centimetres; not less than 4 millimetres for panels above 500 "
            "and up to 2500 square centimetres; and not less than 6 millimetres for panels above "
            "2500 square centimetres. Where the package is a bottle or can, the height shall not "
            "be less than 2 millimetres for capacity up to 200 ml, 4 millimetres above 200 ml and "
            "up to 500 ml, and 6 millimetres above 500 ml."
        ),
        "field": "font_height",
        "severity": "major",
    },
    {
        "clause_id": "PCR-2011-R5",
        "rule_number": "5",
        "title": "Standard quantities and units of measure",
        "text": (
            "Packages of commodities specified in the Second Schedule shall be packed only in "
            "the standard quantities prescribed therein. The unit of weight or measure shall be "
            "expressed in the metric system: quantities below 1000 grams shall be expressed in "
            "grams and 1000 grams or above in kilograms; quantities below 1000 millilitres shall "
            "be expressed in millilitres and above in litres. Use of non-metric units such as "
            "ounces or pounds as the primary declaration is prohibited."
        ),
        "field": "net_quantity",
        "severity": "major",
    },
    {
        "clause_id": "PCR-2011-R18.1",
        "rule_number": "18(1)",
        "title": "Prohibition on altering the declared retail sale price",
        "text": (
            "No retail dealer or other person shall obliterate, smudge or alter the retail sale "
            "price indicated by the manufacturer or packer on the package. A package bearing two "
            "differing maximum retail prices, or an MRP sticker pasted over the printed price, "
            "constitutes a violation."
        ),
        "field": "mrp",
        "severity": "critical",
    },
    {
        "clause_id": "PCR-2011-R32",
        "rule_number": "32",
        "title": "Penalty for contravention",
        "text": (
            "Whoever contravenes the provisions of these rules relating to mandatory "
            "declarations shall be punishable under section 36 of the Legal Metrology Act, "
            "2009 with a fine which may extend to twenty-five thousand rupees for the first "
            "offence, fifty thousand rupees for the second offence, and for subsequent offences "
            "with a fine of not less than fifty thousand rupees extending to one lakh rupees, "
            "or with imprisonment up to one year, or with both."
        ),
        "field": "penalty",
        "severity": "info",
    },
]

# Second Schedule - minimum character height (mm) by principal display panel area (cm^2).
PDP_HEIGHT_TABLE = [
    (100.0, 1.0),
    (500.0, 2.0),
    (2500.0, 4.0),
    (float("inf"), 6.0),
]

# Minimum character height (mm) for bottles and cans by capacity (ml).
CAPACITY_HEIGHT_TABLE = [
    (200.0, 2.0),
    (500.0, 4.0),
    (float("inf"), 6.0),
]


def min_height_for_area(area_cm2: float) -> float:
    """Minimum declaration character height (mm) for a principal display panel area."""
    for limit, height in PDP_HEIGHT_TABLE:
        if area_cm2 <= limit:
            return height
    return 6.0


def min_height_for_capacity(capacity_ml: float) -> float:
    """Minimum declaration character height (mm) for a bottle or can of given capacity."""
    for limit, height in CAPACITY_HEIGHT_TABLE:
        if capacity_ml <= limit:
            return height
    return 6.0
