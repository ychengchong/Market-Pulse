import re


# An 8-K's item number explains what event occurred.
ITEM_EVENT_TYPES = {
    "1.01": "material agreement",
    "1.02": "agreement termination",
    "2.01": "acquisition/deal",
    "2.02": "earnings/results",
    "2.03": "financing",
    "2.04": "financial obligation",
    "2.05": "restructuring",
    "3.01": "listing/compliance",
    "3.02": "capital/financing",
    "4.01": "auditor/accounting",
    "4.02": "accounting/restatement",
    "5.01": "change of control",
    "5.02": "leadership",
    "5.03": "governance",
    "5.07": "shareholder vote",
    "7.01": "company update",
    "8.01": "other event",
}


BAD_8K_PHRASES = [
    "shall not be deemed",
    "pursuant to the requirements",
    "financial statements and exhibits",
    "inline xbrl",
    "check the appropriate box",
    "registrant's telephone",
    "registrant’s telephone",
    "cover page interactive data",
    "exhibit description",
    "written communications pursuant",
    "soliciting material pursuant",
]


BAD_10Q_PHRASES = [
    "forward-looking statement",
    "table of contents",
    "preparing the financial statements",
    "estimates and assumptions",
    "recast of these prior",
    "intercompany transactions",
    "marketable debt securities",
    "maturities between",
    "deferred revenue",
    "shall not be deemed",
    "risk factors",
    "securities and exchange commission",
    "materially adversely affect",
    "we expect these trends",
    "business seasonality and product introductions",
]


def normalise_text(text):
    """Remove repeated spaces and line breaks."""

    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text):
    """
    Split text into sentences while protecting common abbreviations
    such as U.S. and Inc.
    """

    text = normalise_text(text)

    abbreviations = {
        "U.S.": "US_ABBREVIATION",
        "Inc.": "INC_ABBREVIATION",
        "Corp.": "CORP_ABBREVIATION",
        "Mr.": "MR_ABBREVIATION",
        "Ms.": "MS_ABBREVIATION",
        "No.": "NO_ABBREVIATION",
        "D.C.": "DC_ABBREVIATION",
    }

    for abbreviation, replacement in abbreviations.items():
        text = text.replace(abbreviation, replacement)

    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9(])",
        text
    )

    restored_sentences = []

    for sentence in sentences:
        for abbreviation, replacement in abbreviations.items():
            sentence = sentence.replace(replacement, abbreviation)

        sentence = sentence.strip()

        if sentence:
            restored_sentences.append(sentence)

    return restored_sentences


def _find_8k_section_end(lines, start_index):
    """Use the same item/signature boundary for selection and summarisation."""
    for index in range(start_index + 1, len(lines)):
        if (re.match(r"^Item\s+[0-9]+\.[0-9]+", lines[index], re.IGNORECASE)
                or lines[index].upper().startswith("SIGNATURE")):
            return index
    return len(lines)


def find_primary_8k_item(lines):
    """Choose the first body item, excluding short duplicate TOC entries.

    The same item number often appears in both the contents and the disclosure.
    Keep the largest body span per item number, then preserve document order.
    Item 9.01 is an exhibits list rather than a primary event.
    """
    sections = {}
    for index, line in enumerate(lines):
        match = re.match(r"^Item\s+([0-9]+\.[0-9]+)", line, re.IGNORECASE)
        if not match or match[1] == "9.01":
            continue
        end = _find_8k_section_end(lines, index)
        # Page numbers alone cannot turn a TOC entry into disclosure content.
        size = sum(len(value) for value in lines[index + 1:end] if re.search(r"[A-Za-z]", value))
        previous = sections.get(match[1])
        if previous is None or size > previous[0]:
            sections[match[1]] = (size, index)
    if not sections:
        return None, None
    substantive = [(index, item) for item, (size, index) in sections.items() if size]
    candidates = substantive or [(index, item) for item, (_, index) in sections.items()]
    return min(candidates)


def summarise_8k(text, maximum_sentences=4):
    """
    Summarise the main event section of an 8-K.
    """

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    start_index, item_number = find_primary_8k_item(lines)

    if start_index is None:
        # Fallback if no item heading can be found.
        sentences = split_sentences(text)

        useful = [
            sentence
            for sentence in sentences
            if 40 <= len(sentence) <= 700
        ]

        summary = " ".join(useful[:maximum_sentences])

        return {
            "event_type": "other event",
            "summary": summary or "No suitable summary was found.",
            "source_word_count": len(text.split()),
            "summary_method": "rule-based form-aware extractive",
        }

    end_index = _find_8k_section_end(lines, start_index)

    section_lines = lines[start_index + 1:end_index]
    section_text = " ".join(section_lines)

    sentences = split_sentences(section_text)
    useful_sentences = []

    for sentence in sentences:
        lowered = sentence.lower()

        if len(sentence) < 40 or len(sentence) > 700:
            continue

        if any(phrase in lowered for phrase in BAD_8K_PHRASES):
            continue

        useful_sentences.append(sentence)

        if len(useful_sentences) == maximum_sentences:
            break

    event_type = ITEM_EVENT_TYPES.get(
        item_number,
        "other event"
    )

    summary = " ".join(useful_sentences)

    if not summary:
        summary = "No suitable summary was found for this filing."

    return {
        "event_type": event_type,
        "summary": summary,
        "source_word_count": len(text.split()),
        "summary_method": "rule-based form-aware extractive",
    }


