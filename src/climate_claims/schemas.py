from dataclasses import asdict, dataclass, field

CLAIM_TYPES = {"descriptive_factual", "causal_attribution", "predictive", "policy_value"}


@dataclass
class Ambiguity:
    term_or_relation: str
    possible_meanings: list[str]


@dataclass
class TypeMismatch:
    detected: bool
    premise_type: str
    conclusion_type: str
    explanation: str


@dataclass
class Analysis:
    claim: str
    claim_type: str
    type_reason: str
    literal_meaning: str
    implied_argument: str
    ambiguities: list[Ambiguity]
    hidden_assumptions: list[str]
    type_mismatch: TypeMismatch

    @classmethod
    def from_dict(cls, d: dict) -> "Analysis":
        """Build from LLM output (plus a 'claim' key) or from a saved analysis.json."""
        try:
            m = d["type_mismatch"]
            a = cls(
                claim=d["claim"],
                claim_type=d["claim_type"],
                type_reason=d["type_reason"],
                literal_meaning=d["literal_meaning"],
                implied_argument=d["implied_argument"],
                ambiguities=[Ambiguity(x["term_or_relation"], list(x["possible_meanings"]))
                             for x in d["ambiguities"]],
                hidden_assumptions=[str(h) for h in d["hidden_assumptions"]],
                type_mismatch=TypeMismatch(bool(m["detected"]), m["premise_type"],
                                           m["conclusion_type"], m["explanation"]),
            )
        except (KeyError, TypeError) as e:
            raise ValueError(f"LLM output missing or invalid field: {e!r}") from e
        if a.claim_type not in CLAIM_TYPES:
            raise ValueError(f"Unknown claim_type: {a.claim_type!r}")
        return a

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Window:
    """A sentence hit expanded with its surrounding context."""
    doc: str
    lo: int                      # first sentence idx in the window
    hi: int                      # last sentence idx in the window
    score: float
    hit_sentences: list[str]
    sentences: list[tuple[int, str]] = field(default_factory=list)   # (page, text)

    @property
    def id(self) -> str:
        return f"{self.doc}:{self.lo}-{self.hi}"

    @property
    def text(self) -> str:
        return " ".join(t for _, t in self.sentences)


@dataclass
class Finding:
    statement: str
    quote: str
    document: str
    pages: list[int]
    passage_id: str
    likelihood: str | None = None       # IPCC calibrated term found in the quote
    confidence: str | None = None
    stated_as_fact: bool = False
    also_in: list[dict] = field(default_factory=list)   # same quote found in other documents