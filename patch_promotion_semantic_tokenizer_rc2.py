from pathlib import Path

path = Path(
    r".\src\az_enterprise\core\promotion_candidate_analyzer_rc1.py"
)

text = path.read_text(
    encoding="utf-8-sig"
)

start = text.index(
    "    @staticmethod\n"
    "    def _semantic_similarity("
)

end = text.index(
    "\n\n    @staticmethod\n"
    "    def _overlap_ratio(",
    start,
)

new_block = '''    @staticmethod
    def _semantic_similarity(
        left: str,
        right: str,
    ) -> float:

        def tokens(value: str) -> set[str]:

            words = re.findall(
                r"[A-Za-zА-Яа-яЁё0-9]+",
                str(value).lower(),
            )

            stop = {
                "и", "в", "во", "на", "с", "со",
                "к", "ко", "из", "по", "за", "от",
                "до", "для", "не", "но", "это",
                "как", "что", "он", "она", "они",
                "мы", "вы", "его", "ее", "её",
                "их", "у", "о", "об", "а",
                "the", "a", "an", "of", "and",
                "to", "in", "is", "that", "with",
                "for", "on", "from", "by",
            }

            return {
                word
                for word in words
                if (
                    len(word) >= 3
                    and word not in stop
                )
            }

        a = tokens(left)
        b = tokens(right)

        if not a or not b:
            return 0.0

        intersection = len(
            a & b
        )

        union = len(
            a | b
        )

        return (
            intersection / union
            if union
            else 0.0
        )
'''

text = (
    text[:start]
    + new_block
    + text[end:]
)

path.write_text(
    text,
    encoding="utf-8",
)

print("SEMANTIC TOKENIZER RC2 PATCH: OK")