def extract_mda_section(text):
    """Choose a line-anchored MD&A section, excluding TOC and prose references.

    A title can occur in the table of contents and in references to older
    reports. Among real heading lines, use the longest span before the next
    quarterly section. This avoids mistaking a short TOC entry for the body.
    Preserve whole-text fallback when a heading cannot be recognised.
    """
    title = (
        r"management['\u2019]s\s+discussion\s+and\s+analysis\s+"
        r"of\s+financial\s+condition\s+and\s+results\s+of\s+operations"
    )
    headings = list(re.finditer(
        r"^[^\S\n]*(?:item[^\S\n]*2\.?[^\S\n]*)?" + title + r"[^\S\n]*$",
        text, flags=re.IGNORECASE | re.MULTILINE
    ))
    if not headings:
        return normalise_text(text)
    boundary = re.compile(
        r"^[^\S\n]*(?:item[^\S\n]+(?:3|4)\b[^\n]*|part[^\S\n]+ii\b[^\n]*)",
        flags=re.IGNORECASE | re.MULTILINE
    )
    sections = []
    for heading in headings:
        stop = boundary.search(text, heading.end())
        sections.append(text[heading.end():stop.start() if stop else len(text)])
    return normalise_text(max(sections, key=lambda section: len(normalise_text(section))))


def score_10q_sentence(sentence):
    """
    Give useful financial-result sentences a higher score.
    """

    lowered = sentence.lower()

    if len(sentence) < 70 or len(sentence) > 900:
        return -100

    if any(phrase in lowered for phrase in BAD_10Q_PHRASES):
        return -100

    score = 0

    if "revenue" in lowered or "net sales" in lowered:
        score += 5

    if any(
        phrase in lowered
        for phrase in [
            "operating income",
            "net income",
            "gross margin",
            "operating margin",
            "earnings per share",
        ]
    ):
        score += 4

    if any(
        word in lowered
        for word in [
            "increased",
            "decreased",
            "grew",
            "declined",
            "growth",
            "higher",
            "lower",
        ]
    ):
        score += 3

    if re.search(
        r"\$[\d,.]+|\b\d+(?:\.\d+)?%",
        sentence
    ):
        score += 2

    if "quarter" in lowered:
        score += 1

    if any(
        phrase in lowered
        for phrase in [
            "iphone",
            "ipad",
            "mac ",
            "services",
            "azure",
            "cloud",
            "automotive",
            "energy generation",
            "vehicle deliveries",
        ]
    ):
        score += 2

    if any(
        phrase in lowered
        for phrase in [
            "cash flow",
            "cash flows",
            "capital expenditure",
            "capital expenditures",
            "free cash flow",
        ]
    ):
        score += 2

    # Penalise uncertain or prediction-heavy sentences.
    if any(
        phrase in lowered
        for phrase in [
            "we expect",
            "may affect",
            "could affect",
            "may result",
        ]
    ):
        score -= 3

    # Large amounts of numbers usually mean an unreadable table fragment.
    numeric_tokens = re.findall(r"\d[\d,.%]*", sentence)

    if len(numeric_tokens) > 20:
        score -= 4

    return score


def sentences_are_similar(first_sentence, second_sentence):
    """
    Avoid selecting multiple sentences that say nearly the same thing.
    """

    first_words = set(
        re.findall(r"[a-z]+", first_sentence.lower())
    )

    second_words = set(
        re.findall(r"[a-z]+", second_sentence.lower())
    )

    if not first_words or not second_words:
        return False

    overlap = first_words.intersection(second_words)
    union = first_words.union(second_words)

    similarity = len(overlap) / len(union)

    return similarity >= 0.55


def summarise_10q(text, maximum_sentences=4):
    """
    Select important financial-result sentences from a 10-Q's MD&A.
    """

    mda_section = extract_mda_section(text)
    sentences = split_sentences(mda_section)

    candidates = []

    for original_position, sentence in enumerate(sentences):
        score = score_10q_sentence(sentence)

        if score >= 6:
            candidates.append(
                (score, original_position, sentence)
            )

    # Best-scoring sentences first.
    candidates.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = []

    for score, original_position, sentence in candidates:
        duplicate = any(
            sentences_are_similar(sentence, chosen_sentence)
            for _, chosen_sentence in selected
        )

        if duplicate:
            continue

        selected.append(
            (original_position, sentence)
        )

        if len(selected) == maximum_sentences:
            break

    # Put the chosen sentences back into filing order.
    selected.sort(key=lambda item: item[0])

    summary = " ".join(
        sentence
        for _, sentence in selected
    )

    if not summary:
        summary = (
            "No suitable financial-result sentences were found "
            "in the filing."
        )

    return {
        "event_type": "earnings/results",
        "summary": summary,
        "source_word_count": len(text.split()),
        "summary_method": "rule-based form-aware extractive",
    }


def create_summary(text, form=None, maximum_sentences=4):
    """
    Main function used by summarize_filings.py.

    It sends 8-K and 10-Q documents to different summarisation rules.
    """

    if not text or not text.strip():
        return {
            "event_type": "unknown",
            "summary": "The filing contained no readable text.",
            "source_word_count": 0,
            "summary_method": "rule-based form-aware extractive",
        }

    # Keeps older tests working if form is not supplied.
    if form is None:
        upper_text = text.upper()

        if "FORM 8-K" in upper_text or re.search(
            r"\bITEM\s+[0-9]+\.[0-9]+",
            upper_text
        ):
            form = "8-K"
        else:
            form = "10-Q"

    if form.upper() == "8-K":
        return summarise_8k(
            text,
            maximum_sentences=maximum_sentences
        )

    return summarise_10q(
        text,
        maximum_sentences=maximum_sentences
    )